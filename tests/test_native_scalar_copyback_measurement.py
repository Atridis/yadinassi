"""Finite native-only copyback capture; synthetic values are not native fixtures."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture

LABELS = (
    'entered', 'success.error', 'success.value', 'val.error', 'val.value',
    'function.error', 'function.result', 'function.value', 'caught.error',
    'caught.matched', 'caught.value', 'escaped.caught', 'escaped.matched',
    'escaped.value', 'escaped.untouched', 'escaped.val', 'alias.independent.error',
    'alias.independent.second', 'alias.independent.value', 'alias.rightmost.error',
    'alias.rightmost.value', 'alias.unchanged-right.error', 'alias.unchanged-right.value',
    'alias.self-assignment.error', 'alias.self-assignment.value', 'alias.reverted.error',
    'alias.reverted.value', 'timing.error', 'timing.signature', 'timing.value',
    'timing.calls', 'recovery.error', 'recovery.value', 'complete',
)


class ScalarCopybackMeasurementTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start()
            self.addCleanup(patch.stop)

    def diagnostic(self, tokens, **changes):
        marker = dict(schema=1, nonce='a' * 32, phase='completed', witness='client',
                      values=suite.CLIENT_VALUES + ['copyback.core.v1'] + tokens)
        marker.update(changes)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'marker.json'
            path.write_bytes(json.dumps(marker).encode('utf-8'))
            result = suite.client_marker_diagnostics(path, 'a' * 32)
            full.validate_marker_diagnostics(result)
            # Even a well-formed measurement can never become accepted parity.
            with self.assertRaises(suite.FullError):
                suite.client_marker(path, 'a' * 32, 'completed')
        return result

    def test_full_finite_typed_capture_keeps_original_acceptance(self):
        tokens = ['{"U"}', '{"B",0}', '{"B",1}', '{"N",0}', '{"N",999}']
        tokens += ['{"N",43}'] * (34 - len(tokens))
        result = self.diagnostic(tokens)
        self.assertEqual(result, dict(phase='completed', kind='count', ordinal=15,
                                     error_stage=0, copyback=[None, False, True, 0, 999] + [43] * 29))
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual(len(full.CLIENT_VALUES), 15)

    def test_unknown_types_numbers_and_partial_capture_never_export(self):
        for invalid in ('{"S","PRIVATE"}', '{"N",1000}', '{"N",-1}', '{"N",1.0}',
                        '{"N",01}', '{"B",2}', '{"U"}PRIVATE', 'PRIVATE', True, 1, None, []):
            with self.subTest(invalid=invalid):
                result = self.diagnostic([invalid] + ['{"U"}'] * 33)
                self.assertNotIn('copyback', result)
                self.assertNotIn('PRIVATE', str(result))
        for count in (0, 33, 35):
            self.assertNotIn('copyback', self.diagnostic(['{"U"}'] * count))

    def test_nonce_schema_and_phase_guards_precede_measurement(self):
        for change in ({'nonce': 'b' * 32}, {'schema': True}, {'phase': 'error'},
                       {'witness': 'server'}, {'extra': 'PRIVATE'}):
            self.assertNotIn('copyback', self.diagnostic(['{"U"}'] * 34, **change))

    def test_host_rejects_unbounded_or_inconsistent_measurements(self):
        good = dict(phase='completed', kind='count', ordinal=15, error_stage=0, copyback=[None] * 34)
        full.validate_marker_diagnostics(good)
        for records in ([None] * 33, [None] * 35, 'PRIVATE', [1000] * 34,
                        [-1] * 34, [1.0] * 34, ['PRIVATE'] * 34, [{}] * 34):
            with self.subTest(records=records), self.assertRaises(ValueError):
                full.validate_marker_diagnostics({**good, 'copyback': records})
        with self.assertRaises(ValueError):
            full.validate_marker_diagnostics({**good, 'phase': 'error', 'kind': 'none', 'ordinal': -1})

    def test_exact_inverse_restores_audited_shared_source(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        restored = full.client_interpreter_source(raw)
        self.assertEqual(full.digest(restored), 'b98f7cb8e3489fabdd5df6cec8b929b7e059f9931f1fbfedb8d112be53c1f437')
        self.assertNotIn(b'Copyback', restored)
        self.assertEqual(full.digest(suite.client_parity_template(raw)),
                         '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        for changed in (raw + b' ', raw.replace(b'X = 43;', b'X = 44;', 1),
                        raw.replace(full.CLIENT_COPYBACK_CALL, b'', 1)):
            with self.assertRaises(full.FullError):
                full.client_interpreter_source(changed)

    def test_exact_ordered_native_source_has_no_message_capture(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        added = raw.split(full.CLIENT_COPYBACK_MARKER, 1)[1].decode()
        actual = re.findall(r'CopybackRecord\(Records, "([^"]+)"', added)
        standalone = (ROOT / 'integrational_tests/directive_probes/scalar_copyback_core.bsl').read_text(encoding='utf-8')
        self.assertEqual(actual, list(LABELS))
        self.assertEqual(re.findall(r'CopybackRecord\("([^"]+)"', standalone), list(LABELS))
        self.assertNotIn('Message(', added)
        self.assertEqual(added.count('Records.Add("copyback.core.v1")'), 1)
        self.assertEqual(len(LABELS), 34)
        # Native marker budget remains 2048 bytes; no enlarged evidence channel.
        longest = suite.CLIENT_VALUES + ['copyback.core.v1'] + ['{"N",999}'] * 34
        envelope = dict(schema=1, nonce='a'*32, phase='completed', witness='client', values=longest)
        self.assertLess(len(json.dumps(envelope).encode()), 2048)

    def test_exact_stage_serializer_retains_conservative_finite_capture_within_caps(self):
        import copy
        import test_native_client_wire_v3 as wire_fixture
        fixture = wire_fixture.ClientWireV3Tests()
        fixture.setUp()
        stage = copy.deepcopy(fixture.stage)
        stage.update(status='failed', failure_kind='unexpected_failure', failed_case='collections')
        # Conservative serializer envelope, not a fabricated accepted native run.
        for case in stage['cases']:
            case.update(output_size=209715, message_count=32768)
        for key in ('client_dates', 'client_values', 'client_collections', 'client_numbers'):
            stage[key].update(output_size=1048576, message_count=32768)
        for key in suite.CLIENT_WIRE_V3_RECORDS:
            stage[key].update(process_diagnostics=wire_fixture.fixtures.process_diagnostics(
                stage='before_probe', reason='unexpected_processes',
                classes={'native': 100, 'display': 26, 'session_bus': 26, 'shell': 26,
                         'python': 26, 'other': 26, 'unreadable': 26}, zombie_count=256))
        stage['client_probe'].update(status='failed', failure_kind='invalid_result',
            witness_verified=False, marker_diagnostics=dict(phase='completed', kind='count',
                ordinal=15, error_stage=0, copyback=[False] * 34))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'stage3.json'
            suite.write_report(path, stage)
            raw = path.read_bytes()
            self.assertLessEqual(len(raw), 8192)
            self.assertEqual(full.decode_stage3_wire(full.strict_json(raw, 8192)), stage)
            self.assertEqual(suite.decode_stage_wire(json.loads(raw)), stage)
        report = copy.deepcopy(fixture.fixture.envelope['report'])
        report.update(status='stage3_failed', native_tests_completed=False, stage3=stage)
        self.assertLessEqual(len(json.dumps(report, separators=(',', ':'), allow_nan=False).encode()), 32768)
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT),
                         (8192, 8192, 32768))

    def test_current_runtime_still_rejects_nonval_boundary(self):
        from yadinassi import Interpreter
        vm = Interpreter(lambda value: self.fail('unexpected Message'))
        vm.execute((ROOT / full.CLIENT_SOURCE).read_text(encoding='utf-8-sig'))
        values = list(vm.execute('RunScalarCopybackProbe()'))
        self.assertEqual(len(values), 35)
        self.assertEqual(values[0], 'copyback.core.v1')
        self.assertEqual(values[1], '{"B",1}')  # entered
        self.assertEqual(values[2], '{"B",1}')  # non-Val still rejected
        self.assertEqual(values[3], '{"N",1}')  # caller unchanged
        self.assertEqual(values[4], '{"B",0}')  # existing Val path succeeds
        self.assertEqual(values[-1], '{"B",1}')
        self.assertEqual(vm.execution_context, 'client')
