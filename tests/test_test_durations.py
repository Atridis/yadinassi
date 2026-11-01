"""Small synthetic suites: runner instrumentation must not change execution."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_tests import TimedTextTestResult, TimedTextTestRunner

ROOT = Path(__file__).resolve().parents[1]


def outcomes():
    class Cases(unittest.TestCase):
        def test_ok(self):
            pass

        def test_fail(self):
            self.fail('failure detail')

        def test_error(self):
            raise ValueError('error detail')

        @unittest.skip('skip reason')
        def test_skip(self):
            pass

        @unittest.expectedFailure
        def test_expected(self):
            self.fail('expected detail')

        @unittest.expectedFailure
        def test_unexpected(self):
            pass

        def test_subtests(self):
            for i in range(3):
                with self.subTest(i=i):
                    if i == 1:
                        self.fail('subtest detail')
                    if i == 2:
                        raise ValueError('subtest error')

        def test_subtest_skip(self):
            with self.subTest(i=0):
                self.skipTest('subtest skip')

    return unittest.defaultTestLoader.loadTestsFromTestCase(Cases)


def signature(result):
    return (result.testsRun, result.wasSuccessful(), result.shouldStop,
            tuple(len(getattr(result, key)) for key in (
                'errors', 'failures', 'skipped', 'expectedFailures', 'unexpectedSuccesses')))


class TestDurationRunnerTests(unittest.TestCase):
    def test_all_outcomes_and_subtests_preserve_results(self):
        for verbosity in (0, 1, 2):
            for failfast in (False, True):
                with self.subTest(verbosity=verbosity, failfast=failfast):
                    ordinary = unittest.TextTestRunner(stream=io.StringIO(), verbosity=verbosity,
                                                       failfast=failfast).run(outcomes())
                    stream = io.StringIO()
                    timed = TimedTextTestRunner(stream=stream, verbosity=verbosity,
                                                failfast=failfast).run(outcomes())
                    self.assertEqual(signature(timed), signature(ordinary))
                    self.assertEqual(len(timed.slowest), timed.testsRun)
                    if verbosity == 2:
                        lines = [line for line in stream.getvalue().splitlines() if line.endswith(' s')]
                        self.assertEqual(len(lines), timed.testsRun)
                        for line in lines:
                            self.assertRegex(line, r' \.\.\. .+ \.\.\. [0-9]+\.[0-9]{3} s$')
                    if not verbosity:
                        self.assertNotIn('Slowest tests', stream.getvalue())
        text = io.StringIO()
        TimedTextTestRunner(stream=text, verbosity=2).run(outcomes())
        for detail in ('failure detail', 'error detail', 'subtest detail', 'subtest error',
                       'expected failure', 'unexpected success', "skipped 'skip reason'", '(i=1)'):
            self.assertIn(detail, text.getvalue())

    def test_duration_includes_fixtures_and_cleanup_and_no_partial_line(self):
        clock = [0.0]
        stream = io.StringIO()
        events = []

        class Case(unittest.TestCase):
            def setUp(self):
                clock[0] += 1
                events.append('setup')
                self.addCleanup(self.clean)

            def clean(self):
                clock[0] += 4
                events.append('cleanup')
                self.assertEqual(stream.getvalue(), '')

            def tearDown(self):
                clock[0] += 3
                events.append('teardown')

            def test_body(self):
                clock[0] += 2
                events.append('body')

        result = TimedTextTestRunner(stream=stream, verbosity=2)._makeResult()
        with patch('scripts.run_tests.perf_counter', side_effect=lambda: clock[0]):
            Case('test_body')(result)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(events, ['setup', 'body', 'teardown', 'cleanup'])
        self.assertIn(' ... ok ... 10.000 s\n', stream.getvalue())
        self.assertEqual(result.slowest[0][0], 10)

    def test_setup_teardown_cleanup_failures_still_timed(self):
        for stage in ('setUp', 'tearDown', 'cleanup'):
            with self.subTest(stage=stage):
                class Case(unittest.TestCase):
                    def setUp(self):
                        self.addCleanup(self.cleanup)
                        if stage == 'setUp':
                            raise ValueError(stage)

                    def tearDown(self):
                        if stage == 'tearDown':
                            raise ValueError(stage)

                    def cleanup(self):
                        if stage == 'cleanup':
                            raise ValueError(stage)

                    def test_body(self):
                        pass
                stream = io.StringIO()
                result = TimedTextTestRunner(stream=stream, verbosity=2).run(Case('test_body'))
                self.assertEqual((result.testsRun, len(result.errors)), (1, 1))
                self.assertEqual(len(result.slowest), 1)
                self.assertRegex(stream.getvalue(), r' \.\.\. ERROR \.\.\. [0-9.]+ s\n')

    def test_class_fixture_errors_are_not_fictitious_test_timings(self):
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise ValueError('class error')

            def test_not_run(self):
                self.fail('not executed')
        stream = io.StringIO()
        result = TimedTextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Broken))
        self.assertEqual((result.testsRun, len(result.errors), result.slowest), (0, 1, []))
        self.assertIn('class error', stream.getvalue())
        self.assertNotIn('Slowest tests', stream.getvalue())

    def test_top_twenty_bounded_sorted_and_full_ids(self):
        class Case(unittest.TestCase):
            def runTest(self):
                pass
        stream = io.StringIO()
        result = TimedTextTestRunner(stream=stream)._makeResult()
        for i in range(25):
            case = Case()
            with patch('scripts.run_tests.perf_counter', side_effect=[0, i + 1]):
                case(result)
            self.assertLessEqual(len(result.slowest), 20)
        self.assertEqual(sorted(x[0] for x in result.slowest), list(range(6, 26)))
        self.assertTrue(all(x[2] == Case().id() for x in result.slowest))
        self.assertEqual(result.testsRun, 25)

    def test_cli_discovery_filter_exit_codes_and_no_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test_small.py').write_text(
                'import unittest\nclass Small(unittest.TestCase):\n'
                ' def test_one(self): pass\n def test_two(self): pass\n', encoding='utf-8')
            (path / 'ignored.py').write_text('raise RuntimeError("must not import")\n', encoding='utf-8')
            for selection, count in (([], 2), (['-k', 'one'], 1)):
                args = ['discover', '-s', directory, '-v', *selection]
                plain = subprocess.run([sys.executable, '-m', 'unittest', *args],
                                       cwd=ROOT, capture_output=True, text=True, timeout=20)
                timed = subprocess.run([sys.executable, '-m', 'scripts.run_tests', *args],
                                       cwd=ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual((plain.returncode, timed.returncode), (0, 0))
                timed_lines = [x.split(' ... ')[0] for x in timed.stderr.splitlines() if ' ... ok ... ' in x]
                plain_lines = [x.split(' ... ')[0] for x in plain.stderr.splitlines() if x.endswith(' ... ok')]
                self.assertEqual(timed_lines, plain_lines)
                self.assertEqual(len(timed_lines), count)
            (path / 'test_small.py').write_text('raise RuntimeError("import failure")\n', encoding='utf-8')
            for runner in ('unittest', 'scripts.run_tests'):
                failed = subprocess.run([sys.executable, '-m', runner, 'discover', '-s', directory, '-v'],
                                        cwd=ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(failed.returncode, 1)
                self.assertIn('import failure', failed.stderr)

    def test_buffered_output_and_successful_subtests(self):
        class Case(unittest.TestCase):
            def test_body(self):
                print('buffered ordinary output')
                for i in range(2):
                    with self.subTest(i=i):
                        self.assertLess(i, 3)
        stream = io.StringIO()
        result = TimedTextTestRunner(stream=stream, verbosity=2, buffer=True).run(Case('test_body'))
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.testsRun, 1)
        self.assertNotIn('buffered ordinary output', stream.getvalue())
        self.assertEqual(stream.getvalue().count(' ... ok ... '), 1)

    def test_python310_syntax_and_top_summary_order(self):
        import ast
        ast.parse((ROOT / 'scripts/run_tests.py').read_text(encoding='utf-8'), feature_version=(3, 10))
        stream = io.StringIO()
        with patch('scripts.run_tests.perf_counter', side_effect=[0, 1, 0, 3, 0, 2]):
            result = TimedTextTestRunner(stream=stream, verbosity=1).run(
                unittest.TestSuite(unittest.FunctionTestCase(lambda: None) for _ in range(3)))
        self.assertEqual(result.testsRun, 3)
        summary = stream.getvalue().split('Slowest tests', 1)[1]
        times = [float(line.split()[0]) for line in summary.splitlines()[1:]]
        self.assertEqual(times, [3.0, 2.0, 1.0])

    def test_instance_id_shadowing_before_and_during_fixtures(self):
        for stage in ('constructor', 'setUp', 'body', 'cleanup'):
            with self.subTest(stage=stage):
                clock = [0.0]
                class Case(unittest.TestCase):
                    def __init__(self):
                        super().__init__('test_body')
                        if stage == 'constructor':
                            self.id = object()

                    def id(self):
                        raise AssertionError('runner must not call a user id override')

                    def setUp(self):
                        self.addCleanup(self.clean)
                        if stage == 'setUp':
                            self.id = object()

                    def clean(self):
                        clock[0] += 3
                        if stage == 'cleanup':
                            self.id = object()

                    def test_body(self):
                        clock[0] += 2
                        if stage == 'body':
                            self.id = object()

                case = Case()
                expected = unittest.TestCase.id(case)
                stream = io.StringIO()
                with patch('scripts.run_tests.perf_counter', side_effect=lambda: clock[0]):
                    result = TimedTextTestRunner(stream=stream, verbosity=2).run(case)
                self.assertTrue(result.wasSuccessful())
                self.assertEqual(result.testsRun, 1)
                self.assertEqual(result.slowest[0][2], expected)
                self.assertIn(' ... ok ... 5.000 s', stream.getvalue())
                self.assertIn('5.000 s  ' + expected, stream.getvalue())

    def test_workflow_only_main_full_step_uses_runner(self):
        source = (ROOT / '.github/workflows/build.yml').read_text(encoding='utf-8')
        self.assertEqual(source.count('python -m scripts.run_tests discover -s tests -v'), 1)
        self.assertIn('python -m unittest test_regex_family ', source)
        self.assertIn('python -O -m unittest test_regex_family ', source)


if __name__ == '__main__':
    unittest.main()
