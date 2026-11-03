"""Synthetic witnesses prove this temporary observer, not native semantics."""
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_format_numbers_contract as wire
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast

SOURCE_PATH = ROOT / 'integrational_tests/measurements/format_numbers.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')
SOURCE_SHA = '433a8ee21a7fb9d33d981556c1d90ec36e0af9a81a911e650c75a4d7ad2bb73f'


def emit(witness=None, source=SOURCE, *, missing=False):
    output = []
    vm = Interpreter(output.append)
    if missing:
        vm.functions.pop('numberinwords', None)
        vm.functions.pop('числопрописью', None)
    if witness is not None:
        vm.register_function('NumberInWords', witness)
        vm.register_function('ЧислоПрописью', witness)
    vm.execute(source)
    return ('\n'.join(output) + '\n').encode('ascii')


def fixed_rows():
    rows = []
    for line in SOURCE.split('// Fixed measurement inputs start here.\n', 1)[1].splitlines():
        match = re.fullmatch(r'FMObserve\("(\d{2})", "((?:[^\"]|\"\")*)"\); // ([a-z0-9.-]+)', line)
        if not match:
            raise AssertionError('Non-fixed expression in matrix')
        rows.append((int(match[1]), match[2].replace('""', '"'), match[3]))
    return rows


class NumberWordsObserverTests(unittest.TestCase):
    def test_exact_source_pin_and_bounded_fixed_matrix(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode('utf-8')).hexdigest(), SOURCE_SHA)
        rows = fixed_rows()
        self.assertEqual([r[0] for r in rows], list(range(1, 30)))
        self.assertEqual(len({r[2] for r in rows}), 29)
        parse(SOURCE)
        for _, expression, _ in rows:
            statements = parse(expression)
            self.assertEqual(len(statements), 1)
            call = statements[0].expression
            self.assertIsInstance(call, ast.Call)
            self.assertIsInstance(call.callee, ast.Name)
            self.assertIn(call.callee.name, ('NumberInWords', 'ЧислоПрописью'))
            for arg in call.arguments:
                if isinstance(arg, ast.Unary):
                    self.assertEqual(arg.operator, '-')
                    arg = arg.operand
                self.assertIsInstance(arg, ast.Literal)
        self.assertEqual(SOURCE.count('Вычислить(Expression)'), 1)
        self.assertNotIn('ОписаниеОшибки', SOURCE)
        self.assertNotIn('Выполнить(', SOURCE)

    def test_exact_inputs_reach_witness_unchanged(self):
        seen = []
        def witness(*args):
            seen.append(args)
            return 'synthetic'
        records = wire.require_available(emit(witness))
        self.assertEqual(len(seen), 29)
        self.assertTrue(all(r['status'] == 'ok' for r in records))
        self.assertEqual(seen[0], (Decimal(0), 'L=ru_RU'))
        self.assertEqual(seen[2], (Decimal(1), 'L=en_US',
                         'dollar, dollars, cent, cents, 2'))
        self.assertEqual(seen[14], (Decimal(-2), 'Л=ru_RU'))
        self.assertEqual(seen[16], (Decimal('2.25'), 'Л=ru_RU;ДП=Истина',
                         'рубль, рубля, рублей, м, копейка, копейки, копеек, ж, 2'))
        self.assertEqual(seen[24], (Decimal('1457.25'), 'L=en_US',
                         'dollar, dollars, cent, cents, 2'))
        self.assertEqual(seen[25], ())
        self.assertEqual(seen[27], (Decimal(1), 'L=en_US', '', Decimal(3)))
        self.assertEqual(seen[28], (Decimal(1), Decimal(2)))

    def test_unicode_and_empty_outputs_are_lossless(self):
        for value, units in [('', ()), (' \u00a0\U0001f600', (32,160,55357,56832)),
                             ('a'*64, (97,)*64)]:
            records = wire.require_available(emit(lambda *args: value))
            self.assertTrue(all(r['units'] == units for r in records))

    def test_action_and_observer_failures_stay_distinct(self):
        def fails(*args):
            raise ValueError('PRIVATE must not be exported')
        raw = emit(fails)
        self.assertNotIn(b'PRIVATE', raw)
        self.assertTrue(all(r['status'] == 'action-error' for r in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)
        for value in (None, Decimal(1), True, 'x'*65):
            raw = emit(lambda *args: value)
            self.assertTrue(all(r['status'] == 'observer-error' for r in wire.validate_output(raw)))
            with self.assertRaises(wire.AvailabilityError):
                wire.require_available(raw)

    def test_missing_function_does_not_pass_availability(self):
        raw = emit(missing=True)
        self.assertTrue(all(r['status'] == 'action-error' for r in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)

    def test_rectangular_maximum_fits_unraised_cap(self):
        raw = emit(lambda *args: 'x'*64)
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertEqual(wire.MAX_ENCODED_BYTES, 7967)
        self.assertLessEqual(len(raw), wire.MAX_OUTPUT_BYTES)
        wire.require_available(raw)

    def test_hostile_wire_rejected(self):
        raw = emit(lambda *args: 'A')
        mutations = [raw[:-1], raw+b'\n', raw.replace(b'FM-01:', b'FM-02:', 1),
                     raw.replace(b'S1:0041', b'S01:0041', 1),
                     raw.replace(b'S1:0041', b'S2:0041', 1),
                     raw.replace(b'S1:0041', b'S1:004X', 1),
                     raw.replace(b'S1:0041', b'S1:0041secret', 1),
                     raw.replace(b'S6:0041', b'S6:0042', 1), raw.replace(b'\n', b'\r\n'),
                     bytearray(raw), raw.decode('ascii'), b'x'*8193]
        for mutated in mutations:
            with self.subTest(type=type(mutated).__name__):
                with self.assertRaises(wire.ObservationError):
                    wire.validate_output(mutated)


if __name__ == '__main__':
    unittest.main()
