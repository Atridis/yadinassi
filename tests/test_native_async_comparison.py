"""Offline regression and hostile-input tests; no fresh native execution."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from scripts import native_async_comparison as adapter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/native_async_comparison_linux_8_3_27_1508.json'
FIXTURE_SHA256 = '32aae45a687e0e05cc58f328b63997f4d6229d2e76dc33d1274dcefb68fe791b'


def extract_literals(path):
    return adapter.read_pinned_sources(path.read_bytes())


TEMPLATE, SOURCES = extract_literals(ROOT / 'scripts/native_1c_bootstrap/full_suite.py')
OBSERVATION = json.loads(FIXTURE.read_text(encoding='utf-8'))
NATIVE = OBSERVATION['client_async']


class ComparatorTests(unittest.TestCase):
    def compare(self, native=None):
        return adapter.compare(TEMPLATE, SOURCES, NATIVE if native is None else native)

    def test_literal_extraction_rejects_other_bindings(self):
        prefix = 'ASYNC_TEMPLATE = ' + repr(TEMPLATE) + '\nASYNC_CASE_SOURCES = ' + repr(SOURCES) + '\n'
        attacks = [
            'ASYNC_TEMPLATE: str = "changed"',
            'ASYNC_CASE_SOURCES += ("extra",)',
            'ASYNC_TEMPLATE = "changed"',
            'ASYNC_TEMPLATE, other = "changed", 1',
            'if True:\n    ASYNC_TEMPLATE = "changed"',
            'for ASYNC_TEMPLATE in []:\n    pass',
            'with context() as ASYNC_TEMPLATE:\n    pass',
            '(ASYNC_TEMPLATE := "changed")',
            'del ASYNC_TEMPLATE',
            'def ASYNC_TEMPLATE():\n    pass',
            'class ASYNC_TEMPLATE:\n    pass',
            'def function(ASYNC_TEMPLATE):\n    pass',
            'import other as ASYNC_TEMPLATE',
            'from other import ASYNC_TEMPLATE',
            'from other import *',
            'try:\n    pass\nexcept Exception as ASYNC_TEMPLATE:\n    pass',
            'def function():\n    global ASYNC_TEMPLATE',
            'match value:\n    case ASYNC_TEMPLATE:\n        pass',
            'match value:\n    case [*ASYNC_CASE_SOURCES]:\n        pass',
            'match value:\n    case {**ASYNC_TEMPLATE}:\n        pass',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.py'
            path.write_text(prefix, encoding='utf-8')
            self.assertEqual(extract_literals(path), (TEMPLATE, SOURCES))
            for attack in attacks:
                with self.subTest(attack=attack):
                    path.write_text(prefix + attack + '\n', encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, '^invalid_async_comparison_input$'):
                        extract_literals(path)

    def test_pinned_source_reader_is_bounded_and_never_executes(self):
        prefix = ('ASYNC_TEMPLATE = ' + repr(TEMPLATE) + '\nASYNC_CASE_SOURCES = ' + repr(SOURCES) + '\n').encode('utf-8')
        self.assertEqual(adapter.read_pinned_sources(prefix + b'raise RuntimeError("must not execute")\n'), (TEMPLATE, SOURCES))
        self.assertEqual(adapter.read_pinned_sources(b'\xef\xbb\xbf' + prefix.replace(b'\n', b'\r\n')), (TEMPLATE, SOURCES))
        for payload in (None, '', b'', b'\xff', b'pass', b'\x00', b'(' * 1000,
                        b' ' * (adapter.MAX_SOURCE_BYTES + 1),
                        prefix.replace(b'ASYNC_TEMPLATE = ', b'OTHER = ', 1),
                        b'ASYNC_TEMPLATE = call()\nASYNC_CASE_SOURCES = ()\n',
                        prefix.replace(b'ASYNC-REJECT', b'ASYNC-MODIFIED')):
            with self.assertRaisesRegex(adapter.InvalidComparisonInput, '^invalid_async_comparison_input$'):
                adapter.read_pinned_sources(payload)

    def test_actual_runner_rejects_unpinned_sources_without_runtime_import(self):
        import builtins
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name == 'yadinassi' or name.startswith('yadinassi.'):
                self.fail('unpinned source reached runtime import')
            return original(name, *args, **kwargs)
        for sources in (None, [], SOURCES[:-1], (*SOURCES[:-1], SOURCES[-1] + ' '), ('\ud800', *SOURCES[1:])):
            with patch('builtins.__import__', side_effect=guarded):
                with self.assertRaises(adapter.InvalidComparisonInput):
                    adapter.execute_actual(sources)

    def test_host_comparison_never_imports_or_executes_runtime(self):
        import builtins
        actual = adapter.execute_actual(SOURCES)
        original = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name == 'yadinassi' or name.startswith('yadinassi.'):
                self.fail('host comparison imported runtime')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded), patch.object(adapter, 'execute_actual', side_effect=AssertionError('host ran runtime')):
            result = adapter.compare_observations(TEMPLATE, SOURCES, NATIVE, actual)
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['actual_sha256'], hashlib.sha256(adapter.canonical(actual)).hexdigest())

    def test_host_rejects_hostile_actual_schema(self):
        good = adapter.execute_actual(SOURCES)
        malformed = [None, {}, {'status': 'matched'}, [], good[:-1], good + [good[0]], tuple(good), [True] * 8]
        for column, value in [(0, None), (0, []), (0, [True]), (0, [1, 1]), (0, [256]),
                              (0, list(range(25))), (0, ['private']), (1, []),
                              (1, [[4, True]]), (1, [[True, 0]]),
                              (1, [[4, float('nan')]]), (1, [[4, float('inf')]]),
                              (1, [[4, 1000000]]), (1, [[4, -1000000]]),
                              (1, [[6, 1]]), (1, [[3, 2]]), (1, [[5, 8]]),
                              (1, [[7, -1]]), (1, [[7, 0]]), (1, [[4, 1]] * 9),
                              (1, [[4, 1, 2]]), (1, [[4, '/private/path SECRET']]),
                              (2, [[1, 2, 2, 2, 1, 0, '0' * 64]]),
                              (2, [[True, 2, 2, 2, 1, 0]]), (2, [[1, 4, 2, 2, 1, 0]]),
                              (2, [[1, 2, 2, 2, 0, 0]]), (2, [[1, 2, 2, 2, 1, 2]]),
                              (2, [[1, 2, 2, 2, 1, 0]] * 4), (3, 1), (3, None), (4, 0), (4, 'false')]:
            changed = copy.deepcopy(good)
            changed[0][column] = value
            malformed.append(changed)
        malformed.extend(([[[], [], [], False, True, 'extra']] * 8, [[[], [], [], False]] * 8))
        for actual in malformed:
            with self.assertRaisesRegex(adapter.InvalidComparisonInput, '^invalid_async_comparison_input$'):
                adapter.compare_observations(TEMPLATE, SOURCES, NATIVE, actual)

    def test_valid_bounded_failure_actual_never_reports_match(self):
        actual = [[[], [], [], False, True] for _ in range(8)]
        result = adapter.compare_observations(TEMPLATE, SOURCES, NATIVE, actual)
        self.assertEqual(result['cases'], [['mismatched', 'runtimeerror']] * 8)
        self.assertEqual(result['status'], 'mismatched')
        self.assertLess(len(adapter.canonical(actual)), adapter.MAX_ACTUAL_BYTES)

    def test_sanitized_fixture_integrity_and_scope(self):
        # Text-mode newline normalization keeps this portable to CRLF checkout.
        self.assertEqual(hashlib.sha256(FIXTURE.read_text(encoding='utf-8').encode('utf-8')).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(set(OBSERVATION), {'provenance', 'client_async'})
        provenance = OBSERVATION['provenance']
        self.assertEqual(provenance['run_id'], 39972282106)
        self.assertEqual(provenance['run_attempt'], 1)
        self.assertEqual(provenance['commit'], '0218f8466f91a46f759cdd9b4e06f72014fa073a')
        self.assertEqual(provenance['report_sha256'], 'caaee56caab53dfc00bb4bb9c1cef78dd578593d1e8fb1b8517c10ef2499e9c1')
        self.assertEqual(set(NATIVE), {'cases', 'continuity_sha256', 'failure_diagnostics', 'failure_kind',
                                      'marker_validation_failure', 'process_diagnostics', 'status', 'template_sha256', 'version'})
        self.assertLess(len(FIXTURE.read_bytes()), 16384)
        # Optional existing runtime fixture only crosschecks bodies, not expectations.
        previous = ROOT / 'tests/fixtures/async_native_linux_8_3_27_1508.json'
        if previous.exists():
            bodies = json.loads(previous.read_text(encoding='utf-8'))['cases']
            self.assertEqual(list(SOURCES), [case['source'] for case in bodies])

    def test_accepted_offline_replay_and_actual_digest(self):
        first, second = self.compare(), self.compare()
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'matched')
        self.assertEqual(first['actual_sha256'], hashlib.sha256(adapter.canonical(adapter.execute_actual(SOURCES))).hexdigest())

    def test_native_mutations_do_not_change_actual_digest(self):
        baseline = self.compare()
        for kind, case, column, index in [('trace', 0, 5, 2), ('values', 0, 6, 1), ('errors', 6, 7, 0)]:
            native = copy.deepcopy(NATIVE)
            if kind == 'trace':
                native['cases'][case][column][index] = 99
            elif kind == 'values':
                native['cases'][case][column][index][1] = 18
            else:
                native['cases'][case][column][index][1] = 3
            result = self.compare(native)
            self.assertEqual(result['status'], 'mismatched')
            self.assertEqual(result['cases'][case], ['mismatched', kind])
            self.assertEqual(result['actual_sha256'], baseline['actual_sha256'])

    def test_each_error_field_compared(self):
        for field in range(6):
            native = copy.deepcopy(NATIVE)
            native['cases'][6][7][0][field] = 0
            if field == 5:
                native['cases'][6][7][0][field] = 1
            self.assertEqual(self.compare(native)['cases'][6][1], 'errors')

    def test_private_hash_is_ignored_not_copied_into_digest(self):
        native = copy.deepcopy(NATIVE)
        native['cases'][6][7][0][6] = '0' * 64
        self.assertEqual(self.compare(native), self.compare())

    def test_native_lifecycle_and_binding_rejected_before_execution(self):
        mutations = [lambda n: n.update(failure_kind='runtime_error'),
                     lambda n: n.pop('continuity_sha256'),
                     lambda n: n.update(continuity_sha256='bad'),
                     lambda n: n.pop('failure_diagnostics'),
                     lambda n: n.update(failure_diagnostics={}),
                     lambda n: n.pop('marker_validation_failure'),
                     lambda n: n.update(marker_validation_failure={}),
                     lambda n: n.pop('process_diagnostics'),
                     lambda n: n['process_diagnostics'].update(stage='before_exit'),
                     lambda n: n['process_diagnostics'].update(reason='unknown'),
                     lambda n: n['process_diagnostics'].update(unexpected_count=1),
                     lambda n: n['process_diagnostics'].update(zombie_count=True),
                     lambda n: n['process_diagnostics']['classes'].update(other=1),
                     lambda n: n['process_diagnostics']['classes'].pop('native')]
        for mutation in mutations:
            native = copy.deepcopy(NATIVE)
            mutation(native)
            with patch.object(adapter, 'execute_actual') as run:
                with self.assertRaises(adapter.InvalidComparisonInput):
                    self.compare(native)
                run.assert_not_called()

    def test_source_identity_prevents_execution(self):
        for template, sources in [(TEMPLATE + ' ', SOURCES), (TEMPLATE, SOURCES[:-1]),
                                   (TEMPLATE, (SOURCES[0] + ' ', *SOURCES[1:])),
                                   ('\ud800', SOURCES)]:
            with patch.object(adapter, 'execute_actual') as run:
                with self.assertRaisesRegex(adapter.InvalidComparisonInput, '^invalid_async_comparison_input$'):
                    adapter.compare(template, sources, NATIVE)
                run.assert_not_called()

    def test_malformed_native_rejected_before_execution(self):
        mutations = [lambda n: n.update(cases=n['cases'][:-1]),
                     lambda n: n.update(status='failed'),
                     lambda n: n.update(version=True),
                     lambda n: n.update(template_sha256='0'*64)]
        for col, value in [(0, True), (1, True), (2, 1), (3, '0'*64), (4, 62),
                           (5, [True]), (5, [1, 1]), (5, list(range(25))),
                           (6, [[4, float('nan')]]), (6, [[7, 999]]),
                           (6, [[0, 1]]), (6, [[3, 2]]), (6, [[5, 8]]),
                           (7, [[1, 2, 2, 2, 1, 0, '/private/secret']])]:
            mutations.append(lambda n, c=col, v=value: n['cases'][0].__setitem__(c, v))
        for mutation in mutations:
            native = copy.deepcopy(NATIVE)
            mutation(native)
            with patch.object(adapter, 'execute_actual') as run:
                with self.assertRaises(adapter.InvalidComparisonInput):
                    self.compare(native)
                run.assert_not_called()

    def test_runtime_observation_changes_digest_and_result(self):
        baseline = self.compare()
        for offset, value, expected in [(0, [99], 'trace'), (1, [[4, 999]], 'values'),
                                         (2, [[1, 3, 2, 2, 1, 0]], 'errors'),
                                         (3, False, 'lifecycle'), (4, True, 'runtimeerror')]:
            actual = adapter.execute_actual(SOURCES)
            actual[0][offset] = value
            with patch.object(adapter, 'execute_actual', return_value=actual):
                result = self.compare()
            self.assertEqual(result['cases'][0][1], expected)
            self.assertNotEqual(result['actual_sha256'], baseline['actual_sha256'])

    def test_import_failure_is_finite_and_private(self):
        import builtins
        original = builtins.__import__
        for blocked in ('yadinassi', 'yadinassi.native_targets'):
            def guarded(name, *args, **kwargs):
                if name == blocked:
                    raise ImportError('/private/path SECRET import failure')
                return original(name, *args, **kwargs)
            with patch('builtins.__import__', side_effect=guarded):
                result = self.compare()
            self.assertEqual(result['status'], 'mismatched')
            self.assertEqual(result['cases'], [['mismatched', 'runtimeerror']] * 8)
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertNotIn('/private', json.dumps(result))
            self.assertEqual(result['actual_sha256'], hashlib.sha256(
                adapter.canonical([[[], [], [], False, True] for _ in range(8)])).hexdigest())

    def test_close_on_success_and_failure_without_exception_leak(self):
        from yadinassi import Interpreter
        original = Interpreter.close
        closed = []
        def close(vm):
            closed.append(vm)
            original(vm)
        with patch.object(Interpreter, 'close', close):
            self.assertEqual(self.compare()['status'], 'matched')
        self.assertEqual(len(closed), 8)
        closed.clear()
        with patch.object(Interpreter, 'close', close), patch.object(Interpreter, 'execute', side_effect=ValueError('/private/path SECRET')):
            result = self.compare()
        self.assertEqual(len(closed), 8)
        self.assertTrue(all(row == ['mismatched', 'runtimeerror'] for row in result['cases']))
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('/private', json.dumps(result))

    def test_unexpected_error_literals_never_match_other_tag(self):
        actual = adapter.execute_actual(SOURCES)
        actual[6][2][0][1] = 3
        native = copy.deepcopy(NATIVE)
        native['cases'][6][7][0][1] = 3
        with patch.object(adapter, 'execute_actual', return_value=actual):
            self.assertEqual(self.compare(native)['cases'][6][1], 'errors')

    def test_budget_at_probe_indentation(self):
        worst = {'profile': adapter.PROFILE, 'status': 'mismatched',
                 'cases': [['mismatched', 'runtimeerror'] for _ in range(8)],
                 'actual_sha256': 'f' * 64}
        # Result at report['probe']['async_comparison']; count comma/key/indent delta.
        before = {'probe': {'comparison': {'status': 'preserved'}}}
        after = {'probe': {'comparison': {'status': 'preserved'}, 'async_comparison': worst}}
        delta = len(json.dumps(after, indent=2).encode()) - len(json.dumps(before, indent=2).encode())
        self.assertLessEqual(31381 + delta, 32768)
        print('comparison budget: delta=%s pretty_upper=%s wire_upper=7984 unchanged' % (delta, 31381 + delta))


if __name__ == '__main__':
    unittest.main()
