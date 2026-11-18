"""Correctness and reporting tests, deliberately no timing thresholds."""
import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from scripts import benchmark_execution_layers as bench


class ExecutionLayerBenchmarkTests(unittest.TestCase):
    def test_triplets_match_independent_expected_values(self):
        expected = {'arithmetic': Decimal(182), 'calls': Decimal(104),
                    'byref': Decimal(13), 'array': Decimal(78), 'map': Decimal(78)}
        for name, result in expected.items():
            with self.subTest(case=name):
                job = bench.workload(name, 13)
                self.assertEqual(job.expected, result)
                for route in ('default', 'prepared', 'compiled-strict'):
                    with patch.dict(os.environ, {'YADINASSI_UNSAFE_COLLECTION_ABLATION': '1'}):
                        bsl, _ = bench.prepare_bsl(job.source, route)
                        for run in (job.native, job.classes, bsl):
                            # Reusing prepared callable must not accumulate state.
                            for _ in range(2): bench.validate(run(), result)

    def test_default_route_uses_public_constructor_without_override(self):
        with patch.object(bench, 'Interpreter', wraps=bench.Interpreter) as constructor:
            run, info = bench.prepare_bsl('r=1;', 'default')
            constructor.assert_called_once_with()
            bench.validate(run(), Decimal(1))
            self.assertEqual(info['requested_route'], 'default')
            self.assertEqual(info['backend'], 'python-direct')
        with patch.object(bench, 'Interpreter', wraps=bench.Interpreter) as constructor:
            run, info = bench.prepare_bsl('r=1;', 'compiled-strict')
            constructor.assert_called_once_with(execution_backend='compiled-strict')
            bench.validate(run(), Decimal(1))
            self.assertEqual(info['backend'], 'compiled-strict')

    def test_prepared_route_compiles_once_before_invocations(self):
        with patch.object(bench, 'Interpreter', wraps=bench.Interpreter) as constructor:
            run, info = bench.prepare_bsl('r=1;', 'prepared')
            constructor.assert_called_once_with()
        self.assertEqual(info['api'], 'execute_prepared(plan)')
        with patch('yadinassi.experimental_naked_collections.prepare',create=True, side_effect=AssertionError('recompiled')):
            for _ in range(3):bench.validate(run(), Decimal(1))

    def test_edge_workload_size(self):
        for name in bench.CASES:
            job = bench.workload(name, 1)
            bench.validate(job.native(), job.expected)
            bench.validate(job.classes(), job.expected)

    def test_invalid_inputs_and_wrong_results_fail(self):
        for n in (0, -1, True, 1.5, 100001):
            with self.assertRaises(ValueError): bench.workload('array', n)
        with self.assertRaises(ValueError): bench.workload('unknown', 10)
        with self.assertRaises(ValueError): bench.prepare_bsl('r=0;', 'unknown')
        with self.assertRaises(ValueError): bench.prepare_bsl('r=0;', 'experimental')
        with self.assertRaises(ValueError): bench.measure('array', 1, 2)
        for value in (True, 1, 1.0, '1', Decimal(2)):
            with self.assertRaises(AssertionError): bench.validate(value, Decimal(1))

    def test_report_retains_samples_results_and_rotates_order(self):
        report = bench.measure('array', 3, 3)
        self.assertEqual(len(report['samples']), 9)
        for turn in range(3):
            rows = report['samples'][turn*3:(turn+1)*3]
            self.assertEqual(tuple(row['layer'] for row in rows), bench.LAYERS[turn:]+bench.LAYERS[:turn])
            self.assertTrue(all(row['result'] == '3' for row in rows))
        self.assertEqual(set(report['first_execution_seconds']), set(bench.LAYERS))
        self.assertEqual(report['ratios_to_python']['python'], 1)
        self.assertEqual(report['route']['backend'], 'python-direct')
        self.assertIn('bsl_parse_prepare', report['preparation_seconds'])
        self.assertEqual(set(report['summary']), set(bench.LAYERS))

    def test_retired_experimental_route_is_not_reenabled_by_environment(self):
        for value in ('0','1'):
            with patch.dict(os.environ, {'YADINASSI_UNSAFE_COLLECTION_ABLATION': value}):
                with self.assertRaises(ValueError): bench.prepare_bsl('r=1;', 'experimental')

    def test_no_results_are_accepted_on_semantic_mismatch(self):
        with patch.object(bench, 'prepare_bsl', return_value=(lambda: Decimal(-99), {})):
            with self.assertRaises(AssertionError): bench.measure('array', 3, 3)
