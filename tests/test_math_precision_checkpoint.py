"""Bounded follow-up observations; native expected values are intentionally absent."""
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

ROOT = Path(__file__).resolve().parents[1]
START = '// Уточнение математической точности:'
PREVIOUS = 'math.checkpoint.complete: [ok]'
FINAL = 'math.precision-checkpoint.complete: [ok]'


def source():
    return (ROOT / 'integrational_tests/tests/numbers.bsl').read_text(encoding='utf-8-sig')


def calls():
    return [node.expression for node in parse(START + source().split(START, 1)[1].split(
                'Показать("math.precision-checkpoint.complete", "ok");', 1)[0])
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'ПроверитьМатематику']


class MathPrecisionCheckpointTests(unittest.TestCase):
    def outputs(self):
        output = []
        Interpreter(output=output.append).execute(source())
        lines = '\n'.join(output).replace('\r\n', '\n').replace('\r', '\n').splitlines()
        boundary = lines.index(PREVIOUS) + 1
        end = lines.index(FINAL, boundary) + 1
        return lines[:boundary], lines[boundary:end]

    def test_exact_case_count_and_unique_labels(self):
        probes = calls()
        self.assertEqual(len(probes), 18)
        labels = [probe.arguments[0].value for probe in probes]
        self.assertEqual(len(set(labels)), 18)
        self.assertTrue(all(label.startswith('precision.') for label in labels))
        expressions = [probe.arguments[1].value for probe in probes]
        self.assertEqual(len(set(expressions)), 18)

    def test_original_scenario_runtime_output_is_unchanged(self):
        # Run the exact original source independently. Its missing math functions
        # remain errors until implementation; they are not native expectations.
        original = source().split(START, 1)[0]
        output = []
        Interpreter(output=output.append).execute(original)
        self.assertEqual(self.outputs()[0], output)

    def test_owner_observation_labels_and_marker_preserved(self):
        owner = (ROOT / 'tests/fixtures/native_windows/numbers.out').read_text(
            encoding='utf-8-sig').splitlines()
        prefix = owner[:owner.index(PREVIOUS) + 1]
        self.assertEqual(len(prefix), 331)
        self.assertEqual([line.split(': ', 1)[0] for line in prefix],
                         [line.split(': ', 1)[0] for line in self.outputs()[0]])

    def test_all_observations_reach_own_sentinel(self):
        _, added = self.outputs()
        self.assertEqual(len(added), 19)
        self.assertEqual(added[-1], FINAL)
        self.assertEqual([line.split(': ', 1)[0] for line in added[:-1]],
                         ['math.' + call.arguments[0].value for call in calls()])
        for line in added[:-1]:
            self.assertRegex(line, r'^math\.precision\.[a-z.-]+: \[(?:error|serialize-error|\{[^\n]+\})\]$')

    def test_payloads_are_bounded_single_expressions(self):
        for probe in calls():
            label, expression = (argument.value for argument in probe.arguments)
            self.assertLess(len(expression), 100, label)
            self.assertNotRegex(expression, r'[;\n\r]')
            self.assertNotRegex(expression, r'(?i)\b(?:Import|Execute|Eval|While|For|Goto)\b')
            self.assertEqual(len(parse('x = ' + expression + ';')), 1)
        addition = source().split(START, 1)[1]
        self.assertNotRegex(addition, r'\b(?:Процедура|Функция|Пока|Для|Перейти|Выполнить|ОписаниеОшибки)\b')

    def test_conversion_and_power_paths_are_distinguished(self):
        expressions = {probe.arguments[1].value for probe in calls()}
        self.assertTrue({'3.1415926535897936 / 2', 'Tan(1.5707963267948968)',
                         'Tan(Number("1.5707963267948968"))',
                         'Cos(1.5707963267948968)',
                         'Exp(709.782712893383970000000001)',
                         'Exp(Number("709.78271289338397"))',
                         'Pow(3, -1)', 'Pow(1.1, 20)', 'Pow(2, 100)',
                         'Pow(10, 309.5)',
                         'Pow(1.234567890123456789012, 2)'}.issubset(expressions))


if __name__ == '__main__':
    unittest.main()
