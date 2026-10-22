"""Five source-only context discriminators; no predicted native semantics."""
import hashlib
from pathlib import Path
import re
import unittest

from scripts.native_historical_replay import (
    EXCEPTION_CONTEXT_BASE_BLOB, EXCEPTION_CONTEXT_PROBE_BLOCKS,
    HISTORICAL_FUNCTIONS_BLOB, git_blob, historical_functions_source,
    without_exception_context_probes,
)
from yadinassi import Interpreter, ast
from yadinassi.native_targets import WINDOWS_8_3_27_2342, LINUX_8_3_27_1508
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('direct', 'eval', 'direct-nested-try', 'eval-nested-try', 'outside-empty')
BASE_SHA256 = 'b8c1141049f3a604addcdb7e967e045a7a9e6d72258fccb68167417a622dedca'


def literal(text):
    return '"' + text.replace('"', '""') + '"'


class ExceptionContextCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8')
        cls.previous = without_exception_context_probes(cls.source)

    def test_inverse_restores_exact_native_verified_111_source(self):
        self.assertEqual(git_blob(self.previous.encode()), EXCEPTION_CONTEXT_BASE_BLOB)
        self.assertEqual(hashlib.sha256(self.previous.encode()).hexdigest(), BASE_SHA256)
        for ending in ('\n', '\r\n'):
            transported = self.source.replace('\n', ending).replace('\r\n', '\n')
            self.assertEqual(without_exception_context_probes(transported), self.previous)
        for mutant in (self.source + '\n', '\ufeff' + self.source,
                       self.source.replace('exception.handler-state:', 'changed.handler-state:', 1),
                       self.source.replace(EXCEPTION_CONTEXT_PROBE_BLOCKS[0][1], '// missing\n', 1),
                       self.source + EXCEPTION_CONTEXT_PROBE_BLOCKS[1][0]):
            with self.subTest(mutant=mutant[-60:]), self.assertRaises(ValueError):
                without_exception_context_probes(mutant)

    def test_exact_two_by_two_pairing_without_extra_handlers_before_capture(self):
        body = self.source.split(EXCEPTION_CONTEXT_PROBE_BLOCKS[1][0])[1].split(
            EXCEPTION_CONTEXT_PROBE_BLOCKS[1][1])[0]
        expected = ''
        for label, expression, nested in (
                ('direct', 'ErrorInfo()', False), ('eval', 'Eval("ErrorInfo()")', False),
                ('direct-nested-try', 'ErrorInfo()', True),
                ('eval-nested-try', 'Eval("ErrorInfo()")', True)):
            capture = ('Инфо = ' + expression + '; Внутри = Инфо.Description = "exception-context"; '
                       'Статус = "captured";')
            if nested:
                capture = 'Try ' + capture + ' Except Статус = "capture-error"; EndTry;'
            code = 'Try Raise "exception-context"; Except ' + capture + ' EndTry;'
            expected += 'ПроверитьКонтекстОшибки(' + literal(label) + ', ' + literal(code) + ');\n'
        code = 'Инфо = ErrorInfo(); Внутри = Инфо.Description = ""; Статус = "captured";'
        expected += 'ПроверитьКонтекстОшибки("outside-empty", ' + literal(code) + ');\n'
        self.assertEqual(body, expected)
        self.assertEqual(tuple(re.findall(r'^ПроверитьКонтекстОшибки\("([^"]+)"', body, re.M)), LABELS)

    def test_helper_declarations_are_bounded_and_only_read_saved_info_after_capture(self):
        started = False
        for node in parse(self.source):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True
        helper = self.source.split(EXCEPTION_CONTEXT_PROBE_BLOCKS[0][0])[1].split(
            EXCEPTION_CONTEXT_PROBE_BLOCKS[0][1])[0]
        self.assertNotRegex(helper, r'\b(?:Пока|Для|Перейти|While|For|Goto)\b')
        self.assertEqual(helper.count('Выполнить(Код);'), 1)
        self.assertIn('Инфо.Description = """"', helper)
        self.assertIn('Инфо.Cause = Undefined', helper)
        for category in ('AllErrors', 'ScriptRuntimeError', 'ScriptCompileError',
                         'ExceptionRaisedFromScript', 'ConfigurationError', 'OtherError'):
            self.assertIn('Инфо.IsErrorOfCategory(ErrorCategory.' + category + ')', helper)
        for excluded in ('ModuleName', 'LineNumber', 'InitialString', 'ОписаниеОшибки()',
                         'forbidden-category', 'Raise('):
            self.assertNotIn(excluded, helper)

    def test_old_runtime_keeps_every_111_prefix_record_and_appends_only_five(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            old, current = [], []
            Interpreter(old.append, native_target=target).execute(self.previous)
            Interpreter(current.append, native_target=target).execute(self.source)
            self.assertEqual(len(old), 111)
            self.assertEqual(current[:111], old)
            self.assertEqual(len(current), 116)
            self.assertEqual([row.split(':', 1)[0] for row in current[111:]],
                             ['exception-context.' + label for label in LABELS])
            for row in current[111:]:
                self.assertRegex(row, r': \[(captured|capture-error|execute-error|not-captured);inside=')
                for field in ('type', 'description', 'description-empty', 'cause-undefined',
                              'all', 'runtime', 'compile', 'raised', 'configuration', 'other'):
                    self.assertIn(';' + field + '=', row)

    def test_frozen_unit_and_binary_routes_share_the_same_exact_projection(self):
        from scripts import smoke_test
        import test_native_outputs
        from test_native_1c_full_stage import suite
        self.assertIs(smoke_test.historical_functions_source, historical_functions_source)
        self.assertIs(test_native_outputs.historical_functions_source, historical_functions_source)
        output = (ROOT / 'tests/fixtures/native_windows/functions.out').read_bytes()
        self.assertEqual(git_blob(historical_functions_source(self.source.encode(), output)),
                         HISTORICAL_FUNCTIONS_BLOB)
        self.assertEqual(suite.generated_module(self.source.encode()).decode('utf-8-sig'), self.source)
        self.assertEqual(len(suite.INPUT_FILES) + 1, 24)
        self.assertEqual(len(suite.SCENARIOS), 6)


if __name__ == '__main__':
    unittest.main()
