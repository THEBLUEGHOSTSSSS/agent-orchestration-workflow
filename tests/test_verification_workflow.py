"""Executable A-F integration scenarios; reviewer bridges are labeled fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from routing.service import Workflow, digest_file
from routing.validation import validate_ledger
from routing.verification_rules import default_policy, FEATURES, ROLES, judge
from test_selection import load_config, signature

BRIDGE = '''import json,sys
p=json.load(sys.stdin)
role=p['reviewer_role']
fail = sys.argv[1]=='fail' or ('return a-b' in p['artifacts'][0]['content'] and sys.argv[1]=='detect')
r={'verdict':'FAIL' if fail else 'PASS','confidence':.9,'issues':[{'id':'bug','severity':'medium','description':'Addition subtracts b','evidence':['maths.py: return a-b']}] if fail else [],'evidence':['inspected '+p['artifacts'][0]['path']],'recommended_action':'minor_fix' if fail else 'accept','reviewer_specialty':role}
print(json.dumps({'result':r,'usage':{'cost_usd':0,'total_tokens':0},'resolved_model':sys.argv[2]}))
'''


class VerificationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'maths.py').write_text('def add(a,b):\n    return a+b\n')
        (self.root/'bridge.py').write_text(BRIDGE)
        self.policy=default_policy()
        self.policy['reviewers']=[self.reviewer('claude','anthropic','claude'),self.reviewer('gpt','openai','gpt')]
        config=load_config();config['verification']=self.policy
        self.config_path=self.root/'config.json';self.config_path.write_text(json.dumps(config))
        self.w=Workflow(self.root/'state.json',self.config_path)

    def reviewer(self,id,provider,family,mode='pass'):
        return {'reviewer_id':id,'provider':provider,'family':family,'model_id':f'{provider}/{family}-fixture',
            'enabled':True,'roles_supported':list(ROLES),'capabilities':['code'],'cost_class':'low','latency_class':'low',
            'adapter':{'kind':'command','command':[sys.executable,str(self.root/'bridge.py'),mode,'{model}']},
            'max_cost_usd':.01,'max_tokens':1000,'timeout_seconds':5}

    def create(self,risk=.1,check=None,worker_reservation=None):
        self.w.create(dict(task_id='V1',work_key='addition',workspace=str(self.root),objective='add numbers correctly',baseline='fixture',
            scope=['maths.py'],source_kind='synthetic',task_signature=signature(),acceptance_criteria=[{'id':'C1','check':'add(2,3)==5'}],
            verification={'risk_features':{f:risk for f in FEATURES},'artifacts':['maths.py'],
                          'checks':[{'id':'tests','argv':[sys.executable,'-c',check or 'from maths import add; assert add(2,3)==5'],'required':True}],
                          'worker_reservation':worker_reservation or {'cost_usd':0,'tokens':0}}))
        self.w.run('V1',executor=lambda *_:{'exit_code':0})

    def review(self,accepted=True,action=None):
        return {'reviewer':'fixture commander','accepted':accepted,'action':action or ('accept' if accepted else 'retry'),
            'diagnosis':{'attribution':'NONE' if accepted else 'MODEL_RELATED','failure_type':'NONE' if accepted else 'LOCAL_IMPLEMENTATION_ERROR','severity':'none' if accepted else 'low','summary':'checked source'},
            'evidence':[{'path':'maths.py','sha256':digest_file(self.root/'maths.py')}],
            'criteria':[{'id':'C1','status':'passed' if accepted else 'failed','observation':'actual fixture verification'}],
            'static_checker_result':'passed',
            'handoff':{k:[] for k in ('files_inspected','files_modified','current_diff','tests_run','test_results','previous_approach','what_worked','what_failed','known_bad_approaches','remaining_work','constraints')}}

    def test_A_low_no_reviewer(self):
        self.create();s=self.w.verify('V1')
        self.assertEqual(s['judge']['status'],'PASS');self.assertEqual(s['reviews'],[])
        self.assertEqual(self.w.inspect('V1')['status'],'AWAITING_REVIEW')
        self.w.review('V1',self.review());self.assertEqual(validate_ledger(self.w.inspect()),[])

    def test_B_medium_heterogeneous_blind_review(self):
        self.create(.3);s=self.w.verify('V1')
        self.assertEqual(s['selection']['selected'][0]['reviewer']['family'],'claude')
        self.assertEqual(s['judge']['status'],'PASS')
        self.w.review('V1',self.review())
        state=self.w.inspect();self.assertEqual(len(state['reviewer_experiences']),1)
        self.assertFalse(state['reviewer_experiences'][0]['confirmed'])
        e=state['reviewer_experiences'][0]
        self.w.verification_feedback('V1',{'experience_id':e['experience_id'],'correct':True,'basis':'commander_artifact_review','reason':'independently inspected code','actor':'commander','evidence':self.review()['evidence']})
        self.assertTrue(self.w.inspect()['reviewer_experiences'][0]['confirmed'])
        self.assertEqual(validate_ledger(self.w.inspect()),[])

    def test_C_hidden_bug_revision_then_pass(self):
        config=json.loads(self.config_path.read_text());config['verification']['reviewers'][0]['adapter']['command'][2]='detect'
        self.config_path.write_text(json.dumps(config));self.w=Workflow(self.root/'state.json',self.config_path)
        (self.root/'maths.py').write_text('def add(a,b):\n    return a-b\n')
        self.create(.3,check='from pathlib import Path; assert Path("maths.py").exists()')
        s=self.w.verify('V1');self.assertEqual(s['judge']['status'],'REVISE')
        self.w.review('V1',self.review(False))
        self.w.run('V1',executor=lambda *_:{'exit_code':0})
        (self.root/'maths.py').write_text('def add(a,b):\n    return a+b\n')
        self.assertEqual(self.w.verify('V1')['judge']['status'],'PASS')
        self.w.review('V1',self.review());self.assertEqual(self.w.inspect('V1')['worker_attempt_count'],2)
        with self.assertRaises(ValueError):self.w.run('V1',executor=lambda *_:{'exit_code':0})

    def test_D_failed_tests_override_reviewer_pass(self):
        self.create(.3);s=self.w.verify('V1');self.assertEqual(s['judge']['status'],'PASS')
        checks=deepcopy(s['checks']);checks[0]['status']='failed'
        task=self.w.inspect('V1');v=task['verification_layer']
        d=judge(v['risk'],checks,s['reviews'],s['selection'],v['policy'])
        self.assertEqual(d['status'],'REVISE')

    def test_E_conflicting_reviewers_no_majority_vote(self):
        config=json.loads(self.config_path.read_text());config['verification']['reviewers'][1]['adapter']['command'][2]='fail'
        self.config_path.write_text(json.dumps(config));self.w=Workflow(self.root/'state.json',self.config_path)
        self.create(.6);s=self.w.verify('V1')
        self.assertEqual(len(s['reviews']),2);self.assertEqual(s['judge']['status'],'ESCALATE')
        with self.assertRaises(ValueError):self.w.review('V1',self.review())

    def test_F_critical_adversarial_human_gate(self):
        self.create(.8);s=self.w.verify('V1')
        self.assertEqual(len(s['reviews']),3)
        self.assertIn('adversarial_reviewer',[r['role'] for r in s['reviews']])
        self.assertEqual(s['judge']['status'],'HUMAN_APPROVAL_REQUIRED')
        with self.assertRaises(ValueError):self.w.review('V1',self.review())
        self.w.verification_approve('V1',{'session_id':s['session_id'],'actor':'synthetic human','reason':'fixture decision','approved':True})
        self.w.review('V1',self.review());self.assertEqual(validate_ledger(self.w.inspect()),[])

    def test_changed_artifact_invalidates_acceptance(self):
        self.create();self.w.verify('V1');(self.root/'maths.py').write_text('broken')
        with self.assertRaises(ValueError):self.w.review('V1',self.review())

    def test_takeover_requires_fresh_verification(self):
        self.create();self.w.verify('V1');self.w.review('V1',self.review(False,'takeover'))
        record=self.review();record.update(summary='commander inspected',repair_burden=1)
        with self.assertRaises(ValueError):self.w.takeover('V1',record)
        self.w.verify('V1','takeover');self.w.takeover('V1',record)
        self.assertEqual(validate_ledger(self.w.inspect()),[])

    def test_budget_exhaustion_not_acceptance(self):
        config=json.loads(self.config_path.read_text());config['verification']['budgets']['max_reviewer_calls']=0
        self.config_path.write_text(json.dumps(config));self.w=Workflow(self.root/'state.json',self.config_path)
        self.create(.3);s=self.w.verify('V1');self.assertEqual(s['judge']['status'],'ESCALATE')
        with self.assertRaises(ValueError):self.w.review('V1',self.review())

    def test_alias_cannot_change_policy(self):
        self.create(.8);spec={'task_id':'alias','work_key':'addition','workspace':str(self.root),'objective':'same','baseline':'same','scope':['maths.py'],'acceptance_criteria':[{'id':'C1','check':'x'}],'task_signature':signature(),'verification':{}}
        self.w.create(spec);self.assertEqual(self.w.inspect('alias')['verification_layer']['risk']['tier'],'CRITICAL')

    def test_reviewer_role_cannot_create_or_recover(self):
        import os
        from unittest.mock import patch
        self.create()
        with patch.dict(os.environ,{'ADAPTIVE_WORKER_ROLE':'reviewer'}):
            with self.assertRaises(PermissionError):self.w.verify('V1')
            with self.assertRaises(PermissionError):self.w.review('V1',self.review())

    def test_actual_worker_metrics_block_additional_spend(self):
        self.create(.1,check='raise SystemExit(1)');self.w.verify('V1')
        review=self.review(False)
        review['execution_metrics']={'source':'fixture invoice','currency':'USD','estimated_cost':3,'token_usage':{'total_tokens':50000}}
        self.w.review('V1',review)
        reservation=self.w.inspect('V1')['verification_layer']['reservations'][0]
        self.assertEqual(reservation['actual_cost'],3)
        self.assertEqual(reservation['actual_tokens'],50000)
        with self.assertRaises(ValueError):self.w.run('V1',executor=lambda *_:{'exit_code':0})
        self.assertEqual(self.w.inspect('V1')['worker_attempt_count'],1)

    def test_recovered_session_cannot_launch_reviewer(self):
        from unittest.mock import patch
        self.create(.3)
        def abandoned(*args,**kwargs):
            self.w.verification_recover('V1','fixture stopped checks')
            return 0,'ok',None
        with patch('routing.reviewer_runtime.run_command',side_effect=abandoned), patch('routing.reviewer_runtime.run_reviewer') as run:
            with self.assertRaises(ValueError):self.w.verify('V1')
            run.assert_not_called()
        layer=self.w.inspect('V1')['verification_layer']
        self.assertFalse(any(r['kind']=='reviewer' for r in layer['reservations']))

    def test_reviewer_experience_keeps_both_model_identities(self):
        self.create(.3);self.w.verify('V1');self.w.review('V1',self.review())
        state=self.w.inspect();row=state['reviewer_experiences'][0]
        self.assertEqual(row['provider'],'anthropic')
        self.assertEqual(row['resolved_model'],'anthropic/claude-fixture')
        self.assertEqual(row['worker_model_id'],self.w.inspect('V1')['attempts'][0]['worker']['model'])
        self.assertEqual(row['risk_level'],'MEDIUM')

    def test_static_checker_rejects_forged_judge(self):
        self.create(.3,check='raise SystemExit(1)');self.w.verify('V1')
        state=self.w.inspect();task=state['tasks']['V1']
        task['verification_layer']['sessions'][0]['judge']['status']='PASS'
        self.assertTrue(validate_ledger(state))

    def test_judge_uses_confirmed_reliability_and_worker_risk(self):
        self.create(.3);s=self.w.verify('V1');v=self.w.inspect('V1')['verification_layer']
        reviews=deepcopy(s['reviews']);reviews[0]['reliability']={'effective_samples':20,'score':.2}
        self.assertEqual(judge(v['risk'],s['checks'],reviews,s['selection'],v['policy'])['status'],'ESCALATE')
        reviews=deepcopy(s['reviews']);reviews[0]['result']['confidence']=.6
        self.assertEqual(judge(v['risk'],s['checks'],reviews,s['selection'],v['policy'],worker_failure_rate=.8)['status'],'ESCALATE')

    def test_acceptance_cannot_hide_newly_reported_overspend(self):
        self.create();self.w.verify('V1');review=self.review()
        review['execution_metrics']={'source':'invoice','currency':'USD','estimated_cost':3}
        with self.assertRaises(ValueError):self.w.review('V1',review)
        self.assertEqual(self.w.inspect('V1')['status'],'AWAITING_REVIEW')

    def test_invalid_task_not_reviewer_learning_signal(self):
        self.create(.3);self.w.verify('V1');review=self.review()
        review.update(invalid_task=True,invalid_reason='fixture requirements changed')
        self.w.review('V1',review)
        self.assertFalse(self.w.inspect()['reviewer_experiences'][0]['valid'])
    def test_global_opt_in_requires_new_specs_without_migrating_aliases(self):
        self.create()
        spec=self.w.inspect('V1');spec['task_id']='alias'
        config=json.loads(self.config_path.read_text());config['require_verification_for_new_tasks']=True
        self.config_path.write_text(json.dumps(config));self.w=Workflow(self.root/'state.json',self.config_path)
        self.assertEqual(self.w.create(spec)['logical_task_id'],'V1')
        spec['task_id']='new';spec['work_key']='genuinely new scope'
        spec.pop('logical_task_id',None)
        with self.assertRaises(ValueError):self.w.create(spec)
