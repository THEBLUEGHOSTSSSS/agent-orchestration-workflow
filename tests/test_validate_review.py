import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.validate_review import validate


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'evidence.txt').write_text('observed result')
        self.ref = {'path': 'evidence.txt', 'sha256': hashlib.sha256(b'observed result').hexdigest()}
        self.record = {
            'task_id': 'T1', 'baseline': 'revision1', 'commander': 'primary session',
            'status': 'accepted', 'unresolved': [], 'worker_attempts': [],
            'commander_repair': None, 'artifacts': [self.ref], 'experience': self.ref,
            'criteria': [{'id': 'AC1', 'status': 'verified', 'check': 'inspected result',
                          'evidence': self.ref}],
        }

    def attempt(self, number, decision):
        return {'number': number, 'decision': decision, 'review': 'observed assessment', 'evidence': self.ref}

    def test_direct_acceptance(self):
        self.assertEqual(validate(self.record, self.root), [])

    def test_first_attempt_accepted(self):
        self.record['worker_attempts'] = [self.attempt(1, 'accept')]
        self.assertEqual(validate(self.record, self.root), [])

    def test_second_attempt_accepted(self):
        self.record['worker_attempts'] = [self.attempt(1, 'rework'), self.attempt(2, 'accept')]
        self.assertEqual(validate(self.record, self.root), [])

    def test_failed_second_requires_commander_repair(self):
        self.record['worker_attempts'] = [self.attempt(1, 'rework'), self.attempt(2, 'takeover')]
        self.assertTrue(validate(self.record, self.root))
        self.record['commander_repair'] = {'summary': 'fixed by commander, retested', 'evidence': self.ref}
        self.assertEqual(validate(self.record, self.root), [])

    def test_third_attempt_rejected(self):
        self.record['worker_attempts'] = [self.attempt(1, 'rework'), self.attempt(2, 'takeover'), self.attempt(3, 'accept')]
        self.assertIn('maximum two worker attempts', validate(self.record, self.root))

    def test_second_rework_rejected(self):
        self.record['worker_attempts'] = [self.attempt(1, 'rework'), self.attempt(2, 'rework')]
        self.assertIn('only attempt 1 permits rework', validate(self.record, self.root))

    def test_cannot_dispatch_after_acceptance(self):
        self.record['worker_attempts'] = [self.attempt(1, 'accept'), self.attempt(2, 'accept')]
        self.assertTrue(validate(self.record, self.root))

    def test_missing_experience_rejected(self):
        self.record['experience'] = None
        self.assertTrue(validate(self.record, self.root))

    def test_reported_not_accepted(self):
        self.record['status'] = 'reported'
        self.assertTrue(validate(self.record, self.root))

    def test_not_run_rejected(self):
        self.record['criteria'][0]['status'] = 'not-run'
        self.assertTrue(validate(self.record, self.root))

    def test_changed_artifact_invalidates_evidence(self):
        (self.root / 'evidence.txt').write_text('changed')
        self.assertTrue(validate(self.record, self.root))

    def test_missing_file_rejected(self):
        (self.root / 'evidence.txt').unlink()
        self.assertTrue(validate(self.record, self.root))

    def test_outside_path_rejected(self):
        self.record['experience'] = {'path': '../outside', 'sha256': 'irrelevant'}
        self.assertTrue(validate(self.record, self.root))

    def test_malformed_records_fail_closed(self):
        for field in ('worker_attempts', 'criteria', 'artifacts', 'unresolved'):
            for value in (None, 1, 'invalid', {}):
                record = copy.deepcopy(self.record)
                record[field] = value
                with self.subTest(field=field, value=value):
                    self.assertTrue(validate(record, self.root))
        self.assertTrue(validate([], self.root))

    def test_duplicate_criteria_rejected(self):
        self.record['criteria'] *= 2
        self.assertTrue(validate(self.record, self.root))

    def test_symlink_escape_rejected(self):
        (self.root / 'escape').symlink_to(self.root.parent, target_is_directory=True)
        self.record['experience'] = {'path': 'escape/outside', 'sha256': 'irrelevant'}
        self.assertTrue(validate(self.record, self.root))


if __name__ == '__main__':
    unittest.main()
