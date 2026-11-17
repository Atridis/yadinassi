"""Counters are isolated from timing and preserve benchmark correctness."""
from pathlib import Path
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
        with patch.dict(bench.WATCHED, {'bad': ('python_direct.py', 'does_not_exist')}):
            with self.assertRaises(ValueError): bench.validate_targets()

    def test_prepared_excludes_setup_compilation_but_default_counts_it(self):
        default = bench.diagnose('structure.fields', 2, 'default')
        prepared = bench.diagnose('structure.fields', 2, 'prepared')
        self.assertGreater(default['layers']['bsl']['counters']['source_map_compile'], 0)
        self.assertEqual(prepared['layers']['bsl']['counters']['source_map_compile'], 0)
        self.assertEqual(prepared['layers']['bsl']['counters']['builtin_compile'], 0)
        self.assertEqual(default['layers']['bsl']['result'], prepared['layers']['bsl']['result'])
        self.assertIsNone(sys.getprofile())

    def test_count_cardinality_matrix_same_queries_no_fixture_instrumentation(self):
        for size in (1, 4):
            case = bench.diagnose('db.count', 2, 'prepared', catalog_rows=size)
            self.assertEqual(case['expected'], str(2 * size))
            self.assertEqual(case['catalog_rows'], size)
            self.assertEqual(case['layers']['python']['counters']['sqlite_execute'], 2)
            self.assertGreater(case['layers']['python_classes']['counters']['configuration_read_source'], 0)
            self.assertEqual(case['layers']['python_classes']['counters']['sqlite_execute'],
                             case['layers']['bsl']['counters']['sqlite_execute'])

    def test_forms_have_no_false_prepared_or_native_baseline(self):
        case = bench.diagnose('form.event', 2, 'default')
        self.assertEqual(set(case['layers']), {'bsl'})
        self.assertEqual(set(case['statuses']), {'python', 'python_classes'})
        with self.assertRaises(ValueError): bench.diagnose('form.event', 2, 'prepared')

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
        text = bench.render(report)
        self.assertIn('Untimed execution diagnostics', text)
        self.assertIn('SQLite execute API', text)
        self.assertFalse(any(emoji in text for emoji in '🟩🟨🟧'))
        self.assertNotIn('median_seconds', str(case))
        self.assertNotIn('samples', case)
        case['layers']['bsl']['counters']['python_calls'] = -1
        with self.assertRaises(ValueError): bench.render(report)

    def test_timing_runners_do_not_import_or_enable_diagnostics(self):
        for name in ('benchmark_execution_layers.py', 'benchmark_extended_layers.py'):
            text = (bench.ROOT / 'scripts' / name).read_text()
            self.assertNotIn('benchmark_diagnostics', text)
            self.assertNotIn('setprofile', text)
