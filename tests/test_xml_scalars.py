"""Native scalar XML witnesses and separately bounded standalone policies.

The owner fixture is evidence; hostile inputs, lexical extensions and resource
budgets below test our explicit envelope without inventing more native output.
"""

from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import re
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.dates import BSLDate, MAX_TICKS, UnsupportedDateRange, date, shift_date
from yadinassi.serialization import value_from_string_internal, value_to_string_internal
from yadinassi.values import BSLType, NULL
from yadinassi import xml_values
from yadinassi.xml_values import xml_string, xml_value


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
NATIVE = ROOT / 'tests/fixtures/native_windows/values.out'


class NativeXMLScalarEvidenceTests(unittest.TestCase):
    maxDiff = None

    def test_settled_scalar_observations_match_unchanged_owner_fixture(self):
        before = {path: path.read_bytes() for path in (SOURCE, NATIVE)}
        output = []
        Interpreter(output=output.append).execute(SOURCE.read_text(encoding='utf-8-sig'))

        def records(text):
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            return dict(re.findall(
                r'^(xml\.(?:number\.|null\.|undefined\.|date\.write\.)[a-z0-9.-]+): '
                r'\[(.*?)\](?=\nxml\.|\n?\Z)', text, re.MULTILINE | re.DOTALL))

        expected = records(NATIVE.read_text(encoding='utf-8-sig'))
        self.assertEqual(len(expected), 28)
        actual = records('\n'.join(output) + '\n')
        self.assertEqual({label: actual[label] for label in expected}, expected)
        self.assertEqual(before, {path: path.read_bytes() for path in before})


class XMLNumberTests(unittest.TestCase):
    def test_writer_uses_exact_fixed_point_without_localized_presentation(self):
        samples = [
            ('0', '0'), ('-0.000', '0'), ('12345.6700', '12345.67'),
            ('-0.000001', '-0.000001'), ('1000.0000', '1000'),
            ('123456789012345678901234567890.123456789',
             '123456789012345678901234567890.123456789'),
            ('1E-27', '0.000000000000000000000000001'),
            ('1E+5', '100000'), ('0.' + '1' * 540, '0.' + '1' * 540),
        ]
        for number, expected in samples:
            with self.subTest(number=number[:60]):
                actual = xml_string(Decimal(number))
                self.assertIs(type(actual), str)
                self.assertEqual(actual, expected)

    def test_reader_native_decimal_spellings_and_observed_prefixes(self):
        samples = [
            ('+001.2300', '1.23'), ('-0', '0'), ('.5', '0.5'), ('5.', '5'),
            ('1e3', '1'), ('1E-3', '1'), (' 1.5 ', '1.5'),
            ('\t1.5\n', '1.5'), ('1,5', '1'),
        ]
        for text, expected in samples:
            with self.subTest(text=text):
                actual = xml_value(BSLType.NUMBER, text)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))
                self.assertEqual(xml_string(actual), expected)

    def test_bounded_extension_policy_is_complete_numeric_spellings_only(self):
        # Generalizations of the observed grammar, not new native evidence.
        for text, expected in [('-0005.2500', '-5.25'), ('+.5', '0.5'),
                               ('\t\r\n -1.25 \r\n\t', '-1.25'), ('-1.25E+123', '-1.25'),
                               ('+.5e-1', '0.5'), ('-005,25', '-5')]:
            with self.subTest(text=text):
                self.assertEqual(xml_value(BSLType.NUMBER, text), Decimal(expected))
        invalid = [
            '', ' ', '\t', 'NaN', 'sNaN', 'Infinity', '-Infinity', '.', '+', '-',
            '1e', '1e+', '1e-2x', '1e2.5', '1e2e3', '1,', '1,,5', '1,5,6',
            '1.5,6', '.5,6', '1,5e2', '1_000', '1 000', '1\t2',
            '1suffix', '1;2', '1.2.3', '1\x00', '&one;', '<x>1</x>',
            '1\n2', '\v1', '\f1', '\u00a01', '1\u0085', '1\u2003',
            '١', '１', '−1', '＋1', '1ｅ3',
        ]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                xml_value(BSLType.NUMBER, text)

    def test_number_aliases_and_type_names(self):
        vm = Interpreter()
        for writer in ('XMLСтрока', 'XMLString', 'xMlСтРоКа', 'xMlStRiNg'):
            self.assertEqual(vm.execute(f'{writer}(1234.500)'), '1234.5')
        for reader in ('XMLЗначение', 'XMLValue', 'xMlЗнАчЕнИе', 'xMlVaLuE'):
            for type_name in ('Число', 'Number', 'чИсЛо', 'nUmBeR'):
                actual = vm.execute(f'{reader}(Type("{type_name}"), "+001.2300")')
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal('1.23'))
        self.assertEqual(vm.execute('XMLValue(TypeOf(1), "1e3")'), Decimal(1))

    def test_roundtrips_and_internal_codec_keep_number_identity_and_digits(self):
        vm = Interpreter()
        for value in (Decimal('0'), Decimal('-1000.500'), Decimal('1E-27'),
                      Decimal('12345678901234567890.123456789'),
                      Decimal('0.' + '1' * 540)):
            vm.variables['value'] = value
            for expression in (
                'XMLValue(TypeOf(value), XMLString(value))',
                'XMLValue(TypeOf(value), ValueFromStringInternal(ValueToStringInternal(XMLString(value))))',
                'ValueFromStringInternal(ValueToStringInternal(XMLValue(TypeOf(value), XMLString(value))))',
            ):
                with self.subTest(expression=expression, value=str(value)[:60]):
                    actual = vm.execute(expression)
                    self.assertIs(type(actual), Decimal)
                    self.assertEqual(actual, value)
            self.assertEqual(value_to_string_internal(xml_string(value)),
                             '{"S","' + xml_string(value) + '"}')

    def test_decimal_context_precision_exponent_limits_flags_and_traps_are_untouched(self):
        text = '123456789012345678901234567890.123456789'
        value = Decimal(text)
        tiny = Decimal('1E-540')
        nonfinite = [Decimal(source) for source in ('NaN', 'sNaN', 'Infinity', '-Infinity')]
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.Emin, context.Emax = -1, 1
            context.clear_flags()
            for signal in context.traps:
                context.traps[signal] = True
            self.assertEqual(xml_string(value), text)
            self.assertEqual(xml_value(BSLType.NUMBER, text), value)
            self.assertEqual(xml_string(tiny), '0.' + '0' * 539 + '1')
            self.assertEqual(xml_value(BSLType.NUMBER, '1e999999999'), Decimal(1))
            for number in nonfinite:
                with self.assertRaisesRegex(ValueError, 'конечное число'):
                    xml_string(number)
            for invalid in ('NaN', 'sNaN', 'Infinity'):
                with self.assertRaises(ValueError):
                    xml_value(BSLType.NUMBER, invalid)
            self.assertFalse(any(context.flags.values()))

    def test_writer_bounds_expansion_and_discards_insignificant_zeros(self):
        self.assertEqual(xml_string(Decimal('1E-4096')), '0.' + '0' * 4095 + '1')
        self.assertEqual(xml_string(Decimal('1E+4095')), '1' + '0' * 4095)
        for value in (Decimal('1E-4097'), Decimal('1E+4096'),
                      Decimal('1E+999999999'), Decimal('1E-999999999')):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                xml_string(value)
        self.assertEqual(xml_string(Decimal('-0E+999999999')), '0')
        self.assertEqual(xml_string(Decimal('0E-999999999')), '0')
        self.assertEqual(xml_string(Decimal('1.' + '0' * 5000)), '1')

    def test_reader_bounds_raw_input_and_normalized_digits(self):
        for text in ('9' * 4096, '-0.' + '0' * 4095 + '1'):
            self.assertEqual(xml_value(BSLType.NUMBER, text), Decimal(text))
        for text in ('9' * 4097, '0.' + '0' * 4096 + '1',
                     ' ' * xml_values._MAX_NUMBER_TEXT + '1',
                     '1e' + '9' * xml_values._MAX_NUMBER_TEXT,
                     'x' * (xml_values._MAX_NUMBER_TEXT + 1)):
            with self.subTest(length=len(text)), self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                xml_value(BSLType.NUMBER, text)


