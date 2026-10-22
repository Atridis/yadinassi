"""Run the frozen export hook via the real Python CLI, not native 1C evidence."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import smoke_test


REAL_RUN = subprocess.run


class ExportedVariableSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.invocations = 0
        self.env = {key: value for key, value in os.environ.items()
                    if key not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'YADINASSI_TIMEZONE')}
        self.env['PYTHONIOENCODING'] = 'utf-8'

    def invoke(self, *, corrupt=None, module_mutation=None):
        self.invocations += 1
        directory = self.root / f'capture-{self.invocations}'
        calls = []

        def python_cli(command, **kwargs):
            self.assertEqual(command[0], 'real-python-cli')
            self.assertEqual(kwargs['env'], self.env)
            self.assertEqual(kwargs['cwd'], directory)
            self.assertEqual(kwargs['timeout'], 30)
            self.assertEqual(kwargs['encoding'], 'utf-8')
            index = len(calls)
            calls.append(command)
            if command[1] not in ('-c', '-'):
                self.assertTrue(Path(command[1]).read_bytes().startswith(b'\xef\xbb\xbf'))
            if index == 3 and module_mutation is not None:
                path = directory / 'mod.bsl'
                original = path.read_text(encoding='utf-8-sig')
                old, new = module_mutation
                self.assertEqual(original.count(old), 1)
                path.write_text(original.replace(old, new), encoding='utf-8-sig')
            # No shell or executable wrapper: this adapter is portable to Windows.
            environment = dict(kwargs['env'], PYTHONPATH=str(smoke_test.ROOT))
            result = REAL_RUN([sys.executable, '-m', 'yadinassi', *command[1:]],
                              **dict(kwargs, env=environment))
            if corrupt is not None:
                result = corrupt(index, result)
            return result

        with patch.object(smoke_test.subprocess, 'run', side_effect=python_cli), \
                patch('builtins.print'):
            smoke_test.check_exported_module_variables(
                'real-python-cli', directory=directory, env=self.env)
        return directory, calls

    def test_exact_hook_runs_real_cli_declarations_and_ready_imported_fields(self):
        directory, calls = self.invoke()
        self.assertEqual(calls, [
            ['real-python-cli', '-c', smoke_test.EXPORT_VARIABLE_DECLARATIONS],
            ['real-python-cli', str(directory / 'Переменные.bsl')],
            ['real-python-cli', '-'],
            ['real-python-cli', str(directory / 'ИмпортПеременных.bsl')],
        ])
        self.assertEqual((directory / 'mod.bsl').read_text(encoding='utf-8-sig'),
                         smoke_test.EXPORT_VARIABLE_MODULE)
        # A real successful imported-field read would fail the old parser-only hook.
        self.assertTrue(smoke_test.EXPORT_VARIABLE_IMPORT_OUTPUT.startswith('11\n31\n43\n'))

    def test_each_launch_requires_exact_output_zero_exit_and_empty_stderr(self):
        for target in range(4):
            for attribute, value in (('stdout', 'wrong\n'), ('returncode', 1),
                                     ('stderr', 'unexpected diagnostic')):
                def corrupt(index, result):
                    if index == target:
                        setattr(result, attribute, value)
                    return result

                with self.subTest(launch=target, attribute=attribute), \
                        self.assertRaises(AssertionError):
                    self.invoke(corrupt=corrupt)

    def test_imported_output_rejects_missing_extra_and_reordered_records(self):
        for mutation in (lambda output: output.split('\n', 1)[1],
                         lambda output: output + 'unexpected\n',
                         lambda output: output.replace('11\n31\n', '31\n11\n', 1)):
            def corrupt(index, result):
                if index == 3:
                    result.stdout = mutation(result.stdout)
                return result

            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    AssertionError, 'Exported-module variable runtime failed'):
                self.invoke(corrupt=corrupt)

    def test_real_module_semantic_mutations_are_rejected(self):
        mutations = (
            ('Var Private, Value Export, After;', 'Var Private Export, Value Export, After;'),
            ('Var Private, Value Export, After;', 'Var Private, Value Export, After Export;'),
            ('Procedure Alias(first, second)', 'Procedure Alias(Val first, second)'),
            ('Function Copy(Val slot)', 'Function Copy(slot)'),
            ('slot=53; Raise', 'slot=52; Raise'),
            ('Return receiver = ThisObject And receiver = ЭтотОбъект;', 'Return False;'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    AssertionError, 'Exported-module variable runtime failed'):
                self.invoke(module_mutation=mutation)


if __name__ == '__main__':
    unittest.main()
