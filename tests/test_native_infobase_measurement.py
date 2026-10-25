"""Historical measurement grammar and current captured strict137 admission."""
import copy
from dataclasses import replace
import json
import importlib.util
import py_compile
import os
import sys
from pathlib import Path
import tempfile
import unittest
from test_native_async_fixture import historical_tree_collections_module, historical_uuid_values_module
from unittest import mock

import test_native_client_probe as probe
import test_native_1c_full_host as host_fixture
from test_native_1c_full_host import SyntheticFilesystemCase
from test_native_directive_witness import linux_fixture, historical_client137
from infobase_preflight_test_support import offline_fixture

full, suite, ROOT, NONCE = probe.full, probe.suite, probe.ROOT, probe.NONCE
# Deliberately synthetic, all direct calls failed and no profile bit observed.
# This is legal observation syntax, not a predicted or accepted native result.
SYNTHETIC = 'ibc.v1:' + '010000' * 5
CAPTURED = full.INFOBASE_CONTEXT_EXPECTED_TOKEN
SOURCE = 'integrational_tests/directive_probes/infobase_context_core.bsl'


def marker(phase='completed', **patch):
    result = probe.marker(phase)
    if phase == 'completed':
        result['values'].append(CAPTURED)
    result.update(patch)
    return result


class InfobaseMarkerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name).resolve() / 'marker.json'
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes',
                                      new=probe.stage_fixture.portable_fixture_bytes)
            patch.start(); self.addCleanup(patch.stop)

    def read(self, value, phase='completed', source_hash=None):
        self.path.write_bytes(json.dumps(value, separators=(',', ':'),
                                        ensure_ascii=False).encode())
        return suite.infobase_client_marker(self.path, NONCE, phase,
            source_hash=suite.INFOBASE_CONTEXT_SOURCE_SHA256 if source_hash is None else source_hash)

    def test_entered_and_complete_full_prefix_require_captured_observation(self):
        for phase in ('entered', 'completed'):
            self.assertEqual(self.read(marker(phase), phase), marker(phase))
        for slot in ('010000', '130000', '220111', '321122'):
            value = marker(); value['values'][-1] = 'ibc.v1:' + slot * 5
            with self.assertRaises(suite.FullError): self.read(value)
        self.assertLessEqual(self.path.stat().st_size, 2048)
        with self.assertRaises(suite.FullError):
            suite.client_marker(self.path, NONCE, 'completed')

    def test_every_historical_value_and_type_remains_strict(self):
        for index, expected in enumerate(suite.CLIENT_VALUES):
            value = marker(); value['values'][index] = None
            with self.subTest(index=index), self.assertRaises(suite.FullError):
                self.read(value)
            if type(expected) is int:
                value['values'][index] = float(expected)
                with self.assertRaises(suite.FullError): self.read(value)
        for values in (suite.CLIENT_VALUES, suite.CLIENT_VALUES + [SYNTHETIC, SYNTHETIC], []):
            with self.assertRaises(suite.FullError): self.read(marker(values=values))

    def test_token_source_nonce_phase_witness_and_type_fail_closed(self):
        for token in (None, True, 37, '', SYNTHETIC + ' ', SYNTHETIC[:-1],
                      SYNTHETIC.replace('0', '０', 1), 'ibc.v1:' + '110001' * 5,
                      'ibc.v1:' + '320100' * 5, 'ibc.v1:' + '430000' * 5):
            value = marker(); value['values'][-1] = token
            with self.subTest(token=token), self.assertRaises(suite.FullError): self.read(value)
        for patch in ({'nonce': '0' * 32}, {'phase': 'error'}, {'witness': 'server'},
                      {'schema': True}, {'extra': 'PRIVATE'}):
            with self.assertRaises(suite.FullError): self.read(marker(**patch))
        for source in ('0' * 64, suite.INFOBASE_CONTEXT_BASE_SHA256, None):
            with self.assertRaises(suite.FullError):
                suite.infobase_client_marker(self.path, NONCE, 'completed', source_hash=source)

    def test_existing_reader_limits_duplicate_keys_and_nonfinite_guards(self):
        raw = json.dumps(marker(), separators=(',', ':')).encode()
        for value in (b' ' * 2049, raw + b' PRIVATE', raw.replace(b'"schema":1', b'"schema":1,"schema":1'),
                      raw.replace(b'42,', b'NaN,'), b'[' * 20 + b']' * 20):
            self.path.write_bytes(value)
            with self.assertRaises(suite.FullError):
                suite.infobase_client_marker(self.path, NONCE, 'completed',
                    source_hash=suite.INFOBASE_CONTEXT_SOURCE_SHA256)


