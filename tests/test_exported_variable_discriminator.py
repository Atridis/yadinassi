"""Static/Execute source discriminator and measured initialization diagnostics."""
import hashlib
from pathlib import Path
import re
import unittest
from scripts.native_historical_replay import (
    EXPORTED_CONTEXT_BASE_BLOB, EXPORTED_CONTEXT_PROBE_BLOCKS,
    git_blob, without_exported_context_probes, without_exported_variable_probes,
    without_exported_postcreate_probes,
)
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi.native_targets import WINDOWS_8_3_27_2342, LINUX_8_3_27_1508
ROOT = Path(__file__).resolve().parents[1]
LABELS = ('static-read', 'static-write', 'static-routine', 'execute-read', 'execute-routine')

class ExportedContextDiscriminatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = without_exported_postcreate_probes(
            (ROOT / 'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8'))
        cls.previous = without_exported_context_probes(cls.source)

    def test_exact_full131_inverse_and_real_lf_crlf_mutations(self):
        self.assertEqual(git_blob(self.previous.encode()), EXPORTED_CONTEXT_BASE_BLOB)
        self.assertEqual(hashlib.sha256(self.previous.encode()).hexdigest(),
                         'fe5334993790244908376e2768545b271a36b1a1a63cbf05452ce8be4b79d40c')
        self.assertEqual(without_exported_variable_probes(self.source),
                         without_exported_variable_probes(self.previous))
        for ending in ('\n', '\r\n'):
            transported = self.source.replace('\n', ending)
            self.assertEqual(without_exported_context_probes(transported.replace('\r\n', '\n')), self.previous)
            for mutant in (transported + ending,
                    transported.replace('МодульноеВычисления', 'ChangedVariable', 1),
                    transported.replace(EXPORTED_CONTEXT_PROBE_BLOCKS[0][0].rstrip('\n'), '// removed', 1),
                    transported + EXPORTED_CONTEXT_PROBE_BLOCKS[1][0].replace('\n', ending)):
                self.assertNotEqual(mutant, transported)
                with self.assertRaises(ValueError):
                    without_exported_context_probes(mutant.replace('\r\n', '\n'))

    def test_static_and_dynamic_paths_with_only_bounded_diagnostics(self):
        self.assertEqual(tuple(re.findall(r'^ObserveExportContext\("([^"]+)"', self.source, re.M)), LABELS)
        helper = self.source.split(EXPORTED_CONTEXT_PROBE_BLOCKS[0][0])[1].split(
            EXPORTED_CONTEXT_PROBE_BLOCKS[0][1])[0]
        for statement in ('Result = ThisObject.ExportProbeValue;',
                          'ThisObject.ExportProbeValue = 31;',
                          'Result = ThisObject.ExportProbeRead();', 'Execute(Code);'):
            self.assertIn(statement, helper)
        message = helper[helper.index('    Message('):]
        self.assertNotIn('Description', message)
        self.assertNotIn('ErrorInfo', message)
        for label in ('none', 'other', 'field-missing', 'method-missing'):
            self.assertIn('"' + label + '"', helper)
        started = False
        for node in parse(self.source):
            if isinstance(node, (ast.Var, ast.Routine)):
                self.assertFalse(started)
            else:
                started = True

    def test_full136_measured_initialization_and_unmodified131_prefix(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            previous, current = [], []
            Interpreter(previous.append, native_target=target).execute(self.previous)
            Interpreter(current.append, native_target=target).execute(self.source)
            self.assertEqual(len(previous), 131)
            self.assertEqual(current[:131], previous)
            self.assertEqual(len(current), 136)
            self.assertEqual([row.split(':')[0] for row in current[131:]],
                             ['export-context.' + label for label in LABELS])
            kinds = ('field-missing', 'field-missing', 'method-missing',
                     'field-missing', 'method-missing')
            for label, kind, row in zip(LABELS, kinds, current[131:]):
                # Exact bounded diagnostics independently captured in native run 39864376445.
                self.assertEqual(row, 'export-context.' + label + ': [error;kind=' + kind +
                                 ';named={"B",1};result={"U"};value={"N",11}]')
                self.assertNotIn('Description', row)

if __name__ == '__main__':
    unittest.main()
