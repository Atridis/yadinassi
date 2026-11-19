"""Correctness and reporting tests, deliberately no timing thresholds."""
import ast
import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from scripts import benchmark_execution_layers as bench


class ExecutionLayerBenchmarkTests(unittest.TestCase):
    def test_python_arithmetic_references_do_not_convert_each_counter(self):
        for case, casts in (('arithmetic', [182]), ('arithmetic.fractional', []), ('map', [78])):
            with self.subTest(case=case):
                job = bench.workload(case, 13)
                converted = []
                def decimal(value):
                    self.assertIs(type(value), int)
                    converted.append(value)
                    return Decimal(value)
                with patch.object(bench, 'D', decimal):
                    bench.validate(job.native(), job.expected)
                self.assertEqual(converted, casts)

    def test_pairs_match_independent_expected_values(self):
        expected = {'arithmetic': Decimal(182), 'arithmetic.int': Decimal(273),
                    'arithmetic.fractional': Decimal('295.75'), 'calls': Decimal(104),
                    'byref': Decimal(13), 'array': Decimal(78), 'map': Decimal(78)}
        for name, result in expected.items():
            with self.subTest(case=name):
                job = bench.workload(name, 13)
                self.assertEqual(job.expected, result)
                for route in ('default', 'prepared'):
                    with patch.dict(os.environ, {'YADINASSI_UNSAFE_COLLECTION_ABLATION': '1'}):
                        bsl, _ = bench.prepare_bsl(job.source, route)
                        for run in (job.native, bsl):
                            # Reusing prepared callable must not accumulate state.
                            for _ in range(2): bench.validate(run(), result)

    def test_ci_integer_workload_emits_a_native_loop_and_fractional_control_does_not(self):
        vm = bench.Interpreter()
        self.addCleanup(vm.close)
        for name in ('arithmetic.int', 'arithmetic.fractional'):
            with self.subTest(case=name):
                job = bench.workload(name, 100000)
                plan = vm.prepare(job.source)
                tree = ast.parse(plan._plan.generated_source)
                loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)]
                self.assertTrue(loops)
                names = {node.id for node in ast.walk(loops[0]) if isinstance(node, ast.Name)}
                self.assertEqual('_constants' not in names and '_Decimal' not in names,
                                 name == 'arithmetic.int')

    def test_default_route_uses_public_constructor_without_override(self):
        with patch.object(bench, 'Interpreter', wraps=bench.Interpreter) as constructor:
            run, info = bench.prepare_bsl('r=1;', 'default')
            constructor.assert_called_once_with()
            bench.validate(run(), Decimal(1))
            self.assertEqual(info['requested_route'], 'default')
            self.assertEqual(info['backend'], 'python-direct')
        self.assertEqual(info['api'], 'execute_program(preparsed_ast)')

    def test_prepared_route_compiles_once_before_invocations(self):
        vm = bench.Interpreter()
        self.addCleanup(vm.close)
        with patch.object(bench, 'Interpreter', return_value=vm) as constructor, \
                patch.object(bench, 'parse', wraps=bench.parse) as parse, \
                patch.object(vm, 'prepare_program', wraps=vm.prepare_program) as prepare:
            run, info = bench.prepare_bsl('r=1;', 'prepared')
            constructor.assert_called_once_with()
            parse.assert_called_once()
            prepare.assert_called_once()
        self.assertEqual(info['backend'], 'python-direct')
        self.assertEqual(info['api'], 'execute_prepared(plan)')
        self.assertEqual(info['preparation_api'], 'prepare_program(preparsed_ast)')
        with patch.object(bench, 'parse', side_effect=AssertionError('reparsed')), \
                patch.object(vm, 'prepare_program', side_effect=AssertionError('recompiled')), \
                patch.object(vm, 'execute_prepared', wraps=vm.execute_prepared) as execute:
            for _ in range(3):
                bench.validate(run(), Decimal(1))
            self.assertEqual(execute.call_count, 3)
            plans = [call.args[0] for call in execute.call_args_list]
            self.assertTrue(all(plan is plans[0] for plan in plans))

    def test_retired_routes_are_rejected_before_parsing_or_vm_creation(self):
        with patch.object(bench, 'parse', side_effect=AssertionError('parsed retired route')), \
                patch.object(bench, 'Interpreter', side_effect=AssertionError('created VM')):
            for route in ('compiled-strict', 'interpreter', 'hybrid'):
                with self.subTest(route=route), self.assertRaises(ValueError):
                    bench.prepare_bsl('r=1;', route)

    def test_edge_workload_size(self):
        for name in bench.CASES:
            job = bench.workload(name, 1)
            bench.validate(job.native(), job.expected)

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
        self.assertEqual(len(report['samples']), 6)
        for turn in range(3):
            rows = report['samples'][turn*2:(turn+1)*2]
            self.assertEqual(tuple(row['layer'] for row in rows), bench.LAYERS[turn%2:]+bench.LAYERS[:turn%2])
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

    def test_new_reports_never_include_class_layer_data(self):
        for route in ('default','prepared'):
            report=bench.measure('arithmetic.int',3,3,route)
            self.assertEqual(bench.LAYERS,('python','bsl'))
            self.assertFalse(hasattr(bench.workload('arithmetic.int',3),'classes'))
            for field in ('summary','ratios_to_python','first_execution_seconds'):
                self.assertEqual(set(report[field]),{'python','bsl'})
            self.assertEqual({sample['layer'] for sample in report['samples']},{'python','bsl'})
