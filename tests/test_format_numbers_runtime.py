"""Native 48-case checkpoint plus explicitly local policy/property tests."""
from decimal import Decimal, localcontext, ROUND_DOWN
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.formatting import format_value
from yadinassi.values import NULL, to_string
from yadinassi.dates import BSLDate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_format_numbers_contract as contract


class FormatNumbersRuntimeTests(unittest.TestCase):
    def test_exact_native_capture_replay(self):
        raw = (ROOT / 'tests/fixtures/format_numbers/linux-8.3.27.1508.out').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '543fa283c906e7d430e8100cf23fdf376f4d552f8d7efd196fe87fb8a858c63b')
        self.assertEqual(len(contract.require_available(raw)), 48)
        source = (ROOT / 'integrational_tests/measurements/format_numbers.bsl').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         'a7f8e3c6105d4a7f28ef08a0865abcf01f7465f236fffe189c2da7272df04d84')
        output = []
        Interpreter(output.append).execute(source.decode())
        self.assertEqual(('\n'.join(output) + '\n').encode('ascii'), raw)

    def test_supplement_native_supported_cases_and_explicit_policy_gap(self):
        fixture = ROOT / 'tests/fixtures/format_numbers'
        source = (fixture / 'supplement56.bsl').read_bytes()
        raw = (fixture / 'supplement56-linux-8.3.27.1508.out').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         '604a647404ee84b5e98a07b9bad646b568ce6e8645d063b176459294377b8344')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'c73b57a240afa1e27852369d88d7a6d92d3be125f2888456d960f40808c67d0d')
        original = (fixture / 'linux-8.3.27.1508.out').read_bytes()
        self.assertTrue(raw.startswith(original))
        lines = raw.decode('ascii').splitlines()
        self.assertEqual(len(lines), 58)
        output = []
        Interpreter(output.append).execute(source.decode('utf-8'))
        # Two native-supported directive families are deliberately unsupported
        # locally. Assert this gap explicitly, never label all56 native parity.
        for case in (52, 53):
            self.assertTrue(lines[case + 1].startswith(f'FM-{case}: [ok|'))
            lines[case + 1] = f'FM-{case}: [action-error]'
        self.assertEqual(output, lines)

    @unittest.skipUnless(shutil.which('git'), 'Git required for real autocrlf checkout regression')
    def test_immutable_fixtures_survive_real_autocrlf_checkout(self):
        fixture_names = [str(p.relative_to(ROOT)) for p in
                         (ROOT / 'tests/fixtures/format_numbers').iterdir() if p.is_file()]
        paths = ['.gitattributes', 'integrational_tests/measurements/format_numbers.bsl',
                 *fixture_names]
        with tempfile.TemporaryDirectory(prefix='format-autocrlf-') as temporary:
            parent = Path(temporary)
            source, checkout = parent / 'source', parent / 'checkout'
            source.mkdir()
            environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
            def git(*arguments, cwd=source):
                result = subprocess.run(['git', *arguments], cwd=cwd, env=environment,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for name in paths:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            git('init')
            git('-c', 'core.autocrlf=false', 'add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'Local byte-preservation fixture')
            git('-c', 'core.autocrlf=true', 'clone', '--no-local', str(source), str(checkout), cwd=parent)
            for name in paths[1:]:
                self.assertEqual((checkout / name).read_bytes(), (ROOT / name).read_bytes(), name)

    def test_alias_arity_and_omissions(self):
        vm = Interpreter()
        for expression in ('Format(1)', 'Формат(1)', 'fOrMaT(1, 2)'):
            self.assertEqual(vm.execute(expression), '1')
        for expression in ('Format()', 'Format(1, "", 3)', 'Format(, "")', 'Format(1,)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute(expression)

    def test_hostile_decimal_context_is_unchanged(self):
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.rounding = ROUND_DOWN
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            before = context.copy()
            self.assertEqual(format_value(Decimal('-9999.995'), 'NFD=2;NG=0;NDS=.'), '-10000.00')
            self.assertEqual(format_value(Decimal('0.0001'), 'NFD=2'), '0,00')
            self.assertEqual(dict(context.flags), dict(before.flags))
            self.assertEqual(dict(context.traps), dict(before.traps))
            self.assertEqual((context.prec, context.Emax, context.Emin, context.rounding),
                             (before.prec, before.Emax, before.Emin, before.rounding))

    def test_rounding_local_properties(self):
        # Finite integer-coefficient reference, not a claimed native grid.
        for coefficient in range(-999, 1000):
            value = Decimal((int(coefficient < 0), tuple(map(int, str(abs(coefficient)))), -3))
            magnitude = (abs(coefficient) + 5) // 10
            expected = ('-' if coefficient < 0 and magnitude else '') + str(magnitude // 100) + '.' + str(magnitude % 100).zfill(2)
            self.assertEqual(format_value(value, "NFD=2;NG=0;NDS=.;NZ=''"), expected)

    def test_grouping_documented_algorithm(self):
        number = Decimal('987654321')
        for mask, expected in [('4', '98765/4321'), ('3,0', '987/654/321'),
                               ('3,2', '98/76/54/321'), ('0', '987654321')]:
            self.assertEqual(format_value(number, 'NG=' + mask + ';NGS=/'), expected)

    def test_zero_and_scale_local_boundaries(self):
        self.assertEqual(format_value(Decimal('-0')), '')
        self.assertEqual(format_value(Decimal('-0'), "NZ='';NFD=2"), '0,00')
        self.assertEqual(format_value(Decimal('1.2300'), 'NG=0'), '1,23')
        self.assertEqual(format_value(Decimal('1E3'), 'NG=0'), '1000')
        self.assertEqual(format_value(Decimal('1E-324'), 'NG=0'), '0,' + '0' * 323 + '1')
        self.assertEqual(format_value(Decimal('1'), 'NFD=324;NG=0'), '1,' + '0' * 324)

    def test_scanner_local_policy(self):
        self.assertEqual(format_value(Decimal('1.2345'), " nfd = 1 ; ЧДЦ=3;NDS=';';NG=0;"), '1;235')
        self.assertEqual(format_value(Decimal('0'), "NZ='it''s;='"), "it's;=")
        # Generic name/value behavior is witnessed by supplemental cases49–51.
        self.assertEqual(format_value(Decimal('1'), "MYSTERY='a;b';NFD=2"), '1,00')

    def test_unsupported_or_malformed_is_not_plausible_fallback(self):
        for mask in ('ND=5', 'ЧЦ=5', 'NS=2', "NF='$N / Hour'", "ЧФ='$Ч / Час'",
                     "nf='N'", "чф='Ч'", 'NLZ=', 'NN=0', 'DF=yyyy', 'ДФ=yyyy',
                     'DLF=D', 'DE=none', 'BT=yes', 'BF=no', 'L=en', 'Л=ru_RU',
                     'NFD=-1', 'NFD=1.5', 'NFD=325', 'NFD=9999999', 'NFD=²',
                     'NDS=', 'NG=0,3', 'NG=3,2,1', 'NG=33', 'NG=-1',
                     "NZ='unterminated", "NZ='valid'junk", 'NFD', 'NFD=2;bad',
                     'NFD=999;NFD=2', '=value', 'NＦD=2', 'ß=1'):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                format_value(Decimal(1), mask)
        for value in ('NaN', 'sNaN', 'Infinity', '-Infinity', '1E10000000', '1E-10000000'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                format_value(Decimal(value))

    def test_resource_limits_and_no_host_hooks(self):
        for mask in ('x' * 4097, 'NZ=' + '😀' * 2048):
            with self.assertRaises(ValueError):
                format_value(Decimal(1), mask)
        with self.assertRaises(ValueError):
            format_value(Decimal('1E4095'))  # Grouped output exceeds text budget.
        class Hostile:
            def __str__(self):
                raise AssertionError('must not call arbitrary string hook')
        class DecimalChild(Decimal):
            pass
        for value in (Hostile(), [], 1, 1.5, DecimalChild('1')):
            with self.subTest(kind=type(value)), self.assertRaises(TypeError):
                format_value(value)
            with self.assertRaises(TypeError):
                format_value(Decimal(1), value)

    def test_existing_string_conversion_untouched(self):
        with self.assertRaises(ValueError):
            format_value(BSLDate(0))
        self.assertEqual(to_string(Decimal(0)), '0')
        self.assertEqual(to_string(Decimal('1234567.89')), '1\u00a0234\u00a0567,89')
        for value in (True, False, 'abc', None, NULL, BSLDate(100000)):
            self.assertEqual(format_value(value, 'NFD=2;NG=0'), to_string(value))
            with self.assertRaises(ValueError):
                format_value(value, 'DF=yyyy')


if __name__ == '__main__':
    unittest.main()
