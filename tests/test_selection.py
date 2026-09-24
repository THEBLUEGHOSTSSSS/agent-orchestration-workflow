"""Synthetic, in-memory routing scenarios; no fixture is written to the real ledger."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from routing.models import (load_config, profile_task, validate_config,
                            validate_diagnosis, validate_signature)
from routing.selection import route

NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


def signature(**overrides):
    result = dict(domain='coding', task_type='implementation', task_subtype='backend',
                  language='python', framework='stdlib', complexity='medium',
                  reasoning_intensity='medium', tool_intensity='medium', risk_level='medium',
                  cross_module_scope='medium', estimated_execution_volume='medium',
                  verification_strength='strong', scope='multi_file', environment='local',
                  required_capabilities=['coding'])
    result.update(overrides)
    return result


def experience(config, worker_id, n, *, accepted=True, attempt=1, age=1, task=None,
               severity='medium', source='real', version=None, cost=None, currency=None):
    worker = deepcopy(next(w for w in config['workers'] if w['worker_id'] == worker_id))
    if version is not None:
        worker['version'] = version
    return dict(experience_id=f'synthetic-test-{worker_id}-{n}-{attempt}',
                timestamp=(NOW - timedelta(days=age)).isoformat(),
                logical_task_id=f'{worker_id}-{n}', attempt_number=attempt,
                task_signature=task or signature(), worker=worker, routing={},
                execution={'duration_seconds': 10, 'estimated_cost': cost,
                           'currency': currency, 'token_usage': None, 'tool_calls': None},
                verification={'reviewer_result': 'accepted' if accepted else 'rejected',
                              'reviewer': 'synthetic fixture reviewer', 'evidence': ['synthetic fixture']},
                outcome={'accepted': accepted, 'worker_result_status': 'TEST_FIXTURE'},
                diagnosis={'attribution': 'NONE' if accepted else 'MODEL_RELATED',
                           'failure_type': 'NONE' if accepted else 'REASONING_FAILURE',
                           'severity': 'none' if accepted else severity,
                           'summary': '' if accepted else 'synthetic test failure'},
                retry={'required': not accepted, 'action': 'RETRY' if not accepted else None},
                repair={'required': not accepted, 'burden': None, 'takeover': False},
                source_kind=source, valid=True)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.ids = [w['worker_id'] for w in self.config['workers']]
        self.a, self.b = self.ids

    def choose(self, records=(), sig=None, **kwargs):
        return route(sig or signature(), list(records), self.config, now=kwargs.pop('now', NOW), **kwargs)

    def test_cold_start_and_no_history_not_blocked(self):
        choice = self.choose()
        self.assertEqual((choice['selected_worker'], choice['selection_mode'],
                          choice['historical_confidence']), (self.a, 'HEURISTIC', 'LOW'))
        self.assertIsNone(choice['suitability'][self.a]['average_execution_cost'])
        self.assertIsNone(choice['suitability'][self.a]['accepted_tasks_per_cost'])
        self.assertEqual(choice['historical_sample_count'], 0)

    def test_B_empirical_exploitation_overturns_cold_start(self):
        rows = [experience(self.config, self.b, n) for n in range(16)]
        rows += [experience(self.config, self.a, n, accepted=False) for n in range(12)]
        choice = self.choose(rows)
        self.assertEqual((choice['selected_worker'], choice['selection_mode']), (self.b, 'EXPLOIT'))
        self.assertEqual(choice['historical_confidence'], 'HIGH')
        self.assertEqual(len(choice['historical_evidence_used']), 16)
        self.assertIn('score=', choice['routing_reason'])

    def test_C_low_local_failure_retry_same(self):
        diagnosis = {'attribution': 'MODEL_RELATED', 'failure_type': 'LOCAL_IMPLEMENTATION_ERROR',
                     'severity': 'low', 'summary': 'Small local fix needed'}
        choice = self.choose(previous_worker=self.a, diagnosis=diagnosis)
        self.assertEqual((choice['selected_worker'], choice['selection_mode']), (self.a, 'RETRY_SAME'))

    def test_D_serious_model_failure_switches(self):
        diagnosis = {'attribution': 'MODEL_RELATED', 'failure_type': 'REASONING_FAILURE',
                     'severity': 'high', 'summary': 'Reasoning error'}
        choice = self.choose(previous_worker=self.a, diagnosis=diagnosis)
        self.assertEqual((choice['selected_worker'], choice['selection_mode']), (self.b, 'RETRY_SWITCH'))
        diagnosis.update(attribution='ENVIRONMENT_RELATED', failure_type='MISSING_DEPENDENCY')
        choice = self.choose(previous_worker=self.a, diagnosis=diagnosis)
        self.assertEqual((choice['selected_worker'], choice['selection_mode']), (self.a, 'RETRY_SAME'))
        self.assertIn('prerequisite', choice['routing_reason'])

    def test_F_nonreal_polluted_unreviewed_and_nonmodel_not_learned(self):
        bad = [experience(self.config, self.a, n, accepted=False) for n in range(30)]
        for n, row in enumerate(bad):
            if n % 5 == 0:
                row['source_kind'] = 'synthetic'
            elif n % 5 == 1:
                row['source_kind'] = 'probe'
            elif n % 5 == 2:
                row['verification']['reviewer_result'] = 'pending'
            elif n % 5 == 3:
                row['execution']['cancelled'] = True
            else:
                row['diagnosis']['attribution'] = 'ENVIRONMENT_RELATED'
        clean = experience(self.config, self.a, 99)
        clean['worker']['model'] = 'snapshot mismatch'
        bad.append(clean)
        result = self.choose(bad)
        self.assertEqual(result['suitability'][self.a]['sample_count'], 0)
        self.assertEqual(result['suitability'][self.a]['excluded_counts']['non_model_failure'], 6)
        self.assertEqual(result['selection_mode'], 'HEURISTIC')

    def test_G_small_perfect_sample_shrinks_and_attempts_dedup(self):
        rows = [experience(self.config, self.a, n) for n in range(2)]
        rows += [experience(self.config, self.b, n, accepted=(n < 20)) for n in range(24)]
        result = self.choose(rows)
        self.assertEqual(result['selected_worker'], self.b)
        self.assertLess(result['suitability'][self.a]['score'], result['suitability'][self.b]['score'])
        second = experience(self.config, self.b, 0, attempt=2, accepted=False)
        rows.append(second)
        result = self.choose(rows)
        self.assertEqual(result['suitability'][self.b]['sample_count'], 24)
        self.assertEqual(result['suitability'][self.b]['second_pass_acceptance_rate'], 0)

    def test_H_recency_expiry_future_and_version_discount(self):
        current = experience(self.config, self.a, 0, accepted=False)
        old = experience(self.config, self.a, 1, accepted=True, age=100)
        retired = experience(self.config, self.a, 2, age=400)
        future = experience(self.config, self.a, 3, age=-1)
        expired = experience(self.config, self.a, 4)
        expired['expires_at'] = (NOW - timedelta(seconds=1)).isoformat()
        result = self.choose([current, old, retired, future, expired])
        self.assertLess(result['suitability'][self.a]['effective_sample_weight'], 2)
        self.assertEqual(result['suitability'][self.a]['sample_count'], 2)
        self.assertEqual(result['suitability'][self.a]['excluded_counts']['future_or_expired'], 3)
        previous = experience(self.config, self.b, 0, version='old-version')
        res = self.choose([previous])
        self.assertAlmostEqual(res['suitability'][self.b]['effective_sample_weight'],
                               0.5 * 2 ** (-1 / self.config['policy']['recency_half_life_days']))

    def test_zero_version_discount_and_repair_quality(self):
        self.config['policy']['version_discount'] = 0
        old = experience(self.config, self.a, 0, version='old')
        result = self.choose([old])
        self.assertEqual(result['suitability'][self.a]['sample_count'], 0)
        rows = [experience(self.config, self.a, n) for n in range(12)]
        clean = self.choose(rows)['suitability'][self.a]['score']
        for row in rows:
            row['repair'].update(required=True, severity='high')
        self.assertLess(self.choose(rows)['suitability'][self.a]['score'], clean)

    def test_low_assurance_cannot_establish_high_risk_confidence(self):
        rows = [experience(self.config, self.a, n, task=signature(risk_level='low', verification_strength='weak')) for n in range(16)]
        result = self.choose(rows, signature(risk_level='high', environment='production'))
        self.assertEqual(result['historical_confidence'], 'LOW')
        self.assertEqual(result['historical_sample_count'], 0)

    def test_I_exploration_only_with_real_evidence_and_small_gap(self):
        self.config['policy']['exploration_gap'] = 1
        low = signature(risk_level='low')
        rows = [experience(self.config, self.a, n) for n in range(4)]
        self.assertEqual(self.choose(rows, low)['selection_mode'], 'EXPLORE')
        self.assertEqual(self.choose(rows, low)['selected_worker'], self.b)
        self.assertEqual(self.choose([], low)['selection_mode'], 'HEURISTIC')
        self.assertNotEqual(self.choose(rows, signature(risk_level='high'))['selection_mode'], 'EXPLORE')
        self.assertNotEqual(self.choose(rows, signature(risk_level='low', verification_strength='weak'))['selection_mode'], 'EXPLORE')
        self.assertNotEqual(self.choose(rows, signature(risk_level='low', environment='production'))['selection_mode'], 'EXPLORE')

    def test_J_high_risk_and_K_manual_override(self):
        risk = signature(risk_level='high')
        self.assertEqual(self.choose([experience(self.config, self.a, 0)], risk)['selection_mode'], 'EXPLOIT')
        decision = self.choose(manual_worker=self.b)
        self.assertEqual((decision['selected_worker'], decision['selection_mode']), (self.b, 'MANUAL_OVERRIDE'))
        self.config['workers'][1]['enabled'] = False
        with self.assertRaises(ValueError):
            self.choose(manual_worker=self.b)
        with self.assertRaises(ValueError):
            self.choose(sig=signature(required_capabilities=['unknown']))

    def test_M_new_registered_worker_without_special_branch(self):
        third = deepcopy(self.config['workers'][0])
        third.update(worker_id='new_backend', model='new-model', version='v2')
        third['prior']['base'] = 0.85
        self.config['workers'].append(third)
        decision = self.choose()
        self.assertEqual(decision['selected_worker'], 'new_backend')
        self.assertEqual(len(decision['suitability']), 3)

    def test_semantic_filter_and_severity(self):
        frontend = signature(task_type='frontend_style', task_subtype='styling')
        distributed = signature(task_type='distributed_reasoning', task_subtype='consistency',
                                reasoning_intensity='high')
        low = signature(reasoning_intensity='low')
        rows = [experience(self.config, self.a, 0, task=frontend),
                experience(self.config, self.a, 1, task=distributed),
                experience(self.config, self.a, 2, task=low)]
        result = self.choose(rows, signature(reasoning_intensity='high'))
        self.assertEqual(result['suitability'][self.a]['sample_count'], 0)
        soft = experience(self.config, self.a, 0, accepted=False, severity='low')
        severe = experience(self.config, self.a, 1, accepted=False, severity='high')
        self.assertLess(self.choose([severe])['suitability'][self.a]['score'],
                        self.choose([soft])['suitability'][self.a]['score'])
        formatting = deepcopy(severe)
        formatting['diagnosis']['failure_type'] = 'FORMATTING_ERROR'
        self.assertLess(self.choose([severe])['suitability'][self.a]['score'],
                        self.choose([formatting])['suitability'][self.a]['score'])

    def test_currency_mismatch_unknown_remains_null(self):
        a = experience(self.config, self.a, 0, cost=10, currency='EUR')
        b = experience(self.config, self.b, 0, cost=1, currency='USD')
        result = self.choose([a, b])
        self.assertIsNone(result['suitability'][self.a]['average_execution_cost'])
        self.assertIsNone(result['suitability'][self.a]['cost_penalty'])
        self.assertEqual(result['suitability'][self.b]['average_execution_cost'], 1)
        self.assertIsNone(result['suitability'][self.b]['cost_penalty'])

    def test_invalid_contracts_and_config(self):
        with self.assertRaises(ValueError):
            validate_signature({**signature(), 'complexity': True})
        with self.assertRaises(ValueError):
            validate_signature({k: v for k, v in signature().items() if k != 'framework'})
        with self.assertRaises(ValueError):
            validate_signature(signature(required_capabilities=['coding', 'coding']))
        with self.assertRaises(ValueError):
            profile_task(signature(), repo_context={'bad': float('nan')})
        with self.assertRaises(ValueError):
            validate_diagnosis({'attribution': 'NONE', 'failure_type': 'NONE',
                                'severity': 'high', 'summary': 'x'}, True)
        with self.assertRaises(ValueError):
            self.choose(now=datetime(2026, 9, 24))
        for key, value in [('max_worker_attempts', 3), ('max_worker_attempts', True)]:
            config = deepcopy(self.config)
            config[key] = value
            with self.assertRaises(ValueError):
                validate_config(config)
        for field, value in [('base', float('nan')), ('base', True), ('base', 7)]:
            config = deepcopy(self.config)
            config['workers'][0]['prior'][field] = value
            with self.assertRaises(ValueError):
                validate_config(config)
        config = deepcopy(self.config)
        config['policy']['recency_window_days'] = False
        with self.assertRaises(ValueError):
            validate_config(config)
        config = deepcopy(self.config)
        config['workers'].append(deepcopy(config['workers'][0]))
        with self.assertRaises(ValueError):
            validate_config(config)


if __name__ == '__main__':
    unittest.main()
