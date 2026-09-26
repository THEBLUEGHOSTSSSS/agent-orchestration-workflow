"""Offline Jev contract tests. No real credentials or model requests."""
import importlib.util
import io
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from routing import jev


def packet():
    return {'logical_task_id': 'T1', 'items': [
        {'id': 'a', 'claim': 'Tests passed.', 'evidence': 'One test passed.'},
        {'id': 'b', 'claim': 'Deployment accepted.', 'evidence': ''},
    ]}


def response():
    return {'model': 'typesafe/jev-1.13-20260917', 'answers': {
        key: {'type': 'choice', 'choice': 'supported', 'confidence': 0.7,
              'probabilities': {'supported': 0.8, 'contradicted': 0.1, 'insufficient': 0.1}}
        for key in ('a', 'b')}, 'usage': {'input_tokens': 14, 'output_tokens': 12, 'cost': 0.001}}


def cli():
    path = Path(__file__).resolve().parents[1] / 'scripts/screen_evidence.py'
    spec = importlib.util.spec_from_file_location('screen_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JevTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'OPENROUTER_API_KEY': 'secret-test-key',
                                         'ADAPTIVE_WORKER_ROLE': 'commander'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def call(self, value=None, raw=None, error=None, mode='SHADOW'):
        with patch('routing.jev.urllib.request.build_opener') as factory:
            opener = factory.return_value
            if error:
                opener.open.side_effect = error
            else:
                stream = opener.open.return_value.__enter__.return_value
                stream.status = 200
                stream.read.return_value = raw if raw is not None else json.dumps(value or response()).encode()
            result = jev.screen_evidence(packet(), mode)
            return result, opener

    def test_valid_batch_retains_all_evidence(self):
        result, opener = self.call(mode='ASSIST')
        self.assertEqual(result['status'], 'SCREENED')
        self.assertEqual(result['items'], packet()['items'])
        self.assertEqual(set(result['answers']), {'a', 'b'})
        self.assertTrue(result['commander_review_required'])
        self.assertFalse(result['worker_experience_eligible'])
        self.assertEqual(result['source_kind'], 'probe')
        self.assertEqual(result['cost'], 0.001)
        self.assertEqual(result['model_resolved'], response()['model'])
        self.assertEqual(len(result['input_sha256']), 64)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, jev.ENDPOINT)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 30)
        body = json.loads(request.data)
        self.assertEqual(set(body['questions']), {'a', 'b'})
        self.assertEqual(body['state']['items'], packet()['items'])
        self.assertIn('"a"', body['questions']['a']['instructions'])
        self.assertEqual(body['model'], jev.MODEL)
        self.assertNotIn('secret-test-key', json.dumps(result))

    def test_off_never_reads_credential_or_opens_network(self):
        original = os.environ.get
        def guarded(key, default=None):
            self.assertNotEqual(key, 'OPENROUTER_API_KEY')
            return original(key, default)
        with patch.object(os.environ, 'get', side_effect=guarded), patch('routing.jev.urllib.request.build_opener') as factory:
            result = jev.screen_evidence(packet())
        self.assertEqual(result['status'], 'DISABLED')
        factory.assert_not_called()

    def test_missing_key(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}), patch('routing.jev.urllib.request.build_opener') as factory:
            result = jev.screen_evidence(packet(), 'SHADOW')
        self.assertEqual(result['error_code'], 'missing_api_key')
        self.assertEqual(result['items'], packet()['items'])
        factory.assert_not_called()

    def test_worker_refused_even_off(self):
        with patch.dict(os.environ, {'ADAPTIVE_WORKER_ROLE': 'worker'}), patch('routing.jev.urllib.request.build_opener') as factory:
            for mode in jev.MODES:
                with self.assertRaises(PermissionError):
                    jev.screen_evidence(packet(), mode)
        factory.assert_not_called()

    def test_errors_are_unknown_without_sensitive_detail(self):
        errors = [urllib.error.URLError('secret-test-key'), TimeoutError('secret-test-key'),
                  http.client.IncompleteRead(b'secret-test-key'),
                  urllib.error.HTTPError(jev.ENDPOINT, 401, 'secret-test-key', {}, None)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                result, opener = self.call(error=error)
                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertNotIn('secret-test-key', json.dumps(result))
                self.assertEqual(result['items'], packet()['items'])
                opener.open.assert_called_once()

    def test_redirect_handler_rejects_all_redirects(self):
        handler = jev._NoRedirect()
        req = urllib.request.Request(jev.ENDPOINT, headers={'Authorization': 'Bearer secret-test-key'})
        for code in (301, 302, 303, 307, 308):
            with self.assertRaises(urllib.error.HTTPError):
                handler.redirect_request(req, None, code, 'redirect', {}, 'https://attacker.example/')

    def test_numeric_and_schema_failures(self):
        mutations = [
            lambda d: d['answers'].pop('a'),
            lambda d: d['answers'].update(extra=d['answers']['a']),
            lambda d: d['answers']['a'].update(choice='other'),
            lambda d: d['answers']['a'].update(choice='contradicted'),
            lambda d: d['answers']['a'].update(confidence=True),
            lambda d: d['answers']['a'].update(confidence=float('nan')),
            lambda d: d['answers']['a'].update(confidence=float('inf')),
            lambda d: d['answers']['a'].update(probabilities={'supported': 0.8}),
            lambda d: d['answers']['a']['probabilities'].update(supported=0.9),
            lambda d: d['answers']['a']['probabilities'].update(supported=-1),
            lambda d: d['answers']['a']['probabilities'].update(supported='0.8'),
            lambda d: d['answers']['a'].update(type='noul'),
            lambda d: d.update(model=''),
            lambda d: d['usage'].update(input_tokens=-1),
            lambda d: d['usage'].update(output_tokens=True),
            lambda d: d['usage'].update(cost=float('inf')),
            lambda d: d['usage'].update(cost='0.1'),
        ]
        for mutate in mutations:
            value = response(); mutate(value)
            result, _ = self.call(value)
            self.assertEqual(result['status'], 'UNKNOWN', repr(value))
            self.assertEqual(result['answers'], {})

    def test_malformed_oversized_duplicate_response(self):
        for raw in (b'{', b'not json secret-test-key', b'x' * (jev.MAX_RESPONSE_BYTES + 1),
                    b'{"model":"x","model":"y"}', b'null'):
            result, _ = self.call(raw=raw)
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertNotIn('secret-test-key', json.dumps(result))

    def test_deep_response_is_unknown(self):
        result, _ = self.call(raw=b'[' * 2000 + b']' * 2000)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['error_code'], 'invalid_response')

    def test_rounded_probabilities_are_supported(self):
        value = response()
        for answer in value['answers'].values():
            answer['probabilities'] = {'supported': .67, 'contradicted': .16, 'insufficient': .16}
        result, _ = self.call(value)
        self.assertEqual(result['status'], 'SCREENED')

    def test_bounded_strict_packet_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'input.json'
            for text in ('[' * 2000 + ']' * 2000, '{"items":[],"items":[]}', ' ' * (jev.MAX_INPUT_BYTES + 1)):
                src.write_text(text)
                with self.assertRaises(ValueError): jev.read_packet(src)

    def test_output_hardlink_is_refused_before_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'input.json'; dst = Path(tmp) / 'alias.json'
            src.write_text(json.dumps(packet())); os.link(src, dst)
            with patch('routing.jev.urllib.request.build_opener') as factory, patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(cli().main(['--input', str(src), '--output', str(dst), '--mode', 'SHADOW']), 2)
                factory.assert_not_called()
            self.assertEqual(json.loads(src.read_text()), packet())

    def test_missing_usage_remains_null_not_estimated(self):
        value = response(); value.pop('usage')
        result, _ = self.call(value)
        self.assertEqual(result['status'], 'SCREENED')
        self.assertIsNone(result['cost'])
        self.assertIsNone(result['usage'])

    def test_input_bounds_and_no_gold_labels(self):
        cases = []
        p = packet(); p['items'][0]['gold'] = 'supported'; cases.append(p)
        p = packet(); p['gold_labels'] = {}; cases.append(p)
        p = packet(); p['items'][1]['id'] = 'a'; cases.append(p)
        p = packet(); p['items'] = []; cases.append(p)
        p = packet(); p['items'] *= 17; cases.append(p)
        p = packet(); p['items'][0]['claim'] = 'x' * (jev.MAX_TEXT_CHARS + 1); cases.append(p)
        p = packet(); p['items'][0]['evidence'] = {}; cases.append(p)
        p = packet(); p['items'] = [{'id': str(i), 'claim': 'x' * 16000, 'evidence': 'y' * 16000} for i in range(32)]; cases.append(p)
        with patch('routing.jev.urllib.request.build_opener') as factory:
            for value in cases:
                with self.assertRaises(ValueError): jev.screen_evidence(value, 'SHADOW')
        factory.assert_not_called()

    def test_cli_off_and_unknown_exit_convention(self):
        main = cli().main
        with tempfile.TemporaryDirectory() as tmp, patch('sys.stdout', new_callable=io.StringIO):
            src = Path(tmp) / 'input.json'; dst = Path(tmp) / 'output.json'
            src.write_text(json.dumps(packet()))
            self.assertEqual(main(['--input', str(src), '--output', str(dst)]), 0)
            self.assertEqual(json.loads(dst.read_text())['status'], 'DISABLED')
            dst = Path(tmp) / 'unknown.json'
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}):
                self.assertEqual(main(['--mode', 'SHADOW', '--input', str(src), '--output', str(dst)]), 2)
            self.assertEqual(json.loads(dst.read_text())['status'], 'UNKNOWN')
            with patch.dict(os.environ, {'ADAPTIVE_WORKER_ROLE': 'worker'}), patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(main(['--input', str(src), '--output', str(dst)]), 2)
            with patch('sys.stderr', new_callable=io.StringIO) as err:
                self.assertEqual(main(['--input', str(src), '--output', str(src)]), 2)
                self.assertNotIn(str(src), err.getvalue())
            self.assertEqual(json.loads(src.read_text()), packet())


if __name__ == '__main__':
    unittest.main()
