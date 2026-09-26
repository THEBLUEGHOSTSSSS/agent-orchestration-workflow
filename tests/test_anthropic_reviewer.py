"""Offline Rayin/Anthropic-compatible transport tests; no private config reads."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from routing.reviewer_runtime import run_reviewer
from test_reviewer_runtime import packet, result

class AnthropicReviewerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'
        self.write('https://provider.example')
        self.config={'reviewer_id':'claude','provider':'anthropic','family':'claude','model_id':'claude-test',
          'enabled':True,'roles_supported':['correctness_reviewer'],'max_cost_usd':.2,'max_tokens':5000,'timeout_seconds':5,
          'adapter':{'kind':'anthropic_messages','allowed_host':'provider.example','settings_file':str(self.path),'max_output_tokens':1000}}
    def write(self,url):
        self.path.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':url,'ANTHROPIC_AUTH_TOKEN':'PRIVATE-FIXTURE'}}))
    def response(self,**fields):
        return dict(model='claude-test',stop_reason='end_turn',content=[{'type':'text','text':json.dumps(result())}],usage={'input_tokens':100,'output_tokens':20,'cache_read_input_tokens':30},**fields)
    def invoke(self,wire=None):
        with patch('urllib.request.build_opener') as factory:
            response=factory.return_value.open.return_value.__enter__.return_value
            response.status=200;response.read.return_value=json.dumps(wire or self.response()).encode()
            report=run_reviewer(self.config,packet())
            return report,factory
    def test_settings_auth_and_explicit_model_ignore_environment(self):
        with patch.dict(os.environ,{'ANTHROPIC_BASE_URL':'https://wrong.example','ANTHROPIC_MODEL':'deepseek','ANTHROPIC_AUTH_TOKEN':'WRONG'}):
            report,f=self.invoke()
        self.assertEqual(report['status'],'REPORTED')
        request=f.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://provider.example/v1/messages')
        self.assertEqual(request.get_header('Authorization'),'Bearer PRIVATE-FIXTURE')
        self.assertEqual(json.loads(request.data)['model'],'claude-test')
        self.assertEqual(report['usage'],{'cost_usd':None,'total_tokens':150})
        self.assertNotIn('PRIVATE-FIXTURE',json.dumps(report))
    def test_host_scheme_userinfo_and_query_rejected_before_network(self):
        for url in ['http://provider.example','https://wrong.example','https://u:p@provider.example','https://provider.example?secret=x','https://provider.example:444']:
            self.write(url);report,f=self.invoke()
            self.assertEqual(report['status'],'ERROR');f.assert_not_called()
    def test_v1_base_path_and_x_api_key(self):
        self.path.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':'https://provider.example/v1','ANTHROPIC_API_KEY':'KEY-FIXTURE'}}))
        report,f=self.invoke();request=f.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://provider.example/v1/messages')
        self.assertEqual(request.get_header('X-api-key'),'KEY-FIXTURE')
        self.assertEqual(report['status'],'REPORTED')
    def test_truncation_tools_and_wrong_model_fail_closed(self):
        for update in [{'stop_reason':'max_tokens'},{'content':[{'type':'tool_use','name':'shell'}]},{'model':'deepseek'}]:
            wire=self.response();wire.update(update);report,_=self.invoke(wire)
            self.assertEqual(report['status'],'ERROR');self.assertEqual(report['usage']['total_tokens'],150)
    def test_missing_credentials_no_network(self):
        self.path.write_text(json.dumps({'env':{'ANTHROPIC_BASE_URL':'https://provider.example'}}))
        report,f=self.invoke();self.assertEqual(report['status'],'ERROR');f.assert_not_called()
