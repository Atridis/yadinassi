"""Counters are isolated from timing and preserve benchmark correctness."""
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack, closing
import sqlite3
import sys
import unittest
from unittest.mock import patch
from scripts import benchmark_diagnostics as bench


class BenchmarkDiagnosticTests(unittest.TestCase):
    def test_builtin_compile_and_sql_api_calls_are_distinct(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        cursor = db.cursor()
        def run():
            compile('1 + 2', '<diagnostic-test>', 'eval')
            db.execute('CREATE TABLE t(n)')
            cursor.execute('SELECT 1')
            cursor.executemany('INSERT INTO t VALUES (?)', [(1,), (2,)])
            db.executescript('SELECT 1; SELECT 2;')
            return 'checked'
        result, counts = bench.capture(run)
        self.assertEqual(result, 'checked')
        self.assertEqual(counts['builtin_compile'], 1)
        self.assertEqual(counts['sqlite_execute'], 2)
        self.assertEqual(counts['sqlite_executemany'], 1)
        self.assertEqual(counts['sqlite_executescript'], 1)
        self.assertGreater(counts['python_calls'], 0)
        self.assertIsNone(sys.getprofile())

    def test_profile_removed_on_failure_and_existing_profiler_not_overwritten(self):
        def fail(): raise ValueError('injected')
        with self.assertRaises(ValueError): bench.capture(fail)
        self.assertIsNone(sys.getprofile())
        observer = lambda *args: None
        sys.setprofile(observer)
        try:
            with self.assertRaises(RuntimeError): bench.capture(lambda: None)
            self.assertIs(sys.getprofile(), observer)
        finally:
            sys.setprofile(None)

    def test_qualified_targets_exist_and_do_not_count_unrelated_names(self):
        bench.validate_targets()
        def _check(): return 1
        _, counts = bench.capture(_check)
        self.assertEqual(counts['direct_boundary_check'], 0)
        with patch.dict(bench.WATCHED, {'bad': ('execution/direct/python_direct.py', 'does_not_exist')}):
            with self.assertRaises(ValueError): bench.validate_targets()

    def test_targets_are_read_as_utf8_independently_of_host_locale(self):
        original = Path.read_text
        encodings = []
        def read(path, *args, **kwargs):
            encodings.append(kwargs.get('encoding'))
            if kwargs.get('encoding') != 'utf-8':
                raise UnicodeError('host locale must not decode Python source')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            bench.validate_targets()
        self.assertEqual(encodings, ['utf-8'] * len(bench.WATCHED))

    def test_prepared_excludes_setup_compilation_but_default_counts_it(self):
        default = bench.diagnose('structure.fields', 2, 'default')
        prepared = bench.diagnose('structure.fields', 2, 'prepared')
        self.assertEqual(default['layers']['bsl']['counters']['direct_ast_compile'], 1)
        self.assertEqual(prepared['layers']['bsl']['counters']['direct_ast_compile'], 0)
        self.assertGreater(default['layers']['bsl']['counters']['builtin_compile'], 0)
        self.assertEqual(default['layers']['bsl']['counters']['source_map_compile'], 0)
        self.assertEqual(prepared['layers']['bsl']['counters']['source_map_compile'], 0)
        self.assertEqual(prepared['layers']['bsl']['counters']['builtin_compile'], 0)
        self.assertEqual(default['layers']['bsl']['result'], prepared['layers']['bsl']['result'])
        self.assertIsNone(sys.getprofile())

    def test_count_cardinality_matrix_same_queries_no_fixture_instrumentation(self):
        original_connect, original_capture = sqlite3.connect, bench.capture
        captures = []
        active = None

        def record(statement):
            if active is not None:
                active.append(statement)

        def connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            connection.set_trace_callback(record)
            return connection

        def capture(run):
            nonlocal active
            active = []
            captures.append(active)
            try:
                return original_capture(run)
            finally:
                active = None

        for size in (1, 4):
            with self.subTest(size=size):
                captures.clear()
                with patch.object(sqlite3, 'connect', connect), patch.object(bench, 'capture', capture):
                    case = bench.diagnose('db.count', 2, 'prepared', catalog_rows=size)
                self.assertEqual(case['expected'], str(2 * size))
                self.assertEqual(case['catalog_rows'], size)
                self.assertEqual(set(case['layers']), {'python', 'bsl'})
                python = case['layers']['python']['counters']
                bsl = case['layers']['bsl']['counters']
                self.assertEqual(python['sqlite_execute'], 2)
                self.assertEqual(python['sqlite_query_language_begin'], 0)
                self.assertEqual(bsl['configuration_read_source'], 0)
                self.assertEqual(bsl['sqlite_catalog_begin'], 0)
                self.assertEqual(bsl['sqlite_query_language_begin'], 2)
                self.assertEqual(bsl['sqlite_execute'], 2)
                # No fixture, warm-up, reset or readback is in either capture.
                self.assertEqual([len(statements) for statements in captures], [2, 2])
                for statements in captures:
                    for statement in statements:
                        self.assertTrue(statement.startswith('SELECT COUNT(*) FROM '), statement)

    def test_source_counter_observes_cold_warm_and_changed_epoch(self):
        # Set up outside capture, as the production diagnostic does. Explicitly
        # retire any setup read handle so the first observed read is cold.
        with ExitStack() as stack:
            path, context, owner, manager = bench.extended.database(stack)
            backend = context.backend
            backend._close_idle_read_handle()
            def read():
                with closing(backend.begin_read()) as view:
                    return tuple(view.catalogs())
            expected, cold = bench.capture(read)
            actual, warm = bench.capture(read)
            self.assertEqual(actual, expected)
            self.assertEqual(cold['configuration_read_source'], 1)
            self.assertEqual(warm['configuration_read_source'], 0)
            for counts in (cold, warm):
                self.assertEqual(counts['sqlite_catalog_begin'], 1)
                self.assertGreater(counts['sqlite_execute'], 0)
            # A genuine SQLite page change invalidates the retained connection's
            # epoch; a no-op UPDATE is deliberately not used as evidence.
            with closing(sqlite3.connect(path)) as db:
                db.execute('UPDATE catalog_sequence SET next_value=next_value+1')
                db.commit()
            actual, changed = bench.capture(read)
            self.assertEqual(actual, expected)
            self.assertEqual(changed['configuration_read_source'], 1)
            backend._close_idle_read_handle()
            actual, reopened = bench.capture(read)
            self.assertEqual(actual, expected)
            self.assertEqual(reopened['configuration_read_source'], 1)
            for counts in (changed, reopened):
                self.assertEqual(counts['sqlite_catalog_begin'], 1)
                self.assertGreater(counts['sqlite_execute'], 0)
        self.assertIsNone(sys.getprofile())

    def test_forms_have_no_false_prepared_or_native_baseline(self):
        case = bench.diagnose('form.event', 2, 'default')
        self.assertEqual(set(case['layers']), {'bsl'})
        self.assertEqual(set(case['statuses']), {'python'})
        with self.assertRaises(ValueError): bench.diagnose('form.event', 2, 'prepared')

    def test_form_open_keeps_two_detached_copies_and_two_side_compilations(self):
        case = bench.diagnose('form.open', 8, 'default')
        self.assertEqual(case['operations_per_capture'], 1)
        self.assertEqual(case['layers']['bsl']['result'], '1')
        counts = case['layers']['bsl']['counters']
        self.assertEqual(counts['prepared_ast_snapshot'], 2)
        self.assertEqual(counts['direct_ast_compile'], 2)
        self.assertEqual(counts['builtin_compile'], 2)
        self.assertEqual(counts['sqlite_execute'], 0)

    def test_invalid_diagnostic_inputs_fail_before_any_fixture(self):
        with patch.object(bench.extended, 'make_case', side_effect=AssertionError('fixture touched')):
            for n in (True, 0, -1, 65, 2.0):
                with self.assertRaises(ValueError): bench.diagnose('db.count', n, 'default')
            for rows in (True, 0, 1025, 2.0):
                with self.assertRaises(ValueError): bench.diagnose('db.count', 2, 'default', catalog_rows=rows)
            with self.assertRaises(ValueError): bench.diagnose('missing', 2, 'default')

    def test_report_has_counts_not_timing_samples_or_ratios(self):
        case = bench.diagnose('core.byref', 2, 'prepared')
        report = {'schema': 'execution-call-diagnostics-v1', 'environment': {'git_head': 'test'}, 'cases': [case]}
        before = deepcopy(report)
        text = bench.render(report)
        self.assertEqual(report, before)
        self.assertIn('Диагностика вызовов без замера времени', text)
        self.assertIn('API SQLite execute', text)
        self.assertIn('Прямой AST compile_module', text)
        self.assertIn('Объектный _begin | Порт Query', text)
        table = [line for line in text.splitlines() if line.startswith('|')]
        self.assertGreaterEqual(len(table), 3)
        self.assertEqual({len(line.split('|')) - 2 for line in table}, {14})
        self.assertIn('SourceMap.compile', text)
        old_report = deepcopy(report)
        del old_report['cases'][0]['layers']['bsl']['counters']['direct_ast_compile']
        del old_report['cases'][0]['layers']['bsl']['counters']['sqlite_query_language_begin']
        old_report['cases'][0]['layers']['python_classes'] = case['layers']['python']
        old_text = bench.render(old_report)
        self.assertIn('—', old_text)
        self.assertNotIn('Классы yadinassi', old_text)
        self.assertFalse(any(emoji in text for emoji in '🟩🟨🟧'))
        self.assertNotIn('median_seconds', str(case))
        self.assertNotIn('samples', case)
        case['layers']['bsl']['counters']['python_calls'] = -1
        with self.assertRaises(ValueError): bench.render(report)

    def test_timing_runners_do_not_import_or_enable_diagnostics(self):
        for name in ('benchmark_execution_layers.py', 'benchmark_extended_layers.py'):
            text = (bench.ROOT / 'scripts' / name).read_text(encoding='utf-8')
            self.assertNotIn('benchmark_diagnostics', text)
            self.assertNotIn('setprofile', text)
