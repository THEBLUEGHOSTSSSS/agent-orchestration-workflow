"""Real CLI adapter contract; calls mocked, no user authentication accessed."""
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from routing.reviewer_runtime import run_reviewer,run_command
from test_reviewer_runtime import packet,result

class ClaudeReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=Path(self.tmp.name)/'settings.json'
        self.settings.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':'https://provider.example','ANTHROPIC_AUTH_TOKEN':'FAKE-AUTH-KEY'}}))
    def config(self):
        return {'reviewer_id':'claude','provider':'anthropic','family':'claude','model_id':'claude-test','enabled':True,
                'roles_supported':['correctness_reviewer'],'max_cost_usd':.5,'max_tokens':4000,'timeout_seconds':5,
                'adapter':{'kind':'claude_code_reviewer','executable':'claude','settings_file':str(self.settings),'allowed_host':'provider.example'}}
    def wire(self):
        return {'num_turns':1,'is_error':False,'subtype':'success','result':json.dumps(result()),'modelUsage':{'claude-test':{}},
                'usage':{'input_tokens':100,'output_tokens':20},'total_cost_usd':.001}
    def test_cli_isolation_arguments_and_cost_not_invoice(self):
        with patch('routing.reviewer_runtime.run_command',return_value=(0,json.dumps(self.wire()),None)) as run:
            report=run_reviewer(self.config(),packet())
        self.assertEqual(report['status'],'REPORTED')
        argv=run.call_args.args[0]
        for flag in ('--bare','--no-session-persistence','--strict-mcp-config','--disable-slash-commands'):self.assertIn(flag,argv)
        self.assertEqual(argv[argv.index('--tools')+1],'')
        self.assertEqual(argv[argv.index('--setting-sources')+1],'')
        self.assertEqual(argv[argv.index('--max-turns')+1],'2')
        self.assertEqual(argv[argv.index('--model')+1],'claude-test')
        self.assertNotIn('FAKE-AUTH-KEY',json.dumps(argv))
        self.assertEqual(run.call_args.kwargs['provider_environment']['ANTHROPIC_API_KEY'],'FAKE-AUTH-KEY')
        self.assertIsNone(report['usage']['cost_usd'])
        self.assertEqual(report['usage']['total_tokens'],120)
    def test_failed_cli_keeps_usage(self):
        with patch('routing.reviewer_runtime.run_command',return_value=(1,json.dumps(self.wire()),'command_failed')):
            report=run_reviewer(self.config(),packet())
        self.assertEqual(report['status'],'ERROR');self.assertEqual(report['usage']['total_tokens'],120)
    def test_cli_multi_model_cannot_claim_independent_identity(self):
        wire=self.wire();wire['modelUsage']['claude-other']={}
        with patch('routing.reviewer_runtime.run_command',return_value=(0,json.dumps(wire),None)):
            report=run_reviewer(self.config(),packet())
        self.assertEqual(report['status'],'ERROR')
    def test_empty_cli_argument_is_preserved(self):
        import sys
        code,out,error=run_command([sys.executable,'-c','import sys; print(repr(sys.argv[1]))',''],'',2)
        self.assertEqual(out.strip(),"''");self.assertEqual(code,0);self.assertIsNone(error)
    def test_proxy_is_explicit_and_cannot_embed_credentials(self):
        cfg=self.config();cfg['adapter']['proxy_url']='http://127.0.0.1:7890'
        with patch('routing.reviewer_runtime.run_command',return_value=(0,json.dumps(self.wire()),None)) as run:
            self.assertEqual(run_reviewer(cfg,packet())['status'],'REPORTED')
        self.assertEqual(run.call_args.kwargs['proxy_url'],'http://127.0.0.1:7890')
        cfg['adapter']['proxy_url']='http://secret:password@proxy.example'
        with patch('routing.reviewer_runtime.run_command') as run:
            self.assertEqual(run_reviewer(cfg,packet())['status'],'ERROR');run.assert_not_called()
    def test_stdin_is_pipe_for_native_client_compatibility(self):
        import sys
        code,out,error=run_command([sys.executable,'-c','import os,stat,sys; assert stat.S_ISFIFO(os.fstat(0).st_mode); print(sys.stdin.read())'],'probe',2)
        self.assertEqual(code,0);self.assertEqual(out.strip(),'probe');self.assertIsNone(error)

    def test_extra_turns_or_subagents_cannot_be_accepted(self):
        for fields in [{'num_turns':3},{'subagent_stats':{'spawned':1}}]:
            wire=self.wire();wire.update(fields)
            with patch('routing.reviewer_runtime.run_command',return_value=(0,json.dumps(wire),None)):
                report=run_reviewer(self.config(),packet())
            self.assertEqual(report['status'],'ERROR')

    def test_native_schema_output_is_validated(self):
        wire=self.wire();wire.update(result='',structured_output=result(),num_turns=2)
        with patch('routing.reviewer_runtime.run_command',return_value=(0,json.dumps(wire),None)) as run:
            report=run_reviewer(self.config(),packet())
        self.assertEqual(report['status'],'REPORTED')
        argv=run.call_args.args[0];self.assertIn('--json-schema',argv)
        schema=json.loads(argv[argv.index('--json-schema')+1])
        self.assertFalse(schema['additionalProperties'])
