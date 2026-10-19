"""Native XML Date witnesses and separately bounded standalone policies.

The unchanged owner output establishes whole-second half-up reads, truncating
writes and the three winter timezone examples. Grammar budgets, hostile input,
other offsets and DST boundaries are implementation-policy tests, not additional
measurements of 1C. The underlying Date value still retains 100-microsecond ticks.
"""

from datetime import datetime, timedelta
from decimal import Decimal, Inexact, Rounded, ROUND_DOWN, localcontext
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter, timezones, xml_values
from yadinassi.dates import (
    BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange, date,
    date_difference, shift_date,
)
from yadinassi.serialization import (
    value_from_string_internal as read_internal,
    value_to_string_internal as write_internal,
)
from yadinassi.values import BSLType, NULL
from yadinassi.xml_values import xml_string, xml_value


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
NATIVE = ROOT / 'integrational_tests/output/values.out'
BASE = '2024-02-29T12:34:56'
UNIX_EPOCH = datetime(1970, 1, 1)


def read(text):
    return xml_value(BSLType.DATE, text)


def unix_seconds(value):
    delta = value - UNIX_EPOCH
    return delta.days * 86400 + delta.seconds


def local_parts_at_offset(offset):
    def convert(seconds):
        value = UNIX_EPOCH + timedelta(seconds=seconds + offset)
        return (value.year, value.month, value.day,
                value.hour, value.minute, value.second)
    return convert


class NativeXMLDateEvidenceTests(unittest.TestCase):
    maxDiff = None

    def test_all_date_observations_match_unchanged_owner_fixture(self):
        before = {path: path.read_bytes() for path in (SOURCE, NATIVE)}
        output = []
        # The owner confirmed Windows Central European Standard Time, mapped
        # to Europe/Warsaw. Never rewrite its results to fit the test host zone.
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Europe/Warsaw'}):
            Interpreter(output=output.append).execute(SOURCE.read_text(encoding='utf-8-sig'))

        def records(text):
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            return dict(re.findall(
                r'^(xml\.date\.[a-z0-9.-]+): \[(.*?)\](?=\nxml\.|\n?\Z)',
                text, re.MULTILINE | re.DOTALL))

        expected = records(NATIVE.read_text(encoding='utf-8-sig'))
        self.assertEqual(len(expected), 27)
        self.assertEqual(records('\n'.join(output) + '\n'), expected)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_native_fraction_reading_rounds_whole_seconds_half_up(self):
        base = date('20240229123456')
        cases = (('1234', 0), ('12345', 0), ('4999', 0), ('5', 1),
                 ('5001', 1), ('9994', 1), ('9995', 1), ('9999', 1),
                 ('99994', 1), ('99995', 1), ('99996', 1))
        for fraction, expected_delta in cases:
            with self.subTest(fraction=fraction):
                actual = read(BASE + '.' + fraction)
                self.assertEqual(date_difference(actual, base), Decimal(expected_delta))
                self.assertEqual(actual.ticks % TICKS_PER_SECOND, 0)
                self.assertFalse(actual.boundary)
        self.assertEqual(read('2024-02-29T12:34:57.5'), date('20240229123458'))
        self.assertEqual(read('2024-02-29T23:59:59.99995'), date('20240301000000'))

    def test_native_fraction_writing_discards_ticks_without_mutating_date(self):
        base = date('20240229123456')
        for fraction in ('0.1234', '0.5', '0.9999'):
            with self.subTest(fraction=fraction):
                value = shift_date(base, Decimal(fraction))
                ticks = value.ticks
                self.assertEqual(xml_string(value), BASE)
                self.assertEqual(value.ticks, ticks)
                self.assertEqual(date_difference(value, base), Decimal(fraction))
                self.assertEqual(read(xml_string(value)), base)
                self.assertNotEqual(read(xml_string(value)), value)

    def test_native_zoned_examples_use_confirmed_owner_zone(self):
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Europe/Warsaw'}):
            for suffix, expected in (('Z', '20240229133456'),
                                     ('+03:00', '20240229103456'),
                                     ('-05:30', '20240229190456')):
                with self.subTest(suffix=suffix):
                    self.assertEqual(read(BASE + suffix), date(expected))


