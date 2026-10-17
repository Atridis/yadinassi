"""Bounded standalone numeric presentation/conversion, not native precision goldens.

The owner's native numbers.out establishes decimal-comma presentation with
U+00A0 groups of three. These regressions cover its exact reverse conversion
without changing arithmetic precision or importing the host process's locale.
"""

from decimal import Decimal, Inexact, Rounded, localcontext
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.values import BSLType, number, to_string


class NumericPresentationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_decimal_presentation_normalizes_zero_and_fractional_trailing_zeroes(self):
        cases = [('0', '0'), ('-0', '0'), ('0.0000', '0'), ('-0.0000', '0'),
                 ('1', '1'), ('999', '999'), ('1000', '1\u00a0000'),
                 ('1200.000', '1\u00a0200'), ('12345', '12\u00a0345'),
                 ('123456', '123\u00a0456'), ('-1234567', '-1\u00a0234\u00a0567'),
                 ('1.2500', '1,25'), ('-1.2500', '-1,25'),
                 ('0.00100', '0,001'), ('-0.00001', '-0,00001'),
                 ('1234567.8900', '1\u00a0234\u00a0567,89')]
        for source, expected in cases:
            with self.subTest(source=source):
                value = Decimal(source)
                before = value.as_tuple()
                self.assertEqual(to_string(value), expected)
                self.assertEqual(value.as_tuple(), before)
                self.assertIs(type(value), Decimal)

    def test_presentation_does_not_round_or_depend_on_host_decimal_context(self):
        source = '1234567890123456789012345678901234567890.12345678901234567890123456789'
        value = Decimal(source)
        with localcontext() as context:
            context.prec = 4
            self.assertEqual(to_string(value),
                             '1\u00a0234\u00a0567\u00a0890\u00a0123\u00a0456\u00a0789\u00a0012'
                             '\u00a0345\u00a0678\u00a0901\u00a0234\u00a0567\u00a0890,'
                             '12345678901234567890123456789')
            self.assertEqual(to_string(Decimal('1e-35')), '0,' + '0' * 34 + '1')
            self.assertEqual(to_string(Decimal('1e35')), '100' + '\u00a0000' * 11)
        self.assertEqual(value.as_tuple(), Decimal(source).as_tuple())

    def test_presentation_does_not_consult_process_locale(self):
        with patch('locale.localeconv', side_effect=AssertionError('host locale consulted')):
            self.assertEqual(to_string(Decimal('12345.67')), '12\u00a0345,67')
            self.assertEqual(self.vm.execute('String(12345.67)'), '12\u00a0345,67')

    def test_nonnumeric_presentations_and_string_contents_are_unchanged(self):
        for value, expected in [(None, ''), (True, 'Да'), (False, 'Нет'),
                                ('1.2500', '1.2500'), ('1,2500', '1,2500'),
                                ('123.45,67', '123.45,67'),
                                ('1234.5000', '1234.5000'), ('1234,5000', '1234,5000'),
                                ('1\u00a0234,5000', '1\u00a0234,5000')]:
            with self.subTest(value=value):
                self.assertEqual(to_string(value), expected)
        self.assertEqual(self.vm.execute('String("1.2500")'), '1.2500')

    def test_number_accepts_canonical_dot_and_single_decimal_comma_exactly(self):
        cases = ['0', '-0.000', '1.25', '-1234.5600', '0.0000000000000000000001',
                 '123456789012345678901234567890123456789.1234567890123456789']
        for source in cases:
            for spelling in (source, source.replace('.', ',')):
                with self.subTest(spelling=spelling):
                    value = number(spelling)
                    self.assertIs(type(value), Decimal)
                    self.assertEqual(value.as_tuple(), Decimal(source).as_tuple())
                    result = self.vm.execute(f'Number("{spelling}")')
                    self.assertIs(type(result), Decimal)
                    self.assertEqual(result.as_tuple(), Decimal(source).as_tuple())

    def test_number_accepts_only_exact_localized_groups_without_losing_scale(self):
        cases = [('1\u00a0234', '1234'), ('12\u00a0345', '12345'),
                 ('123\u00a0456', '123456'), ('1\u00a0234\u00a0567', '1234567'),
                 ('+1\u00a0234,5000', '1234.5000'),
                 ('-12\u00a0345\u00a0678,00000100', '-12345678.00000100'),
                 ('001\u00a0234,5000', '001234.5000'),
                 ('  -1\u00a0234,5  ', '-1234.5'),
                 ('\t+123\u00a0456,25\r\n', '123456.25')]
        for source, canonical in cases:
            with self.subTest(source=source):
                expected = Decimal(canonical)
                self.assertEqual(number(source).as_tuple(), expected.as_tuple())
                self.vm.variables['source'] = source
                for name in ('Number', 'чИсЛо'):
                    result = self.vm.execute(f'{name}(source)')
                    self.assertIs(type(result), Decimal)
                    self.assertEqual(result.as_tuple(), expected.as_tuple())

    def test_grouped_conversion_and_roundtrip_ignore_decimal_precision_and_traps(self):
        canonical = '-123456789012345678901234567890123456789.9876543210987654321000'
        localized = ('-123\u00a0456\u00a0789\u00a0012\u00a0345\u00a0678\u00a0901'
                     '\u00a0234\u00a0567\u00a0890\u00a0123\u00a0456\u00a0789,'
                     '9876543210987654321000')
        expected = Decimal(canonical)
        self.vm.variables['source'] = localized
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            self.assertEqual(number(localized).as_tuple(), expected.as_tuple())
            result = self.vm.execute('original = Number(source); Number(String(original))')
            self.assertIs(type(result), Decimal)
            self.assertEqual(result, expected)
            self.assertEqual(self.vm.variables['original'].as_tuple(), expected.as_tuple())
            self.assertFalse(context.flags[Inexact])
            self.assertFalse(context.flags[Rounded])

    def test_grouped_input_rejects_wrong_groups_separators_and_non_ascii_digits(self):
        invalid = ['1234\u00a0567', '1\u00a023', '1\u00a02345', '1\u00a02\u00a0345',
                   '1\u00a0\u00a0234', '1\u00a0234\u00a056', '1\u00a0+234',
                   '1\u00a0234.5', '1\u00a0234,', '1\u00a0234,,5',
                   '1\u00a0234,5.6', '1\u00a0234,5\u00a0678', '1\u00a0234e2',
                   '1\u00a0234,5e2', '1\u00a0234_567', '1\u00a0234,5_6',
                   '1 234', '1 234,5', '1\u202f234', '1\u202f234,5',
                   '1\t234,5', '1\u00a0234 567,5', '1\u00a0234\u202f567,5',
                   '١\u00a0234,5', '1\u00a0٢٣٤,5', '1\u00a0234,٥',
                   '１\u00a0234,5', '1\u00a0２３４,5', '1\u00a0234,５']
        for source in invalid:
            with self.subTest(source=source):
                with self.assertRaises((ValueError, ArithmeticError)):
                    number(source)
                self.vm.variables['invalid'] = source
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('Number(invalid)', 'grouped-numbers.bsl')

    def test_plain_signed_input_allows_outer_whitespace(self):
        for source in ['+12,500', '  -12,500  ', '\t12,500\r\n', '00012,500',
                       '\u00a01.5\u00a0', '\u00a0-1.25e3\u00a0', '\u00a012,500\u00a0']:
            with self.subTest(source=source):
                expected = Decimal(source.strip().replace(',', '.'))
                self.assertEqual(number(source).as_tuple(), expected.as_tuple())
                self.vm.variables['source'] = source
                result = self.vm.execute('Число(source)')
                self.assertIs(type(result), Decimal)
                self.assertEqual(result.as_tuple(), expected.as_tuple())
        # Existing canonical exponent syntax remains supported independently.
        self.assertEqual(self.vm.execute('Number("1.25e3")'), Decimal('1250'))

    def test_presentation_roundtrips_exact_decimal_values_without_float(self):
        sources = ['0', '-0.000', '0.1', '-0.100000000000000000000000000000001',
                   '999', '1000', '-1234.5000', '123456789012345678901234567890123456789',
                   '123456789012345678901234567890123456789.9876543210987654321']
        for source in sources:
            with self.subTest(source=source):
                original = Decimal(source)
                self.assertEqual(number(to_string(original)), original)
                self.vm.variables['original'] = original
                converted = self.vm.execute('Number(String(original))')
                self.assertIs(type(converted), Decimal)
                self.assertEqual(converted, original)
                self.assertIs(self.vm.variables['original'], original)
                self.assertIs(self.vm.execute('TypeOf(original)'), BSLType.NUMBER)

    def test_literal_number_and_boolean_conversion_keep_decimal_types(self):
        for expression, expected in [('1.2500', Decimal('1.2500')),
                                     ('-0.25', Decimal('-0.25')),
                                     ('Number(True)', Decimal(1)),
                                     ('Число(Ложь)', Decimal(0)),
                                     ('Number(1.25)', Decimal('1.25'))]:
            with self.subTest(expression=expression):
                result = self.vm.execute(expression)
                self.assertIs(type(result), Decimal)
                self.assertEqual(result, expected)
        # A comma remains an argument separator, not decimal literal syntax.
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('Message(1,25)')

    def test_aliases_message_and_concatenation_share_numeric_presentation(self):
        self.vm.execute('''
            value = nUmBeR("-12.5000");
            mEsSaGe(value); сОоБщИтЬ(value);
            Message(sTrInG(value)); Сообщить(сТрОкА(value));
            Message("value=" + value);
            Message(чИсЛо("-12,5000"));
            Message(TypeOf(value) = Тип("Число"));
        ''')
        self.assertEqual(self.output, ['-12,5'] * 4 + ['value=-12,5', '-12,5', 'Да'])
        self.assertIs(type(self.vm.variables['value']), Decimal)
        self.assertEqual(self.vm.variables['value'], Decimal('-12.5000'))

    def test_grouping_is_shared_by_direct_message_string_and_concatenation(self):
        self.vm.execute('''
            value = nUmBeR("-1\u00a0234,5000");
            mEsSaGe(value); сОоБщИтЬ(value);
            Message(sTrInG(value)); Сообщить(сТрОкА(value));
            Message("value=" + value);
            Message(чИсЛо("-1234.5000"));
            Message(Number(String(value)) = value);
        ''')
        self.assertEqual(self.output,
                         ['-1\u00a0234,5'] * 4 + ['value=-1\u00a0234,5', '-1\u00a0234,5', 'Да'])
        self.assertEqual(self.vm.variables['value'].as_tuple(), Decimal('-1234.5000').as_tuple())

    def test_grouping_is_visible_to_string_builtins_but_not_rewritten_in_strings(self):
        cases = [('StrLen(1234.5)', Decimal(7)), ('Left(1234.5, 2)', '1\u00a0'),
                 ('Mid(1234.5, 2, 3)', '\u00a023'), ('Find(1234.5, ",")', Decimal(6)),
                 ('StrReplace(1234.5, ",", ".")', '1\u00a0234.5'),
                 ('StrConcat(StrSplit(1234.5, ","), "|")', '1\u00a0234|5'),
                 ('StrReplace("x1\u00a0234,5y", 1234.5, 9876.5)', 'x9\u00a0876,5y'),
                 ('StrLen("1234.5000")', Decimal(9)),
                 ('String("1234.5000")', '1234.5000')]
        for expression, expected in cases:
            with self.subTest(expression=expression):
                self.assertEqual(self.vm.execute(expression), expected)

    def test_string_builtins_use_shared_numeric_presentation_for_all_arguments(self):
        cases = [('StrLen(1.2500)', Decimal(4)), ('СтрДлина(-1.25)', Decimal(5)),
                 ('Left(12.5, 3)', '12,'), ('Прав(12.5, 2)', ',5'),
                 ('Mid(-12.5, 2, 3)', '12,'), ('Найти(12.5, ",")', Decimal(3)),
                 ('Find("x12,5y", 12.5)', Decimal(2)),
                 ('StrReplace(12.5, ",", ".")', '12.5'),
                 ('СтрЗаменить("x12,5y", 12.5, 3.75)', 'x3,75y'),
                 ('TrimAll(12.5)', '12,5'), ('СокрЛ(12.5)', '12,5'),
                 ('TrimR(12.5)', '12,5'), ('Upper(12.5)', '12,5'),
                 ('НРег(12.5)', '12,5'), ('IsBlankString(0)', False),
                 ('StrConcat(StrSplit(12.5, ","), "|")', '12|5'),
                 ('СтрСоединить(СтрРазделить("a1,25b", 1.25), "|")', 'a||||b'),
                 ('Left("abcd", "2,9")', 'ab')]
        for expression, expected in cases:
            with self.subTest(expression=expression):
                result = self.vm.execute(expression)
                self.assertIs(type(result), type(expected))
                self.assertEqual(result, expected)
        self.vm.execute('a = New Array; a.Add(1.25); a.Add(-2.5); a.Add(0);')
        self.assertEqual(self.vm.execute('StrConcat(a, "|")'), '1,25|-2,5|0')
        self.assertEqual(self.vm.execute('StrConcat(New FixedArray(a), 0.5)'),
                         '1,250,5-2,50,50')

    def test_mixed_repeated_grouping_and_nonfinite_inputs_fail(self):
        invalid = ['1,2.3', '1.2,3', '1,,2', '1,2,3', '1.2.3', ',', '.', '',
                   '1 234,5', '1\u202f234,5', 'not a number',
                   'NaN', 'Infinity', '-Infinity', '1,', ',5', '1,2e3',
                   '1_000,25', '1,2_5', '١,٢', '１２,５']
        for source in invalid:
            with self.subTest(source=source):
                with self.assertRaises((ValueError, ArithmeticError)):
                    number(source)
                self.vm.variables['invalid'] = source
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('Number(invalid)', 'numbers.bsl')
        for value in [None, Decimal('NaN'), Decimal('Infinity'), object()]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    number(value)

    def test_failed_conversion_is_catchable_and_preserves_previous_value(self):
        self.vm.execute('''
            value = Number("1\u00a0234,5");
            Try
                value = Число("12\u00a034,5");
            Except
                Message("caught");
                Message(Find(ErrorDescription(), "numbers.bsl:4:") > 0);
            EndTry;
            Message(value); Message(TypeOf(value) = Type("Number"));
            Message(Number(String(value)) = value);
        ''', 'numbers.bsl')
        self.assertEqual(self.output, ['caught', 'Да', '1\u00a0234,5', 'Да', 'Да'])
        self.assertEqual(self.vm.variables['value'], Decimal('1234.5'))


if __name__ == '__main__':
    unittest.main()
