"""Frozen-smoke orchestration contracts, not additional native 1C evidence.

Subprocess responses use synthetic earlier output plus native-backed suffixes.
The fixed String and Chars records are copied from native artifact fixtures.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import smoke_test
from scripts.native_historical_replay import without_fixed_string_probes, without_service_filled_probes


class FixedStringSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.complete = (smoke_test.ROOT / 'integrational_tests/tests/values.bsl').read_text(
            encoding='utf-8')
        cls.full_source = cls.complete
        cls.complete = without_service_filled_probes(cls.complete)
        cls.previous = without_fixed_string_probes(cls.complete)
        cls.fixture = json.loads(
            (smoke_test.ROOT / 'tests/fixtures/chars_namespace_linux.json').read_text(
                encoding='utf-8'))
        cls.boundary = 'types-extra.checkpoint.complete: [ok]\n'
        # Earlier values records may contain embedded newlines. Preserve this
        # entire opaque prefix, not a guessed physical-line or record count.
        cls.old_output = ('synthetic earlier observation: [line one\nline two]\n'
                          + cls.boundary + '\n'.join(cls.fixture['records']) + '\n')
        cls.fixed_fixture = json.loads(
            (smoke_test.ROOT / 'tests/fixtures/fixed_string_default_linux.json').read_text(
                encoding='utf-8'))
        cls.new_records = cls.fixed_fixture['records']
        cls.new_suffix = '\n'.join(cls.new_records) + '\n'
        cls.current_output = cls.old_output + cls.new_suffix
        cls.member_output = ''.join(f'{code}\n' * 8 for code in (13, 11, 160, 10, 12, 9))
        cls.member_output += '10\n' + '1\n' * 5

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source_directory = self.root / 'integrational_tests/tests'
        source_directory.mkdir(parents=True)
        self.source_path = source_directory / 'values.bsl'
        self.source_path.write_text(self.full_source, encoding='utf-8')
        fixture_directory = self.root / 'tests/fixtures'
        fixture_directory.mkdir(parents=True)
        self.fixture_path = fixture_directory / 'chars_namespace_linux.json'
        self.fixture_path.write_text(json.dumps(self.fixture), encoding='utf-8')
        (fixture_directory / 'fixed_string_default_linux.json').write_text(
            json.dumps(self.fixed_fixture), encoding='utf-8')
        self.invocation = 0
        self.executable = str(self.root / 'dist/Yadinassi.exe')
        self.env = {'PATH': 'synthetic', 'PYTHONIOENCODING': 'utf-8'}
        patcher = patch.object(smoke_test, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def results(self):
        responses = [subprocess.CompletedProcess([], 0, self.member_output, '')
                     for _ in range(6)]
        responses.append(subprocess.CompletedProcess([], 1, '42\n', 'пока не поддерживается'))
        responses.append(subprocess.CompletedProcess([], 0, self.old_output, ''))
        responses.append(subprocess.CompletedProcess([], 0, self.current_output, ''))
        return responses

    def invoke(self):
        self.invocation += 1
        with patch('builtins.print'):
            smoke_test.check_chars_namespace(
                self.executable, directory=self.root / f'capture-{self.invocation}', env=self.env)

    def reject_current(self, stdout):
        responses = self.results()
        responses[-1].stdout = stdout
        with patch.object(smoke_test.subprocess, 'run', side_effect=responses) as run:
            with self.assertRaisesRegex(AssertionError, 'current fixed String checkpoint'):
                self.invoke()
            self.assertEqual(run.call_count, 9)

    def test_fixture_bound_previous_and_complete_current_source_both_execute(self):
        self.assertEqual(hashlib.sha256(self.previous.encode()).hexdigest(),
                         self.fixture['source_sha256'])
        self.assertEqual(len(self.fixture['records']), 100)
        with patch.object(smoke_test.subprocess, 'run', side_effect=self.results()) as run:
            self.invoke()
        self.assertEqual(run.call_count, 9)
        self.assertEqual(run.call_args_list[-2].kwargs['input'], self.previous)
        self.assertEqual(run.call_args_list[-1].kwargs['input'], self.complete)
        for call in run.call_args_list[-2:]:
            self.assertEqual(call.args[0], [self.executable, '-'])
            self.assertEqual(call.kwargs['encoding'], 'utf-8')
            self.assertEqual(call.kwargs['timeout'], 30)
            self.assertEqual(call.kwargs['env'], self.env)

    def test_wrong_historical_fixture_hash_rejected_before_checkpoint_execution(self):
        changed = {**self.fixture, 'source_sha256': '0' * 64}
        self.fixture_path.write_text(json.dumps(changed), encoding='utf-8')
        with patch.object(smoke_test.subprocess, 'run', side_effect=self.results()) as run:
            with self.assertRaisesRegex(AssertionError, 'source identity changed'):
                self.invoke()
            self.assertEqual(run.call_count, 7)

    def test_changed_previous_source_rejected_before_checkpoint_execution(self):
        self.source_path.write_text(self.full_source.replace('NULL', 'Null', 1), encoding='utf-8')
        with patch.object(smoke_test.subprocess, 'run', side_effect=self.results()) as run:
            with self.assertRaisesRegex(ValueError, '^NStr candidate source binding changed$'):
                self.invoke()
            self.assertEqual(run.call_count, 7)

    def test_every_native_chars_record_remains_mandatory(self):
        for index in range(100):
            records = self.fixture['records'].copy()
            records[index] += 'changed'
            responses = self.results()
            responses[-2].stdout = self.old_output.split(self.boundary)[0] + self.boundary
            responses[-2].stdout += '\n'.join(records) + '\n'
            with self.subTest(record=index), \
                    patch.object(smoke_test.subprocess, 'run', side_effect=responses) as run:
                with self.assertRaisesRegex(AssertionError, 'complete native Chars checkpoint'):
                    self.invoke()
                self.assertEqual(run.call_count, 8)

    def test_current_output_preserves_every_previous_byte(self):
        changes = [self.old_output.replace('earlier', 'altered', 1),
                   self.old_output[:-1], self.old_output + '\n',
                   self.old_output.replace(self.fixture['records'][0], 'changed', 1)]
        for changed in changes:
            with self.subTest(previous=changed[:80]):
                self.reject_current(changed + self.new_suffix)

    def test_every_appended_record_and_completion_marker_is_mandatory(self):
        for index in range(16):
            changed = self.new_records[:index] + self.new_records[index + 1:]
            with self.subTest(missing=index):
                self.reject_current(self.old_output + '\n'.join(changed) + '\n')
        self.reject_current(self.current_output + self.new_records[0] + '\n')

    def test_duplicate_reordered_or_wrong_labels_are_rejected_without_value_predictions(self):
        changes = []
        duplicate = self.new_records.copy()
        duplicate[1] = duplicate[0]
        changes.append(duplicate)
        reordered = self.new_records.copy()
        reordered[0], reordered[1] = reordered[1], reordered[0]
        changes.append(reordered)
        renamed = self.new_records.copy()
        renamed[0] = renamed[0].replace('fixed1', 'unknown')
        changes.append(renamed)
        for changed in changes:
            with self.subTest(records=changed[:2]):
                self.reject_current(self.old_output + '\n'.join(changed) + '\n')

    def test_raw_controls_unicode_separators_and_noncanonical_framing_are_rejected(self):
        for control in ('\x00', '\t', '\r', '\v', '\f', '\x1c', '\x85', '\u2028', '\u2029'):
            changed = self.new_records.copy()
            changed[0] += control + 'changed'
            with self.subTest(control=repr(control)):
                self.reject_current(self.old_output + '\n'.join(changed) + '\n')
        for suffix in (self.new_suffix[:-1], self.new_suffix + '\n',
                       self.new_suffix.replace('\n', '\r\n')):
            with self.subTest(framing=repr(suffix[-80:])):
                self.reject_current(self.old_output + suffix)

    def test_every_measured_fixed_payload_remains_exact(self):
        for index in range(16):
            changed = self.new_records.copy()
            changed[index] += 'changed'
            with self.subTest(record=index):
                self.reject_current(self.old_output + '\n'.join(changed) + '\n')

    def test_wrong_fixed_fixture_source_hash_rejected(self):
        changed = {**self.fixed_fixture, 'source_sha256': '0' * 64}
        (self.root / 'tests/fixtures/fixed_string_default_linux.json').write_text(
            json.dumps(changed), encoding='utf-8')
        with patch.object(smoke_test.subprocess, 'run', side_effect=self.results()) as run:
            with self.assertRaisesRegex(AssertionError, 'Fixed String checkpoint source identity'):
                self.invoke()
            self.assertEqual(run.call_count, 8)

    def test_checkpoint_exit_failures_and_stderr_are_never_accepted(self):
        for index in (7, 8):
            for field, value in (('returncode', 1), ('stderr', 'unexpected')):
                responses = self.results()
                setattr(responses[index], field, value)
                with self.subTest(index=index, field=field), \
                        patch.object(smoke_test.subprocess, 'run', side_effect=responses) as run:
                    with self.assertRaises(AssertionError):
                        self.invoke()
                    self.assertEqual(run.call_count, index + 1)


if __name__ == '__main__':
    unittest.main()
