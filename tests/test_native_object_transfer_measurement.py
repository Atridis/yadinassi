"""Bounded native-only object capture; synthetic records are not native evidence."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture

SOURCE = 'integrational_tests/directive_probes/object_transfer_core.bsl'


def labels():
    return re.findall(r'ObjectTransferRecord\("([^"]+)"',
                      (ROOT / SOURCE).read_text(encoding='utf-8'))


def encode_observation(value):
    return 'U' if value is None else value


class ObjectTransferMeasurementTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start()
            self.addCleanup(patch.stop)

    def marker(self, values, **changes):
        return dict(schema=1, nonce='a' * 32, phase='completed', witness='client',
                    values=values, **changes)

    def observations(self, values=None):
        if values is None:
            values = [None, False, True, 0, 999, 1] * 8
        return suite.CLIENT_VALUES + ['object.transfer.v1'] + [encode_observation(x) for x in values]

    def test_capture_is_finite_and_does_not_grant_native_acceptance(self):
        records = [None, False, True, 0, 999, 1] * 8
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'completed.json'
            path.write_bytes(json.dumps(self.marker(self.observations(records))).encode())
            with self.assertRaises(suite.FullError):
                suite.client_marker(path, 'a' * 32, 'completed')
            actual = suite.client_marker_diagnostics(path, 'a' * 32)
            self.assertEqual(actual, dict(phase='completed', kind='count', ordinal=50,
                                         error_stage=0, object_transfer=records))
            self.assertEqual(full.validate_marker_diagnostics(actual), actual)
            self.assertEqual(len(suite.CLIENT_VALUES), 50)
            self.assertEqual(suite.CLIENT_VALUES, full.CLIENT_VALUES)

    def test_malformed_or_nonmatching_baseline_never_exports_observations(self):
        values = self.observations()
        cases = [values[:-1], values + [1], values[:50] + ['wrong'] + values[51:]]
        for index in (0, 4, 15, 49):
            changed = values.copy(); changed[index] = 'PRIVATE'; cases.append(changed)
        for bad in ('PRIVATE', '1', '{"N",1}', 1000, -1, 1.5, None, {}, []):
            changed = values.copy(); changed[70] = bad; cases.append(changed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'completed.json'
            for data in [self.marker(x) for x in cases] + [
                    {**self.marker(values), 'nonce': 'b' * 32},
                    {**self.marker(values), 'phase': 'error'},
                    {**self.marker(values), 'extra': 'PRIVATE'},
                    {**self.marker(values), 'witness': 'PRIVATE'}]:
                path.write_bytes(json.dumps(data).encode())
                self.assertNotIn('object_transfer', suite.client_marker_diagnostics(path, 'a' * 32))
            path.write_bytes(b'x' * 2049)
            self.assertNotIn('object_transfer', suite.client_marker_diagnostics(path, 'a' * 32))

    def test_host_accepts_only_bounded_failed_count_metadata(self):
        valid = dict(phase='completed', kind='count', ordinal=50, error_stage=0,
                     object_transfer=[None] * 48)
        for changes in ({'phase': 'error'}, {'kind': 'value'}, {'ordinal': 49},
                        {'error_stage': 1}, {'object_transfer': [None] * 47},
                        {'object_transfer': [None] * 49}, {'object_transfer': 'PRIVATE'},
                        {'object_transfer': [1.0] * 48}, {'object_transfer': [1000] * 48},
                        {'object_transfer': [-1] * 48}, {'object_transfer': ['PRIVATE'] * 48}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                full.validate_marker_diagnostics({**valid, **changes})
        self.assertEqual(full.validate_marker_diagnostics(valid), valid)

    def test_exact_mechanical_adapter_and_shared_inverse(self):
        standalone = (ROOT / SOURCE).read_text(encoding='utf-8')
        expected = standalone[standalone.index('&At'):]
        expected = expected.replace('Procedure ObjectTransferRecord(Val Label, Val Value)',
            'Procedure ObjectTransferRecord(Records, Val Label, Val Value)').replace(
            'Message("object.transfer.core." + Label + ": " + ValueToStringInternal(Value));',
            'If Value = Undefined Then\n        Records.Add("U");\n    Else\n        Records.Add(Value);\n    EndIf;').replace(
            'Procedure RunObjectTransferProbe() Export', 'Function RunObjectTransferProbe()').replace(
            '    ObjectTransferRecord("entered", True);',
            '    Records = New Array;\n    Records.Add("object.transfer.v1");\n    ObjectTransferRecord("entered", True);').replace(
            '    ObjectTransferRecord("', '    ObjectTransferRecord(Records, "')
        self.assertTrue(expected.endswith('EndProcedure\n'))
        expected = expected[:-len('EndProcedure\n')] + '    Return Records;\nEndFunction\n'
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        actual = raw.split(full.CLIENT_OBJECT_MARKER, 1)[1].decode()
        self.assertEqual(actual, expected)
        self.assertEqual(len(labels()), 48)
        self.assertEqual(len(set(labels())), 48)
        self.assertEqual(re.findall(r'ObjectTransferRecord\(Records, "([^"]+)"', actual), labels())
        self.assertNotIn('Message(', actual)
        shared = full.client_interpreter_source(raw)
        self.assertEqual(full.digest(shared),
            '52d3dcb83a911f7219893b3705f77d2652e31557ebdfeabaf4384813d3cca07c')
        self.assertEqual(full.digest(suite.client_parity_template(raw)),
            '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        for changed in (raw + b' ', raw[:-1], raw.replace(b'P.N = 11;', b'P.N = 12;')):
            with self.assertRaises(full.FullError):
                full.client_interpreter_source(changed)

    def test_current_interpreter_rejects_objects_and_records_are_not_expected_native_values(self):
        from yadinassi import Interpreter
        messages = []
        vm = Interpreter(messages.append)
        vm.execute((ROOT / SOURCE).read_text(encoding='utf-8'))
        self.assertEqual(messages, [])
        vm.execute('RunObjectTransferProbe()')
        self.assertEqual(len(messages), 48)
        by_label = dict(zip(labels(), messages))
        for label in labels():
            if label.endswith('.error'):
                self.assertTrue(by_label[label].endswith('{"B",1}'), label)
        self.assertTrue(messages[0].endswith('{"B",1}'))
        self.assertTrue(messages[-1].endswith('{"B",1}'))
        self.assertEqual(vm.execution_context, 'client')
        integrated = Interpreter(lambda _: self.fail('unexpected dialog'))
        integrated.execute((ROOT / full.CLIENT_SOURCE).read_text(encoding='utf-8-sig'))
        values = list(integrated.execute('RunObjectTransferProbe()'))
        self.assertEqual(values[0], 'object.transfer.v1')
        actual_tokens = []
        for value in values[1:]:
            if value == 'U':
                actual_tokens.append('{"U"}')
            elif type(value) is bool:
                actual_tokens.append('{"B",' + str(int(value)) + '}')
            else:
                actual_tokens.append('{"N",' + str(value) + '}')
        self.assertEqual(actual_tokens, [line.split(': ', 1)[1] for line in messages])

    def test_private_marker_budget_does_not_require_larger_caps(self):
        # Maximum permitted token length, independent of expected native values.
        marker = self.marker(self.observations([False] * 48))
        self.assertLess(len(json.dumps(marker, separators=(',', ':')).encode()), 2048)
        self.assertLess(len(json.dumps(marker).encode()), 2048)
        self.assertLess(len(json.dumps(marker, indent=2).encode()), 2048)
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT),
                         (8192, 8192, 32768))

    def test_measurement_failure_never_reaches_later_client_records(self):
        import test_native_client_probe as fixture_module
        fixture = fixture_module.ClientSuiteIntegrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        failed = {**fixture.client, 'status': 'failed', 'failure_kind': 'invalid_result',
                  'completed': False, 'witness_verified': False,
                  'marker_diagnostics': dict(phase='completed', kind='count', ordinal=50,
                                            error_stage=0, object_transfer=[False] * 48)}
        with mock.patch.object(suite, 'run_client_probe', return_value=failed) as probe, \
                mock.patch.object(suite, 'run_client_watchdog') as watchdog:
            result = suite.run_suite(fixture.launcher, fixture.platform, fixture.epf,
                fixture.work, fixture.inputs, fixture_module.NONCE, client_probe=True,
                watchdog_check=True, client_dates=True, client_values=True,
                client_collections=True, client_numbers=True)
        probe.assert_called_once()
        watchdog.assert_not_called()
        self.assertEqual(result['failure_kind'], 'invalid_result')
        self.assertEqual(result['client_probe'], failed)
        for name in ('dates', 'values', 'collections', 'numbers', 'watchdog'):
            self.assertEqual(result['client_' + name], getattr(suite, 'empty_' + name + '_report')())

    def test_exact_serializer_bounds_reachable_measurement_failure(self):
        import test_native_client_wire_v3 as wire_fixture
        fixture = wire_fixture.ClientWireV3Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        stage = copy.deepcopy(fixture.stage)
        stage.update(status='failed', failure_kind='invalid_result', failed_case=None)
        # Ordinary-client rejection precedes every optional client. Their hashes,
        # outputs and diagnostics cannot coexist with this capture in a real run.
        for name in ('dates', 'values', 'collections', 'numbers', 'watchdog'):
            stage['client_' + name] = getattr(suite, 'empty_' + name + '_report')()
        for case in stage['cases']:
            case.update(output_size=209715, message_count=32768)
        stage['client_probe'].update(status='failed', failure_kind='invalid_result',
            completed=False, witness_verified=False,
            marker_diagnostics=dict(phase='completed', kind='count', ordinal=50,
                error_stage=0, object_transfer=[False] * 48),
            process_diagnostics=wire_fixture.fixtures.process_diagnostics(
                stage='after_exit', reason='unexpected_processes',
                classes={'native': 100, 'display': 26, 'session_bus': 26, 'shell': 26,
                         'python': 26, 'other': 26, 'unreadable': 26}, zombie_count=256))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'stage3.json'
            suite.write_report(path, stage)
            raw = path.read_bytes()
            self.assertEqual(len(raw), 7072)
            self.assertLessEqual(len(raw), 8192)
            self.assertEqual(full.decode_stage3_wire(full.strict_json(raw, 8192)), stage)
            self.assertEqual(suite.decode_stage_wire(json.loads(raw)), stage)
        report = copy.deepcopy(fixture.fixture.envelope['report'])
        report.update(status='stage3_failed', native_tests_completed=False, stage3=stage)
        self.assertLessEqual(len(json.dumps(report, indent=2, sort_keys=True).encode()), 32768)
