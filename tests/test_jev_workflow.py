"""Advisory stage must not acquire acceptance or execution authority."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from routing.service import Workflow, digest_file
from routing.validation import validate_ledger
from test_selection import ORIGINAL, signature


class ScreeningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); (self.root/'proof.txt').write_text('actual proof')
        self.w=Workflow(self.root/'state.json',ORIGINAL)
        self.w.create(dict(task_id='T1',work_key='bounded original task',workspace=str(self.root),
            objective='verify',baseline='fixture',scope=['proof.txt'],source_kind='probe',
            acceptance_criteria=[{'id':'C1','check':'inspect proof'}],task_signature=signature()))
        self.packet={'logical_task_id':'T1','items':[{'id':'C1','claim':'test passed','evidence':'test not run'}]}

    def run_attempt(self): self.w.run('T1',executor=lambda *_:{'exit_code':0})

    def test_requires_report_and_same_identity(self):
        with self.assertRaises(ValueError): self.w.screen('T1',self.packet)
        self.run_attempt()
        with self.assertRaises(ValueError): self.w.screen('T1',dict(self.packet,logical_task_id='other'))

    def test_disabled_preserves_state_experience_and_attempt_limit(self):
        self.run_attempt(); before=self.w.inspect()
        result=self.w.screen('T1',self.packet)
        after=self.w.inspect()
        self.assertEqual(result['status'],'DISABLED')
        self.assertEqual(after['tasks']['T1']['status'],'AWAITING_REVIEW')
        self.assertEqual(after['tasks']['T1']['worker_attempt_count'],1)
        self.assertEqual(after['experiences'],before['experiences'])
        self.assertEqual(validate_ledger(after),[])
        with self.assertRaises(ValueError): self.run_attempt()

    def test_missing_key_unknown_still_needs_review(self):
        self.run_attempt()
        with patch.dict('os.environ',{},clear=True): result=self.w.screen('T1',self.packet,'SHADOW')
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(self.w.inspect()['tasks']['T1']['status'],'AWAITING_REVIEW')

    def test_worker_cannot_screen(self):
        self.run_attempt()
        with patch.dict('os.environ',{'ADAPTIVE_WORKER_ROLE':'worker'}):
            with self.assertRaises(PermissionError): self.w.screen('T1',self.packet)

    def test_no_attachment_after_concurrent_change(self):
        self.run_attempt()
        from routing.jev import screen_evidence
        def concurrent(packet,mode):
            result=screen_evidence(packet,'OFF')
            self.w.store.transaction(lambda s:s['tasks']['T1'].update(status='TAKEOVER_REQUIRED'))
            return result
        with patch('routing.jev.screen_evidence',side_effect=concurrent):
            with self.assertRaises(ValueError): self.w.screen('T1',self.packet)
        self.assertNotIn('advisory_screens',self.w.inspect()['tasks']['T1']['attempts'][0])