class XMLSentinelTests(unittest.TestCase):
    def test_empty_xml_retains_null_undefined_type_and_codec_identity(self):
        vm = Interpreter()
        for value, kind, expression, payload in (
                (NULL, BSLType.NULL, 'Null', '{"L"}'),
                (None, BSLType.UNDEFINED, 'Undefined', '{"U"}')):
            self.assertEqual(xml_string(value), '')
            self.assertIs(xml_value(kind, ''), value)
            self.assertIs(value_from_string_internal(value_to_string_internal(xml_value(kind, ''))), value)
            for writer in ('XMLСтрока', 'XMLString', 'xMlStRiNg'):
                self.assertEqual(vm.execute(f'{writer}({expression})'), '')
            for reader in ('XMLЗначение', 'XMLValue', 'xMlVaLuE'):
                self.assertIs(vm.execute(f'{reader}(TypeOf({expression}), "")'), value)
            self.assertEqual(vm.execute(f'ValueToStringInternal(XMLValue(TypeOf({expression}), XMLString({expression})))'), payload)
            self.assertIs(vm.execute(f'TypeOf(XMLValue(TypeOf({expression}), ""))'), kind)
        for type_name, expected in (('Null', NULL), ('Неопределено', None), ('Undefined', None)):
            self.assertIs(vm.execute(f'XMLValue(Type("{type_name}"), "")'), expected)
        self.assertEqual(xml_value(BSLType.STRING, ''), '')

    def test_nonempty_sentinel_inputs_are_explicitly_unsupported(self):
        for kind in (BSLType.NULL, BSLType.UNDEFINED):
            for text in (' ', '\t', '\n', 'Null', 'Undefined', 'null', '0', 'false', '<x/>', '\x00'):
                with self.subTest(kind=kind, text=text), self.assertRaisesRegex(ValueError, 'пока не поддерживается'):
                    xml_value(kind, text)


