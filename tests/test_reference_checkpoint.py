"""Probe safety and packaging only; new output is not a native oracle."""
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter
from yadinassi import ast
from yadinassi.parser import parse
from scripts.native_historical_replay import without_extended_exception_probes

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'integrational_tests/tests/functions.bsl'


class ReferenceCheckpointTests(unittest.TestCase):
    def test_declarations_precede_body(self):
        program = parse(SCRIPT.read_text(encoding='utf-8'))
        started = False
        for node in program:
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_all_cases_are_distinct_and_bounded(self):
        text = SCRIPT.read_text(encoding='utf-8')
        calls = re.findall(r'^Проверить(?:АргументСсылки|ФункциональныйНовый)\("([^"]+)"',
                           text, re.MULTILINE)
        self.assertEqual(len(calls), 28)
        self.assertEqual(len(set(calls)), 28)
        helpers = text.split('// Проверка привязки свойства/индекса:', 1)[1].split(
            'Показать(Сложить(2, 3));', 1)[0]
        self.assertNotRegex(helpers, r'\b(?:Пока|Для|Перейти|While|For|Goto)\b')

    def test_local_run_preserves_native_prefix_and_reaches_sentinel(self):
        output = []
        Interpreter(output=output.append).execute(without_extended_exception_probes(
            SCRIPT.read_text(encoding='utf-8')))
        native = (ROOT / 'tests/fixtures/native_windows/functions.out').read_text(encoding='utf-8-sig')
        native_lines = native.splitlines()
        boundary = native_lines.index('execute.checkpoint.complete: [ok]') + 1
        prefix = native_lines[:boundary]
        self.assertEqual(output[:len(prefix)], prefix)
        added = output[len(prefix):]
        self.assertEqual(len(added), 29)
        self.assertEqual(added[-1], 'reference-new.checkpoint.complete: [ok]')
        for line in added[:-1]:
            self.assertRegex(line, r'^(reference|dynamic-new)\.[^:]+: \[(ok|error);')
            if line.startswith('reference.'):
                for field in ('fixed-array', 'fixed-property', 'fixed-map', 'missing', 'calls'):
                    self.assertIn(';' + field + '=', line)


if __name__ == '__main__':
    unittest.main()
