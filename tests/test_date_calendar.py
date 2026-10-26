"""Date calendar functions: unchanged native records and bounded generalization.

NativeCalendarEvidenceTests consumes the owner's real 559-line dates.out and
all 48 appended observations. The remaining tests independently exercise the
specified Gregorian subset, safety limits and runtime integration; their
expected values are not additional claims about unobserved native behavior.
"""

import calendar
from datetime import datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from scripts.native_historical_replay import historical_dates_source

from yadinassi import BSLError, Interpreter
from yadinassi.syntax import ast
from yadinassi.dates import (
    BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange, add_month,
    begin_period, component, date, date_difference, day_of_year, end_period,
    shift_date, week_day, week_of_year,
)
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.syntax.parser import parse
from yadinassi.serialization import (
    value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_of
from yadinassi.value_checks import value_is_filled
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, equal, to_string


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/dates.bsl'
NATIVE = ROOT / 'tests/fixtures/native_windows/dates.out'
FINAL = 'date.calendar.checkpoint.complete: [ok]'
BASE = '20240229123456'
PERIODS = (
    ('minute', 'Minute', 'Минуты'), ('hour', 'Hour', 'Часа'),
    ('day', 'Day', 'Дня'), ('week', 'Week', 'Недели'),
    ('month', 'Month', 'Месяца'), ('quarter', 'Quarter', 'Квартала'),
    ('year', 'Year', 'Года'),
)
UNITS = tuple(item[0] for item in PERIODS)
ALIASES = tuple((english + name, russian + suffix, unit, ending)
                for unit, name, suffix in PERIODS
                for english, russian, ending in (('BegOf', 'Начало', False),
                                                  ('EndOf', 'Конец', True)))
NUMBERS = (('DayOfYear', 'ДеньГода', day_of_year),
           ('WeekDay', 'ДеньНедели', week_day),
           ('WeekOfYear', 'НеделяГода', week_of_year))


def normalized(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def quote(text):
    return '"' + text.replace('"', '""').replace('\n', '\n|') + '"'


def canonical(value):
    return (f'{value.year:04}{value.month:02}{value.day:02}'
            f'{value.hour:02}{value.minute:02}{value.second:02}')


def array(*items):
    result = BSLArray()
    for item in items:
        result.add(item)
    return result


def mapping(*entries):
    result = BSLMap()
    for key, value in entries:
        result.insert(key, value)
    return result


def unary_calls(value):
    return ([lambda unit=unit: begin_period(value, unit) for unit in UNITS]
            + [lambda unit=unit: end_period(value, unit) for unit in UNITS]
            + [lambda function=function: function(value)
               for _, _, function in NUMBERS])


class NativeCalendarEvidenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.native = normalized(NATIVE.read_text(encoding='utf-8-sig'))
        cls.source = historical_dates_source(SOURCE.read_bytes(), NATIVE.read_bytes()).decode('utf-8-sig')
        cls.records = dict(re.findall(
            r'^date\.(calendar\.[a-z0-9.-]+): \[(.*?)\](?=\ndate\.|\n?\Z)',
            cls.native, re.MULTILINE | re.DOTALL))
        cls.expressions = {
            node.expression.arguments[0].value: node.expression.arguments[1].value
            for node in parse(cls.source)
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьДату'
            and node.expression.arguments[0].value.startswith('calendar.')}

    def test_full_559_line_owner_fixture_matches_without_modifying_evidence(self):
        paths = (SOURCE, NATIVE, ROOT / 'integrational_tests/meta.md')
        before = {path: path.read_bytes() for path in paths}
        output = []
        Interpreter(output=output.append).execute(self.source, str(SOURCE))
        actual = ''.join(normalized(message) + '\n' for message in output)
        self.assertEqual(len(self.native.splitlines()), 559)
        self.assertEqual(len(output), 100)
        self.assertEqual(output[50], 'date.checkpoint.complete: [ok]')
        self.assertEqual(output[-1], FINAL)
        self.assertMultiLineEqual(actual, self.native)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_every_calendar_label_has_the_exact_native_value_or_error(self):
        self.assertEqual(len(self.expressions), 48)
        self.assertEqual(set(self.records), set(self.expressions) | {'calendar.checkpoint.complete'})
        for label, expression in self.expressions.items():
            with self.subTest(label=label):
                expected = self.records[label]
                if expected == 'error':
                    with self.assertRaises(BSLError):
                        Interpreter().execute(expression)
                else:
                    value = Interpreter().execute(expression)
                    self.assertMultiLineEqual(normalized(write(value)), expected)
        self.assertEqual(self.records['calendar.checkpoint.complete'], 'ok')

    def test_native_period_and_shift_witnesses_preserve_zero_numeric_deltas(self):
        labels = [label for label in self.expressions if label.startswith('calendar.period.')]
        labels += ['calendar.month.' + label
                   for label in ('forward-year', 'backward-year', 'leap-january')]
        self.assertEqual(len(labels), 17)
        for label in labels:
            with self.subTest(label=label):
                observed = read(self.records[label])
                actual = Interpreter().execute(self.expressions[label])
                self.assertEqual(observed.get('Delta'), Decimal(0))
                self.assertEqual(actual.get('Delta'), observed.get('Delta'))
                self.assertEqual(actual.get('Value'), observed.get('Value'))
                self.assertEqual(actual.get('Value').ticks % TICKS_PER_SECOND, 0)

    def test_normal_native_calendar_streams_reencode_and_restore_dates(self):
        boundary_labels = {'calendar.month.min-underflow', 'calendar.month.max-overflow',
                           'calendar.edge.end-max-week'}
        for label, expression in self.expressions.items():
            if self.records[label] == 'error' or label in boundary_labels:
                continue
            with self.subTest(label=label):
                restored = read(self.records[label])
                self.assertMultiLineEqual(normalized(write(restored)), self.records[label])
                original = Interpreter().execute(expression)
                if type(original) is BSLDate:
                    self.assertFalse(original.boundary)
                    self.assertEqual(original, restored)
                elif type(original) is BSLStructure:
                    for entry in original:
                        self.assertEqual(entry.value, restored.get(entry.key))
                else:
                    self.assertEqual(original, restored)


class CalendarMonthTests(unittest.TestCase):
    def test_clipping_year_crossings_and_time_preservation(self):
        cases = (
            ('20240131123456', 1, '20240229123456'),
            ('20230131123456', 1, '20230228123456'),
            ('20240229123456', 12, '20250228123456'),
            ('20240331123456', -1, '20240229123456'),
            ('20231215123456', 2, '20240215123456'),
            ('20240115123456', -2, '20231115123456'),
            ('16000229123456', 1200, '17000228123456'),
            ('19000131123456', 1, '19000228123456'),
            ('20000131123456', 1, '20000229123456'),
            ('20000229123456', -4800, '16000229123456'),
        )
        for source, months, expected in cases:
            with self.subTest(source=source, months=months):
                result = add_month(shift_date(date(source), Decimal('0.1234')), Decimal(months))
                self.assertEqual(result, date(expected))
                self.assertFalse(result.boundary)
                self.assertEqual(result.ticks % TICKS_PER_SECOND, 0)

    def test_counts_truncate_toward_zero_even_with_zero_and_fractional_ticks(self):
        source = shift_date(date('20240515123456'), Decimal('0.9999'))
        for count, expected in (
                ('0', '20240515123456'), ('-0', '20240515123456'),
                ('0.999999', '20240515123456'), ('-0.999999', '20240515123456'),
                ('1.999999', '20240615123456'), ('-1.999999', '20240415123456'),
                ('12.999', '20250515123456'), ('-12.999', '20230515123456'),
                ('1e-999999999', '20240515123456'), ('-1e-999999999', '20240515123456')):
            with self.subTest(count=count):
                self.assertEqual(add_month(source, Decimal(count)), date(expected))

    def test_negative_source_fraction_uses_preceding_whole_second(self):
        source = shift_date(date('20240301000000'), Decimal('-0.0001'))
        self.assertEqual(add_month(source, Decimal(0)), date('20240229235959'))
        self.assertEqual(add_month(source, Decimal(1)), date('20240329235959'))
        self.assertEqual(add_month(source, Decimal(-1)), date('20240129235959'))

    def test_clipping_is_not_associative_and_does_not_restore_end_of_month(self):
        source = date('20240131')
        clipped = add_month(source, Decimal(1))
        self.assertEqual(add_month(clipped, Decimal(1)), date('20240329'))
        self.assertEqual(add_month(source, Decimal(2)), date('20240331'))
        self.assertEqual(add_month(clipped, Decimal(-1)), date('20240129'))
        self.assertEqual(date_difference(add_month(clipped, Decimal(1)),
                                         add_month(source, Decimal(2))), Decimal(-172800))

    def test_gregorian_month_matrix_against_independent_calendar_oracle(self):
        for year in (1, 4, 100, 400, 1600, 1700, 1900, 2000, 2023, 2024, 2400, 9999):
            for month in range(1, 13):
                for day in (1, calendar.monthrange(year, month)[1]):
                    source = datetime(year, month, day, 17, 28, 39)
                    value = shift_date(date(canonical(source)), Decimal('0.4321'))
                    for count in (-25, -13, -12, -1, 0, 1, 12, 13, 25):
                        index = (year - 1) * 12 + month - 1 + count
                        if not 0 <= index < 9999 * 12:
                            continue
                        target_year, target_month = divmod(index, 12)
                        target_year, target_month = target_year + 1, target_month + 1
                        target = source.replace(year=target_year, month=target_month,
                                                day=min(day, calendar.monthrange(
                                                    target_year, target_month)[1]))
                        with self.subTest(source=source, count=count):
                            self.assertEqual(add_month(value, Decimal(count)), date(canonical(target)))

    def test_whole_supported_span_and_exact_known_endpoints(self):
        minimum = date('00010101000000')
        self.assertEqual(add_month(minimum, Decimal(119987)), date('99991201000000'))
        self.assertEqual(add_month(date('99991201000000'), Decimal(-119987)), minimum)
        self.assertEqual(add_month(date('99991130235959'), Decimal(1)), date('99991230235959'))
        for source in (minimum, date('99991231235959')):
            result = add_month(source, Decimal(0))
            self.assertEqual(result, source)
            self.assertFalse(result.boundary)


class CalendarPeriodTests(unittest.TestCase):
    def test_all_units_have_exact_whole_second_limits(self):
        expected = {
            'minute': ('20240229123400', '20240229123459'),
            'hour': ('20240229120000', '20240229125959'),
            'day': ('20240229000000', '20240229235959'),
            'week': ('20240226000000', '20240303235959'),
            'month': ('20240201000000', '20240229235959'),
            'quarter': ('20240101000000', '20240331235959'),
            'year': ('20240101000000', '20241231235959'),
        }
        for fraction in ('0', '0.0001', '0.1234', '0.9999'):
            source = shift_date(date(BASE), Decimal(fraction))
            for unit, (first, last) in expected.items():
                with self.subTest(unit=unit, fraction=fraction):
                    for result, wanted in ((begin_period(source, unit), first),
                                           (end_period(source, unit), last)):
                        self.assertEqual(result, date(wanted))
                        self.assertEqual(result.ticks % TICKS_PER_SECOND, 0)
                        self.assertFalse(result.boundary)

    def test_periods_floor_negative_source_fraction_to_correct_calendar_day(self):
        source = shift_date(date('20240401000000'), Decimal('-0.0001'))
        expected = {
            'minute': ('20240331235900', '20240331235959'),
            'hour': ('20240331230000', '20240331235959'),
            'day': ('20240331000000', '20240331235959'),
            'week': ('20240325000000', '20240331235959'),
            'month': ('20240301000000', '20240331235959'),
            'quarter': ('20240101000000', '20240331235959'),
            'year': ('20240101000000', '20241231235959'),
        }
        for unit, (first, last) in expected.items():
            with self.subTest(unit=unit):
                self.assertEqual(begin_period(source, unit), date(first))
                self.assertEqual(end_period(source, unit), date(last))

    def test_week_is_monday_to_sunday_and_crosses_calendar_year(self):
        for offset in range(7):
            source = shift_date(date('20201228123456'), Decimal(offset * 86400))
            self.assertEqual(begin_period(source, 'week'), date('20201228000000'))
            self.assertEqual(end_period(source, 'week'), date('20210103235959'))
        self.assertEqual(begin_period(date('20210104123456'), 'week'), date('20210104000000'))
        self.assertEqual(end_period(date('20210104123456'), 'week'), date('20210110235959'))

    def test_month_quarter_and_year_ends_cover_all_months_and_leap_centuries(self):
        for year in (1, 4, 100, 400, 1600, 1700, 1900, 2000, 2023, 2024, 2400, 9999):
            for month in range(1, 13):
                value = date(canonical(datetime(year, month, 15, 12, 34, 56)))
                last_month_day = calendar.monthrange(year, month)[1]
                first_quarter_month = ((month - 1) // 3) * 3 + 1
                last_quarter_month = first_quarter_month + 2
                expected = {
                    'month': (datetime(year, month, 1), datetime(year, month, last_month_day, 23, 59, 59)),
                    'quarter': (datetime(year, first_quarter_month, 1), datetime(
                        year, last_quarter_month, calendar.monthrange(year, last_quarter_month)[1], 23, 59, 59)),
                    'year': (datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59)),
                }
                for unit, (first, last) in expected.items():
                    with self.subTest(year=year, month=month, unit=unit):
                        self.assertEqual(begin_period(value, unit), date(canonical(first)))
                        self.assertEqual(end_period(value, unit), date(canonical(last)))

    def test_begin_end_idempotence_and_closed_whole_second_period_lengths(self):
        source = shift_date(date(BASE), Decimal('0.9'))
        lengths = {'minute': 60, 'hour': 3600, 'day': 86400, 'week': 7 * 86400,
                   'month': 29 * 86400, 'quarter': 91 * 86400, 'year': 366 * 86400}
        for unit in UNITS:
            first, last = begin_period(source, unit), end_period(source, unit)
            with self.subTest(unit=unit):
                self.assertEqual(begin_period(first, unit), first)
                self.assertEqual(begin_period(last, unit), first)
                self.assertEqual(end_period(first, unit), last)
                self.assertEqual(end_period(last, unit), last)
                self.assertEqual(date_difference(last, first), Decimal(lengths[unit] - 1))
                self.assertLessEqual(first.ticks, source.ticks)
                self.assertLess(source.ticks, last.ticks + TICKS_PER_SECOND)

    def test_minimum_and_maximum_periods_do_not_construct_year_ten_thousand(self):
        minimum, maximum = date('00010101000000'), date('99991231235959')
        starts = {'minute': '99991231235900', 'hour': '99991231230000',
                  'day': '99991231000000', 'week': '99991227000000',
                  'month': '99991201000000', 'quarter': '99991001000000',
                  'year': '99990101000000'}
        for unit in UNITS:
            with self.subTest(unit=unit):
                self.assertEqual(begin_period(minimum, unit), minimum)
                self.assertEqual(begin_period(maximum, unit), date(starts[unit]))
                if unit != 'week':
                    result = end_period(maximum, unit)
                    self.assertFalse(result.boundary)
                    self.assertEqual(result, maximum)
        self.assertEqual(end_period(minimum, 'week'), date('00010107235959'))


class CalendarNumberingTests(unittest.TestCase):
    def test_week_one_contains_january_first_and_is_not_iso_numbering(self):
        for source, expected, iso in (('20210101', 1, 53), ('20160104', 2, 1),
                                      ('20181231', 53, 1), ('20121231', 54, 1)):
            with self.subTest(source=source):
                value = date(source)
                self.assertEqual(week_of_year(value), Decimal(expected))
                self.assertEqual(datetime.strptime(source, '%Y%m%d').isocalendar().week, iso)
                self.assertNotEqual(expected, iso)
        self.assertEqual(week_day(date('20240303')), Decimal(7))
        self.assertEqual(week_day(date('20240304')), Decimal(1))

    def test_each_day_of_representative_gregorian_years_matches_independent_oracle(self):
        for year in (1, 4, 100, 400, 1600, 1700, 1900, 1999, 2000, 2012,
                     2015, 2016, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 9999):
            first = datetime(year, 1, 1)
            for index in range(366 if calendar.isleap(year) else 365):
                current = first + timedelta(days=index, hours=12, minutes=34, seconds=56)
                value = date(canonical(current))
                with self.subTest(date=canonical(current)):
                    results = (day_of_year(value), week_day(value), week_of_year(value))
                    self.assertTrue(all(type(result) is Decimal for result in results))
                    self.assertEqual(results, (Decimal(index + 1), Decimal(current.weekday() + 1),
                                               Decimal((index + first.weekday()) // 7 + 1)))

    def test_numbering_has_full_400_year_gregorian_repeat(self):
        for year in range(1600, 2000):
            for month, day in ((1, 1), (2, 28), (3, 1), (12, 31)):
                first = date(canonical(datetime(year, month, day)))
                repeated = date(canonical(datetime(year + 400, month, day)))
                for _, _, function in NUMBERS:
                    self.assertEqual(function(first), function(repeated))

    def test_numbering_uses_actual_day_after_fractional_arithmetic(self):
        source = date('20240101000000')
        previous = shift_date(source, Decimal('-0.0001'))
        self.assertEqual((day_of_year(previous), week_day(previous), week_of_year(previous)),
                         (Decimal(365), Decimal(7), Decimal(53)))
        for fraction in ('0', '0.0001', '0.9999'):
            value = shift_date(source, Decimal(fraction))
            self.assertEqual((day_of_year(value), week_day(value), week_of_year(value)),
                             (Decimal(1), Decimal(1), Decimal(1)))


class CalendarValidationTests(unittest.TestCase):
    def test_exact_native_types_reject_python_values_and_subclasses_without_conversion(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('host string conversion')
            def __int__(self):
                raise AssertionError('host integer conversion')
        class DateSubclass(BSLDate):
            pass
        class DecimalSubclass(Decimal):
            pass
        for value in (None, False, True, 1, 1.0, '20240229', Decimal(1), [], {},
                      datetime(2024, 2, 29), Hostile(), DateSubclass(date(BASE).ticks)):
            for operation in unary_calls(value) + [lambda: add_month(value, Decimal(1))]:
                with self.subTest(kind=type(value)), self.assertRaises((TypeError, ValueError)):
                    operation()
        for value in (None, False, True, 1, 1.0, '1', [], {}, Hostile(),
                      date(BASE), DecimalSubclass('1')):
            with self.subTest(count=type(value)), self.assertRaises((TypeError, ValueError)):
                add_month(date(BASE), value)

    def test_month_counts_are_finite_and_have_bounded_coefficient_digits(self):
        for text in ('NaN', '-NaN', 'sNaN', 'Infinity', '-Infinity'):
            with self.subTest(count=text), self.assertRaises((TypeError, ValueError)):
                add_month(date(BASE), Decimal(text))
        limit = Decimal((0, (1,) + (0,) * 4095, -4095))
        self.assertEqual(add_month(date(BASE), limit), date('20240329123456'))
        for sign in (0, 1):
            excess = Decimal((sign, (1,) + (0,) * 4096, -4096))
            with self.subTest(sign=sign), self.assertRaisesRegex(ValueError, '4096'):
                add_month(date(BASE), excess)
        for text in ('1e999999999', '-1e999999999', '120001', '-120001'):
            with self.subTest(count=text), self.assertRaises((TypeError, ValueError)):
                add_month(date(BASE), Decimal(text))

    def test_host_decimal_context_cannot_round_signal_or_change_results(self):
        source = shift_date(date(BASE), Decimal('0.1234'))
        expected = [operation() for operation in unary_calls(source)]
        with localcontext() as context:
            context.prec, context.Emax, context.Emin = 1, 1, -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual([operation() for operation in unary_calls(source)], expected)
            self.assertEqual(add_month(source, Decimal('12.999999')), date('20250228123456'))
            self.assertEqual(add_month(source, Decimal('-12.999999')), date('20230228123456'))
            self.assertEqual(add_month(source, Decimal('1e-999999999')), date(BASE))
            self.assertEqual(week_of_year(date('20121231')), Decimal(54))
            self.assertFalse(any(context.flags.values()))

    def test_unknown_internal_period_names_are_rejected(self):
        for unit in ('', 'second', 'fortnight', 'Day', None, Decimal(1)):
            for function in (begin_period, end_period):
                with self.subTest(unit=unit, function=function.__name__), \
                        self.assertRaises((TypeError, ValueError)):
                    function(date(BASE), unit)


class CalendarBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.minimum, self.maximum = date('00010101000000'), date('99991231235959')
        self.boundaries = (add_month(self.minimum, Decimal(-1)),
                           add_month(self.maximum, Decimal(1)),
                           end_period(self.maximum, 'week'))

    def test_only_observed_scalar_streams_and_type_are_claimed(self):
        for value, ticks in zip(self.boundaries, (0, 0, MAX_TICKS)):
            with self.subTest(ticks=ticks):
                self.assertIs(type(value), BSLDate)
                self.assertTrue(value.boundary)
                self.assertEqual(value.ticks, ticks)
                self.assertIs(type_of(value), BSLType.DATE)
                self.assertEqual(write(value), write(BSLDate(ticks)))
                restored = read(write(value))
                self.assertFalse(restored.boundary)
                self.assertEqual(restored, BSLDate(ticks))

    def test_unobserved_month_overshoots_and_fractional_source_endpoints_are_rejected(self):
        cases = [(self.minimum, '-2'), (self.minimum, '-12'), (self.minimum, '-1.5'),
                 (self.maximum, '2'), (self.maximum, '12'), (self.maximum, '1.5'),
                 (date('00010102000000'), '-1'), (date('00010101000001'), '-1'),
                 (date('99991230235959'), '1'), (date('99991231235958'), '1'),
                 (shift_date(self.minimum, Decimal('0.0001')), '-1'),
                 (shift_date(self.maximum, Decimal('-0.0001')), '1')]
        for source, months in cases:
            with self.subTest(source=write(source), months=months), \
                    self.assertRaises(UnsupportedDateRange):
                add_month(source, Decimal(months))
        # Equality of decimal values is sufficient; textual scale is not new evidence.
        self.assertTrue(add_month(self.minimum, Decimal('-1.000')).boundary)
        self.assertTrue(add_month(self.maximum, Decimal('1.000')).boundary)

    def test_only_exact_maximum_has_observed_overflowing_end_of_week_stream(self):
        for canonical_text in ('99991227000000', '99991228123456', '99991229000000',
                               '99991230000000', '99991231000000', '99991231235958'):
            with self.subTest(source=canonical_text), self.assertRaises(UnsupportedDateRange):
                end_period(date(canonical_text), 'week')
        with self.assertRaises(UnsupportedDateRange):
            end_period(shift_date(self.maximum, Decimal('-0.0001')), 'week')
        known = end_period(date('99991226000000'), 'week')
        self.assertFalse(known.boundary)
        self.assertEqual(known, date('99991226235959'))

    def test_all_calendar_functions_reject_existing_and_new_opaque_boundaries(self):
        values = self.boundaries + (shift_date(self.minimum, Decimal(-1)),
                                   shift_date(self.maximum, Decimal(1)))
        for value in values:
            for operation in unary_calls(value) + [lambda: add_month(value, Decimal(0)),
                                                   lambda: add_month(value, Decimal(1))]:
                with self.subTest(stream=write(value)), self.assertRaises(UnsupportedDateRange):
                    operation()

    def test_calendar_boundaries_cannot_be_compared_hashed_presented_or_used_as_keys(self):
        for value in self.boundaries:
            operations = [lambda: hash(value), lambda: str(value), lambda: to_string(value),
                          lambda: value_is_filled(value), lambda: component(value, 'year'),
                          lambda: date_difference(value, self.minimum),
                          lambda: date_difference(self.maximum, value),
                          lambda: shift_date(value, Decimal(0)),
                          lambda: BSLMap().insert(value, 'unknown'),
                          lambda: BSLMap().get(value), lambda: BSLMap().delete(value),
                          lambda: BSLFixedMap(BSLMap()).get(value),
                          lambda: BSLArray().find(value), lambda: BSLFixedArray(BSLArray()).find(value)]
            for other in (value, self.minimum, self.maximum, None, False, Decimal(0), 'date'):
                operations += [lambda other=other: equal(value, other),
                               lambda other=other: equal(other, value),
                               lambda other=other: value == other,
                               lambda other=other: value != other]
            for operation in operations:
                with self.assertRaises(UnsupportedDateRange):
                    operation()

    def test_nested_streams_cannot_turn_boundary_evidence_into_normal_dates(self):
        for value in self.boundaries:
            containers = (array(value), BSLFixedArray(array(value)),
                          BSLStructure('When', value), BSLFixedStructure('When', value),
                          mapping(('When', value)), BSLFixedMap(mapping(('When', value))),
                          BSLKeyAndValue('When', value), BSLKeyAndValue(value, None))
            for container in containers:
                with self.subTest(container=type(container)), self.assertRaises(UnsupportedDateRange):
                    write(container)


class CalendarRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('source = Date(2024, 2, 29, 12, 34, 56) + 0.1234;')

    def test_all_18_bilingual_functions_and_case_variants(self):
        source = self.vm.variables['source']
        self.assertEqual(len(ALIASES) + len(NUMBERS) + 1, 18)
        for english, russian, unit, ending in ALIASES:
            expected = (end_period if ending else begin_period)(source, unit)
            for name in (english, russian, english.swapcase(), russian.swapcase()):
                with self.subTest(alias=name):
                    self.assertEqual(self.vm.execute(name + '(source)'), expected)
        for english, russian, function in NUMBERS:
            for name in (english, russian, english.swapcase(), russian.swapcase()):
                with self.subTest(alias=name):
                    self.assertEqual(self.vm.execute(name + '(source)'), function(source))
        for name in ('AddMonth', 'ДобавитьМесяц', 'aDdMoNtH', 'дОбАвИтЬмЕсЯц'):
            self.assertEqual(self.vm.execute(name + '(source, 1.5)'), date('20240329123456'))

    def test_bad_arity_omissions_and_types_are_catchable_and_preserve_assignment(self):
        names = [name for pair in [(en, ru) for en, ru, _, _ in ALIASES]
                 + [(en, ru) for en, ru, _ in NUMBERS] for name in pair]
        failures = [name + suffix for name in names
                    for suffix in ('()', '(source, 1)', '(, source)', '(Undefined)', '(0)', '("20240229")')]
        failures += [name + suffix for name in ('AddMonth', 'ДобавитьМесяц')
                     for suffix in ('()', '(source)', '(source, 1, 2)', '(source,,1)',
                                    '(, 1)', '(source, Undefined)', '(source, "1")',
                                    '(source, True)', '(0, 1)')]
        for expression in failures:
            with self.subTest(expression=expression):
                self.vm.execute('saved = 7; caught = False; Try saved = ' + expression
                                + '; Except caught = True; EndTry;')
                self.assertIs(self.vm.execute('caught'), True)
                self.assertEqual(self.vm.execute('saved'), Decimal(7))
        self.assertEqual(self.vm.execute('AddMonth(source, 1)'), date('20240329123456'))

    def test_registered_alias_overrides_are_local_and_do_not_change_sibling_alias(self):
        self.vm.register_function('AddMonth', lambda *args: 'override')
        self.vm.register_function('BegOfDay', lambda *args: 'start override')
        self.assertEqual(self.vm.execute('AddMonth(source, 1)'), 'override')
        self.assertEqual(self.vm.execute('BegOfDay(source)'), 'start override')
        self.assertEqual(self.vm.execute('ДобавитьМесяц(source, 1)'), date('20240329123456'))
        self.assertEqual(self.vm.execute('НачалоДня(source)'), date('20240229000000'))
        self.assertEqual(Interpreter().execute('AddMonth(Date(2024,2,29),1)'), date('20240329'))

    def test_arguments_evaluate_once_and_normal_calls_do_not_mutate_source(self):
        self.vm.execute('''
            Var calls;
            Function PickDate(Val value) calls = calls + 1; Return value; EndFunction
            Function PickCount() calls = calls + 10; Return 1.5; EndFunction
            calls = 0; shifted = AddMonth(PickDate(source), PickCount());
        ''')
        self.assertEqual(self.vm.execute('calls'), Decimal(11))
        self.assertEqual(self.vm.execute('shifted'), date('20240329123456'))
        self.assertEqual(self.vm.execute('source - Date(2024,2,29,12,34,56)'), Decimal('0.1234'))
        self.vm.execute('calls = 0; result = EndOfDay(PickDate(source));')
        self.assertEqual(self.vm.execute('calls'), Decimal(1))

    def test_eval_execute_defaults_and_runtime_error_recovery(self):
        self.assertEqual(self.vm.execute('Eval("AddMonth(source, 1.5)")'), date('20240329123456'))
        self.vm.execute('''
            Function DefaultDate(Val value = '20240229123456')
                Return EndOfMonth(AddMonth(value, 12));
            EndFunction
            saved = Undefined; Execute("saved = НачалоКвартала(AddMonth(source, 2));");
        ''')
        self.assertEqual(self.vm.execute('saved'), date('20240401000000'))
        self.assertEqual(self.vm.execute('DefaultDate()'), date('20250228235959'))
        for expression in ('AddMonth(source, Undefined)', 'WeekDay(0)',
                           'EndOfWeek(Date(9999,12,30))', 'AddMonth(Date(1,1,2),-1)'):
            for dynamic in ('Eval', 'Execute'):
                self.vm.execute('saved = 7; caught = False;')
                body = expression if dynamic == 'Eval' else 'saved = ' + expression + ';'
                call = dynamic + '(' + quote(body) + ')'
                statement = 'saved = ' + call + ';' if dynamic == 'Eval' else call + ';'
                self.vm.execute('Try ' + statement + ' Except caught = True; EndTry;')
                self.assertTrue(self.vm.execute('caught'))
                self.assertEqual(self.vm.execute('saved'), Decimal(7))
                self.assertIsNone(self.vm.locals)
                self.assertEqual(self.vm._execute_depth[0], 0)
        self.assertEqual(self.vm.execute('Eval("WeekOfYear(Date(2016,1,4))")'), Decimal(2))

    def test_calendar_results_work_as_collection_values_and_typed_map_keys(self):
        self.vm.execute('''
            first = EndOfMonth(source); items = New Array;
            items.Add(first); fixed = New FixedArray(items);
            record = New FixedStructure("When", first);
            map = New Map; map.Insert(first, "original");
            map.Insert(EndOfDay(Date(2024,2,29)), "replacement");
            map.Insert(AddMonth(first, 0) + 0.0001, "fraction");
            frozen = New FixedMap(map);
            restored = ValueFromStringInternal(ValueToStringInternal(record));
            mapRestored = ValueFromStringInternal(ValueToStringInternal(
                New Structure("When", AddMonth(source, 1))));
        ''')
        self.assertEqual(self.vm.execute('items.Find(EndOfDay(source))'), Decimal(0))
        self.assertEqual(self.vm.execute('fixed.Find(EndOfMonth(source))'), Decimal(0))
        self.assertEqual(self.vm.execute('map.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('frozen[EndOfDay(source)]'), 'replacement')
        self.assertEqual(self.vm.execute('frozen[EndOfDay(source) + 0.0001]'), 'fraction')
        self.assertIs(self.vm.execute('(restored.When = first)'), True)
        self.assertEqual(self.vm.execute('mapRestored.When'), date('20240329123456'))
        first = self.vm.variables['first']
        for container in (array(first), BSLFixedArray(array(first)), BSLStructure('When', first),
                          BSLFixedStructure('When', first), mapping((first, first)),
                          BSLFixedMap(mapping((first, first))), BSLKeyAndValue(first, first)):
            self.assertEqual(write(read(write(container))), write(container))
        restored = read(write(mapping((first, 'present'))))
        self.assertEqual(restored.get(end_period(date(BASE), 'day')), 'present')

    def test_boundary_errors_through_bsl_are_catchable_and_scalar_codec_still_works(self):
        for boundary in (add_month(date('00010101'), Decimal(-1)),
                         add_month(date('99991231235959'), Decimal(1)),
                         end_period(date('99991231235959'), 'week')):
            self.vm.variables['opaque'] = boundary
            self.vm.execute('boundaryMap = New Map;')
            self.assertIs(self.vm.execute('TypeOf(opaque)'), BSLType.DATE)
            self.assertEqual(self.vm.execute('ValueToStringInternal(opaque)'), write(boundary))
            failures = ['AddMonth(opaque, 0)', 'String(opaque)', 'opaque = opaque',
                        'boundaryMap.Get(opaque)', 'ValueToStringInternal(New Structure("When",opaque))']
            failures += [en + '(opaque)' for en, _, _, _ in ALIASES]
            failures += [en + '(opaque)' for en, _, _ in NUMBERS]
            for expression in failures:
                self.vm.execute('saved = 7; caught = False; Try saved = ' + expression
                                + '; Except caught = True; EndTry;')
                self.assertTrue(self.vm.execute('caught'), expression)
                self.assertEqual(self.vm.execute('saved'), Decimal(7))


class CalendarCLITests(unittest.TestCase):
    PROGRAM = '''source = Date(2024,2,29,12,34,56) + 0.1234;
Message(ValueToStringInternal(AddMonth(source,12)));
Message(ValueToStringInternal(КонецКвартала(source)));
Message(ValueToStringInternal(BegOfWeek(source)));
Message(WeekOfYear(Date(2016,1,4)));
Message(DayOfYear(Date(2024,12,31)));
Message(WeekDay(Date(2024,3,3)));
Message(ValueToStringInternal(AddMonth(Date(9999,12,31,23,59,59),1)));
'''
    OUTPUT = ('{"D",20250228123456}\n{"D",20240331235959}\n'
              '{"D",20240226000000}\n2\n366\n7\n{"D",00010101000000}\n')

    def run_cli(self, *arguments, stdin=None, cwd=ROOT):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(
            filter(None, [str(ROOT), environment.get('PYTHONPATH')]))
        return subprocess.run([sys.executable, '-m', 'yadinassi', *arguments],
                              input=stdin, capture_output=True, encoding='utf-8',
                              cwd=cwd, env=environment, timeout=15)

    def test_all_command_aliases_bom_file_stdin_and_console(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'Календарь.bsl'
            source.write_text(self.PROGRAM, encoding='utf-8-sig')
            cases = [((flag, self.PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), ((source.name,), None),
                      (('-',), self.PROGRAM), ((), self.PROGRAM + '/exit\n')]
            for arguments, stdin in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, self.OUTPUT, ''))

    def test_cli_diagnostics_have_source_line_and_console_recovers_saved_value(self):
        code = 'saved = Date(2024,2,29);\nsaved = AddMonth(saved, Undefined);\n'
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            source = temporary / 'ОшибкаКалендаря.bsl'
            source.write_text(code, encoding='utf-8-sig')
            cases = [((flag, code), None, '<команда>:2:', '')
                     for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None, str(source) + ':2:', ''),
                      (('-',), code, '<stdin>:2:', ''),
                      ((), code + 'ValueToStringInternal(EndOfMonth(saved))\n/exit\n',
                       '<консоль>:1:', '{"D",20240229235959}\n')]
            for arguments, stdin, location, expected in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments, stdin=stdin, cwd=temporary)
                    self.assertEqual((result.returncode, result.stdout), (1, expected))
                    self.assertIn(location, result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('TypeError', result.stderr)

    def test_bom_imported_calendar_routines_and_dynamic_recovery(self):
        module_text = '''Function MonthEnd(Val source = '20240229123456') Export
    Return EndOfMonth(AddMonth(source,12));
EndFunction
Function Dynamic(Val source) Export
    saved = Undefined; Execute("saved = НачалоНедели(source);");
    Return saved;
EndFunction
Function Failure() Export
    Return EndOfWeek(Date(9999,12,30));
EndFunction
'''
        main_text = '''// #Импорт Календарь.bsl
Message(ValueToStringInternal(Календарь.MonthEnd()));
Message(ValueToStringInternal(Календарь.Dynamic(Date(2024,2,29))));
Try Календарь.Failure(); Except Message("caught"); EndTry;
Message(ValueToStringInternal(Календарь.MonthEnd()));
'''
        expected = ('{"D",20250228235959}\n{"D",20240226000000}\n'
                    'caught\n{"D",20250228235959}\n')
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary).resolve()
            project = temporary / 'проект'
            project.mkdir()
            module, main = project / 'Календарь.bsl', project / 'Основное.bsl'
            module.write_text(module_text, encoding='utf-8-sig')
            main.write_text(main_text, encoding='utf-8-sig')
            for path in (main, main.relative_to(temporary)):
                result = self.run_cli(str(path), cwd=temporary)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, ''))
            main.write_text('// #Импорт Календарь.bsl\nКалендарь.Failure();\n', encoding='utf-8-sig')
            result = self.run_cli(str(main), cwd=temporary)
            self.assertEqual((result.returncode, result.stdout), (1, ''))
            self.assertIn(str(module) + ':9:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