class XMLDateGrammarPolicyTests(unittest.TestCase):
    def test_canonical_dates_year_padding_and_whole_second_roundtrips(self):
        cases = (('0001-01-01', '00010101000000'),
                 ('0004-02-29T00:00:00', '00040229000000'),
                 ('0099-12-31T23:59:59', '00991231235959'),
                 ('0999-01-01T01:02:03', '09990101010203'),
                 ('1600-02-29T00:00:00', '16000229000000'),
                 ('1900-03-01T00:00:00', '19000301000000'),
                 ('2000-02-29T00:00:00', '20000229000000'),
                 ('2024-02-29', '20240229000000'),
                 (BASE, '20240229123456'),
                 ('9999-12-31T23:59:59', '99991231235959'))
        for text, expected in cases:
            with self.subTest(text=text):
                result = read(text)
                self.assertIs(type(result), BSLDate)
                self.assertEqual(result, date(expected))
                self.assertEqual(xml_string(result), text if 'T' in text else text + 'T00:00:00')
                self.assertEqual(read(xml_string(result)), result)
                self.assertEqual(read_internal(write_internal(result)), result)
                self.assertIs(result.require_known(), result)

    def test_reject_noncanonical_forms_without_permissive_iso_parsing(self):
        invalid = (
            '', ' ', '20240229', '20240229T123456', '2024-2-29', '2024-02-9',
            '024-02-29', '02024-02-29', '+2024-02-29', '-2024-02-29',
            '2024-060', '2024-W09-4', '2024', '2024-02',
            '2024-02-29T12:34', '2024-02-29T1:34:56', '2024-02-29T12:3:56',
            '2024-02-29T12:34:5', '2024-02-29 12:34:56', '2024-02-29t12:34:56',
            '2024-02-29X12:34:56', '2024-02-29\n12:34:56',
            BASE + '.', BASE + ',5', BASE + '.5e1', BASE + '.5.0',
            BASE + '.+5', BASE + '.-5', BASE + '. 5', BASE + 'z',
            '2024-02-29Z', '2024-02-29+00:00', '2024-02-29.5',
            BASE + '+0000', BASE + '+00', BASE + '+0:00', BASE + '+00:0',
            BASE + '+00:00:00', BASE + '+00:00Z', BASE + 'ZZ',
            BASE + 'Z.5', BASE + '+00:00.5', BASE + '\x00',
            ' ' + BASE, BASE + ' ', '\t' + BASE, BASE + '\n', BASE + '\r',
            '\u00a0' + BASE, '\u2003' + BASE, BASE + '\u0085',
            '２０２４-02-29T12:34:56', '٢٠٢٤-02-29T12:34:56',
            '2024‐02-29T12:34:56', '2024-02-29T12：34:56',
            BASE + '.５', BASE + '+０0:00', BASE + '−00:00',
            '<date>' + BASE + '</date>', BASE + '&amp;', '\ud800',
        )
        with patch.object(timezones, 'local_parts', side_effect=AssertionError('conversion reached')):
            for text in invalid:
                with self.subTest(text=text), self.assertRaises(ValueError):
                    read(text)

    def test_invalid_calendar_components_and_offsets_are_rejected(self):
        invalid = ('0000-01-01', '10000-01-01', '2024-00-01', '2024-13-01',
                   '2024-01-00', '2024-01-32', '2024-04-31', '2023-02-29',
                   '1900-02-29', '2024-02-30', '2024-02-29T24:00:00',
                   '2024-02-29T23:60:00', '2024-02-29T23:59:60',
                   '2024-02-29T99:00:00', BASE + '+14:01', BASE + '-14:01',
                   BASE + '+15:00', BASE + '-99:00', BASE + '+00:60')
        with patch.object(timezones, 'local_parts', side_effect=AssertionError('conversion reached')):
            for text in invalid:
                with self.subTest(text=text), self.assertRaises(ValueError):
                    read(text)

    def test_resource_budget_is_checked_before_parsing_and_has_exact_boundary(self):
        prefix = BASE + '.'
        for digit, expected in (('4', '20240229123456'), ('5', '20240229123457')):
            text = prefix + digit * (4096 - len(prefix))
            self.assertEqual(len(text), 4096)
            self.assertEqual(read(text), date(expected))
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read(text + digit)
        with patch.object(xml_values, '_DATE') as grammar:
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read('x' * 100000)
            grammar.fullmatch.assert_not_called()

    def test_types_are_exact_and_do_not_invoke_host_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('host string hook')
            def __int__(self):
                raise AssertionError('host integer hook')
            def __eq__(self, other):
                raise AssertionError('host comparison hook')

        class HostileText(str):
            def __len__(self):
                raise AssertionError('host length hook')
            def __getitem__(self, key):
                raise AssertionError('host subscript hook')

        class HostileDate(BSLDate):
            def require_known(self):
                raise AssertionError('host date hook')

        for text in (None, NULL, True, 1, Decimal(1), [], Hostile(), HostileText(BASE)):
            with self.subTest(kind=type(text).__name__), self.assertRaises(TypeError):
                read(text)
        for kind in ('Date', date('20240229'), Hostile(), None):
            with self.subTest(kind=type(kind).__name__), self.assertRaises(TypeError):
                xml_value(kind, BASE)
        with self.assertRaises(TypeError):
            xml_string(HostileDate(0))


