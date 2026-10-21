"""Owner PR52 numeric parsing evidence plus explicitly local safety boundaries."""
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.numbers import number_from_binary_string, number_from_hex_string

ROOT = Path(__file__).resolve().parents[1]


class NumericRadixTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda text: None)

    def test_native_checkpoint_numeric_output_exact(self):
        output = []
        Interpreter(output=output.append).execute((ROOT / 'integrational_tests/tests/numbers.bsl').read_text(encoding='utf-8-sig'))
        expected = (ROOT / 'tests/fixtures/native_windows/numbers.out').read_text(encoding='utf-8-sig').splitlines()
        self.assertEqual(output, expected)

    def test_native_fixture_reads_do_not_depend_on_default_encoding(self):
        original = Path.read_text
        observed = []

        def read_utf8(path, *args, **kwargs):
            self.assertEqual(kwargs.get('encoding'), 'utf-8-sig')
            observed.append(path.name)
            return original(path, *args, **kwargs)

        with patch.object(Path, 'read_text', read_utf8):
            self.test_native_checkpoint_numeric_output_exact()
        self.assertEqual(observed, ['numbers.bsl', 'numbers.out'])

    def test_bilingual_case_insensitive_function_names(self):
        for name in ('ЧислоИзДвоичнойСтроки', 'numberfrombinarystring', 'NUMBERFROMBINARYSTRING'):
            self.assertEqual(self.vm.execute(f'{name}("0b0011001")'), 25)
        for name in ('ЧислоИзШестнадцатеричнойСтроки', 'numberfromhexstring', 'NUMBERFROMHEXSTRING'):
            self.assertEqual(self.vm.execute(f'{name}("0xAbCdEf")'), 11259375)

    def test_native_zero_and_widths(self):
        for function, text in ((number_from_binary_string, '0b'), (number_from_hex_string, '0x')):
            self.assertEqual(function(text + '0'), 0)
            self.assertEqual(function(text + '0000'), 0)
        for size in (32, 128):
            self.assertEqual(number_from_binary_string('0b' + '1' * size), Decimal(2**size - 1))
            self.assertEqual(number_from_hex_string('0x' + 'F' * (size // 4)), Decimal(2**size - 1))
        self.assertEqual(number_from_binary_string('0b1' + '0' * 32), Decimal(4294967296))
        self.assertEqual(number_from_hex_string('0x100000000'), Decimal(4294967296))

    def test_uint128_preserves_all_39_decimal_digits(self):
        exact = Decimal('340282366920938463463374607431768211455')
        self.assertEqual(number_from_hex_string('0x' + 'F' * 32), exact)
        self.assertEqual(number_from_binary_string('0b' + '1' * 128), exact)
        self.vm.execute('n = NumberFromHexString("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"); '
                        's = ValueToStringInternal(n); restored = ValueFromStringInternal(s);')
        self.assertEqual(self.vm.variables['s'], '{"N",340282366920938463463374607431768211455}')
        self.assertIs(type(self.vm.variables['restored']), Decimal)
        self.assertEqual(self.vm.variables['restored'], exact)
        self.assertTrue(self.vm.execute('(TypeOf(restored) = Type("Number"))'))

    def test_native_invalid_grammar(self):
        for function, texts in (
            (number_from_binary_string, ('0B101', '101', ' 0b101 ', '0b102', '-0b1')),
            (number_from_hex_string, ('0X1A', '1A', ' 0x1A ', '0x1G', '-0x1')),
        ):
            for value in texts:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    function(value)

    def test_documented_ascii_grammar_excludes_python_extensions(self):
        for function, prefix in ((number_from_binary_string, '0b'), (number_from_hex_string, '0x')):
            for payload in ('', '+1', '-0', '1_0', '1.0', ' 1', '1 ', '1\n', '\t1',
                            '١', '１', '\x001', '\ud800', '\u200b1'):
                with self.subTest(prefix=prefix, payload=payload), self.assertRaises(ValueError):
                    function(prefix + payload)
            for text in ('', '0', '+0' + prefix[-1] + '1'):
                with self.assertRaises(ValueError):
                    function(text)

    def test_hex_digits_and_small_values_against_arithmetic(self):
        for value in range(1024):
            self.assertEqual(number_from_binary_string('0b' + format(value, 'b')), Decimal(value))
            for spelling in (format(value, 'x'), format(value, 'X')):
                self.assertEqual(number_from_hex_string('0x' + spelling), Decimal(value))

    def test_strict_argument_types_are_local_guards(self):
        class StringSubclass(str):
            pass
        for function in (number_from_binary_string, number_from_hex_string):
            for value in (None, True, 1, 1.0, Decimal(1), [], StringSubclass('0b1')):
                with self.subTest(function=function.__name__, value=value), self.assertRaises(TypeError):
                    function(value)
        for argument in ('1', 'True', 'Undefined', 'New Array', 'Type("String")'):
            for function in ('NumberFromBinaryString', 'NumberFromHexString'):
                with self.assertRaises(BSLError):
                    self.vm.execute(f'{function}({argument})')

    def test_arity_and_omitted_arguments(self):
        for function in ('NumberFromBinaryString', 'NumberFromHexString'):
            for arguments in ('', ',', '"0b1", "0b0"', '"0b1",'):
                with self.subTest(function=function, arguments=arguments), self.assertRaises(BSLError):
                    self.vm.execute(f'{function}({arguments})')

    def test_local_resource_limits_include_leading_zeros(self):
        for function, prefix, limit, digit in ((number_from_binary_string, '0b', 4096, '1'),
                                              (number_from_hex_string, '0x', 1024, 'F')):
            self.assertEqual(function(prefix + '0' * limit), 0)
            self.assertEqual(function(prefix + digit * limit), Decimal(2**4096 - 1))
            for payload in ('0' * (limit + 1), digit * (limit + 1), '0' * 100000):
                with self.assertRaisesRegex(ValueError, 'предел Yadinassi'):
                    function(prefix + payload)

    def test_maximum_local_width_still_fits_existing_numeric_codec(self):
        self.vm.variables['input'] = '0x' + 'F' * 1024
        self.vm.execute('n = NumberFromHexString(input); s = ValueToStringInternal(n); '
                        'copy = ValueFromStringInternal(s);')
        self.assertEqual(self.vm.variables['copy'], Decimal(2**4096 - 1))

    def test_decimal_context_is_not_observed_or_changed(self):
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(number_from_hex_string('0x' + 'F' * 32), Decimal(2**128 - 1))
            self.assertEqual(number_from_binary_string('0b' + '1' * 4096), Decimal(2**4096 - 1))
            self.assertFalse(any(context.flags.values()))

    def test_collection_keys_and_serialized_nested_values(self):
        self.vm.execute('''n = NumberFromHexString("0x100000000");
        a = New Array; a.Add(n); m = New Map; m.Insert(n, "found");
        restored = ValueFromStringInternal(ValueToStringInternal(a));
        found = m.Get(NumberFromBinaryString("0b100000000000000000000000000000000"));''')
        self.assertEqual(self.vm.variables['restored'].items, [Decimal(4294967296)])
        self.assertEqual(self.vm.variables['found'], 'found')

    def test_eval_execute_routines_and_single_argument_evaluation(self):
        self.vm.execute('''Function Input() calls = calls + 1; Return "0x1A"; EndFunction
        Var calls; calls = 0; b = 0; n = NumberFromHexString(Input());
        Execute("b = ЧислоИзДвоичнойСтроки(""0b101"");");''')
        self.assertEqual(self.vm.variables['calls'], 1)
        self.assertEqual(self.vm.variables['n'], 26)
        self.assertEqual(self.vm.variables['b'], 5)
        self.assertEqual(self.vm.execute('Eval("NumberFromHexString(""0xF"")")'), 15)

    def test_catchable_errors_preserve_assignment_and_recover(self):
        self.vm.execute('''saved = 42;
        Try saved = NumberFromBinaryString("0B1"); Except caught = True; EndTry;
        recovered = NumberFromHexString("0x1A");''')
        self.assertEqual(self.vm.variables['saved'], 42)
        self.assertIs(self.vm.variables['caught'], True)
        self.assertEqual(self.vm.variables['recovered'], 26)

    def test_registration_is_per_interpreter_and_alias(self):
        self.vm.register_function('NumberFromHexString', lambda value: 'override')
        self.assertEqual(self.vm.execute('NumberFromHexString("0x1A")'), 'override')
        self.assertEqual(self.vm.execute('ЧислоИзШестнадцатеричнойСтроки("0x1A")'), 26)
        self.assertEqual(Interpreter().execute('NumberFromHexString("0x1A")'), 26)


if __name__ == '__main__':
    unittest.main()
