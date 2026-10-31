"""Finite rejected diagnostics and exact history; no native behavior claims."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_async_fixture as history
import test_native_tree_load_harness as original_tests
import test_native_1c_output_artifact as artifact
import test_native_1c_full_host as host_tests
from scripts import native_historical_replay as replay

ROOT = Path(__file__).resolve().parents[1]
PATHS = ('scripts/native_1c_bootstrap/full_suite.py', 'scripts/native_1c_full_host.py')
CODES = '0123456789ABCDEFGHIJKLMNOPQR'


def diagnostic_output(code):
    prefix = b''.join(f'old{i}: [ok]\n'.encode('ascii') for i in range(976))
    payload = ('1?C0' + code + '-!' + '.' * 58).encode('ascii')
    return prefix + b''.join(f'TL{i:02d}: ['.encode('ascii') + payload + b']\n' for i in range(1, 46)) + __import__('test_native_tree_move_contract').synthetic_record()[1] + __import__('test_native_tree_total_contract').synthetic_record()[1]


class CalibrationHarnessTests(host_tests.SyntheticFilesystemCase):
    def test_exact_outer_source_and_harness_inverse(self):
        text = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        restored = replay.without_tree_load_calibration(text)
        self.assertEqual(hashlib.sha256(restored.encode('utf-8-sig')).hexdigest(),
                         '0f36f76a44f63f9623a3c204c5cace3dd4d4328b4465f3bb002f660fc96e684b')
        prior = json.loads((ROOT / 'tests/tree_load_source_inverse.json').read_text(encoding='utf-8'))
        for path in PATHS:
            current = (ROOT / path).read_text(encoding='utf-8')
            restored = history.without_tree_load_calibration_measurement(current, host=path.endswith('full_host.py'))
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), prior[path]['candidate_sha256'])
            self.assertTrue(history.without_tree_load_measurement(current, host=path.endswith('full_host.py')))

    def test_drift_fails_even_with_rebased_outer_checksum(self):
        inventory = json.loads((ROOT / 'tests/tree_load_calibration_source_inverse.json').read_text(encoding='utf-8'))
        for path in PATHS:
            source = (ROOT / path).read_text(encoding='utf-8')
            source = history.without_tree_rows_diagnostic_measurement(source, host=path.endswith('full_host.py'))
            for altered in (source + '\n', source.replace('73ffd118', '73ffd119', 1)):
                with self.assertRaises(AssertionError):
                    history.without_tree_load_calibration_measurement(altered, host=path.endswith('full_host.py'))
                forged = copy.deepcopy(inventory)
                forged[path]['candidate_sha256'] = hashlib.sha256(altered.encode()).hexdigest()
                with mock.patch.object(history.json, 'loads', return_value=forged), self.assertRaises(AssertionError):
                    history.without_tree_load_calibration_measurement(altered, host=path.endswith('full_host.py'))
        source = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        altered = source.replace('Stage = "R"', 'Stage = "S"', 1)
        with mock.patch.object(replay, 'TREE_LOAD_CALIBRATION_SOURCE_SHA256', hashlib.sha256(altered.encode('utf-8-sig')).hexdigest()), self.assertRaises(ValueError):
            replay.without_tree_load_calibration(altered)

    def test_all_stages_reject_identical_host_native_and_artifact(self):
        full = artifact.full
        for code in CODES:
            with self.subTest(stage=code):
                payload = diagnostic_output(code)
                with self.assertRaisesRegex(full.FullError, '^tree_load_observation_invalid$'):
                    full.validate_tree_load_observations(payload)
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve(); capture = root / 'capture'; capture.mkdir()
                    sources = root / 'integrational_tests/tests'; sources.mkdir(parents=True)
                    cases = []; inputs = {}
                    for name in full.SCENARIOS:
                        key = f'integrational_tests/tests/{name}.bsl'
                        source_bytes = (ROOT / key).read_bytes().replace(b'\r\n', b'\n') if name == 'collections' else b'synthetic source'
                        if name == 'collections':
                            self.assertEqual(full.digest(source_bytes), full.COLLECTIONS_SOURCE_SHA256)
                        (root / key).write_bytes(source_bytes)
                        inputs[key] = full.digest(source_bytes)
                        output = payload if name == 'collections' else b'ok\n'
                        (capture / (name + '.out')).write_bytes(output)
                        cases.append({'name': name, 'status': 'ok', 'source_sha256': inputs[key],
                                      'output_sha256': full.digest(output), 'output_size': len(output)})
                    def runner(command, cwd, **limits):
                        return 0, payload if Path(command[-2]).stem == 'collections' else b'ok\n', b''
                    compared = full.compare_outputs(root, capture, {'status': 'ok', 'cases': cases}, inputs, runner=runner)
                    collection = compared['cases'][0]
                    self.assertEqual(collection['failure_kind'], 'tree_load_observation_invalid')
                    self.assertEqual(collection['acceptance_status'], 'rejected')
                report = artifact.accepted_report()
                key = 'integrational_tests/tests/collections.bsl'
                report['stage3']['input_sha256'][key] = full.COLLECTIONS_SOURCE_SHA256
                report['trusted_input_sha256'][key] = full.COLLECTIONS_SOURCE_SHA256
                report['stage3']['cases'][0].update(source_sha256=full.COLLECTIONS_SOURCE_SHA256,
                    output_sha256=full.digest(payload), output_size=len(payload), message_count=1023)
                report['comparison']['cases'][0].update(native_sha256=full.digest(payload), native_size=len(payload),
                    interpreter_sha256=full.digest(payload), interpreter_size=len(payload))
                payloads = dict.fromkeys(full.ARTIFACT_FILES[:-1], artifact.PAYLOAD)
                payloads['collections.out'] = payload
                with self.assertRaisesRegex(full.FullError, '^native_artifact_evidence_invalid$'):
                    full.output_artifact_files(payloads, report, artifact.smoke.IMAGE)

    def test_history_reads_ignore_cp1252_default_including_utf8_mode(self):
        targets = {ROOT / p for p in PATHS} | {ROOT / 'tests' / name for name in
            ('tree_load_source_inverse.json', 'tree_unload_supplement_source_inverse.json',
             'tree_load_calibration_source_inverse.json')}
        real_read = Path.read_text; real_open = Path.open; seen = set()
        def read(path, *args, **kwargs):
            if path in targets and (not args or args[0] is None) and kwargs.get('encoding') is None:
                kwargs['encoding'] = 'cp1252'
            return real_read(path, *args, **kwargs)
        def opened(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
            if path in targets and 'b' not in mode:
                self.assertEqual(encoding, 'utf-8')
                seen.add(path)
            return real_open(path, mode, buffering, encoding, errors, newline)
        with mock.patch.object(Path, 'read_text', read), mock.patch.object(Path, 'open', opened):
            original_tests.LoadHarnessHistoryTests().test_exact976_harness_precedes_existing_history()
            original_tests.LoadHarnessHistoryTests().test_source_and_harness_drift_rejected_even_with_rebased_outer_hash()
            self.test_exact_outer_source_and_harness_inverse()
            self.test_drift_fails_even_with_rebased_outer_checksum()
        self.assertEqual(seen, targets)
        # A genuine omitted-encoding read must fail decoding, not merely an assertion.
        with mock.patch.object(Path, 'read_text', read), self.assertRaises(UnicodeDecodeError):
            (ROOT / 'tests/tree_load_source_inverse.json').read_text()


if __name__ == '__main__':
    unittest.main()
