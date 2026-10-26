"""Source-only fixed-GMT probes; these tests do not predict native results."""
import hashlib
from pathlib import Path
import re
import unittest

from scripts.native_historical_replay import (
    CURRENT_DATES_BLOB, HISTORICAL_DATES_BLOB, git_blob, historical_dates_source,
)
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/dates.bsl'
NATIVE = ROOT / 'tests/fixtures/native_windows/dates.out'
FINAL = 'date.gmt-fraction.checkpoint.complete: [ok]'
FRACTIONS = ('0.0001', '0.4999', '0.5', '0.9999')


class FractionalTimezoneCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.raw = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        self.source = self.raw.decode('utf-8')
        self.historical = historical_dates_source(self.raw, NATIVE.read_bytes())
        self.expressions = {
            node.expression.arguments[0].value: node.expression.arguments[1].value
            for node in parse(self.source)
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьДату'
            and node.expression.arguments[0].value.startswith('gmt-fraction.')}

    def test_exact_source_append_preserves_helpers_and_original_scopes(self):
        self.assertEqual(git_blob(self.raw), CURRENT_DATES_BLOB)
        self.assertEqual(git_blob(self.historical), HISTORICAL_DATES_BLOB)
        self.assertTrue(self.raw.startswith(self.historical))
        append = self.raw[len(self.historical):].decode()
        self.assertNotRegex(append, r'\b(?:Процедура|Функция|Перем|Для|Пока|Выполнить|Вычислить)\b')
        self.assertEqual(self.source.count('Вычислить('), 1)
        routines = [node.name for node in parse(self.source) if isinstance(node, ast.Routine)]
        self.assertEqual(routines, ['НаблюдатьДату', 'ПроверитьКлючиДат'])
        self.assertTrue(append.endswith('Сообщить("' + FINAL + '");\n'))

    def test_numeric_projections_and_complete_bounded_matrix(self):
        self.assertEqual(len(self.expressions), 84)
        for label, expression in self.expressions.items():
            self.assertRegex(label, r'^gmt-fraction\.[a-z0-9.-]+$')
            self.assertLessEqual(len(expression), 300)
            self.assertNotRegex(expression, r'[;\r\n]')
            self.assertNotRegex(expression, r'(?i)\b(?:Eval|Execute|Import|CurrentDate|ValueToStringInternal)\b')
            self.assertIn(' - ', expression)
            self.assertTrue(parse('observed = ' + expression + ';'))
        for direction, method in (('local', 'ToLocalTime'), ('universal', 'ToUniversalTime')):
            for name, zone in (('zero', 'GMT+0'), ('positive', 'GMT+5:30'), ('negative', 'GMT-3:45')):
                for when, base in (('early', 'Date(2024,3,1,0,0,0)'), ('late', 'Date(2024,2,29,23,59,59)')):
                    for fraction in FRACTIONS:
                        key = f'gmt-fraction.{direction}.{name}.{when}.{fraction.replace(".", "-")}'
                        self.assertEqual(self.expressions[key], f'{method}({base} + {fraction},"{zone}") - {base}')
                for fraction in FRACTIONS:
                    expression = self.expressions[f'gmt-fraction.inverse.{direction}.{name}.{fraction.replace(".", "-")}']
                    self.assertIn('ToUniversalTime(', expression)
                    self.assertIn('ToLocalTime(', expression)
                    self.assertEqual(expression.count('"' + zone + '"'), 2)
        for direction, method in (('local', 'МестноеВремя'), ('universal', 'УниверсальноеВремя')):
            for fraction in FRACTIONS:
                self.assertIn(method + '(', self.expressions[f'gmt-fraction.alias.{direction}.{fraction.replace(".", "-")}'])
                self.assertEqual(self.expressions['gmt-fraction.input.' + fraction.replace('.', '-')],
                                 f'(Date(2024,2,29,23,59,59) + {fraction}) - Date(2024,2,29,23,59,59)')

    def test_all_records_complete_without_claiming_native_success(self):
        output, old_output = [], []
        Interpreter(output=output.append).execute(self.source)
        Interpreter(output=old_output.append).execute(self.historical.decode())
        self.assertEqual(output[:100], old_output)
        self.assertEqual(len(output), 185)
        self.assertEqual(output[-1], FINAL)
        self.assertEqual([line.split(': [', 1)[0] for line in output[100:-1]],
                         ['date.' + label for label in self.expressions])
        for line in output[100:-1]:
            self.assertRegex(line, r'^date\.gmt-fraction\.[a-z0-9.-]+: \[(?:error|serialize-error|\{"N",[^\n]+\})\]$')

    def test_historical_reconstruction_rejects_source_or_capture_mutations(self):
        output = NATIVE.read_bytes()
        self.assertEqual(historical_dates_source(self.raw.replace(b'\n', b'\r\n'), output), self.historical)
        mutations = (self.raw + b'\n', self.raw.replace(b'GMT+5:30', b'GMT+5:31', 1),
                     self.raw.replace(b'construct.parts', b'construct.other', 1), self.raw[:-1])
        for changed in mutations:
            with self.subTest(source_sha256=hashlib.sha256(changed).hexdigest()), self.assertRaises(ValueError):
                historical_dates_source(changed, output)
        for changed in (output + b'\n', output[:-1], output.replace(b'date.', b'wrong.', 1)):
            with self.subTest(output_sha256=hashlib.sha256(changed).hexdigest()), self.assertRaises(ValueError):
                historical_dates_source(self.raw, changed)


if __name__ == '__main__':
    unittest.main()