class XMLDatePrecisionPolicyTests(unittest.TestCase):
    def test_rounding_is_exact_and_independent_of_decimal_context(self):
        samples = (('.00000000000000000001', '20240229123456'),
                   ('.49999999999999999999', '20240229123456'),
                   ('.50000000000000000000', '20240229123457'),
                   ('.99999999999999999999', '20240229123457'))
        fractional_date = shift_date(date('20240229123456'), Decimal('0.9999'))
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.Emax = 1
            context.Emin = -1
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            for suffix, expected in samples:
                self.assertEqual(read(BASE + suffix), date(expected))
            self.assertEqual(xml_string(fractional_date), BASE)

    def test_rounding_carries_across_minute_day_month_year_and_century(self):
        cases = (('2024-02-29T12:34:59.5', '20240229123500'),
                 ('2024-02-29T12:59:59.5', '20240229130000'),
                 ('2024-02-28T23:59:59.5', '20240229000000'),
                 ('2024-02-29T23:59:59.5', '20240301000000'),
                 ('2023-12-31T23:59:59.5', '20240101000000'),
                 ('1899-12-31T23:59:59.5', '19000101000000'),
                 ('1900-02-28T23:59:59.5', '19000301000000'),
                 ('1999-12-31T23:59:59.5', '20000101000000'))
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(read(text), date(expected))

    def test_writer_discards_fractions_even_at_midnight_and_minimum(self):
        for text in ('00010101000000', '20231231235959', '20240228235959',
                     '20240229235959', '99991231235958'):
            base = date(text)
            for fraction in ('0.0001', '0.4999', '0.5', '0.9999'):
                with self.subTest(text=text, fraction=fraction):
                    value = shift_date(base, Decimal(fraction))
                    self.assertEqual(xml_string(value), xml_string(base))
                    self.assertEqual(read(xml_string(value)), base)

    def test_range_overflow_is_explicit_and_never_saturated(self):
        self.assertEqual(read('9999-12-31T23:59:59.4999999'), BSLDate(MAX_TICKS))
        for text in ('9999-12-31T23:59:59.5', '9999-12-31T23:59:59.9999',
                     '9999-12-31T23:59:59.5+14:00',
                     '0001-01-01T00:00:00+00:01',
                     '9999-12-31T23:59:59-00:01'):
            with self.subTest(text=text), self.assertRaises(UnsupportedDateRange):
                read(text)
        for ticks in (0, MAX_TICKS):
            with self.subTest(ticks=ticks), self.assertRaises(UnsupportedDateRange):
                xml_string(BSLDate(ticks, boundary=True))


