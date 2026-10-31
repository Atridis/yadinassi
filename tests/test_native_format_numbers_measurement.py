"""Synthetic Format witnesses prove the observer, not native Format semantics."""
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
SOURCE_SHA = '604a647404ee84b5e98a07b9bad646b568ce6e8645d063b176459294377b8344'


def emit(witness=None, source=SOURCE):
    output = []
    vm = Interpreter(output.append)
    if witness is not None:
        vm.register_function('Format', witness)
        vm.register_function('Формат', witness)
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

class FormatObserverTests(unittest.TestCase):
    def test_exact_source_pin_and_bounded_fixed_matrix(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode('utf-8')).hexdigest(), SOURCE_SHA)
        rows = fixed_rows()
        self.assertEqual([r[0] for r in rows], list(range(1,57)))
        self.assertEqual(len({r[2] for r in rows}), 56)
        parse(SOURCE)
        for _, expression, _ in rows:
            statements = parse(expression)
            self.assertEqual(len(statements), 1)
            call = statements[0].expression
            self.assertIsInstance(call, ast.Call)
            self.assertIsInstance(call.callee, ast.Name)
            self.assertIn(call.callee.name, ('Format', 'Формат'))
            for arg in call.arguments:
                if isinstance(arg, ast.Unary):
                    self.assertEqual(arg.operator, '-')
                    arg = arg.operand
                self.assertIsInstance(arg, ast.Literal)
        self.assertEqual(SOURCE.count('Вычислить(Expression)'), 1)
        self.assertNotIn('ОписаниеОшибки', SOURCE)
        self.assertNotIn('Выполнить(', SOURCE)

    def test_original_48_source_prefix_unchanged(self):
        prefix = SOURCE.split('FMObserve("49",', 1)[0].encode('utf-8')
        self.assertEqual(hashlib.sha256(prefix).hexdigest(),
                         'a7f8e3c6105d4a7f28ef08a0865abcf01f7465f236fffe189c2da7272df04d84')

    def test_exact_inputs_reach_witness_unchanged(self):
        seen = []
        def witness(*args):
            seen.append(args)
            return 'synthetic'
        raw = emit(witness)
        records = wire.require_available(raw)
        self.assertEqual(len(seen), 56)
        self.assertTrue(all(r['status']=='ok' for r in records))
        self.assertEqual(seen[7], (Decimal('1.235'), 'NFD=2'))
        self.assertEqual(seen[8][0], Decimal('-1.235'))
        self.assertEqual(seen[17][1], "NFD=2;NG=3;NGS=' ';NDS=,")
        self.assertEqual(seen[18][1], "NFD=2;NG=3;NGS='';NDS=.")
        self.assertEqual(seen[20][1], 'NFD=2;NG=0;NDS=.')
        self.assertEqual(seen[21][1], "NFD=2;NZ='';NG=0;NDS=.")
        self.assertEqual(seen[44], (Decimal(1),))
        self.assertEqual(seen[45], (Decimal(1), '', Decimal(3)))
        self.assertEqual(seen[46], (Decimal(1), Decimal(2)))
        self.assertEqual(seen[48][1], 'MYSTERY=foo;NFD=2;NG=0;NDS=.')
        self.assertEqual(seen[49][1], "UNUSED=';=non';NFD=2;NG=0;NDS=.")
        self.assertEqual(seen[50][1], 'НЕИЗВЕСТНО=2;NFD=2;NG=0;NDS=.')
        self.assertEqual(seen[51][1], 'ND=5;NFD=2;NG=0;NDS=.')
        self.assertEqual(seen[52][1], 'DF=yyyy')
        self.assertEqual(seen[53][1], 'NFD=2;NG=3,0;NGS=_;NDS=.')
        self.assertEqual(seen[54][1], 'NFD=2;NG=3,2;NGS=_;NDS=.')
        self.assertEqual(seen[55][1], 'nfd=1;ЧДЦ=3;NG=0;NDS=.')

    def test_unicode_and_empty_outputs_are_lossless(self):
        for value, units in [('',()), (' \u00a0\U0001f600', (32,160,55357,56832)), ('a'*32,(97,)*32)]:
            records=wire.require_available(emit(lambda *args:value))
            self.assertTrue(all(r['units']==units for r in records))

    def test_action_and_observer_failures_stay_distinct(self):
        def fails(*args):
            raise ValueError('PRIVATE must not be exported')
        raw=emit(fails)
        self.assertNotIn(b'PRIVATE',raw)
        self.assertTrue(all(r['status']=='action-error' for r in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        for value in (None,Decimal(1),True,'x'*33):
            raw=emit(lambda *args:value)
            self.assertTrue(all(r['status']=='observer-error' for r in wire.validate_output(raw)))
            with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)

    def test_missing_function_does_not_pass_availability(self):
        raw=emit()
        self.assertTrue(all(r['status']=='action-error' for r in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)

    def test_rectangular_maximum_fits_unraised_cap(self):
        raw=emit(lambda *args:'x'*32)
        self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(len(raw),wire.MAX_OUTPUT_BYTES)
        wire.require_available(raw)

    def test_hostile_wire_rejected(self):
        raw=emit(lambda *args:'A')
        mutations=[raw[:-1],raw+b'\n',raw.replace(b'FM-01:',b'FM-02:',1),
                   raw.replace(b'S1:0041',b'S01:0041',1),
                   raw.replace(b'S1:0041',b'S2:0041',1),
                   raw.replace(b'S1:0041',b'S1:004X',1),
                   raw.replace(b'S1:0041',b'S1:0041secret',1),
                   raw.replace(b'S6:0041',b'S6:0042',1),raw.replace(b'\n',b'\r\n'),
                   bytearray(raw),raw.decode('ascii'), b'x'*8193]
        for mutated in mutations:
            with self.subTest(type=type(mutated).__name__):
                with self.assertRaises(wire.ObservationError):wire.validate_output(mutated)

if __name__=='__main__':unittest.main()
