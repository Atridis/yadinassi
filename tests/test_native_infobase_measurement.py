"""Bounded measurement mechanics only; no invented native expectation."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_client_probe as probe
import test_native_1c_full_host as host_fixture
from test_native_1c_full_host import SyntheticFilesystemCase
from test_native_directive_witness import linux_fixture

full, suite, ROOT, NONCE = probe.full, probe.suite, probe.ROOT, probe.NONCE
# Deliberately synthetic, all direct calls failed and no profile bit observed.
# This is legal observation syntax, not a predicted or accepted native result.
SYNTHETIC = 'ibc.v1:' + '010000' * 5
SOURCE = 'integrational_tests/directive_probes/infobase_context_core.bsl'


def marker(phase='completed', **patch):
    result = probe.marker(phase)
    if phase == 'completed':
        result['values'].append(SYNTHETIC)
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

    def test_entered_and_complete_full_prefix_with_independent_observation(self):
        for phase in ('entered', 'completed'):
            self.assertEqual(self.read(marker(phase), phase), marker(phase))
        for slot in ('010000', '130000', '220111', '321122'):
            value = marker(); value['values'][-1] = 'ibc.v1:' + slot * 5
            self.assertEqual(self.read(value), value)
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
    def test_exact_source_core_module_binding_and_tamper_rejection(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
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

    def test_whole_strict136_preflight_reads_exact_restored_bytes(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'candidate.bsl'; path.write_bytes(raw)
            seen = []
            def runner(arguments, cwd):
                restored = Path(arguments[-1]).read_bytes()
                self.assertNotEqual(Path(arguments[-1]), path)
                self.assertEqual(restored, full.infobase_shared_source(raw))
                seen.append(full.digest(restored))
                return 0, json.dumps(full.CLIENT_VALUES, ensure_ascii=False, separators=(',', ':')).encode(), b''
            full.verify_client_interpreter(ROOT, path, full.digest(raw), runner=runner)
            self.assertEqual(seen, [full.INFOBASE_CONTEXT_BASE_SHA256])
            def altered_runner(arguments, cwd):
                Path(arguments[-1]).write_bytes(b'changed')
                return 0, json.dumps(full.CLIENT_VALUES, ensure_ascii=False, separators=(',', ':')).encode(), b''
            with self.assertRaises(full.FullError) as raised:
                full.verify_client_interpreter(ROOT, path, full.digest(raw), runner=altered_runner)
            self.assertEqual(str(raised.exception), 'source_changed')

    def test_plan_is_unmeasured_and_binds_all_source_identities(self):
        plan = json.loads((ROOT / 'integrational_tests/directive_probes/infobase_context_measurement.json').read_text())
        self.assertIsNone(plan['native_expected_token'])
        self.assertEqual(plan['native_execution'], 'pending')
        self.assertEqual(plan['source_sha256'], full.INFOBASE_CONTEXT_SOURCE_SHA256)
        self.assertEqual(plan['module_sha256'], full.INFOBASE_CONTEXT_MODULE_SHA256)
        self.assertEqual(plan['strict136_source_sha256'], full.INFOBASE_CONTEXT_BASE_SHA256)
        self.assertEqual(plan['core_sha256'], full.digest(linux_fixture(ROOT / SOURCE)))
        self.assertEqual(plan['token_bytes'], len(SYNTHETIC))

    @unittest.skipIf(os.name == 'nt', 'native host bounded child is POSIX-only')
    def test_real_interpreter_runs_restored136_without_new_builtin(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        full.verify_client_interpreter(ROOT, ROOT / full.CLIENT_SOURCE, full.digest(raw))
        from yadinassi import Interpreter, BSLError
        with self.assertRaises(BSLError): Interpreter().execute('InfoBaseConnectionString()')

    def test_four_parity_outputs_and_async_literal_identity_unchanged(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        plan = json.loads((ROOT / 'integrational_tests/directive_probes/date_null_measurement.json').read_text())
        for name, expected in plan['four_adapter_sha256'].items():
            scenario = linux_fixture(ROOT / f'integrational_tests/tests/{name}.bsl')
            self.assertEqual(full.digest(getattr(suite, f'client_{name}_module')(scenario, raw)), expected)
        self.assertEqual(full.async_source_identity(linux_fixture(ROOT / 'scripts/native_1c_bootstrap/full_suite.py')),
                         plan['async8_identity'])


class InfobaseFixtureAdapterTests(unittest.TestCase):
    def test_forced_synthetic_adapter_covers_reads_and_restores_exact_reader(self):
        original = full.read_regular
        self.assertIs(full, host_fixture.full)
        self.assertIs(full, probe.smoke.FULL)
        case = InfobaseSourceTests('test_whole_strict136_preflight_reads_exact_restored_bytes')
        with mock.patch.object(host_fixture, '_USE_SYNTHETIC_FILE_READER', True):
            case.setUp()
            try:
                reader = full.read_regular
                self.assertIsNot(reader, original)
                case.test_whole_strict136_preflight_reads_exact_restored_bytes()
                self.assertEqual(reader.call_count, 3)
            finally:
                case.doCleanups()
        self.assertIs(full.read_regular, original)


class InfobaseHarnessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = probe.ClientProbeHarness()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        (f.inputs / suite.CLIENT_TARGET).write_bytes(linux_fixture(ROOT / suite.CLIENT_SOURCE))
        f.hashes = suite.input_hashes(f.inputs, client_probe=True)
        f.platform = replace(f.platform, database=Path('/tmp/onec-smoke/db'))
        def tail(mode):
            if mode == 'enterprise' and 'completed' in f.run_markers:
                path = f.work / 'completed.json'
                value = json.loads(path.read_text()); value['values'].append(SYNTHETIC)
                path.write_bytes(json.dumps(value, separators=(',', ':')).encode())
        self.tail = tail
        f.hook = tail

    def test_positive_route_captures_only_finite_source_bound_token(self):
        f = self.fixture
        record = f.run_probe()
        self.assertEqual(record['status'], 'ok')
        self.assertEqual(record['infobase_context'], SYNTHETIC)
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


class InfobaseLifecycleTests(unittest.TestCase):
    def test_actual_suite_late_input_failure_discards_capture(self):
        fixture = probe.ClientSuiteIntegrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        path = fixture.inputs / suite.CLIENT_TARGET
        path.write_bytes(linux_fixture(ROOT / suite.CLIENT_SOURCE))
        fixture.client.update(source_sha256=full.INFOBASE_CONTEXT_SOURCE_SHA256,
            module_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256,
            roundtrip_sha256=full.INFOBASE_CONTEXT_MODULE_SHA256, infobase_context=SYNTHETIC)
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
                     'client_probe': {'infobase_context': SYNTHETIC, 'witness_verified': True}}
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
                     'client_probe': dict(suite.empty_client_report(), infobase_context=SYNTHETIC), **extras}
            if 'client_async' in stage:
                stage['client_async']['status'] = 'failed'
            suite.fail_client_process_checkpoint(stage, False)
            self.assertNotIn('infobase_context', stage['client_probe'])
            self.assertEqual(stage['status'], 'failed')

    def test_host_failure_discards_capture_without_changing_old_evidence(self):
        report = {'stage3': {'client_probe': {'infobase_context': SYNTHETIC,
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
            infobase_context=SYNTHETIC, **dict.fromkeys(suite.CLIENT_FLAGS, True))
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
