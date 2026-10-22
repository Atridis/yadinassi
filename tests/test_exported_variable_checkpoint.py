"""Parser bootstrap and genuine native probes; no assumed native field semantics."""
import hashlib
from pathlib import Path
import re
import tempfile
import unittest

from scripts.native_historical_replay import (
    EXPORTED_VARIABLE_BASE_BLOB, EXPORTED_VARIABLE_PROBE_BLOCKS,
    git_blob, without_exported_variable_probes,
)
from yadinassi import BSLError, Interpreter, ast
from yadinassi.parser import parse
from yadinassi.native_targets import WINDOWS_8_3_27_2342, LINUX_8_3_27_1508

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('object-context', 'initial-undefined', 'read', 'write-routine-read',
          'routine-write-read', 'private-list-entry', 'private-write',
          'second-export-entry', 'undeclared-read', 'undeclared-write',
          'local-shadow', 'reference-alias', 'value-parameter',
          'reference-after-error', 'collection-shared')


class ExportedVariableCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8')
        cls.previous = without_exported_variable_probes(cls.source)

    def test_exact_inverse_and_real_negative_mutations_for_both_checkout_endings(self):
        self.assertEqual(git_blob(self.previous.encode()), EXPORTED_VARIABLE_BASE_BLOB)
        self.assertEqual(hashlib.sha256(self.previous.encode()).hexdigest(),
                         '25974f519be63a5283731c68d70b59d0ee20b39cd706f96998031b12f5429094')
        for ending in ('\n', '\r\n'):
            transported = self.source.replace('\n', ending)
            normalized = transported.replace('\r\n', '\n')
            self.assertEqual(without_exported_variable_probes(normalized), self.previous)
            mutants = (transported + ending,
                       transported.replace('МодульноеВычисления', 'ChangedVariable', 1),
                       transported.replace(EXPORTED_VARIABLE_PROBE_BLOCKS[0][0].rstrip('\n'), '// removed', 1),
                       transported + EXPORTED_VARIABLE_PROBE_BLOCKS[2][0].replace('\n', ending))
            for mutant in mutants:
                self.assertNotEqual(mutant, transported)
                with self.assertRaises(ValueError):
                    without_exported_variable_probes(mutant.replace('\r\n', '\n'))

    def test_per_name_bilingual_metadata_and_legacy_ast_default(self):
        for declaration in ('Var A, B Export, C, D Export;', 'Перем A, B Экспорт, C, D Экспорт;'):
            node, = parse(declaration)
            self.assertEqual(node.names, ['A', 'B', 'C', 'D'])
            self.assertEqual(node.exported_names, ('B', 'D'))
            self.assertEqual(ast.Var(node.token, ['A']).exported_names, ())
        node, = parse('#Region declarations\nVar A Export;\n#EndRegion')
        self.assertEqual(node.exported_names, ('A',))

    def test_non_module_exports_fail_explicitly_before_execution(self):
        for code in ('Procedure P() Var A Export; EndProcedure',
                     'If True Then Var A Export; EndIf;',
                     'Try Var A Export; Except EndTry;',
                     'For i=1 To 1 Do Var A Export; EndDo;'):
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'только на уровне модуля'):
                parse(code)
        for code in ('Var A Export Export;', 'Var A Export,;', 'Var Export A;'):
            with self.subTest(code=code), self.assertRaises(BSLError):
                parse(code)

    def test_declarations_and_helpers_precede_executable_code(self):
        started = False
        routines_started = False
        for node in parse(self.source):
            if isinstance(node, ast.Routine):
                routines_started = True
            elif isinstance(node, ast.Var):
                self.assertFalse(routines_started, node)
            if isinstance(node, (ast.Var, ast.Routine)):
                self.assertFalse(started, node)
            else:
                started = True
        body = self.source.split(EXPORTED_VARIABLE_PROBE_BLOCKS[2][0])[1].split(
            EXPORTED_VARIABLE_PROBE_BLOCKS[2][1])[0]
        self.assertEqual(tuple(re.findall(r'^ObserveExportProbe\("([^"]+)"', body, re.M)), LABELS)
        self.assertIn('ExportProbeAlias(ThisObject.ExportProbeValue, ThisObject.ExportProbeValue)', body)
        self.assertIn('ExportProbeFail(ThisObject.ExportProbeValue)', body)
        self.assertIn('ThisObject.ExportProbePrivate = 59', body)
        self.assertNotIn('ОписаниеОшибки', body)

    def test_bootstrap_preserves_all_116_outputs_and_completes_15_real_observations(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            previous, current = [], []
            Interpreter(previous.append, native_target=target).execute(self.previous)
            Interpreter(current.append, native_target=target).execute(self.source)
            self.assertEqual(len(previous), 116)
            self.assertEqual(current[:116], previous)
            self.assertEqual(len(current), 131)
            self.assertEqual([row.split(':')[0] for row in current[116:]],
                             ['export-variable.' + label for label in LABELS])
            # This is a local bootstrap limitation, not a native expected answer.
            self.assertTrue(current[116].startswith('export-variable.object-context: [error;'))
            for row in current[116:]:
                self.assertRegex(row, r': \[(?:ok|error);result=.+;value=.+;private=.+\]$')

    def test_import_fields_remain_fail_closed_in_parser_only_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'mod.bsl').write_text('Var Public Export; Public=11;', encoding='utf-8')
            for operation in ('Message(mod.Public);', 'mod.Public=12;', 'Message(mod.interpreter);'):
                with self.subTest(operation=operation), self.assertRaises(BSLError):
                    Interpreter(lambda _: None).execute('// #Import mod.bsl\n' + operation, str(root / 'main.bsl'))


if __name__ == '__main__':
    unittest.main()