class XMLDateTimezonePolicyTests(unittest.TestCase):
    def test_naive_forms_ignore_timezone_configuration_and_never_convert(self):
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Definitely/Invalid'}), \
                patch.object(timezones, 'local_parts', side_effect=AssertionError('local conversion')):
            self.assertEqual(read('2024-02-29'), date('20240229000000'))
            self.assertEqual(read(BASE), date('20240229123456'))
            self.assertEqual(read(BASE + '.5'), date('20240229123457'))
            self.assertEqual(xml_string(date('20240229123456')), BASE)

    def test_offsets_convert_rounded_utc_instant_once_using_integer_seconds(self):
        cases = (('Z', 0), ('+00:00', 0), ('-00:00', 0),
                 ('+03:00', 10800), ('-05:30', -19800),
                 ('+05:45', 20700), ('+14:00', 50400), ('-14:00', -50400))
        expected_local = (2025, 1, 2, 3, 4, 5)
        seconds = unix_seconds(datetime(2024, 2, 29, 12, 34, 57))
        for suffix, offset in cases:
            with self.subTest(suffix=suffix), patch.object(
                    timezones, 'local_parts', return_value=expected_local) as convert:
                self.assertEqual(read(BASE + '.5' + suffix), date('20250102030405'))
                convert.assert_called_once_with(seconds - offset)
                self.assertIs(type(convert.call_args.args[0]), int)

    def test_offset_and_local_conversion_cross_calendar_and_unix_boundaries(self):
        cases = (('2024-03-01T00:00:00+03:00', '20240229210000'),
                 ('2023-12-31T23:59:59.5-05:30', '20240101053000'),
                 ('1970-01-01T00:00:00+00:01', '19691231235900'),
                 ('1969-12-31T23:59:59.5Z', '19700101000000'))
        with patch.object(timezones, 'local_parts', side_effect=local_parts_at_offset(0)):
            for text, expected in cases:
                with self.subTest(text=text):
                    self.assertEqual(read(text), date(expected))
        with patch.object(timezones, 'local_parts', side_effect=local_parts_at_offset(20700)):
            self.assertEqual(read('2024-02-29T20:00:00Z'), date('20240301014500'))

    def test_warsaw_dst_is_applied_at_rounded_instant(self):
        cases = (('2024-03-31T00:59:59.4999Z', '20240331015959'),
                 ('2024-03-31T00:59:59.5Z', '20240331030000'),
                 ('2024-03-31T02:59:59.5+02:00', '20240331030000'),
                 ('2024-10-27T00:59:59.4999Z', '20241027025959'),
                 ('2024-10-27T00:59:59.5Z', '20241027020000'),
                 ('2024-07-01T12:00:00Z', '20240701140000'))
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Europe/Warsaw'}):
            for text, expected in cases:
                with self.subTest(text=text):
                    self.assertEqual(read(text), date(expected))

    def test_conversion_failures_and_local_range_crossings_are_explicit(self):
        for failure in (OSError('host conversion'), OverflowError(), ValueError()):
            with self.subTest(error=type(failure).__name__), patch.object(
                    timezones, 'local_parts', side_effect=failure), \
                    self.assertRaisesRegex(UnsupportedDateRange, 'местную дату'):
                read(BASE + 'Z')
        for parts in ((0, 12, 31, 23, 59, 59), (10000, 1, 1, 0, 0, 0)):
            with self.subTest(parts=parts), patch.object(timezones, 'local_parts', return_value=parts), \
                    self.assertRaises(UnsupportedDateRange):
                read(BASE + 'Z')
        for zone, text in (('Etc/GMT+1', '0001-01-01T00:00:00Z'),
                           ('Etc/GMT-1', '9999-12-31T23:59:59Z')):
            with self.subTest(zone=zone), patch.dict(os.environ, {'YADINASSI_TIMEZONE': zone}), \
                    self.assertRaises(UnsupportedDateRange):
                read(text)

    def test_invalid_configuration_surfaces_distinctly_without_host_fallback(self):
        error = timezones.TimezoneConfigurationError('YADINASSI_TIMEZONE: invalid zone')
        with patch.object(timezones, 'local_parts', side_effect=error), \
                self.assertRaises(timezones.TimezoneConfigurationError) as caught:
            read(BASE + 'Z')
        self.assertIs(caught.exception, error)
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Definitely/Invalid'}), \
                patch.object(timezones.time, 'localtime', side_effect=AssertionError('host fallback')), \
                self.assertRaises(timezones.TimezoneConfigurationError):
            read(BASE + 'Z')


