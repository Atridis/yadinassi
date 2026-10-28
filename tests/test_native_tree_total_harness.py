"""Exact historical recovery and real host rejection before semantic equality."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from scripts import native_historical_replay as history
import test_native_async_fixture as fixture_history
import test_native_1c_full_stage as stage
import test_native_1c_full_host as host_fixtures

# Use the very module instance patched by the Windows synthetic-file fixture.
host = host_fixtures.full
from test_native_tree_total_contract import synthetic_output, synthetic_records

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '55bf37f0ac53a5ae2e1a519a190847ddece4df0abcf387179e0fd7ae22bdca5c'
BASE_SHA = 'a0212150d3d5d2a7252971aa8ba509d439ced04e85b5a157ff1148bf3eff4574'


class TotalHarnessTests(unittest.TestCase):
    def source(self):
        value = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(value).hexdigest(), SOURCE_SHA)
        return value

    def test_exact1022_source_and_harness_inverses(self):
        before = history.without_tree_total_probes(self.source().decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(before).hexdigest(), BASE_SHA)
        self.assertEqual(stage.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 1023)
        for path in ('scripts/native_1c_full_host.py', 'scripts/native_1c_bootstrap/full_suite.py'):
            value = (ROOT/path).read_text(encoding='utf-8')
            old = fixture_history.without_tree_total_measurement(value, host=path.endswith('full_host.py'))
            self.assertIn(BASE_SHA, old)
            for changed in (value+'\n', value.replace('\n','\r\n'), value.replace(SOURCE_SHA,'0'*64)):
                with self.assertRaises(AssertionError):
                    fixture_history.without_tree_total_measurement(changed, host=path.endswith('full_host.py'))
        text = self.source().decode('utf-8-sig')
        for changed in (text+'\n', text.replace('\n','\r\n'), text.replace('Rows.иТоГ','Rows.Итог')):
            with self.assertRaises(ValueError):
                history.without_tree_total_probes(changed)

    def test_each_prefix_and_sole_final_total_are_required(self):
        good = synthetic_output()
        self.assertEqual(host.validate_tree_total_observations(good), {'records':1,'message_units':39})
        self.assertEqual(host.validate_tree_move_observations(good), {'records':1,'message_units':199})
        self.assertEqual(host.validate_tree_load_observations(good)['records'],45)
        records = synthetic_records()
        reordered = b''.join(row[1] for row in records[:-2]+records[-2:][::-1])
        for changed in (b''.join(row[1] for row in records[:-1]), good+records[-1][1], reordered,
                        good+b'extra: [ok]\n', good.replace(b'TT: [1E',b'TT: [1!'),good[:-1]):
            with self.assertRaises(host.FullError):
                host.validate_tree_total_observations(changed)
        for label, validator in ((b'TM: [',host.validate_tree_move_observations), (b'TL45: [',host.validate_tree_load_observations)):
            with self.assertRaises(host.FullError):
                validator(good.replace(label,label+b'!',1))


class TotalHostBoundaryTests(host_fixtures.SyntheticFilesystemCase):
    def test_identical_bad_native_and_host_never_reach_semantic_equality(self):
        good = synthetic_output()
        for bad in (good.replace(b'TT: [1E',b'TT: [1!'),good.replace(b'TT: [1E',b'TT: [1T')):
            for native, actual in ((bad,bad),(bad,good),(good,bad)):
                with self.subTest(native_bad=native==bad, actual_bad=actual==bad), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve(); inputs = {}; payload=b'ok\n'
                    for name in host.SCENARIOS:
                        path=root/f'integrational_tests/tests/{name}.bsl';path.parent.mkdir(parents=True,exist_ok=True)
                        source=(ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n',b'\n') if name=='collections' else b'// synthetic\n'
                        path.write_bytes(source);inputs[f'integrational_tests/tests/{name}.bsl']=host.digest(source)
                    outputs=dict.fromkeys(host.SCENARIOS,payload);outputs['collections']=native
                    capture=host.quarantine_outputs(root,outputs)
                    report=host_fixtures.fixture(payload,input_hashes=inputs)[0]['report']['stage3']
                    report['cases'][0].update(output_size=len(native),output_sha256=host.digest(native),message_count=1023)
                    context={'stage3':report,'trusted_input_sha256':inputs}
                    module=host.map_contract()
                    with mock.patch.object(host,'validate_semantic_context'), mock.patch.object(host,'map_contract',return_value=module), \
                            mock.patch.object(module,'compare_collections',side_effect=AssertionError('semantic equality reached')) as equality:
                        result=host.compare_outputs(root,capture,report,inputs,
                            runner=lambda args,cwd:(0,actual if Path(args[-2]).stem=='collections' else payload,b''),
                            native_target=host.LINUX_TARGET,comparison_mode=host.MAP_MODE,runtime_evidence=context)
                    equality.assert_not_called()
                    self.assertEqual(result['cases'][0]['failure_kind'],'tree_total_observation_invalid')
                    self.assertEqual(result['cases'][0]['acceptance_status'],'rejected')
                    self.assertEqual(result['acceptance_status'],'rejected')

    def test_matching_bad_total_cannot_export_as_valid_artifact(self):
        import test_native_1c_output_artifact as artifacts
        good=synthetic_output()
        for payload, valid in ((good,True),(good.replace(b'TT: [1E',b'TT: [1!'),False),
                               (good.replace(b'TT: [1E',b'TT: [1T'),False)):
            report=artifacts.accepted_report()
            key='integrational_tests/tests/collections.bsl'
            report['stage3']['input_sha256'][key]=host.COLLECTIONS_SOURCE_SHA256
            report['trusted_input_sha256'][key]=host.COLLECTIONS_SOURCE_SHA256
            report['stage3']['cases'][0].update(source_sha256=host.COLLECTIONS_SOURCE_SHA256,
                output_sha256=host.digest(payload),output_size=len(payload),message_count=1023)
            report['comparison']['cases'][0].update(native_sha256=host.digest(payload),native_size=len(payload),
                interpreter_sha256=host.digest(payload),interpreter_size=len(payload))
            payloads=dict.fromkeys(host.ARTIFACT_FILES[:-1],artifacts.PAYLOAD);payloads['collections.out']=payload
            if valid:
                self.assertEqual(host.output_artifact_files(payloads,report,artifacts.smoke.IMAGE)['collections.out'],payload)
            else:
                with self.assertRaisesRegex(host.FullError,'^native_artifact_evidence_invalid$'):
                    host.output_artifact_files(payloads,report,artifacts.smoke.IMAGE)


class TotalWindowsFixtureWiringTests(unittest.TestCase):
    def test_host_module_identity_and_windows_reader_coverage(self):
        self.assertIs(host, host_fixtures.full)
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(host_fixtures, '_USE_SYNTHETIC_FILE_READER', True), \
                mock.patch.object(host_fixtures, 'read_synthetic_file', wraps=host_fixtures.read_synthetic_file) as reader:
            path = Path(directory).resolve()/'fixture.bin'
            path.write_bytes(b'bounded synthetic fixture')
            case = host_fixtures.SyntheticFilesystemCase()
            case.setUp()
            try:
                self.assertEqual(host.read_regular(path, 64, nonempty=True), b'bounded synthetic fixture')
                reader.assert_called_once_with(path, 64, nonempty=True)
            finally:
                case.doCleanups()
