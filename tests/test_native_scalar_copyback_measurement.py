"""Audited scalar-copyback capture provenance and strict whole-source parity."""
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


def capture():
    return json.loads((ROOT / 'integrational_tests/directive_probes/scalar_copyback_core.native.json').read_text(encoding='utf-8'))


def token(value):
    if value is None:
        return '{"U"}'
    if type(value) is bool:
        return '{"B",' + str(int(value)) + '}'
    return '{"N",' + str(value) + '}'


class ScalarCopybackParityTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start()
            self.addCleanup(patch.stop)

    def test_contract_is_bound_to_independently_audited_native_capture(self):
        data = capture()
        self.assertEqual(data['target']['platform_version'], '8.3.27.1508')
        self.assertEqual(data['capture']['run_id'], 39944524944)
        self.assertEqual(data['capture']['summary_zip_sha256'],
            'b5cc52786344468500083531e1a14daaf3415c0826fc58b402bdb5eaf92a606c')
        self.assertEqual(data['capture']['acceptance'], 'rejected_measurement_only')
        self.assertEqual([entry['label'] for entry in data['observations']], list(LABELS))
        expected = ['copyback.core.v1'] + [token(entry['value']) for entry in data['observations']]
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual(full.CLIENT_VALUES[15:50], expected)
        self.assertEqual(len(full.CLIENT_VALUES), 136)
        self.assertEqual(full.CLIENT_VALUES[135:], ['dn.v1:22222277'])
        # Historical scalar capture identity; the whole current source additionally
        # contains the separately captured object operations.
        self.assertEqual(data['capture']['source_sha256'],
                         "52d3dcb83a911f7219893b3705f77d2652e31557ebdfeabaf4384813d3cca07c")

    def test_exact_whole_source_computes_all_captured_values(self):
        from yadinassi import Interpreter
        vm = Interpreter(lambda value: self.fail('unexpected Message'))
        vm.execute(linux_fixture(ROOT / full.CLIENT_SOURCE).decode('utf-8-sig'))
        actual = list(vm.execute('ВычислитьПробу()'))
        self.assertEqual(actual, suite.CLIENT_VALUES)
        self.assertEqual(vm.execution_context, 'client')

    def test_standalone_source_computes_same_captured_records(self):
        from yadinassi import Interpreter
        messages = []
        vm = Interpreter(messages.append)
        vm.execute((ROOT / 'integrational_tests/directive_probes/scalar_copyback_core.bsl').read_text(encoding='utf-8'))
        self.assertEqual(messages, [])
        vm.execute('RunScalarCopybackProbe()')
        expected = ['copyback.core.' + entry['label'] + ': ' + token(entry['value'])
                    for entry in capture()['observations']]
        self.assertEqual(messages, expected)

    def test_native_marker_accepts_only_complete_typed_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'marker.json'
            marker = dict(schema=1, nonce='a' * 32, phase='completed', witness='client',
                          values=suite.CLIENT_VALUES)
            path.write_bytes(json.dumps(marker, separators=(',', ':')).encode())
            self.assertEqual(suite.client_marker(path, 'a' * 32, 'completed'), marker)
            self.assertLess(len(path.read_bytes()), 2048)
            for index in range(15, 50):
                values = list(suite.CLIENT_VALUES)
                values[index] = 'PRIVATE'
                path.write_bytes(json.dumps({**marker, 'values': values}, separators=(',', ':')).encode())
                with self.assertRaises(suite.FullError):
                    suite.client_marker(path, 'a' * 32, 'completed')
                diagnostic = suite.client_marker_diagnostics(path, 'a' * 32)
                self.assertEqual(diagnostic, dict(phase='completed', kind='value',
                                                 ordinal=index, error_stage=0))
                self.assertNotIn('PRIVATE', str(diagnostic))
                self.assertNotIn('copyback', diagnostic)
            for values in (suite.CLIENT_VALUES[:15], suite.CLIENT_VALUES[:-1], suite.CLIENT_VALUES + [True]):
                path.write_bytes(json.dumps({**marker, 'values': values}, separators=(',', ':')).encode())
                with self.assertRaises(suite.FullError):
                    suite.client_marker(path, 'a' * 32, 'completed')

    def test_measurement_only_diagnostic_extension_is_removed(self):
        with self.assertRaises(ValueError):
            full.validate_marker_diagnostics(dict(phase='completed', kind='count', ordinal=15,
                                                  error_stage=0, copyback=[None] * 34))
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT),
                         (8192, 8192, 32768))

    def test_exact_order_and_legacy_inverse_are_preserved(self):
        raw = linux_fixture(ROOT / full.CLIENT_SOURCE)
        added = raw.split(b'// BEGIN bounded scalar copyback measurement', 1)[1].decode()
        self.assertEqual(re.findall(r'CopybackRecord\(Records, "([^"]+)"', added), list(LABELS))
        self.assertNotIn('Message(', added)
        self.assertEqual(full.digest(suite.client_parity_template(raw)),
                         '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        self.assertEqual(added.count('Records.Add("copyback.core.v1")'), 1)
