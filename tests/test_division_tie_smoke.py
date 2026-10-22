"""Synthetic frozen-smoke framing contracts, not native rounding evidence."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import smoke_test
from test_division_tie_checkpoint import probes


class DivisionTieSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / 'capture'
        self.prefix = (smoke_test.ROOT / 'tests/fixtures/native_windows/numbers.out').read_text(encoding='utf-8-sig')
        self.records = json.loads((smoke_test.ROOT / 'tests/fixtures/division_half_ties_linux.json').read_text(encoding='utf-8'))['records']

    def invoke(self, output, status=0, stderr=''):
        result = subprocess.CompletedProcess([], status, output, stderr)
        with patch.object(smoke_test.subprocess, 'run', return_value=result) as run, patch('builtins.print'):
            smoke_test.check_division_tie_checkpoint('synthetic-executable', directory=self.directory, env={'synthetic': 'yes'})
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['synthetic-executable', '-'])
        source = (smoke_test.ROOT / 'integrational_tests/tests/numbers.bsl').read_text(encoding='utf-8')
        self.assertEqual(run.call_args.kwargs['input'], source)
        self.assertEqual(run.call_args.kwargs['timeout'], 30)

    def output(self, records=None):
        return self.prefix + '\n'.join(self.records if records is None else records) + '\n'

    def test_full_source_executes_with_complete_native_prefix_and_every_new_label(self):
        self.invoke(self.output())

    def test_every_changed_native_value_or_error_is_rejected(self):
        for index in range(len(self.records) - 1):
            records = self.records.copy()
            records[index] = records[index].split(': [', 1)[0] + ': [error]'
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.invoke(self.output(records))
            self.directory.rmdir()

    def test_every_record_is_mandatory(self):
        for index in range(len(self.records)):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.invoke(self.output(self.records[:index] + self.records[index+1:]))
            self.directory.rmdir()

    def test_wrong_order_duplicates_labels_payload_framing_and_prefix_are_rejected(self):
        bad = []
        records = self.records.copy(); records[0],records[1]=records[1],records[0];bad.append(self.output(records))
        records = self.records.copy();records[0]=records[1];bad.append(self.output(records))
        bad += [self.output().replace('math.division-tie.', 'wrong.', 1),self.output()+'\n', self.output()[:-1],
                self.output().replace('[{"N",0.000000003725290298461914063}]', '[bad\tvalue]',1), self.output().replace('[{"N",0.000000003725290298461914063}]', '[{"S","unexpected"}]',1),
                self.output().replace('div.', 'bad.',1)]
        bad += [self.output().replace('[{"N",0.000000003725290298461914063}]', '[' + value + ']', 1)
                for value in ('{"N",--..}', '{"N",1.2.3}', '{"B",2}', '{"B",-1}')]
        for output in bad:
            with self.subTest(output=output[-100:]), self.assertRaises(AssertionError):
                self.invoke(output)
            self.directory.rmdir()

    def test_nonzero_exit_and_stderr_are_rejected(self):
        for status,stderr in ((1,''),(0,'unexpected')):
            with self.assertRaises(AssertionError):
                self.invoke(self.output(),status,stderr)
            self.directory.rmdir()


if __name__ == '__main__':
    unittest.main()
