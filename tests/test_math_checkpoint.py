"""Packaging and isolation of pending native observations; never a math oracle."""
from pathlib import Path
import re
import unittest

from yadinassi import Interpreter, ast
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/numbers.bsl'
START = '// Математический checkpoint:'
END = '// Разные порядки результата'
PREVIOUS = 'numeric-bits.checkpoint.complete: [ok]'
FINAL = 'math.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def normalize(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def calls():
    return [node.expression for node in parse(source().split(
                'Показать("math.checkpoint.complete", "ok");', 1)[0])
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'ПроверитьМатематику']


class MathCheckpointTests(unittest.TestCase):
    def outputs(self):
        result = []
        Interpreter(output=result.append).execute(source())
        lines = normalize('\n'.join(result) + '\n').splitlines()
        boundary = lines.index(PREVIOUS) + 1
        end = lines.index(FINAL, boundary) + 1
        return lines[:boundary], lines[boundary:end]

    def test_declarations_precede_body(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_exact_counts_labels_and_family(self):
        probes = calls()
        self.assertEqual(len(probes), 48)
        labels = [call.arguments[0].value for call in probes]
        self.assertEqual(len(set(labels)), 48)
        self.assertEqual(sum(label.startswith('string.') for label in labels), 3)
        families = {call.arguments[1].value.split('(', 1)[0] for call in probes
                    if not call.arguments[0].value.startswith('string.')}
        self.assertEqual(families, {'Sqrt', 'Log', 'Log10', 'Exp', 'Sin', 'Cos',
                                    'Tan', 'ASin', 'ACos', 'ATan', 'Pow'})

    def test_existing_native_output_is_exact_prefix(self):
        native = normalize((ROOT / 'integrational_tests/output/numbers.out').read_text(
            encoding='utf-8-sig')).splitlines()
        native_prefix = native[:native.index(PREVIOUS) + 1]
        self.assertEqual(self.outputs()[0], native_prefix)

    def test_every_case_reaches_sentinel(self):
        _, added = self.outputs()
        self.assertEqual(len(added), 49)
        self.assertEqual(added[-1], FINAL)
        labels = [line.split(': ', 1)[0] for line in added[:-1]]
        self.assertEqual(labels, ['math.' + call.arguments[0].value for call in calls()])
        for line in added[:-1]:
            self.assertRegex(line, r'^math\.[a-z0-9.-]+: \[(?:error|serialize-error|\{[^\n]+\})\]$')

    def test_dynamic_payloads_are_single_bounded_expressions(self):
        for call in calls():
            label, expression = (argument.value for argument in call.arguments)
            self.assertLess(len(expression), 100, label)
            self.assertNotRegex(expression, r'[;\n\r]')
            self.assertNotRegex(expression, r'(?i)\b(?:Import|Execute|Eval|While|For|Goto)\b')
            parsed = parse('x = ' + expression + ';')
            self.assertEqual(len(parsed), 1)
        helper = source().split(START, 1)[1].split(END, 1)[0]
        self.assertNotRegex(helper, r'\b(?:Пока|Для|Перейти|While|For|Goto|Выполнить|ОписаниеОшибки)\b')
        self.assertEqual(helper.count('Вычислить('), 1)

    def test_exact_edt_boundary_literals_are_preserved(self):
        expressions = {call.arguments[1].value for call in calls()}
        self.assertTrue({'Exp(709.78271289338397)', 'Exp(709.78271289338398)',
                         'Tan(3.1415926535897932 / 2)',
                         'Tan(3.1415926535897936 / 2)',
                         'Pow(0, 0)', 'Pow(0, -1)', 'Pow(-2, 0.5)',
                         'Pow(9007199254740993, 1)'}.issubset(expressions))

    def test_error_recovery_and_success_serialization(self):
        helper = START + source().split(START, 1)[1].split(END, 1)[0]
        output = []
        Interpreter(output=output.append).execute('''
Процедура Показать(Метка, Знач Значение)
    Сообщить(Метка + ": [" + Строка(Значение) + "]");
КонецПроцедуры
''' + helper + '''
ПроверитьМатематику("missing", "MissingMathFunction(2)");
ПроверитьМатематику("invalid", "Pow(2, )");
ПроверитьМатематику("number", "2 + 3");
ПроверитьМатематику("string", "Строка(5)");
''')
        self.assertEqual(output, ['math.missing: [error]', 'math.invalid: [error]',
                                 'math.number: [{"N",5}]', 'math.string: [{"S","5"}]'])


if __name__ == '__main__':
    unittest.main()
