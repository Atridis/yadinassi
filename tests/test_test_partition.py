"""Synthetic coverage/fixture tests: never run the repository test suite here."""
import io
import json
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest import mock

from scripts import test_partition as partition


def case(module, name, action=None):
    def test_body(self):
        if action:
            action(self)
    cls = type(name, (unittest.TestCase,), {'__module__': module, 'test_body': test_body})
    return cls('test_body')


def weights(tests, seconds=4, intel=None):
    return {partition.identity(test)[0]: {'seconds': seconds,
            'intel_seconds': seconds if intel is None else intel} for test in tests}


class PartitionTests(unittest.TestCase):
    def test_exact_union_disjoint_two_shards_and_deterministic_balance(self):
        tests = [case('module_%d' % i, 'Case') for i in range(5)]
        history = {}
        for test, seconds in zip(tests, (10, 8, 6, 4, 1)):
            history.update(weights([test], seconds))
        def plan():
            return partition.partition_suite(unittest.TestSuite(
                unittest.TestSuite([test]) for test in tests), history)
        p = plan()
        _, light = p.select('light')
        _, first = p.select('heavy', 2, 0)
        _, second = p.select('heavy', 2, 1)
        self.assertEqual(len(light['selected_ids']), 1)
        self.assertEqual(first['estimated_intel_seconds'], 14)
        self.assertEqual(second['estimated_intel_seconds'], 14)
        groups = [set(report['selected_ids']) for report in (light, first, second)]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual(set.union(*groups), set(history))
        self.assertEqual(p.select('heavy', 2, 0)[1], plan().select('heavy', 2, 0)[1])

    def test_unknown_forces_whole_module_light_even_known_slow_test(self):
        known, new = case('same', 'Known'), case('same', 'New')
        p = partition.partition_suite(unittest.TestSuite([
            unittest.TestSuite([known]), unittest.TestSuite([new])]), weights([known], 100))
        self.assertEqual(len(p.groups), 1)
        self.assertEqual(len(p.select('light')[1]['selected_ids']), 2)
        self.assertEqual(p.select('heavy')[1]['selected_ids'], [])
        self.assertEqual(len(partition.partition_suite(unittest.TestSuite([known, new]), {}).select('light')[1]['selected_ids']), 2)

    def test_load_tests_custom_suite_retained_with_cross_module_fixture_groups(self):
        events = []
        class CustomSuite(unittest.TestSuite):
            def run(self, result, debug=False):
                events.append('custom')
                return super().run(result, debug)
        tests = [case('one', 'A'), case('two', 'B'), case('two', 'C')]
        custom = CustomSuite(tests[:2])
        p = partition.partition_suite(unittest.TestSuite([custom, unittest.TestSuite(tests[2:])]), weights(tests))
        self.assertEqual(len(p.groups), 1)
        selected, _ = p.select('heavy', 2, 0)
        self.assertIs(list(selected)[0], custom)
        result = selected.run(unittest.TestResult())
        self.assertEqual(result.testsRun, 3)
        self.assertEqual(events, ['custom'])

    def test_class_fixtures_cleanup_skips_and_subtests_not_split(self):
        events = []
        class Fixture(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                events.append('setup')
                cls.addClassCleanup(events.append, 'cleanup')
            def test_a(self):
                with self.subTest(i=1):
                    self.assertTrue(True)
            @unittest.skip('intentional')
            def test_b(self):
                pass
        tests = [Fixture('test_a'), Fixture('test_b')]
        p = partition.partition_suite(unittest.TestSuite([unittest.TestSuite(tests)]), weights(tests))
        selected, report = p.select('heavy')
        result = partition.PartitionRunner(stream=io.StringIO()).run(selected)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(events, ['setup', 'cleanup'])
        self.assertEqual(result.executed_ids, report['selected_ids'])
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(set(result.durations), set(report['selected_ids']))

    def test_duplicate_id_and_invalid_selections_rejected(self):
        test = case('m', 'A')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            partition.partition_suite(unittest.TestSuite([test, test]), {})
        p = partition.partition_suite(unittest.TestSuite([test]), {})
        for args in [('bad', 1, 0), ('all', 3, 0), ('all', 2, 2), ('all', 2, -1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                p.select(*args)

    def test_history_absent_and_strict_malformed_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            self.assertEqual(partition.load_history(path), {})
            data = {'schema': 1, 'source': {'commit': 'a'*40, 'run': 123},
                    'tests': {'m.C.test_a': {'seconds': 4.0, 'intel_seconds': 2.0}}}
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(partition.load_history(path), data['tests'])
            for value in [float('nan'), float('inf'), -1, True, '3']:
                data['tests']['m.C.test_a']['seconds'] = value
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.subTest(value=value), self.assertRaises(ValueError):
                    partition.load_history(path)
            path.write_text('{"schema":1,"schema":1}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                partition.load_history(path)

    def test_shadowed_instance_id_uses_standard_identity(self):
        test = case('m', 'Shadow', lambda self: setattr(self, 'id', object()))
        test.id = object()
        p = partition.partition_suite(unittest.TestSuite([test]), {})
        suite, report = p.select('light')
        result = partition.PartitionRunner(stream=io.StringIO()).run(suite)
        self.assertEqual(result.executed_ids, report['selected_ids'])

    def test_cli_report_and_plan_are_data_only_and_failure_is_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            args = ['--tier', 'light', '--history', str(path/'absent'),
                    '--report', str(path/'nested'/'report'), '--plan-output', str(path/'nested'/'plan')]
            test = case('synthetic', 'Fail', lambda self: self.fail('intentional'))
            with mock.patch.object(unittest.TestLoader, 'discover', return_value=unittest.TestSuite([test])) as discover:
                with mock.patch('sys.stderr', io.StringIO()):
                    self.assertEqual(partition.main(args), 1)
            discover.assert_called_once_with('tests')
            report = json.loads((path/'nested'/'report').read_text(encoding='utf-8'))
            plan = json.loads((path/'nested'/'plan').read_text(encoding='utf-8'))
            self.assertFalse(report['success'])
            self.assertEqual(report['counts']['failures'], 1)
            self.assertEqual(report['selected_ids'], report['executed_ids'])
            self.assertEqual(report['selected_ids'], plan['selected_ids'])
            self.assertNotIn('intentional', (path/'nested'/'report').read_text(encoding='utf-8'))

    def test_class_setup_failure_reports_missing_execution_and_no_success(self):
        class Bad(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise ValueError('fixture failure')
            def test_body(self):
                pass
        suite = unittest.TestSuite([unittest.TestSuite([Bad('test_body')])])
        selected, report = partition.partition_suite(suite, {}).select('light')
        result = partition.PartitionRunner(stream=io.StringIO()).run(selected)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.executed_ids, [])
        self.assertEqual(len(report['selected_ids']), 1)

    def test_class_fixture_skip_is_covered_without_claiming_execution(self):
        class Skipped(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest('platform')
            def test_body(self):
                self.fail('not reached')
        suite = unittest.TestSuite([unittest.TestSuite([Skipped('test_body')])])
        selected, report = partition.partition_suite(suite, {}).select('light')
        result = partition.PartitionRunner(stream=io.StringIO()).run(selected)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.executed_ids, [])
        self.assertEqual(result.skipped_fixture_ids, report['selected_ids'])

    def test_module_skip_and_custom_load_tests_hook_are_preserved(self):
        module = types.ModuleType('partition_synthetic_module')
        calls = []
        def setup():
            raise unittest.SkipTest('module platform')
        module.setUpModule = setup
        test = case(module.__name__, 'A')
        class Custom(unittest.TestSuite):
            def run(self, result, debug=False):
                calls.append('custom run')
                return super().run(result, debug)
        custom = Custom([test])
        def load_tests(loader, standard, pattern):
            calls.append('load_tests')
            return custom
        module.load_tests = load_tests
        with mock.patch.dict(sys.modules, {module.__name__: module}):
            loaded = unittest.TestLoader().loadTestsFromModule(module)
            self.assertIs(loaded, custom)
            selected, report = partition.partition_suite(unittest.TestSuite([loaded]), {}).select('light')
            result = partition.PartitionRunner(stream=io.StringIO()).run(selected)
        self.assertEqual(calls, ['load_tests', 'custom run'])
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.executed_ids, [])
        self.assertEqual(result.skipped_fixture_ids, report['selected_ids'])

    def test_plan_only_does_not_execute_and_cannot_emit_success_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            test = case('m', 'NotRun', lambda self: self.fail('must not run'))
            with mock.patch.object(unittest.TestLoader, 'discover', return_value=unittest.TestSuite([test])):
                with mock.patch.object(partition.PartitionRunner, 'run') as run:
                    self.assertEqual(partition.main(['--tier', 'all', '--history', str(path/'missing'),
                        '--plan-output', str(path/'plan'), '--plan-only']), 0)
                    run.assert_not_called()
            self.assertNotIn('success', json.loads((path/'plan').read_text(encoding='utf-8')))

    def test_function_case_identity_uses_actual_fixture_module(self):
        def body():
            pass
        test = unittest.FunctionTestCase(body)
        self.assertEqual(partition.identity(test), (unittest.FunctionTestCase.id(test), type(test).__module__))
        selected, report = partition.partition_suite(unittest.TestSuite([test]), {}).select('light')
        result = partition.PartitionRunner(stream=io.StringIO()).run(selected)
        self.assertEqual(result.executed_ids, report['selected_ids'])

    def test_empty_custom_suite_behavior_is_not_silently_dropped(self):
        events = []
        class Empty(unittest.TestSuite):
            def run(self, result, debug=False):
                events.append('ran')
                return result
        selected, report = partition.partition_suite(unittest.TestSuite([Empty()]), {}).select('light')
        selected.run(unittest.TestResult())
        self.assertEqual(events, ['ran'])
        self.assertEqual(report['selected_ids'], [])


if __name__ == '__main__':
    unittest.main()
