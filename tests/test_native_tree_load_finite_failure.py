"""Rejected finite diagnostics only: synthetic tests, never native acceptance."""
import copy
import json
import itertools
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import test_native_1c_output_artifact as artifact
import test_native_tree_load_calibration_harness as calibration

full = artifact.full


class FiniteFailureTests(artifact.SyntheticFilesystemCase):
    invoke = artifact.OrchestrationTests.invoke

    def native(self, **updates):
        result = dict(source_sha256=full.COLLECTIONS_SOURCE_SHA256, message_count=1021)
        result.update(updates)
        return result

    def test_all_28_exact_stages_and_no_observation_acceptance(self):
        for code in calibration.CODES:
            with self.subTest(code=code):
                data = calibration.diagnostic_output(code)
                self.assertEqual(full.tree_load_calibration_failure(data, self.native()),
                                 'tree_load_calibration_' + code)
                with self.assertRaisesRegex(full.FullError, '^tree_load_observation_invalid$'):
                    full.validate_tree_load_observations(data)

    def test_unknown_mixed_malformed_labels_count_source_fail_closed(self):
        data = calibration.diagnostic_output('A')
        mutations = [data.replace(b'1?C0A-', b'1?C0Z-'),
            data.replace(b'1?C0A-', b'1?C0B-', 1),
            data.replace(b'TL01:', b'TL99:', 1), data.replace(b'TL45:', b'TL44:', 1),
            data.replace(b'1?C0A-!', b'1?C0A-?', 1), data.replace(b'1?C0A-', b'1?C0AA-', 1),
            data.replace(b'old0: [ok]\n', b'', 1), data + b'extra: [ok]\n',
            data[:-1], b'\xff' + data, data.replace(b'old0: [ok]', b'old0: ["TL01: [1?C0A-!]"', 1)]
        for changed in mutations:
            with self.subTest(changed=changed[:70]):
                self.assertIsNone(full.tree_load_calibration_failure(changed, self.native()))
        for metadata in (self.native(source_sha256='0'*64), self.native(message_count=1020),
                         self.native(message_count='1021'), self.native(message_count=True)):
            self.assertIsNone(full.tree_load_calibration_failure(data, metadata))

    def test_all_stages_propagate_through_real_main_summary_without_export(self):
        for code, mode in itertools.product(calibration.CODES, (full.BYTE_EXACT, full.MAP_MODE)):
            with self.subTest(code=code, mode=mode):
                result, exported, retained = self.invoke(through_main=True, comparison_mode=mode,
                    collections_payload=calibration.diagnostic_output(code),
                    post_create=(artifact.PAYLOAD, (0, artifact.PAYLOAD, b'')))
                self.assertNotEqual(result['exit_code'], 0)
                self.assertEqual(exported, [])
                self.assertNotIn('native_output_artifact_ready=true', result['ready'])
                report = result['summary']
                self.assertFalse(report['native_evidence_accepted'])
                self.assertEqual(report['error'], 'native_artifact_evidence_invalid')
                compared = report['probe']['comparison']
                case = compared['cases'][0]
                self.assertEqual(case['failure_kind'], 'tree_load_calibration_' + code)
                self.assertEqual((case['status'], case['acceptance_status']), ('error', 'rejected'))
                for field in ('interpreter_size','interpreter_sha256','mismatch','semantic'):
                    self.assertIsNone(case[field])
                # Fixed existing key, shorter token: report shape and size cannot grow.
                generic = copy.deepcopy(report)
                generic['probe']['comparison']['cases'][0]['failure_kind'] = 'tree_load_observation_invalid'
                self.assertLess(len(json.dumps(report)), len(json.dumps(generic)))
                target = full.LINUX_TARGET if mode == full.MAP_MODE else full.WINDOWS_TARGET
                full.validate_comparison(compared, report['probe']['stage3'], target, mode)
                for mutate in ('unknown', 'accepted', 'other_case', 'source', 'input_source', 'input_none', 'input_list', 'input_string', 'count'):
                    bad = copy.deepcopy(compared); stage = copy.deepcopy(report['probe']['stage3'])
                    if mutate == 'unknown': bad['cases'][0]['failure_kind'] = 'tree_load_calibration_Z'
                    if mutate == 'accepted': bad['cases'][0]['acceptance_status'] = 'accepted'
                    if mutate == 'other_case':
                        bad['cases'][1].update({k:v for k,v in case.items() if k != 'name'})
                    if mutate == 'source': stage['cases'][0]['source_sha256'] = '0'*64
                    if mutate == 'input_source': stage['input_sha256']['integrational_tests/tests/collections.bsl'] = '0'*64
                    if mutate == 'input_none': stage['input_sha256'] = None
                    if mutate == 'input_list': stage['input_sha256'] = []
                    if mutate == 'input_string': stage['input_sha256'] = 'bad'
                    if mutate == 'count': stage['cases'][0]['message_count'] = 1020
                    with self.assertRaises(full.FullError):
                        full.validate_comparison(bad, stage, target, mode)

    def test_mixed_and_malformed_native_through_main_stay_generic(self):
        original = calibration.diagnostic_output('A')
        for data in (original.replace(b'1?C0A-', b'1?C0B-', 1),
                     original.replace(b'1?C0A-!', b'1?C0A-?', 1)):
            result, exported, retained = self.invoke(through_main=True,
                collections_payload=data, post_create=(artifact.PAYLOAD, (0, artifact.PAYLOAD, b'')))
            self.assertNotEqual(result['exit_code'], 0)
            self.assertEqual(exported, [])
            self.assertFalse(result['summary']['native_evidence_accepted'])
            self.assertEqual(result['summary']['probe']['comparison']['cases'][0]['failure_kind'],
                             'tree_load_observation_invalid')

    def test_real_crlf_checkout_fixtures_keep_source_binding(self):
        # Real CRLF bytes on disk, not a platform-flag mock. Only synthetic
        # checkout preparation canonicalizes LF; production guards stay strict.
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory).resolve()
            # Cover the complete source set consumed by actual smoke.main
            # staging, not only the direct compare_outputs six-scenario fixture.
            for rel in artifact.smoke.FULL_STAGED_FILES:
                target = checkout / rel; target.parent.mkdir(parents=True, exist_ok=True)
                raw = (artifact.smoke.ROOT / rel).read_bytes().replace(b'\r\n', b'\n')
                target.write_bytes(raw.replace(b'\n', b'\r\n'))
            raw = (checkout / 'integrational_tests/tests/collections.bsl').read_bytes()
            self.assertIn(b'\r\n', raw)
            self.assertNotEqual(full.digest(raw), full.COLLECTIONS_SOURCE_SHA256)
            with mock.patch.object(calibration, 'ROOT', checkout), \
                    mock.patch.object(artifact.smoke, 'ROOT', checkout):
                names = unittest.defaultTestLoader.getTestCaseNames(type(self))
                suite = unittest.TestSuite(type(self)(name) for name in names
                    if name != 'test_real_crlf_checkout_fixtures_keep_source_binding')
                suite.addTest(calibration.CalibrationHarnessTests(
                    'test_all_stages_reject_identical_host_native_and_artifact'))
                import test_native_tree_rows_failure as rows
                suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(rows.RowsFailureTests))
                result = unittest.TestResult()
                with mock.patch.object(artifact.smoke, 'main', wraps=artifact.smoke.main) as actual_main:
                    suite.run(result)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
                self.assertEqual(result.skipped, [])
                self.assertEqual(result.testsRun, len(names) + len(
                    unittest.defaultTestLoader.getTestCaseNames(rows.RowsFailureTests)))
                self.assertEqual(actual_main.call_count, 28 * 2 + 2 + 81 * 2)

    def test_orchestration_fixture_rejects_unreviewed_checkout_bytes(self):
        source = artifact.smoke.ROOT / 'integrational_tests/tests/collections.bsl'
        read_bytes = Path.read_bytes
        reviewed = read_bytes(source).replace(b'\r\n', b'\n')
        self.assertTrue(reviewed.startswith(b'\xef\xbb\xbf'))
        for changed in (reviewed[3:], reviewed.replace(b'\n', b'\r'), reviewed + b'// changed\n'):
            def read_checkout(path):
                return changed if path == source else read_bytes(path)
            with mock.patch.object(Path, 'read_bytes', read_checkout), self.assertRaises(AssertionError):
                self.invoke(through_main=True)

    def test_host_only_failure_remains_generic(self):
        from test_native_tree_load_contract import synthetic_output
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); capture = root / 'capture'; capture.mkdir()
            source_dir = root / 'integrational_tests/tests'; source_dir.mkdir(parents=True)
            inputs = {}; cases = []
            for name in full.SCENARIOS:
                key = f'integrational_tests/tests/{name}.bsl'
                source = (calibration.ROOT / key).read_bytes().replace(b'\r\n', b'\n')
                if name == 'collections':
                    self.assertEqual(full.digest(source), full.COLLECTIONS_SOURCE_SHA256)
                (root / key).write_bytes(source); inputs[key] = full.digest(source)
                payload = synthetic_output() if name == 'collections' else b'ok\n'
                (capture / f'{name}.out').write_bytes(payload)
                cases.append(dict(name=name, status='ok', source_sha256=inputs[key],
                    output_size=len(payload), output_sha256=full.digest(payload),
                    message_count=1021 if name == 'collections' else 1))
            def runner(args, cwd):
                return 0, calibration.diagnostic_output('A') if Path(args[-2]).stem == 'collections' else b'ok\n', b''
            compared = full.compare_outputs(root, capture, dict(status='ok', cases=cases, input_sha256=inputs),
                                            inputs, runner=runner)
            self.assertEqual(compared['cases'][0]['failure_kind'], 'tree_load_observation_invalid')
            # Linux byte-exact uses the same bounded vocabulary, independently
            # of the Linux typed-map and Windows main-summary tests above.
            for code in calibration.CODES:
                payload = calibration.diagnostic_output(code)
                (capture / 'collections.out').write_bytes(payload)
                cases[0].update(output_size=len(payload), output_sha256=full.digest(payload))
                result = full.compare_outputs(root, capture,
                    dict(status='ok', cases=cases, input_sha256=inputs), inputs,
                    runner=runner, native_target=full.LINUX_TARGET, comparison_mode=full.BYTE_EXACT)
                self.assertEqual(result['cases'][0]['failure_kind'], 'tree_load_calibration_' + code)
                self.assertEqual(result['cases'][0]['acceptance_status'], 'rejected')


if __name__ == '__main__':
    unittest.main()
