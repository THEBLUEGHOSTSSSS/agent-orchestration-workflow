"""Offline adapter contract tests: no provider requests or CLI permission bypass."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from routing.adapters import build_command
from routing.models import load_config, validate_config
from routing.service import Workflow
from routing.selection import route
from test_selection import signature

ROOT = Path(__file__).resolve().parents[1]


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / 'examples/registry.portable.json')

    def test_neutral_defaults_require_explicit_configuration(self):
        cfg = load_config()
        self.assertTrue(all(not w['enabled'] for w in cfg['workers']))
        with self.assertRaises(ValueError): route(signature(), [], cfg)

    def test_native_default_omits_model_and_effort_overrides(self):
        codex, claude, _ = self.config['workers']
        self.assertEqual(build_command(codex, '/tmp/project'), ['codex', 'exec', '--sandbox', 'workspace-write', '--json', '-'])
        self.assertEqual(build_command(claude, '/tmp/project'), ['claude', '--print', '--output-format', 'json'])

    def test_native_configured_models_and_provider_effort(self):
        codex, claude, custom = self.config['workers']
        codex.update(model='any-codex-model', reasoning_effort='minimal')
        claude.update(model='any-claude-model', reasoning_effort='max')
        custom['reasoning_effort'] = 'provider-specific-budget'
        validate_config(self.config)
        self.assertIn('model_reasoning_effort="minimal"', build_command(codex, '/tmp'))
        self.assertEqual(build_command(claude, '/tmp')[-4:], ['--model','any-claude-model','--effort','max'])

    def test_generic_substitution_no_shell_or_recursive_expansion(self):
        worker = self.config['workers'][2]
        worker.update(model='literal-{workspace}',reasoning_effort='off')
        worker['adapter']['command'] = ['runner','{model}','{workspace}','{reasoning_effort}']
        self.assertEqual(build_command(worker,'/a b'), ['runner','literal-{workspace}','/a b','off'])

    def test_legacy_original_registry_still_works(self):
        cfg = load_config(ROOT / 'examples/registry.original.json')
        argv = build_command(cfg['workers'][0], '/tmp')
        self.assertEqual(argv, ['codex-worker','/tmp','--model','gpt-6-sol','--reasoning-effort','xhigh'])

    def test_each_adapter_executes_with_cwd_stdin_and_shared_review_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = root/'fake.py'
            runner.write_text('import sys,json,os; p=json.load(sys.stdin); print(json.dumps({"argv":sys.argv[1:],"cwd":os.getcwd(),"attempt":p["attempt_number"]}))')
            for number, kind in enumerate(('codex_cli','claude_code','command','codex_worker')):
                cfg = copy.deepcopy(self.config)
                worker = cfg['workers'][0]
                worker.update(enabled=True,availability='available',model='arbitrary-model',reasoning_effort='custom-effort',adapter={'kind':kind,'command':[sys.executable,str(runner)]})
                config = root/f'config{number}.json';config.write_text(json.dumps(cfg))
                w = Workflow(root/f'state{number}.json',config)
                task = dict(task_id=f'T{number}',workspace=str(root),baseline='synthetic',work_key=f'adapter{kind}',objective='validate transport',scope=['result'],acceptance_criteria=[dict(id='C',check='transport')],task_signature=signature(),source_kind='synthetic')
                w.create(task); result=w.run(task['task_id'],timeout=5)
                self.assertEqual(result['status'],'AWAITING_REVIEW')
                execution=result['attempts'][0]['execution']
                self.assertEqual(execution['exit_code'],0)
                observed=json.loads(Path(execution['log_path']).read_text())
                self.assertEqual(Path(observed['cwd']).resolve(),root.resolve())
                self.assertEqual(observed['attempt'],1)
                with self.assertRaises(ValueError): w.run(task['task_id'])

if __name__ == '__main__': unittest.main()
