"""Lifecycle and real subprocess tests; all data stays in temporary synthetic ledgers."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from test_selection import load_config, ORIGINAL
from routing.service import Workflow, digest_file
from routing.validation import validate_ledger
from test_selection import signature


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proof = self.root / 'proof.txt'
        self.proof.write_text('verified artifact')
        self.w = Workflow(self.root / 'state.json', ORIGINAL)
        self.spec = dict(task_id='T1', workspace=str(self.root), objective='bounded task',
                         baseline='test-baseline', work_key='original work', scope=['proof.txt'],
                         acceptance_criteria=[dict(id='C1', check='inspect artifact')],
                         task_signature=signature(), source_kind='synthetic')
        self.w.create(self.spec)

    def run_task(self, worker=None):
        return self.w.run('T1', worker, executor=lambda *_: {'exit_code': 0})

    def review(self, accepted=True, action=None, failure='LOCAL_IMPLEMENTATION_ERROR', severity='low', attribution='MODEL_RELATED'):
        return dict(reviewer='test commander', accepted=accepted, action=action or ('accept' if accepted else 'retry'),
                    diagnosis=dict(attribution='NONE' if accepted else attribution,
                                   failure_type='NONE' if accepted else failure,
                                   severity='none' if accepted else severity, summary='observed evidence'),
                    evidence=[dict(path='proof.txt', sha256=digest_file(self.proof))],
                    criteria=[dict(id='C1', status='passed' if accepted else 'failed', observation='inspected')],
                    static_checker_result='passed',
                    handoff={key: [] for key in ('files_inspected', 'files_modified', 'current_diff', 'tests_run', 'test_results', 'previous_approach', 'what_worked', 'what_failed', 'known_bad_approaches', 'remaining_work', 'constraints')})

    def test_A_cold_start_execution_review_experience(self):
        self.assertEqual(self.w.preview('T1')['selection_mode'], 'HEURISTIC')
        self.run_task()
        with self.assertRaises(ValueError): self.run_task()
        self.w.review('T1', self.review())
        state = self.w.inspect()
        self.assertEqual(state['experiences'][0]['outcome']['worker_result_status'], 'FIRST_PASS_ACCEPTED')
        self.assertEqual(validate_ledger(state), [])
        with self.assertRaises(ValueError): self.run_task()

    def test_C_same_worker_second_success(self):
        self.run_task()
        self.w.review('T1', self.review(False))
        self.assertEqual(self.w.preview('T1')['selected_worker'], 'gpt6_sol_xhigh')
        self.run_task()
        self.w.review('T1', self.review())
        rows = self.w.inspect()['experiences']
        self.assertEqual(rows[0]['retry']['action'], 'SAME_WORKER')
        self.assertEqual(rows[1]['outcome']['worker_result_status'], 'SECOND_PASS_ACCEPTED')
        self.assertEqual(validate_ledger(self.w.inspect()), [])

    def test_D_switch_and_E_takeover_no_third(self):
        self.run_task()
        self.w.review('T1', self.review(False, failure='REASONING_FAILURE', severity='high'))
        self.assertEqual(self.w.preview('T1')['selected_worker'], 'gpt56_sol_high')
        self.run_task()
        with self.assertRaises(ValueError): self.w.review('T1', self.review(False))
        self.w.review('T1', self.review(False, action='takeover'))
        with self.assertRaises(ValueError): self.run_task('gpt6_sol_xhigh')
        record = self.review()
        record.update(summary='commander fixed and rechecked', repair_burden=3)
        self.w.takeover('T1', record)
        self.assertFalse(any(e['outcome']['accepted'] for e in self.w.inspect()['experiences']))
        self.assertEqual(validate_ledger(self.w.inspect()), [])

    def test_D_switch_then_success_experience(self):
        self.run_task()
        self.w.review('T1', self.review(False, failure='REASONING_FAILURE', severity='high'))
        self.run_task(); self.w.review('T1', self.review())
        rows = self.w.inspect()['experiences']
        self.assertEqual(rows[0]['retry']['action'], 'DIFFERENT_WORKER')
        self.assertFalse(rows[0]['outcome']['accepted'])
        self.assertTrue(rows[1]['outcome']['accepted'])
        self.assertEqual(rows[1]['worker']['worker_id'], 'gpt56_sol_high')
        self.assertEqual(validate_ledger(self.w.inspect()), [])

    def test_M_new_worker_execution_and_experience(self):
        config = load_config(); third = copy.deepcopy(config['workers'][0])
        third.update(worker_id='third', model='local-model', provider='local')
        config['workers'].append(third)
        path = self.root / 'config.json'; path.write_text(json.dumps(config))
        w = Workflow(self.root / 'state.json', path)
        w.run('T1', 'third', executor=lambda *_: {'exit_code': 0})
        w.review('T1', self.review())
        self.assertEqual(w.inspect()['experiences'][0]['worker']['worker_id'], 'third')

    def test_F_environment_failure_and_K_override(self):
        self.run_task('gpt56_sol_high')
        self.w.review('T1', self.review(False, attribution='ENVIRONMENT_RELATED', failure='MISSING_DEPENDENCY'))
        self.assertEqual(self.w.preview('T1')['selected_worker'], 'gpt56_sol_high')
        self.assertEqual(self.w.inspect()['experiences'][0]['diagnosis']['attribution'], 'ENVIRONMENT_RELATED')
        self.run_task('gpt6_sol_xhigh')
        self.w.review('T1', self.review(False, action='takeover'))
        with self.assertRaises(ValueError): self.w.preview('T1', 'gpt56_sol_high')

    def test_L_alias_fix_subtask_restart_share_budget(self):
        self.run_task()
        self.w.review('T1', self.review(False))
        self.run_task()
        self.w.review('T1', self.review(False, action='takeover'))
        for name, extra in [('renamed', {}), ('fix-task', {'parent_task_id': 'T1', 'work_key': 'fix'}), ('subtask', {'logical_task_id': 'T1', 'work_key': 'sub'})]:
            spec = dict(self.spec, task_id=name, **extra)
            self.w.create(spec)
            fresh = Workflow(self.root / 'state.json', ORIGINAL)
            with self.assertRaises(ValueError): fresh.run(name, 'gpt56_sol_high')
        self.w.create(dict(self.spec, task_id='renamed-fix', work_key='fix'))
        with self.assertRaises(ValueError): self.w.reserve('renamed-fix')
        self.assertEqual(len(self.w.inspect()['tasks']), 1)

    def test_concurrent_reservation_only_one_launch(self):
        def reserve(_):
            try: return self.w.reserve('T1')['attempt']['attempt_number']
            except ValueError: return 'refused'
        with ThreadPoolExecutor(4) as pool: values = list(pool.map(reserve, range(4)))
        self.assertEqual(values.count(1), 1)
        self.assertEqual(values.count('refused'), 3)
        self.w.recover('T1', 'test simulated interrupted execution, no live process')
        self.assertEqual(self.w.inspect('T1')['worker_attempt_count'], 1)
        with self.assertRaises(ValueError): self.w.reserve('T1')

    def test_evidence_and_recursive_entry_rejected(self):
        with patch.dict(os.environ, {'ADAPTIVE_WORKER_ROLE': 'worker'}):
            with self.assertRaises(PermissionError): self.w.reserve('T1')
            with self.assertRaises(PermissionError): self.w.create(self.spec)
        self.run_task()
        record = self.review()
        self.proof.write_text('changed')
        with self.assertRaises(ValueError): self.w.review('T1', record)
        record = self.review()
        record['criteria'][0]['status'] = 'not_run'
        with self.assertRaises(ValueError): self.w.review('T1', record)

    def test_static_checker_invalidates_changed_final_evidence(self):
        self.run_task(); self.w.review('T1', self.review())
        state = self.w.inspect()
        altered = copy.deepcopy(state)
        altered['tasks']['T1']['attempts'][0]['review']['criteria'][0]['status'] = 'not_run'
        self.assertTrue(validate_ledger(altered))
        self.proof.write_text('later mutation')
        self.assertTrue(validate_ledger(state))

    def test_corrupt_state_fails_closed(self):
        (self.root / 'state.json').write_text('{broken')
        with self.assertRaises(ValueError): self.w.preview('T1')

    def test_timeout_kills_descendant_after_leader_exits(self):
        marker = self.root / 'survived.txt'
        child = 'import signal,time,pathlib; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(.8); pathlib.Path(' + repr(str(marker)) + ').write_text("survived")'
        leader = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); time.sleep(10)'
        config = load_config()
        config['workers'][0]['adapter'] = {'kind': 'command', 'command': [sys.executable, '-c', leader]}
        path = self.root / 'config.json'; path.write_text(json.dumps(config))
        Workflow(self.root / 'state.json', path).run('T1', timeout=.3)
        time.sleep(.8)
        self.assertFalse(marker.exists())

    def test_cli_validation_and_role_guard(self):
        cli = str(Path(__file__).resolve().parents[1] / 'scripts/route_worker.py')
        command = [sys.executable, cli, '--state', str(self.root / 'state.json'), 'validate']
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        env = dict(os.environ, ADAPTIVE_WORKER_ROLE='worker')
        self.assertEqual(subprocess.run(command, env=env, capture_output=True).returncode, 1)

    def test_takeover_cannot_skip_verification(self):
        self.run_task(); self.w.review('T1', self.review(False, action='takeover'))
        record = self.review(); record.update(summary='repair', repair_burden=1)
        record['static_checker_result'] = 'not_run'
        with self.assertRaises(ValueError): self.w.takeover('T1', record)

    def test_real_subprocess_adapter_and_timeout(self):
        config = load_config()
        config['workers'][0]['adapter'] = {'kind': 'command', 'command': [sys.executable, '-c', 'import json,sys,os; p=json.load(sys.stdin); assert p["max_attempts"]==2; assert os.environ["ADAPTIVE_WORKER_ROLE"]=="worker"; print("bounded evidence")']}
        path = self.root / 'config.json'; path.write_text(json.dumps(config))
        w = Workflow(self.root / 'state.json', path)
        result = w.run('T1', timeout=3)
        self.assertEqual(result['attempts'][0]['execution']['exit_code'], 0)
        self.assertTrue(Path(result['attempts'][0]['execution']['log_path']).exists())
        w.review('T1', self.review(False))
        config['workers'][0]['adapter']['command'] = [sys.executable, '-c', 'import time; time.sleep(10)']
        path.write_text(json.dumps(config))
        result = Workflow(self.root / 'state.json', path).run('T1', timeout=.1)
        self.assertIn('timeout', result['attempts'][1]['execution']['error'])
        self.assertEqual(result['worker_attempt_count'], 2)


if __name__ == '__main__': unittest.main()