class XMLDateWriterTests(unittest.TestCase):
    def test_fixed_width_whole_second_calendar_output(self):
        for source, expected in (
                ('00010101000000', '0001-01-01T00:00:00'),
                ('00990203040506', '0099-02-03T04:05:06'),
                ('20240229123456', '2024-02-29T12:34:56'),
                ('99991231235959', '9999-12-31T23:59:59')):
            self.assertEqual(xml_string(date(source)), expected)
    def test_fractional_writer_truncates_without_mutating_date(self):
        base = date('20240229123456')
        for delta in ('0.0001', '0.1234', '0.5', '0.9999', '-0.0001'):
            value = shift_date(base, Decimal(delta))
            ticks = value.ticks
            expected = '2024-02-29T12:34:55' if delta.startswith('-') else '2024-02-29T12:34:56'
            self.assertEqual(xml_string(value), expected)
            self.assertEqual(value.ticks, ticks)

    def test_bilingual_aliases_and_internal_string_codec(self):
        vm = Interpreter()
        for writer in ('XMLСтрока', 'XMLString', 'xMlСтРоКа', 'xMlStRiNg'):
            self.assertEqual(vm.execute(f'{writer}(Date(2024,2,29,12,34,56))'),
                             '2024-02-29T12:34:56')
        self.assertEqual(vm.execute('ValueToStringInternal(XMLString(Date(1,1,1)))'),
                         '{"S","0001-01-01T00:00:00"}')

    def test_unknown_boundary_dates_cannot_be_presented_as_known_dates(self):
        for ticks in (0, MAX_TICKS):
            with self.assertRaises(UnsupportedDateRange):
                xml_string(BSLDate(ticks, boundary=True))


class XMLScalarSafetyTests(unittest.TestCase):
    def test_exact_runtime_types_only_and_no_host_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('host string hook')
            def __eq__(self, other):
                raise AssertionError('host comparison hook')

        class HostNumber(Decimal):
            def is_finite(self):
                raise AssertionError('host decimal hook')
            def as_tuple(self):
                raise AssertionError('host tuple hook')

        class HostString(str):
            def __len__(self):
                raise AssertionError('host length hook')
            def strip(self, *args):
                raise AssertionError('host strip hook')
            def __eq__(self, other):
                raise AssertionError('host comparison hook')

        class HostDate(BSLDate):
            def require_known(self):
                raise AssertionError('host date hook')

        for value in (Hostile(), HostNumber('1'), HostString('1'), HostDate(0),
                      1, 1.5, [], {}, BSLType.NUMBER):
            with self.subTest(kind=type(value)), self.assertRaises(TypeError):
                xml_string(value)
        for kind in (Hostile(), 'Number', None, NULL, Decimal(1), True):
            with self.subTest(kind=type(kind)), self.assertRaises(TypeError):
                xml_value(kind, '1')
        for kind in (BSLType.NUMBER, BSLType.NULL, BSLType.UNDEFINED):
            for value in (Hostile(), HostString('1'), None, NULL, Decimal(1), True):
                with self.subTest(kind=kind, value_type=type(value)), self.assertRaises(TypeError):
                    xml_value(kind, value)

    def test_arity_failure_assignment_preservation_and_recovery(self):
        vm = Interpreter()
        invalid = (
            'XMLString()', 'XMLString(Null, Undefined)', 'XMLValue()',
            'XMLValue(Type("Number"))', 'XMLValue(Type("Null"), "", 1)',
            'XMLValue(, "1")', 'XMLValue(Type("Number"), 1)',
            'XMLValue(Type("Number"), "NaN")', 'XMLValue(Type("Number"), "1junk")',
            'XMLValue(Type("Null"), " ")', 'XMLValue(Type("Undefined"), "0")',
        )
        for expression in invalid:
            with self.subTest(expression=expression):
                vm.execute('saved = "old"; caught = False;')
                with self.assertRaises(BSLError):
                    vm.execute('saved = ' + expression)
                self.assertEqual(vm.execute('saved'), 'old')
                vm.execute(f'Try saved = {expression}; Except caught = True; EndTry;')
                self.assertTrue(vm.execute('caught'))
                self.assertEqual(vm.execute('saved'), 'old')
                self.assertEqual(vm.execute('XMLValue(Type("Number"), "1.5")'), Decimal('1.5'))
                self.assertIs(vm.execute('XMLValue(Type("Null"), "")'), NULL)

    def test_reader_arguments_evaluate_once_left_to_right(self):
        vm = Interpreter()
        vm.execute('''Перем Порядок;
Функция Первый()
    Порядок = Порядок + "1";
    Возврат Тип("Число");
КонецФункции
Функция Второй()
    Порядок = Порядок + "2";
    Возврат "+001.2300";
КонецФункции
Порядок = "";
Результат = XMLЗначение(Первый(), Второй());''')
        self.assertEqual(vm.execute('Порядок'), '12')
        self.assertEqual(vm.execute('Результат'), Decimal('1.23'))


if __name__ == '__main__':
    unittest.main()