class InfobaseSourceTests(SyntheticFilesystemCase):
    def test_historical_source_core_module_binding_and_tamper_rejection(self):
        raw = historical_client137()
        core = linux_fixture(ROOT / SOURCE)
        self.assertEqual(full.digest(raw), full.INFOBASE_CONTEXT_SOURCE_SHA256)
        self.assertEqual(full.digest(full.generated_module(raw)), full.INFOBASE_CONTEXT_MODULE_SHA256)
        self.assertEqual(core, full.INFOBASE_CONTEXT_CORE)
        self.assertEqual(core, suite.INFOBASE_CONTEXT_CORE)
        baseline = full.infobase_shared_source(raw)
        self.assertEqual(suite.infobase_shared_source(raw), baseline)
        self.assertEqual(full.digest(baseline), full.INFOBASE_CONTEXT_BASE_SHA256)
        self.assertIn(b'Var Shape, Aliases, EnglishArity, RussianArity, IBCArityTemporary;', core)
        self.assertEqual(core.count(b'EnglishValue = InfoBaseConnectionString();'), 4)
        self.assertIn(b'// Arity runs in this dual no-context observer', core)
        for changed in (raw + b'\n', raw[:-1], raw.replace(full.INFOBASE_CONTEXT_CALL, b'', 1),
                        raw.replace(core, core + core, 1), raw.replace(b'ContextServerCounter = 100;', b'ContextServerCounter = 101;')):
            with self.assertRaises(full.FullError): full.infobase_shared_source(changed)
            with self.assertRaises(suite.FullError): suite.infobase_shared_source(changed)

    def test_whole138_preflight_reads_original_source_bytes(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        with tempfile.TemporaryDirectory() as folder, offline_fixture(full):
            path = Path(folder).resolve() / 'candidate.bsl'; path.write_bytes(raw)
            seen = []
            def runner(arguments, cwd):
                self.assertEqual(Path(arguments[-2]), path)
                self.assertEqual(arguments[-1], str(Path('/tmp/onec-smoke/db')))
                self.assertEqual(path.read_bytes(), raw)
                seen.append(full.digest(path.read_bytes()))
                return 0, json.dumps(full.CLIENT_RUNTIME_VALUES + [full.PREPROCESSOR_DEFAULT_TOKEN], ensure_ascii=False,
                                     separators=(',', ':')).encode(), b''
            full.verify_client_interpreter(ROOT, path, full.digest(raw), runner=runner, preprocessor_measurement=True)
            self.assertEqual(seen, [full.PREPROCESSOR_SOURCE_SHA256])
            def altered_runner(arguments, cwd):
                Path(arguments[-2]).write_bytes(b'changed')
                return 0, json.dumps(full.CLIENT_RUNTIME_VALUES + [full.PREPROCESSOR_DEFAULT_TOKEN], ensure_ascii=False,
                                     separators=(',', ':')).encode(), b''
            with self.assertRaises(full.FullError) as raised:
                full.verify_client_interpreter(ROOT, path, full.digest(raw), runner=altered_runner, preprocessor_measurement=True)
            self.assertEqual(str(raised.exception), 'source_changed')

    def test_plan_is_unmeasured_and_binds_all_source_identities(self):
        plan = json.loads((ROOT / 'integrational_tests/directive_probes/infobase_context_measurement.json').read_text(encoding='utf-8'))
        self.assertIsNone(plan['native_expected_token'])
        self.assertEqual(plan['native_execution'], 'pending')
        self.assertEqual(plan['source_sha256'], full.INFOBASE_CONTEXT_SOURCE_SHA256)
        self.assertEqual(plan['module_sha256'], full.INFOBASE_CONTEXT_MODULE_SHA256)
        self.assertEqual(plan['strict136_source_sha256'], full.INFOBASE_CONTEXT_BASE_SHA256)
        self.assertEqual(plan['core_sha256'], full.digest(linux_fixture(ROOT / SOURCE)))
        self.assertEqual(plan['token_bytes'], len(SYNTHETIC))

    @unittest.skipUnless(sys.platform == 'linux', 'fixed native fixture is Linux-only')
    def test_real_interpreter_runs_original_whole138_with_real_context(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        full.verify_client_interpreter(ROOT, ROOT / full.CLIENT_SOURCE, full.digest(raw), preprocessor_measurement=True)
        from yadinassi import Interpreter, BSLError
        with self.assertRaises(BSLError): Interpreter().execute('InfoBaseConnectionString()')

    def test_four_parity_outputs_and_async_literal_identity_unchanged(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        plan = json.loads((ROOT / 'integrational_tests/directive_probes/date_null_measurement.json').read_text(encoding='utf-8'))
        for name, expected in plan['four_adapter_sha256'].items():
            scenario = linux_fixture(ROOT / f'integrational_tests/tests/{name}.bsl')
            adapter = historical_tree_collections_module if name == 'collections' else historical_uuid_values_module if name == 'values' else getattr(suite, f'client_{name}_module')
            self.assertEqual(full.digest(adapter(scenario, raw)), expected)
        self.assertEqual(full.async_source_identity(linux_fixture(ROOT / 'scripts/native_1c_bootstrap/full_suite.py')),
                         plan['async8_identity'])


class InfobaseFixtureAdapterTests(unittest.TestCase):
    def test_forced_synthetic_adapter_covers_reads_and_restores_exact_reader(self):
        original = full.read_regular
        self.assertIs(full, host_fixture.full)
        self.assertIs(full, probe.smoke.FULL)
        case = InfobaseSourceTests('test_whole138_preflight_reads_original_source_bytes')
        with mock.patch.object(host_fixture, '_USE_SYNTHETIC_FILE_READER', True):
            case.setUp()
            try:
                reader = full.read_regular
                self.assertIsNot(reader, original)
                case.test_whole138_preflight_reads_original_source_bytes()
                self.assertEqual(reader.call_count, 4)
            finally:
                case.doCleanups()
        self.assertIs(full.read_regular, original)


class InfobaseHarnessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = probe.ClientProbeHarness()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        (f.inputs / suite.CLIENT_TARGET).write_bytes(historical_client137())
        f.hashes = suite.input_hashes(f.inputs, client_probe=True)
        f.platform = replace(f.platform, database=Path('/tmp/onec-smoke/db'))
        def tail(mode):
            if mode == 'enterprise' and 'completed' in f.run_markers:
                path = f.work / 'completed.json'
                value = json.loads(path.read_text(encoding='utf-8')); value['values'].append(CAPTURED)
                path.write_bytes(json.dumps(value, separators=(',', ':')).encode())
        self.tail = tail
        f.hook = tail

    def test_positive_route_captures_only_finite_source_bound_token(self):
        f = self.fixture
        record = f.run_probe()
        self.assertEqual(record['status'], 'ok')
        self.assertEqual(record['infobase_context'], CAPTURED)
        full.validate_client_probe(record, full.INFOBASE_CONTEXT_SOURCE_SHA256,
                                  full.INFOBASE_CONTEXT_MODULE_SHA256, infobase_allowed=True)
        self.assertEqual(f.events, ['build', 'dump', 'enterprise'])
        self.assertNotIn('/tmp/onec-smoke/db', json.dumps(record))
        self.assertNotIn(str(f.work), json.dumps(record))

    def test_actual_database_path_must_match_internal_candidate_directory(self):
        f = self.fixture
        f.platform = replace(f.platform, database=f.root / 'different')
        record = f.run_probe()
        self.assertEqual(record['failure_kind'], 'invalid_input')
        self.assertEqual(f.events, [])
        self.assertNotIn('infobase_context', record)

    def test_late_source_change_and_failed_exit_never_retain_capture(self):
        f = self.fixture
        def changed(mode):
            self.tail(mode)
            if mode == 'enterprise':
                path = f.work / 'src' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes() + b'\n')
        f.hook = changed
        record = f.run_probe()
        self.assertEqual(record['failure_kind'], 'module_mismatch')
        self.assertNotIn('infobase_context', record)
        f.reset(); f.hook = self.tail; f.run_error = 'timeout'
        record = f.run_probe()
        self.assertEqual(record['failure_kind'], 'timeout')
        self.assertNotIn('infobase_context', record)

    def test_missing_or_changed_tail_is_not_valid_historical_success(self):
        f = self.fixture
        f.hook = None
        record = f.run_probe()
        self.assertEqual(record['failure_kind'], 'invalid_result')
        self.assertNotIn('infobase_context', record)
        self.assertNotIn(SYNTHETIC, json.dumps(record.get('marker_diagnostics')))
        self.assertEqual(record['marker_diagnostics']['kind'], 'count')
        self.assertEqual(record['marker_diagnostics']['ordinal'], 136)


class InfobaseLifecycleTests(unittest.TestCase):
    def test_actual_suite_late_input_failure_discards_capture(self):
        fixture = probe.ClientSuiteIntegrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        path = fixture.inputs / suite.CLIENT_TARGET
        path.write_bytes(historical_client137())
        fixture.client.update(source_sha256=full.INFOBASE_CONTEXT_SOURCE_SHA256,
            module_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
            roundtrip_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256, infobase_context=CAPTURED)
        def captured(*args, **kwargs):
            path.write_bytes(path.read_bytes() + b'\n')
            return fixture.client
        with mock.patch.object(suite, 'run_client_probe', side_effect=captured):
            result = fixture.run_suite()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure_kind'], 'invalid_input')
        self.assertNotIn('infobase_context', result['client_probe'])
        self.assertTrue(result['client_probe']['witness_verified'])

    def test_actual_envelope_failure_discards_capture_and_all_outputs(self):
        for quiet in (False, True):
            stage = {'schema': 1, 'status': 'ok', 'nonce': NONCE, 'cases': [],
                     'client_probe': {'infobase_context': CAPTURED, 'witness_verified': True}}
            report = {'status': 'ok', 'stage3': stage, 'native_tests_completed': True}
            with tempfile.TemporaryDirectory() as folder:
                envelope = json.loads(suite.build_envelope(report, NONCE, Path(folder), quiet=quiet))
            self.assertEqual(envelope['outputs'], [])
            self.assertEqual(stage['status'], 'failed')
            self.assertNotIn('infobase_context', stage['client_probe'])
            self.assertTrue(stage['client_probe']['witness_verified'])

    def test_final_checkpoint_discards_capture_when_another_lane_is_last(self):
        for extras in ({}, {'client_dates': suite.empty_dates_report()},
                       {'client_async': suite.empty_async_report()}):
            stage = {'status': 'ok', 'failure_kind': 'none',
                     'client_probe': dict(suite.empty_client_report(), infobase_context=CAPTURED), **extras}
            if 'client_async' in stage:
                stage['client_async']['status'] = 'failed'
            suite.fail_client_process_checkpoint(stage, False)
            self.assertNotIn('infobase_context', stage['client_probe'])
            self.assertEqual(stage['status'], 'failed')

    def test_host_failure_discards_capture_without_changing_old_evidence(self):
        report = {'stage3': {'client_probe': {'infobase_context': CAPTURED,
                                             'witness_verified': True, 'source_sha256': 'f' * 64}}}
        error = probe.smoke.SmokeError('container_cleanup_unverified', validated_report=report)
        self.assertNotIn('infobase_context', error.validated_report['stage3']['client_probe'])
        self.assertTrue(report['stage3']['client_probe']['witness_verified'])
        self.assertEqual(report['stage3']['client_probe']['source_sha256'], 'f' * 64)
        full.discard_infobase_capture(report)
        full.discard_infobase_capture(None)

    def test_capture_rejected_for_wrong_source_module_other_record_or_incomplete_proof(self):
        record = dict(status='ok', failure_kind='none', process_diagnostics=probe.process_diagnostics(),
            source_sha256=full.INFOBASE_CONTEXT_SOURCE_SHA256,
            module_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
            roundtrip_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
            infobase_context=CAPTURED, **dict.fromkeys(suite.CLIENT_FLAGS, True))
        for source, module, allowed in ((record['source_sha256'], record['module_sha256'], False),
                                        ('0' * 64, record['module_sha256'], True),
                                        (record['source_sha256'], '0' * 64, True)):
            with self.assertRaises(ValueError):
                full.validate_client_probe(record, source, module, infobase_allowed=allowed)
        for key in (*suite.CLIENT_FLAGS, 'roundtrip_sha256', 'status'):
            bad = copy.deepcopy(record)
            bad[key] = False if key in suite.CLIENT_FLAGS else ('failed' if key == 'status' else None)
            with self.assertRaises(ValueError):
                full.validate_client_probe(bad, record['source_sha256'], record['module_sha256'], infobase_allowed=True)


class InfobaseCapturedContractTests(unittest.TestCase):
    def test_capture_binds_literal_tokens_and_current_contract(self):
        capture = json.loads((ROOT / 'integrational_tests/directive_probes/infobase_context_native.json').read_text(encoding='utf-8'))
        self.assertEqual(capture['native_run'], 40137786320)
        self.assertEqual(capture['expected_token'], CAPTURED)
        self.assertEqual(CAPTURED, suite.INFOBASE_CONTEXT_EXPECTED_TOKEN)
        self.assertEqual(full.CLIENT_RUNTIME_VALUES, full.CLIENT_VALUES + [CAPTURED])
        self.assertEqual(suite.CLIENT_RUNTIME_VALUES, full.CLIENT_RUNTIME_VALUES)
        self.assertEqual(len(full.CLIENT_RUNTIME_VALUES), 137)
        self.assertEqual(capture['source_sha256'], full.INFOBASE_CONTEXT_SOURCE_SHA256)
        self.assertEqual(capture['module_sha256'], full.INFOBASE_CONTEXT_MODULE_SHA256)

    def test_legal_observation_is_not_a_runtime_expectation(self):
        record = dict(status='ok', failure_kind='none', process_diagnostics=probe.process_diagnostics(),
            source_sha256=full.INFOBASE_CONTEXT_SOURCE_SHA256,
            module_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
            roundtrip_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
            infobase_context=SYNTHETIC, **dict.fromkeys(suite.CLIENT_FLAGS, True))
        self.assertEqual(full.validate_infobase_context(SYNTHETIC), SYNTHETIC)
        with self.assertRaises(ValueError):
            full.validate_client_probe(record, full.INFOBASE_CONTEXT_SOURCE_SHA256,
                full.INFOBASE_CONTEXT_MODULE_SHA256, infobase_allowed=True)


class InfobaseHelperSourceTests(SyntheticFilesystemCase):
    def test_valid_timestamp_bytecode_cannot_replace_verified_helper_source(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            helper = directory / 'native_infobase_fixture.py'
            clean, poison = b'VALUE = "CLEAN"\n', b'VALUE = "EVIL!"\n'
            self.assertEqual(len(clean), len(poison))
            helper.write_bytes(poison)
            before = helper.stat()
            py_compile.compile(str(helper), doraise=True)
            helper.write_bytes(clean)
            os.utime(helper, ns=(before.st_atime_ns, before.st_mtime_ns))
            # Demonstrate that ordinary loader cache selection would be poisoned.
            spec = importlib.util.spec_from_file_location('ordinary_helper', helper)
            cached = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cached)
            self.assertEqual(cached.VALUE, 'EVIL!')
            with mock.patch.object(full, '__file__', str(directory / 'native_1c_full_host.py')):
                source_only = full._load_infobase_fixture()
            self.assertEqual(source_only.VALUE, 'CLEAN')
