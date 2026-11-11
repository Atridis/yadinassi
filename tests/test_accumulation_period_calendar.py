"""Host date/index guards only; no unmeasured native statement semantics."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import unittest

from yadinassi.accumulation_periods import CalendarSpan, bind_dates
from yadinassi.dates import BSLDate, MAX_TICKS, _from_parts
from yadinassi.query_parser import Parameter


class AccumulationPeriodCalendarTests(unittest.TestCase):
    def test_named_dates_bind_caseless_without_changing_parameters(self):
        value = _from_parts((2024, 2, 29, 12, 0, 0))
        parameters = {'start': value, 'finish': value}
        self.assertEqual(bind_dates((Parameter('START'), Parameter('Finish')), parameters, 2),
                         (datetime(2024, 2, 29, 12),) * 2)
        self.assertEqual(parameters, {'start': value, 'finish': value})

    def test_missing_date_is_not_a_default(self):
        with self.assertRaisesRegex(ValueError, 'Missing accumulation'):
            bind_dates((Parameter('Absent'),), {}, 1)

    def test_only_exact_named_parameter_tuple_is_accepted(self):
        for args in ([Parameter('A')], ('A',), (), (Parameter('A'), Parameter('B'))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                bind_dates(args, {'a': _from_parts((2024, 1, 1))}, 1)

    def test_non_dates_and_fractional_seconds_are_refused(self):
        for value in (None, False, 0, '20240101', datetime(2024, 1, 1), BSLDate(1)):
            with self.subTest(value=value), self.assertRaises(TypeError):
                bind_dates((Parameter('A'),), {'a': value}, 1)

    def test_unknown_boundary_state_is_refused(self):
        for ticks in (0, MAX_TICKS):
            with self.assertRaises(ValueError):
                bind_dates((Parameter('A'),), {'a': BSLDate(ticks, boundary=True)}, 1)

    def test_reversed_dates_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'Reversed'):
            bind_dates((Parameter('A'), Parameter('B')),
                       {'a': _from_parts((2024, 2, 1)), 'b': _from_parts((2024, 1, 1))}, 2)

    def test_day_index_respects_partial_endpoints(self):
        span = CalendarSpan(datetime(2024, 2, 28, 12), datetime(2024, 3, 1, 3), 'day')
        self.assertEqual(span.count, 3)
        self.assertEqual([span.label(i) for i in span.bounded_indices(3)],
                         [datetime(2024, 2, 28), datetime(2024, 2, 29), datetime(2024, 3, 1)])
        self.assertEqual(span.index(datetime(2024, 2, 29, 23, 59, 59)), 1)
        for value in (datetime(2024, 2, 28, 11, 59, 59), datetime(2024, 3, 1, 3, 0, 1)):
            with self.assertRaises(ValueError): span.index(value)

    def test_month_index_crosses_year_and_leap_month(self):
        span = CalendarSpan(datetime(2023, 12, 31, 23), datetime(2024, 3, 1), 'month')
        self.assertEqual(span.count, 4)
        self.assertEqual(span.label(0), datetime(2023, 12, 1))
        self.assertEqual(span.label(3), datetime(2024, 3, 1))
        self.assertEqual(span.index(datetime(2024, 2, 29, 23, 59, 59)), 2)

    def test_last_date_never_constructs_an_overflow_successor(self):
        last = datetime(9999, 12, 31, 23, 59, 59)
        for mode, expected in (('day', datetime(9999, 12, 31)), ('month', datetime(9999, 12, 1))):
            span = CalendarSpan(last, last, mode)
            self.assertEqual(span.count, 1)
            self.assertEqual(span.label(0), expected)
            self.assertEqual(span.index(last), 0)

    def test_wide_interval_keeps_constant_space_and_refuses_expansion(self):
        span = CalendarSpan(datetime.min, datetime(9999, 12, 31, 23, 59, 59), 'day')
        self.assertEqual(span.count, 3652059)
        with self.assertRaisesRegex(ValueError, 'expansion limit'): span.bounded_indices(10000)
        self.assertEqual(span.label(span.count - 1), datetime(9999, 12, 31))

    def test_zero_negative_boolean_or_float_expansion_limits_are_refused(self):
        span = CalendarSpan(datetime(2024, 1, 1), datetime(2024, 1, 1), 'day')
        for limit in (0, -1, True, 1.0):
            with self.subTest(limit=limit), self.assertRaises(ValueError): span.bounded_indices(limit)

    def test_calendar_modes_and_indices_are_closed(self):
        for mode in ('Day', 'week', 'auto', '', None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                CalendarSpan(datetime(2024, 1, 1), datetime(2024, 1, 1), mode)
        span = CalendarSpan(datetime(2024, 1, 1), datetime(2024, 1, 1), 'month')
        for index in (-1, 1, True, 0.0):
            with self.subTest(index=index), self.assertRaises(ValueError): span.label(index)

    def test_calendar_rejects_tz_fold_fraction_and_subclasses(self):
        class Foreign(datetime): pass
        for value in (datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 1, fold=1),
                      datetime(2024, 1, 1, microsecond=1), Foreign(2024, 1, 1)):
            with self.subTest(value=value), self.assertRaises(TypeError):
                CalendarSpan(value, datetime(2024, 1, 2), 'day')

    def test_calendar_is_immutable_and_reversed_range_is_refused(self):
        span = CalendarSpan(datetime(2024, 1, 1), datetime(2024, 1, 1), 'day')
        with self.assertRaises(FrozenInstanceError): span.start = datetime(2023, 1, 1)
        with self.assertRaises(ValueError): CalendarSpan(datetime(2024, 2, 1), datetime(2024, 1, 1), 'day')
