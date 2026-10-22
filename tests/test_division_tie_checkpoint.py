"""Source-only exact-half matrix; local execution is not native rounding evidence."""
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import re
import unittest

from scripts.native_historical_replay import (
    historical_numbers_source, git_blob, HISTORICAL_NUMBERS_BLOB,
    CURRENT_NUMBERS_BLOB, HISTORICAL_NUMBERS_OUTPUT_BLOB,
)
from yadinassi import Interpreter, ast
from yadinassi.parser import parse
from yadinassi.values import divide

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/numbers.bsl'
OUTPUT = ROOT / 'tests/fixtures/native_windows/numbers.out'
START = '// Begin exact division half-tie observations.\n'
END = '// End exact division half-tie observations.\n'


def probes():
    addition = SOURCE.read_text(encoding='utf-8').split(START, 1)[1].split(END, 1)[0]
    return {node.expression.arguments[0].value: node.expression.arguments[1].value
            for node in parse(addition) if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and node.expression.callee.name == 'ПроверитьМатематику'}


class DivisionTieCheckpointTests(unittest.TestCase):
    def test_exact_source_reconstruction_preserves_all_original_observations(self):
        source, output = SOURCE.read_bytes(), OUTPUT.read_bytes()
        historical = historical_numbers_source(source, output)
        self.assertEqual(git_blob(source.replace(b'\r\n', b'\n')), CURRENT_NUMBERS_BLOB)
        self.assertEqual(git_blob(historical), HISTORICAL_NUMBERS_BLOB)
        self.assertEqual(git_blob(output.replace(b'\r\n', b'\n')), HISTORICAL_NUMBERS_OUTPUT_BLOB)
        before, after = [], []
        Interpreter(before.append).execute(historical.decode('utf-8'))
        Interpreter(after.append).execute(source.decode('utf-8'))
        self.assertEqual(len(before), 350)
        self.assertEqual(before, output.decode('utf-8-sig').splitlines())
        self.assertEqual(after[:350], before)
        self.assertEqual(len(after), 421)
        self.assertEqual(after[-1], 'division-tie.checkpoint.complete: [ok]')
        self.assertEqual([line.split(': ', 1)[0] for line in after[350:-1]],
                         ['math.' + label for label in probes()])
        self.assertEqual(historical.decode().splitlines()[306], 'Сообщить(1234.5);')
        self.assertEqual(before[29:32], ['present.direct.next:', '1\u00a0234,5', 'numbers.complete: [ok]'])

    def test_reconstruction_rejects_source_and_output_drift_without_filtering(self):
        source, output = SOURCE.read_bytes(), OUTPUT.read_bytes()
        for changed in (source + b'\n', source[:-1], source.replace(b'268435456', b'268435457', 1)):
            with self.assertRaises(ValueError):
                historical_numbers_source(changed, output)
        for changed in (output + b'\n', output[:-1], output.replace(b'1', b'2', 1)):
            with self.assertRaises(ValueError):
                historical_numbers_source(source, changed)
        self.assertEqual(historical_numbers_source(source.replace(b'\n', b'\r\n'), output.replace(b'\n', b'\r\n')),
                         historical_numbers_source(source, output))

    def test_unique_bounded_single_expressions_and_no_display_rounding(self):
        cases = probes()
        self.assertEqual(len(cases), 70)
        self.assertEqual(len(set(cases.values())), 70)
        for label, expression in cases.items():
            self.assertTrue(label.startswith('division-tie.'))
            self.assertLess(len(expression), 120)
            self.assertNotRegex(expression, r'[;\r\n]')
            self.assertNotRegex(expression, r'(?i)String|Строка|Import|Execute|While|For|Goto')
            self.assertEqual(len(parse('x = ' + expression + ';')), 1)
        addition = SOURCE.read_text(encoding='utf-8').split(START, 1)[1]
        self.assertEqual(addition.count(END), 1)
        self.assertNotRegex(addition, r'\b(?:Процедура|Функция|Пока|Для|Перейти|Выполнить|ОписаниеОшибки)\b')

    def test_target_quantum_candidates_are_exact_adjacent_brackets_not_expectations(self):
        cases = probes()
        ties, scales, parities = 0, set(), set()
        for label, expression in cases.items():
            if label.endswith(('.lower', '.upper')) or '.pow.' in label:
                continue
            left, right = map(Decimal, expression.split(' / '))
            exponent = left.as_tuple().exponent
            scale = 27 + 9 * ((max(0, -exponent) + 8) // 9) + 9 * (right.adjusted() // 9)
            exact = Fraction(left) / Fraction(right)
            units = exact * 10**scale
            lower = units.numerator // units.denominator
            if label + '.lower' in cases:
                self.assertEqual(units - lower, Fraction(1, 2), label)
                for suffix, coefficient in (('lower', lower), ('upper', lower+1)):
                    candidate = Fraction(cases[label+'.'+suffix].split(' = ')[1])
                    self.assertEqual(candidate * 10**scale, coefficient, label)
                scales.add(scale)
                parities.add(abs(lower) % 2)
                ties += 1
        self.assertEqual(ties, 16)
        self.assertEqual(scales, {18, 27, 36})
        self.assertEqual(parities, {0, 1})

    def test_signs_padding_near_half_and_fractional_block_transition(self):
        expressions = set(probes().values())
        for n in (1, 3):
            for a, b in ((n,268435456),(-n,268435456),(n,-268435456),(-n,-268435456)):
                self.assertIn(f'{a} / {b}', expressions)
            self.assertIn(f'{n} / 268435456.000', expressions)
        for n in (1,-1):
            for d in (268435455,268435457):
                self.assertIn(f'{n} / {d}', expressions)
        self.assertIn('0.000000001 / 268435456', expressions)
        self.assertIn('0.0000000001 / 268435456', expressions)

    def test_power_is_observed_independently_and_runtime_guards_remain(self):
        cases = probes()
        self.assertEqual(cases['division-tie.pow.odd-base-reciprocal'], 'Pow(-3, -1)')
        self.assertEqual(cases['division-tie.pow.odd-base-cube'], 'Pow(-3, -3)')
        for base, exp, label in ((2,-28,'positive-even'),(-2,-28,'negative-even'),
                                 (2,-37,'positive-odd'),(-2,-37,'negative-odd')):
            prefix = 'division-tie.pow.' + label
            self.assertEqual(cases[prefix], f'Pow({base}, {exp})')
            exact = Fraction(base) ** exp
            lower = Fraction(cases[prefix+'.lower'].split(' = ')[1])
            upper = Fraction(cases[prefix+'.upper'].split(' = ')[1])
            self.assertEqual(exact - lower, upper - exact)
            with self.assertRaisesRegex(ValueError, 'точная половина'):
                divide(Decimal(1), Decimal(base) ** abs(exp))
        for n in (1, 3, -1, -3):
            for d in (268435456, -268435456):
                with self.assertRaisesRegex(ValueError, 'точная половина'):
                    divide(Decimal(n), Decimal(d))


if __name__ == '__main__':
    unittest.main()
