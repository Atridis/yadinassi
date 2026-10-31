"""Synthetic Format witnesses prove the observer, not native Format semantics."""
from decimal import Decimal
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_format_dates_contract as wire
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast

SOURCE_PATH = ROOT / 'integrational_tests/measurements/format_dates.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')
SOURCE_SHA = '606d4932ec82cc57b2465d4a3d344a8dfec776cbc0b5c2ca34e3a1e50a4ef9a9'


def emit(witness=None, source=SOURCE, *, missing=False):
    output = []
    vm = Interpreter(output.append)
    if missing:
        vm.functions.pop("format", None)
        vm.functions.pop("формат", None)
    if witness is not None:
        vm.register_function('Format', witness)
        vm.register_function('Формат', witness)
    vm.execute(source)
    return ('\n'.join(output) + '\n').encode('ascii')


def fixed_rows():
    rows = []
    for line in SOURCE.split('// Fixed measurement inputs start here.\n', 1)[1].splitlines():
        match = re.fullmatch(r'FDObserve\("(\d{2})", "((?:[^\"]|\"\")*)"\); // ([a-z0-9.-]+)', line)
        if not match:
            raise AssertionError('Non-fixed expression in matrix')
        rows.append((int(match[1]), match[2].replace('""', '"'), match[3]))
    return rows

class FormatObserverTests(unittest.TestCase):
    def test_exact_source_pin_and_bounded_fixed_matrix(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode('utf-8')).hexdigest(), SOURCE_SHA)
        rows = fixed_rows()
        self.assertEqual([r[0] for r in rows], list(range(1,29)))
        self.assertEqual(len({r[2] for r in rows}), 28)
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
                if isinstance(arg, ast.Binary):
                    self.assertEqual(arg.operator, '+')
                    self.assertIsInstance(arg.left, ast.Literal)
                    self.assertIsInstance(arg.right, ast.Literal)
                else:
                    self.assertIsInstance(arg, ast.Literal)
        self.assertEqual(SOURCE.count('Вычислить(Expression)'), 1)
        self.assertNotIn('ОписаниеОшибки', SOURCE)
        self.assertNotIn('Выполнить(', SOURCE)

    def test_original40_source_capture_and_attribution_preserved(self):
        import json
        fixture = ROOT / 'tests/fixtures/format_dates'
        original = (fixture / 'original40.bsl').read_bytes()
        capture = (fixture / 'original40.out').read_bytes()
        receipt = json.loads((fixture / 'original40-provenance.json').read_text())
        self.assertEqual(hashlib.sha256(original).hexdigest(), '5482cefd7c689ab05e04410ea3a701391f350a659dfe8767e118b3c771b678aa')
        self.assertTrue((fixture / 'supplement56.bsl').read_bytes().startswith(original))
        self.assertEqual((fixture / 'parser28.bsl').read_bytes(), SOURCE.encode())
        self.assertEqual(hashlib.sha256((fixture / 'supplement56.bsl').read_bytes()).hexdigest(), '7290d1cd2cb6b9f3c77679d8e62a920b87c91417a8569502afe314abb09fa4fb')
        self.assertEqual(hashlib.sha256((fixture / 'supplement56.out').read_bytes()).hexdigest(), 'fe558102e1e7f6cf879243b10ec377906d908a784fe2ed497c19826a4359fa8f')
        self.assertTrue((fixture / 'supplement56.out').read_bytes().startswith(capture))
        self.assertEqual(hashlib.sha256(capture).hexdigest(), '186c4441a7ce4c3fb70ccd9f4304be7af1bef5d5cb2797eb91b17500881658b8')
        self.assertEqual(len(capture.splitlines()), 42)
        self.assertEqual(receipt['cases'], 40)
        self.assertEqual(receipt['head'], '1eaf2de6b60e199f21debc3d182b779b4a74b153')
        self.assertFalse(receipt['runtime_parity_accepted'])
        self.assertEqual(wire.MAX_ENCODED_BYTES, 4110)

    def test_exact_inputs_reach_witness_unchanged(self):
        seen = []
        def witness(*args):
            seen.append(args)
            return 'synthetic'
        raw = emit(witness)
        records = wire.require_available(raw)
        self.assertEqual(len(seen), 28)
        self.assertTrue(all(r['status']=='ok' for r in records))
        self.assertEqual(seen[0], (Decimal('1234.5'), 'NFD=1;NG=0;NDS=.'))
        self.assertEqual(seen[1][1], 'NFD=1;NG=0;nds=.'); self.assertEqual(seen[9][1], 'чдц=1')
        self.assertEqual(seen[18][1], "DE='A'"); self.assertEqual(seen[19][1], "de='A'")
        self.assertEqual(seen[25][1], "ДП='B';DE='A'")
        self.assertEqual(seen[26][1], 'NFD=1;NG=0;L=en'); self.assertEqual(seen[27][1], 'NFD=1;NG=0;l=en')

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
        raw=emit(missing=True)
        self.assertTrue(all(r['status']=='action-error' for r in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)

    def test_rectangular_maximum_fits_unraised_cap(self):
        raw=emit(lambda *args:'x'*32)
        self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(len(raw),wire.MAX_OUTPUT_BYTES)
        wire.require_available(raw)

    @unittest.skipUnless(shutil.which('git'), 'Git required for autocrlf regression')
    def test_date_source_survives_real_autocrlf_checkout(self):
        paths = ['.gitattributes', 'integrational_tests/measurements/format_dates.bsl']
        with tempfile.TemporaryDirectory(prefix='date-format-autocrlf-') as temporary:
            parent = Path(temporary)
            source, checkout = parent / 'source', parent / 'checkout'
            source.mkdir()
            environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
            def git(*arguments, cwd=source):
                result = subprocess.run(['git', *arguments], cwd=cwd, env=environment,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for name in paths:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            git('init')
            git('-c', 'core.autocrlf=false', 'add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'Local source preservation')
            git('-c', 'core.autocrlf=true', 'clone', '--no-local', str(source), str(checkout), cwd=parent)
            self.assertEqual((checkout / paths[1]).read_bytes(), SOURCE.encode())

    def test_hostile_wire_rejected(self):
        raw=emit(lambda *args:'A')
        mutations=[raw[:-1],raw+b'\n',raw.replace(b'FD-01:',b'FD-02:',1),
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
