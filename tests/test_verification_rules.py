"""Synthetic fixtures only: no paid calls or capability claims."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest

from routing.verification_rules import (FEATURES, ROLES, default_policy, validate_policy,
                                        assess_risk, select_reviewers, judge)


def reviewer(name, family='gpt'):
    return dict(reviewer_id=name, provider='openai' if family == 'gpt' else 'anthropic',
                family=family, model_id=f'{family}-{name}', enabled=True,
                roles_supported=list(ROLES), capabilities=[], cost_class='low',
                latency_class='low', adapter={'kind':'command', 'command':['review-test']},
                max_cost_usd=.2, max_tokens=6000, timeout_seconds=45)


class VerificationRulesTests(unittest.TestCase):
    def setUp(self):
        self.p = default_policy()
        self.signature = dict(domain='coding', task_type='implementation')
        self.worker = dict(model_id='gpt-worker', family='gpt')
        self.p['reviewers'] = [reviewer('first'), reviewer('second','claude')]

    def select(self, tier='HIGH', history=None):
        return select_reviewers(self.signature,self.worker,history or [],self.p,tier)

    def reports(self, selection):
        return [dict(role=s['role'], reviewer_id=s['reviewer']['reviewer_id'],
                     reliability=s['reliability'], independence_score=s['independence_score'],
                     result=dict(verdict='PASS',confidence=.9,issues=[], evidence=['artifact.py:1'],
                                 recommended_action='accept',reviewer_specialty=s['role']))
                for s in selection['selected']]

    def test_defaults_low_and_copy(self):
        p = default_policy()
        self.assertEqual([], p['reviewers'])
        q = validate_policy(p)
        q['weights']['complexity']=100
        self.assertEqual(1,p['weights']['complexity'])
        risk = assess_risk(dict.fromkeys(FEATURES,0),p)
        selection = select_reviewers({}, {}, [], p, risk)
        result=judge(risk,[dict(id='artifact',required=True,status='passed')],[],selection,p)
        self.assertEqual('PASS',result['status'])
        self.assertTrue(any('Commander' in x for x in result['reasons']))

    def test_risk_floors(self):
        features=dict.fromkeys(FEATURES,0)
        features['irreversibility']=1
        self.assertEqual('CRITICAL',assess_risk(features,self.p)['tier'])
        features['irreversibility']=0
        features['security_risk']=.8
        self.assertEqual('HIGH',assess_risk(features,self.p)['tier'])
        for value in (float('nan'),float('inf'),True,-.1,1.1):
            features['complexity']=value
            with self.assertRaises(ValueError): assess_risk(features,self.p)

    def test_bad_config(self):
        for change in ({'alias':'Google/GEMINI-pro'}, {'reviewers':[reviewer('gemini')]}):
            with self.assertRaises(ValueError): validate_policy(dict(self.p,**change))
        p=deepcopy(self.p); p['reviewers'][0]['provider']='anthropic'
        with self.assertRaises(ValueError): validate_policy(p)
        p=deepcopy(self.p); p['tiers']['CRITICAL']['human_approval']=False
        with self.assertRaises(ValueError): validate_policy(p)

    def test_roles_independence_and_critical(self):
        selection=self.select('CRITICAL')
        self.assertEqual([],selection['missing_roles'])
        self.assertEqual(3,len(selection['selected']))
        self.assertEqual('adversarial_reviewer',selection['selected'][-1]['role'])
        self.assertEqual('claude',selection['selected'][0]['reviewer']['family'])
        self.assertNotEqual(selection['selected'][0]['reviewer']['reviewer_id'],selection['selected'][1]['reviewer']['reviewer_id'])
        self.assertEqual('HUMAN_APPROVAL_REQUIRED',judge('CRITICAL',[dict(id='artifact',required=True,status='passed')],self.reports(selection),selection,self.p)['status'])

    def test_history_is_conditional_shrunk_and_real(self):
        selection=self.select('MEDIUM')
        r=selection['selected'][0]
        self.assertEqual(.5,r['reliability']['score'])
        h=dict(reviewer_id=r['reviewer']['reviewer_id'], model_id=r['reviewer']['model_id'],
               role=r['role'],task_signature=self.signature, timestamp=datetime.now(timezone.utc).isoformat(),
               correct=True,source_kind='real',confirmed=True)
        rel=self.select('MEDIUM',[h])['selected'][0]['reliability']
        self.assertGreater(rel['score'],.5); self.assertLess(rel['score'],.61)
        for changes in ({'source_kind':'synthetic'},{'confirmed':False},{'own_execution':True},
                        {'task_signature':dict(domain='other',task_type='implementation')},
                        {'model_id':'other-model'}, {'valid':False}):
            rel=self.select('MEDIUM',[dict(h,**changes)])['selected'][0]['reliability']
            self.assertEqual(0,rel['samples'])
        old=dict(h,timestamp=(datetime.now(timezone.utc)-timedelta(days=365)).isoformat())
        self.assertLess(self.select('MEDIUM',[old])['selected'][0]['reliability']['score'],rel['score']+.05)

    def test_model_family_inference_and_same_model_allowed(self):
        self.worker = dict(model_id='openai/gpt-first')
        self.p['reviewers'] = [reviewer('first')]
        selection = self.select('MEDIUM')
        self.assertEqual(.3, selection['selected'][0]['independence_score'])
        checks = [dict(id='artifact', required=True, status='passed')]
        self.assertEqual('PASS', judge('MEDIUM',checks,self.reports(selection),selection,self.p)['status'])
        self.worker = dict(model_id='gpt-other')
        self.assertEqual(.6,self.select('MEDIUM')['selected'][0]['independence_score'])

    def test_strong_conditional_history_can_override_independence_bonus(self):
        r = self.p['reviewers'][0]
        history = [dict(reviewer_id=r['reviewer_id'],model_id=r['model_id'],role='correctness_reviewer',
                        task_signature=self.signature,timestamp=datetime.now(timezone.utc).isoformat(),
                        correct=True,source_kind='real',confirmed=True) for _ in range(100)]
        selection=self.select('MEDIUM',history)
        self.assertEqual(r['reviewer_id'],selection['selected'][0]['reviewer']['reviewer_id'])
        self.assertIn('latency',selection['selected'][0]['score_components'])
        high=self.select('HIGH',history)
        self.assertTrue(all(x['reliability']['samples']==0 for x in high['selected']))

    def test_zero_revision_and_empty_checks_and_specialty(self):
        self.p['max_revision_rounds']=0
        self.assertEqual(0,validate_policy(self.p)['max_revision_rounds'])
        selection=self.select('MEDIUM')
        reports=self.reports(selection)
        self.assertEqual('ESCALATE',judge('MEDIUM',[],reports,selection,self.p)['status'])
        checks=[dict(id='artifact',required=True,status='passed')]
        reports[0]['result']['reviewer_specialty']='security_reviewer'
        self.assertEqual('ESCALATE',judge('MEDIUM',checks,reports,selection,self.p)['status'])
        reports=self.reports(selection); reports[0]['valid']=False
        self.assertEqual('ESCALATE',judge('MEDIUM',checks,reports,selection,self.p)['status'])

    def test_required_check_overrides_pass(self):
        selection=self.select()
        result=judge('HIGH',[dict(id='actual',status='failed',required=True)],self.reports(selection),selection,self.p)
        self.assertEqual('REVISE',result['status'])

    def test_severe_low_confidence_not_outvoted(self):
        selection=self.select()
        reports=self.reports(selection)
        reports[1]['result'].update(confidence=.1,issues=[dict(id='auth',severity='critical',description='Bypass',evidence=['source:2'])])
        result=judge('HIGH',[dict(id='suite',status='passed',required=True)],reports,selection,self.p)
        self.assertEqual('ESCALATE',result['status'])
        self.assertTrue(any('auth' in r for r in result['reasons']))

    def test_missing_conflict_and_uncertain(self):
        selection=self.select()
        reports=self.reports(selection)
        self.assertEqual('ESCALATE',judge('HIGH',[],reports[:1],selection,self.p)['status'])
        reports[1]['result']['verdict']='REVISE'
        self.assertEqual('ESCALATE',judge('HIGH',[],reports,selection,self.p)['status'])
        reports=self.reports(selection); reports[0]['result']['evidence']=[]
        self.assertEqual('ESCALATE',judge('HIGH',[],reports,selection,self.p)['status'])
        self.assertEqual('ESCALATE',judge('HIGH',[],[],dict(selected=[],missing_roles=[]),self.p)['status'])


if __name__ == '__main__':
    unittest.main()
