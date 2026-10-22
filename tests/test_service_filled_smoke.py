"""Synthetic transport tests, never native ValueIsFilled expectations."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import smoke_test
from scripts.native_historical_replay import without_service_filled_probes
from test_service_filled_checkpoint import CASES


class ServiceFilledSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / 'capture'
        self.old = 'opaque previous records\nincluding embedded\nnewlines\n'
        self.records = [f'types-extra.service-filled.{label}.{lang}: [error]'
                        for label, _ in CASES for lang in ('ru', 'en')]
        self.records.append('types-extra.service-filled.checkpoint.complete: [ok]')

    def invoke(self, records=None, old=None, tail=''):
        records = self.records if records is None else records
        old = self.old if old is None else old
        replies = [subprocess.CompletedProcess([], 0, self.old, ''),
                   subprocess.CompletedProcess([], 0, old + '\n'.join(records) + '\n' + tail, '')]
        with patch.object(smoke_test.subprocess, 'run', side_effect=replies) as run, patch('builtins.print'):
            smoke_test.check_service_filled_checkpoint('binary', directory=self.directory, env={'PATH': 'test'})
        return run

    def test_both_entire_sources_execute_and_native_errors_are_valid(self):
        run = self.invoke()
        complete = (smoke_test.ROOT / 'integrational_tests/tests/values.bsl').read_text(encoding='utf-8')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].kwargs['input'], without_service_filled_probes(complete))
        self.assertEqual(run.call_args_list[1].kwargs['input'], complete)

    def test_boolean_success_does_not_require_any_guessed_default(self):
        for index in range(24):
            self.records[index] = self.records[index].replace('[error]', '[value={"B",' + str(index % 2) + '}]')
        self.invoke()

    def test_missing_duplicate_reordered_and_extra_records_fail(self):
        changes = [self.records[:i] + self.records[i + 1:] for i in range(25)]
        changes += [self.records + self.records[:1],
                    [self.records[1], self.records[0]] + self.records[2:]]
        for changed in changes:
            with self.subTest(changed=changed[:2]), self.assertRaises(AssertionError):
                self.invoke(changed)
            self.directory.rmdir()

    def test_controls_wrong_types_and_exception_text_never_become_oracle(self):
        for value in ('[serialize-error]', '[value={"N",1}]', '[error: locale text]',
                      '[value={"B",2}]', '[error]\t', '[error]\r', '[error]\u2028'):
            records = self.records.copy()
            records[0] = records[0].replace('[error]', value)
            with self.subTest(value=value), self.assertRaises(AssertionError):
                self.invoke(records)
            self.directory.rmdir()

    def test_old_output_and_framing_cannot_be_truncated(self):
        for old, tail in ((self.old[:-1], ''), ('changed\n', ''), (self.old, '\n')):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                self.invoke(old=old, tail=tail)
            self.directory.rmdir()
