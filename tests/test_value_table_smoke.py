"""Packaging transport contracts, using unchanged owner checkpoint files.

These mocked-process tests verify smoke orchestration, not native execution or
new 1C observations. Runtime/native parity is tested separately.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import smoke_test


class ValueTableSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = (smoke_test.ROOT / 'integrational_tests/tests/collections.bsl').read_text(
            encoding='utf-8-sig')
        cls.owner_bytes = (smoke_test.ROOT / 'integrational_tests/output/collections.out').read_bytes()
        cls.expected = cls.owner_bytes.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
        cls.command, cls.command_expected = smoke_test.table_command_checkpoint(cls.program, cls.expected)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'outside-source' / 'table-checkpoint'
        self.directory.parent.mkdir()
        tests = self.root / 'integrational_tests/tests'
        tests.mkdir(parents=True)
        output = self.root / 'integrational_tests/output'
        output.mkdir(parents=True)
        (tests / 'collections.bsl').write_text(self.program, encoding='utf-8-sig')
        self.output = output / 'collections.out'
        self.output.write_bytes(self.owner_bytes)
        self.executable = str(self.root / 'dist' / 'Yadinassi.exe')
        self.env = {'PATH': 'preserved', 'YADINASSI_TIMEZONE': 'UTC'}
        patcher = patch.object(smoke_test, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def invoke(self):
        with patch('builtins.print'):
            smoke_test.check_table_checkpoint(self.executable, directory=self.directory, env=self.env)

    def success_results(self):
        return [subprocess.CompletedProcess([], 0, expected, '')
                for expected in [self.expected] * 3 + [self.command_expected] * 3]

    def test_full_owner_output_and_bounded_sample_use_all_six_transports(self):
        self.assertEqual(len(self.expected.splitlines()), 3937)
        with patch.object(smoke_test.subprocess, 'run', side_effect=self.success_results()) as run:
            self.invoke()
        self.assertEqual(run.call_count, 6)
        source = self.directory / 'Таблицы с пробелами.bsl'
        self.assertTrue(source.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual(source.read_text(encoding='utf-8-sig'), self.program)
        calls = run.call_args_list
        self.assertEqual(calls[0].args[0], [self.executable, str(source)])
        self.assertIsNone(calls[0].kwargs['input'])
        self.assertEqual(calls[1].args[0], [self.executable, '-'])
        self.assertEqual(calls[1].kwargs['input'], self.program)
        self.assertEqual(calls[2].args[0], [self.executable])
        self.assertEqual(calls[2].kwargs['input'], self.program + '/exit\n')
        for call, flag in zip(calls[3:], ('-c', '-с', '--command')):
            argv = [self.executable, flag, self.command]
            self.assertEqual(call.args[0], argv)
            self.assertNotIn('input', call.kwargs)
            self.assertLess(len(subprocess.list2cmdline(argv).encode('utf-16-le')) // 2 + 1, 32767)
        for call in calls:
            self.assertEqual(call.kwargs['cwd'], self.directory.parent)
            self.assertEqual(call.kwargs['encoding'], 'utf-8')
            self.assertTrue(call.kwargs['capture_output'])
            self.assertEqual(call.kwargs['timeout'], 30)
            self.assertEqual(call.kwargs['env'], dict(self.env, YADINASSI_TIMEZONE='Europe/Warsaw',
                                                     PYTHONTZPATH='', TZ='UTC0'))
        self.assertEqual(self.env, {'PATH': 'preserved', 'YADINASSI_TIMEZONE': 'UTC'})
        # Independently locate complete owner records, preserving embedded newlines.
        selected = re.findall(r'^(table\.[a-z0-9.-]+): \[', self.command_expected, re.MULTILINE)
        self.assertEqual(selected, ['table.' + label for label in smoke_test.TABLE_COMMAND_LABELS])
        self.assertEqual(len(selected), 8)
        for label in selected:
            pattern = r'^' + re.escape(label) + r': \[.*?(?=^table\.[a-z0-9.-]+: \[|\Z)'
            owner = re.search(pattern, self.expected, re.MULTILINE | re.DOTALL).group()
            bounded = re.search(pattern, self.command_expected, re.MULTILINE | re.DOTALL).group()
            self.assertEqual(bounded, owner)

    def test_missing_completion_marker_rejected_before_process_launch(self):
        self.output.write_text(self.expected.removesuffix('table.checkpoint.complete: [ok]\n'),
                               encoding='utf-8')
        with patch.object(smoke_test.subprocess, 'run') as run:
            with self.assertRaisesRegex(AssertionError, 'completion marker'):
                self.invoke()
            run.assert_not_called()

    def test_native_error_artifact_rejected_even_when_empty(self):
        self.output.with_suffix('.err').write_bytes(b'')
        with patch.object(smoke_test.subprocess, 'run') as run:
            with self.assertRaisesRegex(AssertionError, 'Native error file'):
                self.invoke()
            run.assert_not_called()

    def test_every_transport_fails_on_exit_stdout_or_stderr_mismatch(self):
        for index in range(6):
            for field in ('returncode', 'stdout', 'stderr'):
                with self.subTest(transport=index, field=field):
                    # check_table_checkpoint intentionally requires a fresh directory.
                    self.directory = self.root / 'outside-source' / f'case-{index}-{field}'
                    results = self.success_results()
                    setattr(results[index], field, 1 if field == 'returncode' else 'unexpected')
                    with patch.object(smoke_test.subprocess, 'run', side_effect=results) as run:
                        with self.assertRaisesRegex(AssertionError, 'mismatch'):
                            self.invoke()
                        self.assertEqual(run.call_count, index + 1)

    def test_windows_utf16_overflow_rejected_before_command_launch(self):
        with patch.object(smoke_test.subprocess, 'run', side_effect=self.success_results()) as run:
            with patch.object(smoke_test.subprocess, 'list2cmdline', return_value='x' * 32766):
                with self.assertRaisesRegex(AssertionError, 'Windows UTF-16 argv limit'):
                    self.invoke()
            self.assertEqual(run.call_count, 3)

    def test_bounded_sample_requires_unique_helper_and_observation_boundaries(self):
        cases = [(self.program.replace('// Конец помощников checkpoint ТаблицыЗначений.', ''), self.expected),
                 (self.program, self.expected.replace('table.codec.table: [', 'table.codec.absent: [', 1)),
                 (self.program, self.expected + self.command_expected)]
        for program, expected in cases:
            with self.subTest(program_length=len(program), output_length=len(expected)):
                with self.assertRaises(AssertionError):
                    smoke_test.table_command_checkpoint(program, expected)


if __name__ == '__main__':
    unittest.main()
