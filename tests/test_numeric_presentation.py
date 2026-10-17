"""Bounded standalone numeric presentation/conversion, not native precision goldens.

Only decimal-comma presentation is established by the owner's basic.out. These
regressions keep that shared presentation consistent without changing arithmetic
precision, grouping, or importing the host process's locale.
"""

from decimal import Decimal, localcontext
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
                 ('1', '1'), ('1000', '1000'), ('1200.000', '1200'),
                 ('1.2500', '1,25'), ('-1.2500', '-1,25'),
                 ('0.00100', '0,001'), ('-0.00001', '-0,00001'),
                 ('1234567.8900', '1234567,89')]
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
            self.assertEqual(to_string(value), source.replace('.', ','))
            self.assertEqual(to_string(Decimal('1e-35')), '0,' + '0' * 34 + '1')
            self.assertEqual(to_string(Decimal('1e35')), '1' + '0' * 35)
        self.assertEqual(value.as_tuple(), Decimal(source).as_tuple())

    def test_presentation_does_not_consult_process_locale(self):
        with patch('locale.localeconv', side_effect=AssertionError('host locale consulted')):
            self.assertEqual(to_string(Decimal('12345.67')), '12345,67')
            self.assertEqual(self.vm.execute('String(12345.67)'), '12345,67')

    def test_nonnumeric_presentations_and_string_contents_are_unchanged(self):
        for value, expected in [(None, ''), (True, 'Да'), (False, 'Нет'),
                                ('1.2500', '1.2500'), ('1,2500', '1,2500'),
                                ('123.45,67', '123.45,67')]:
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

    def test_plain_signed_comma_input_allows_outer_whitespace(self):
        for source in ['+12,500', '  -12,500  ', '\t12,500\r\n', '00012,500']:
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
                   '1 234,5', '1\u00a0234,5', '1\u202f234,5', 'not a number',
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
            value = Number("12,5");
            Try
                value = Число("1,2.3");
            Except
                Message("caught");
                Message(Find(ErrorDescription(), "numbers.bsl:4:") > 0);
            EndTry;
            Message(value); Message(TypeOf(value) = Type("Number"));
            Message(Number(String(value)) = value);
        ''', 'numbers.bsl')
        self.assertEqual(self.output, ['caught', 'Да', '12,5', 'Да', 'Да'])
        self.assertEqual(self.vm.variables['value'], Decimal('12.5'))


if __name__ == '__main__':
    unittest.main()