class XMLDateInterpreterTests(unittest.TestCase):
    def test_aliases_case_and_type_identity(self):
        vm = Interpreter()
        for reader in ('XMLЗначение', 'XMLValue', 'xMlЗнАчЕнИе', 'xMlVaLuE'):
            for type_name in ('Дата', 'Date', 'дАтА', 'dAtE'):
                with self.subTest(reader=reader, type_name=type_name):
                    actual = vm.execute(f'{reader}(Type("{type_name}"), "{BASE}.5")')
                    self.assertIs(type(actual), BSLDate)
                    self.assertEqual(actual, date('20240229123457'))
        for writer in ('XMLСтрока', 'XMLString', 'xMlСтРоКа', 'xMlStRiNg'):
            self.assertEqual(vm.execute(f'{writer}(Date(2024,2,29,12,34,56) + 0.9999)'), BASE)
        self.assertIs(vm.execute(f'TypeOf(XMLValue(Type("Date"), "{BASE}"))'), BSLType.DATE)
        self.assertEqual(vm.execute(f'XMLValue(TypeOf(Date(2024,2,29)), "{BASE}")'),
                         date('20240229123456'))

    def test_arity_types_and_parse_errors_preserve_assignment_and_recover(self):
        vm = Interpreter()
        invalid = ('XMLString()', 'XMLString(Date(2024,2,29), 1)', 'XMLValue()',
                   'XMLValue(Type("Date"))', 'XMLValue(Type("Date"), "", 1)',
                   'XMLValue(, "2024-02-29")', 'XMLValue("Date", "2024-02-29")',
                   'XMLValue(Type("Date"), 20240229)', 'XMLValue(Type("Date"), "")',
                   'XMLValue(Type("Date"), "2023-02-29")',
                   'XMLValue(Type("Date"), "2024-02-29T24:00:00")',
                   'XMLValue(Type("Date"), "9999-12-31T23:59:59.5")')
        for expression in invalid:
            with self.subTest(expression=expression):
                vm.execute('saved = "old"; caught = False;')
                with self.assertRaises(BSLError):
                    vm.execute('saved = ' + expression)
                self.assertEqual(vm.execute('saved'), 'old')
                vm.execute(f'Try saved = {expression}; Except caught = True; EndTry;')
                self.assertTrue(vm.execute('caught'))
                self.assertEqual(vm.execute('saved'), 'old')
                self.assertEqual(vm.execute(f'XMLValue(Type("Date"), "{BASE}")'),
                                 date('20240229123456'))

    def test_reader_arguments_evaluate_once_in_order(self):
        vm = Interpreter()
        vm.execute('''Перем Порядок;
Функция Первый()
    Порядок = Порядок + "1";
    Возврат Тип("Дата");
КонецФункции
Функция Второй()
    Порядок = Порядок + "2";
    Возврат "2024-02-29T12:34:56.5";
КонецФункции
Порядок = "";
Результат = XMLЗначение(Первый(), Второй());''')
        self.assertEqual(vm.execute('Порядок'), '12')
        self.assertEqual(vm.execute('Результат'), date('20240229123457'))


if __name__ == '__main__':
    unittest.main()
