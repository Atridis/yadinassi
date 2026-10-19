"""Documented clock contracts and explicit local policies, not native fixtures.

All exact timestamps are deterministic injected host samples. Whole-second Date
precision, nanosecond flooring and defensive range/error behavior are local
implementation policies, not measurements of a real 1C clock.
"""

from datetime import datetime, timedelta
from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter, clocks
from yadinassi.dates import (
    BSLDate, TICKS_PER_SECOND, UnsupportedDateRange, date, date_difference,
)
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.serialization import (
    value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_of
from yadinassi.value_checks import value_is_filled
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, equal, to_string


ROOT = Path(__file__).resolve().parents[1]
UNIX_EPOCH = datetime(1970, 1, 1)
NS_PER_SECOND = 1_000_000_000
EPOCH_MILLISECONDS = 62_135_596_800_000
MIN_NS = -62_135_596_800 * NS_PER_SECOND
MAX_NS = 253_402_300_800 * NS_PER_SECOND - 1
BASE = datetime(2024, 2, 29, 12, 34, 56)
DATE_FUNCTIONS = (clocks.current_date, clocks.current_universal_date)
FUNCTIONS = DATE_FUNCTIONS + (clocks.current_universal_date_in_milliseconds,)
NAMES = tuple(name for ru, _, en in clocks.BUILTINS for name in (ru, en))


def unix_ns(value, nanoseconds=0):
    delta = value - UNIX_EPOCH
    return (delta.days * 86400 + delta.seconds) * NS_PER_SECOND + nanoseconds


def canonical(value):
    return (f'{value.year:04}{value.month:02}{value.day:02}'
            f'{value.hour:02}{value.minute:02}{value.second:02}')


def localtime_at_offset(offset):
    def convert(seconds):
        return (UNIX_EPOCH + timedelta(seconds=seconds + offset)).timetuple()
    return convert


def array(*values):
    result = BSLArray()
    for value in values:
        result.add(value)
    return result


def mapping(*entries):
    result = BSLMap()
    for key, value in entries:
        result.insert(key, value)
    return result


class ClockSamplingTests(unittest.TestCase):
    def test_each_function_reads_wall_clock_exactly_once(self):
        with patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(0)):
            for function in FUNCTIONS:
                with self.subTest(function=function.__name__), patch.object(
                        clocks.time, 'time_ns', return_value=unix_ns(BASE, 123456789)) as sample:
                    result = function()
                    sample.assert_called_once_with()
                    self.assertIs(type(result), BSLDate if function in DATE_FUNCTIONS else Decimal)

    def test_local_date_uses_exact_floored_sample_and_host_conversion(self):
        with patch.object(clocks, '_read_time_ns', return_value=unix_ns(BASE, 999999999)), \
                patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(20700)) as local:
            result = clocks.current_date()
        local.assert_called_once_with(unix_ns(BASE) // NS_PER_SECOND)
        self.assertIs(type(local.call_args.args[0]), int)
        self.assertEqual(result, date('20240229181956'))
        self.assertEqual(result.ticks % TICKS_PER_SECOND, 0)

    def test_utc_functions_never_use_host_calendar_or_timezone_conversion(self):
        with patch.object(clocks, '_read_time_ns', return_value=unix_ns(BASE, 123456789)), \
                patch.object(clocks.time, 'localtime', side_effect=AssertionError('local clock used')), \
                patch.object(clocks.time, 'gmtime', side_effect=AssertionError('C calendar used')):
            self.assertEqual(clocks.current_universal_date(), date('20240229123456'))
            self.assertEqual(clocks.current_universal_date_in_milliseconds(),
                             Decimal('63844806896123'))

    def test_each_invocation_samples_again_instead_of_caching(self):
        with patch.object(clocks, '_read_time_ns', side_effect=[
                unix_ns(BASE), unix_ns(BASE) + NS_PER_SECOND,
                unix_ns(BASE) - NS_PER_SECOND]) as sample:
            values = [clocks.current_universal_date() for _ in range(3)]
        self.assertEqual(sample.call_count, 3)
        self.assertEqual([date_difference(value, values[0]) for value in values],
                         [Decimal(0), Decimal(1), Decimal(-1)])

    def test_wall_clock_may_repeat_or_move_backward(self):
        for function in FUNCTIONS:
            with self.subTest(function=function.__name__), \
                    patch.object(clocks, '_read_time_ns', side_effect=[
                        unix_ns(BASE), unix_ns(BASE), unix_ns(BASE) - NS_PER_SECOND]), \
                    patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(0)):
                first, repeated, earlier = function(), function(), function()
                self.assertEqual(first, repeated)
                if type(first) is BSLDate:
                    self.assertEqual(date_difference(earlier, first), Decimal(-1))
                else:
                    self.assertEqual(earlier, first - Decimal(1000))

    def test_system_clock_failure_is_a_recoverable_value_error(self):
        for function in FUNCTIONS:
            for failure in (OSError('clock failed'), OverflowError(), ValueError()):
                with self.subTest(function=function.__name__, failure=type(failure).__name__), \
                        patch.object(clocks.time, 'time_ns', side_effect=failure), \
                        self.assertRaisesRegex(ValueError, 'системные часы'):
                    function()

    def test_noninteger_system_samples_are_rejected_without_coercion(self):
        class HostValue:
            def __int__(self):
                raise AssertionError('unexpected host conversion')

        class IntSubclass(int):
            pass

        for value in (None, True, False, 1.0, Decimal(1), '1', [], HostValue(), IntSubclass(1)):
            for function in FUNCTIONS:
                with self.subTest(kind=type(value).__name__, function=function.__name__), \
                        patch.object(clocks.time, 'time_ns', return_value=value), \
                        self.assertRaises(TypeError):
                    function()


class ClockCalendarTests(unittest.TestCase):
    def test_utc_epoch_leap_dates_centuries_and_endpoints(self):
        cases = (datetime(1, 1, 1), datetime(4, 2, 29), datetime(1600, 2, 29),
                 datetime(1900, 3, 1), datetime(1969, 12, 31, 23, 59, 59),
                 UNIX_EPOCH, datetime(2000, 2, 29), BASE, datetime(2400, 2, 29),
                 datetime(9999, 12, 31, 23, 59, 59))
        for sample in cases:
            for nanoseconds in (0, 1, 99999, 500000000, 999999999):
                with self.subTest(sample=sample, nanoseconds=nanoseconds), \
                        patch.object(clocks, '_read_time_ns', return_value=unix_ns(sample, nanoseconds)):
                    result = clocks.current_universal_date()
                    self.assertEqual(result, date(canonical(sample)))
                    self.assertIs(result.require_known(), result)
                    self.assertFalse(result.boundary)
                    self.assertEqual(result.ticks % TICKS_PER_SECOND, 0)

    def test_negative_unix_subseconds_floor_to_preceding_second(self):
        for timestamp, expected in ((-1, '19691231235959'),
                                    (-999999999, '19691231235959'),
                                    (-1000000000, '19691231235959'),
                                    (-1000000001, '19691231235958')):
            for function in DATE_FUNCTIONS:
                with self.subTest(timestamp=timestamp, function=function.__name__), \
                        patch.object(clocks, '_read_time_ns', return_value=timestamp), \
                        patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(0)):
                    self.assertEqual(function(), date(expected))

    def test_fractional_samples_do_not_round_across_day_month_or_year(self):
        for sample in (datetime(2023, 12, 31, 23, 59, 59),
                       datetime(2024, 2, 28, 23, 59, 59),
                       datetime(2024, 2, 29, 23, 59, 59)):
            for function in DATE_FUNCTIONS:
                with self.subTest(sample=sample, function=function.__name__), \
                        patch.object(clocks, '_read_time_ns', return_value=unix_ns(sample, 999999999)), \
                        patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(0)):
                    self.assertEqual(function(), date(canonical(sample)))

    def test_local_and_utc_dates_can_be_different_calendar_days(self):
        for sample, offset, expected in (
                (datetime(2024, 2, 29, 20, 30), 20700, '20240301021500'),
                (datetime(2024, 3, 1, 1), -12600, '20240229213000'),
                (datetime(2023, 12, 31, 23), 7200, '20240101010000')):
            with self.subTest(sample=sample, offset=offset), \
                    patch.object(clocks, '_read_time_ns', return_value=unix_ns(sample)), \
                    patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(offset)):
                self.assertEqual(clocks.current_date(), date(expected))
                self.assertEqual(clocks.current_universal_date(), date(canonical(sample)))
                self.assertEqual(date_difference(clocks.current_date(),
                                                 clocks.current_universal_date()), Decimal(offset))

    def test_local_range_applies_after_timezone_conversion(self):
        # A local year-1/year-9999 Date can be valid even when its UTC year is not.
        for sample, parts, expected in (
                (MIN_NS - NS_PER_SECOND, (1, 1, 1, 0, 59, 59), '00010101005959'),
                (MAX_NS + 1, (9999, 12, 31, 23, 0, 0), '99991231230000')):
            with self.subTest(sample=sample), \
                    patch.object(clocks, '_read_time_ns', return_value=sample), \
                    patch.object(clocks.time, 'localtime', return_value=parts):
                self.assertEqual(clocks.current_date(), date(expected))
                with self.assertRaises(UnsupportedDateRange):
                    clocks.current_universal_date()

    def test_local_conversion_failures_and_invalid_calendar_parts_are_bounded(self):
        for failure in (OSError(), OverflowError(), ValueError()):
            with self.subTest(failure=type(failure).__name__), \
                    patch.object(clocks, '_read_time_ns', return_value=0), \
                    patch.object(clocks.time, 'localtime', side_effect=failure), \
                    self.assertRaises(UnsupportedDateRange):
                clocks.current_date()
        for parts in ((0, 12, 31, 23, 59, 59), (10000, 1, 1, 0, 0, 0),
                      (2024, 1, 1, 23, 59, 60), (2023, 2, 29, 0, 0, 0)):
            with self.subTest(parts=parts), patch.object(clocks, '_read_time_ns', return_value=0), \
                    patch.object(clocks.time, 'localtime', return_value=parts), \
                    self.assertRaises(UnsupportedDateRange):
                clocks.current_date()

    def test_utc_outside_year_one_to_9999_rejects_instead_of_clamping(self):
        for timestamp in (MIN_NS - 1, MAX_NS + 1, -(10 ** 100), 10 ** 100):
            with self.subTest(timestamp=timestamp), \
                    patch.object(clocks, '_read_time_ns', return_value=timestamp), \
                    self.assertRaises(UnsupportedDateRange):
                clocks.current_universal_date()


class ClockMillisecondTests(unittest.TestCase):
    def test_milliseconds_use_year_one_epoch_and_exact_decimal_type(self):
        for timestamp, expected in ((MIN_NS, '0'), (MIN_NS + 1000000, '1'),
                                    (0, '62135596800000'),
                                    (unix_ns(BASE, 123456789), '63844806896123'),
                                    (MAX_NS, '315537897599999')):
            with self.subTest(timestamp=timestamp), \
                    patch.object(clocks, '_read_time_ns', return_value=timestamp):
                result = clocks.current_universal_date_in_milliseconds()
                self.assertIs(type(result), Decimal)
                self.assertEqual(result, Decimal(expected))
                self.assertEqual(result.as_tuple().exponent, 0)
                self.assertEqual(result.as_tuple().sign, 0)

    def test_millisecond_floors_do_not_round_or_truncate_negative_unix_time_toward_zero(self):
        for nanoseconds, milliseconds in ((-1000001, -2), (-1000000, -1), (-999999, -1),
                                          (-1, -1), (0, 0), (1, 0), (999999, 0),
                                          (1000000, 1), (1000001, 1),
                                          (999999999, 999), (1000000000, 1000)):
            with self.subTest(nanoseconds=nanoseconds), \
                    patch.object(clocks, '_read_time_ns', return_value=nanoseconds):
                self.assertEqual(clocks.current_universal_date_in_milliseconds(),
                                 Decimal(EPOCH_MILLISECONDS + milliseconds))

    def test_submillisecond_fractions_remain_exact_far_from_unix_epoch(self):
        for base in (MIN_NS, unix_ns(BASE), MAX_NS - 999999999):
            for nanoseconds, fraction in ((0, 0), (999999, 0), (1000000, 1),
                                          (123999999, 123), (999999999, 999)):
                with self.subTest(base=base, nanoseconds=nanoseconds), \
                        patch.object(clocks, '_read_time_ns', return_value=base + nanoseconds):
                    self.assertEqual(clocks.current_universal_date_in_milliseconds(),
                                     Decimal(EPOCH_MILLISECONDS + base // 1000000 + fraction))

    def test_millisecond_date_relation_uses_same_sample_but_preserves_fraction(self):
        for timestamp in (MIN_NS, -1, 0, unix_ns(BASE, 123456789), MAX_NS):
            with self.subTest(timestamp=timestamp), \
                    patch.object(clocks, '_read_time_ns', return_value=timestamp):
                value = clocks.current_universal_date()
                milliseconds = clocks.current_universal_date_in_milliseconds()
                self.assertEqual(int(milliseconds) // 1000, value.ticks // TICKS_PER_SECOND)
                self.assertEqual(int(milliseconds) % 1000, timestamp // 1000000 % 1000)

    def test_millisecond_range_rejects_even_one_nanosecond_outside_calendar(self):
        for timestamp in (MIN_NS - 1, MAX_NS + 1, -(10 ** 100), 10 ** 100):
            with self.subTest(timestamp=timestamp), \
                    patch.object(clocks, '_read_time_ns', return_value=timestamp), \
                    self.assertRaises(UnsupportedDateRange):
                clocks.current_universal_date_in_milliseconds()

    def test_host_decimal_context_cannot_round_signal_or_change_clocks(self):
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_UP
            context.Emax = 1
            context.Emin = -1
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.clear_flags()
            with patch.object(clocks, '_read_time_ns', return_value=unix_ns(BASE, 123999999)), \
                    patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(0)):
                self.assertEqual(clocks.current_date(), date('20240229123456'))
                self.assertEqual(clocks.current_universal_date(), date('20240229123456'))
                self.assertEqual(clocks.current_universal_date_in_milliseconds(),
                                 Decimal('63844806896123'))
            self.assertFalse(any(context.flags.values()))


@unittest.skipUnless(hasattr(time, 'tzset'), 'POSIX host timezone selection requires time.tzset')
class HostTimezoneTests(unittest.TestCase):
    def run_timezone(self, timezone, samples):
        # Only the child process changes TZ; tests never alter the suite's clock
        # or its ambient process timezone, and need no system zoneinfo package.
        program = '''
import json, sys, time
from unittest.mock import patch
from yadinassi import clocks
from yadinassi.serialization import value_to_string_internal as write
time.tzset()
rows = []
for timestamp in json.loads(sys.argv[1]):
    with patch.object(clocks, '_read_time_ns', return_value=timestamp):
        rows.append([write(clocks.current_date()), write(clocks.current_universal_date()),
                     str(clocks.current_universal_date_in_milliseconds())])
print(json.dumps(rows))
'''
        completed = subprocess.run([sys.executable, '-c', program, json.dumps(samples)],
                                   cwd=ROOT, env={**os.environ, 'TZ': timezone},
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_host_nonwholehour_offsets_cross_utc_calendar_days(self):
        samples = [unix_ns(datetime(2024, 2, 29, 20, 30)),
                   unix_ns(datetime(2024, 3, 1, 1))]
        east = self.run_timezone('NPT-5:45', samples)
        west = self.run_timezone('NST3:30', samples)
        self.assertEqual(east[0][0], '{"D",20240301021500}')
        self.assertEqual(west[1][0], '{"D",20240229213000}')
        self.assertEqual([row[1:] for row in east], [row[1:] for row in west])

    def test_host_daylight_rules_apply_at_spring_transition(self):
        rows = self.run_timezone('EST5EDT,M3.2.0/2,M11.1.0/2', [
            unix_ns(datetime(2024, 3, 10, 6, 59, 59), 999999999),
            unix_ns(datetime(2024, 3, 10, 7))])
        self.assertEqual([row[0] for row in rows],
                         ['{"D",20240310015959}', '{"D",20240310030000}'])
        self.assertEqual([row[1] for row in rows],
                         ['{"D",20240310065959}', '{"D",20240310070000}'])
        self.assertEqual(int(rows[1][2]) - int(rows[0][2]), 1)

    def test_host_daylight_fall_fold_has_two_instants_for_one_local_date(self):
        rows = self.run_timezone('EST5EDT,M3.2.0/2,M11.1.0/2', [
            unix_ns(datetime(2024, 11, 3, 5, 30)),
            unix_ns(datetime(2024, 11, 3, 6, 30))])
        self.assertEqual([row[0] for row in rows], ['{"D",20241103013000}'] * 2)
        self.assertEqual([row[1] for row in rows],
                         ['{"D",20241103053000}', '{"D",20241103063000}'])
        self.assertEqual(int(rows[1][2]) - int(rows[0][2]), 3600000)

    def test_host_utc_timezone_and_pre_unix_sample(self):
        rows = self.run_timezone('UTC0', [-1, 0, unix_ns(BASE, 999999999)])
        self.assertEqual([row[0] for row in rows], [row[1] for row in rows])
        self.assertEqual(rows[0], ['{"D",19691231235959}', '{"D",19691231235959}',
                                   '62135596799999'])


class ClockRuntimeTests(unittest.TestCase):
    def setUp(self):
        sample = patch.object(clocks, '_read_time_ns', return_value=unix_ns(BASE, 123456789))
        local = patch.object(clocks.time, 'localtime', side_effect=localtime_at_offset(20700))
        self.sample = sample.start()
        self.addCleanup(sample.stop)
        local.start()
        self.addCleanup(local.stop)
        self.vm = Interpreter()

    def test_all_bilingual_names_case_variants_and_type_identity(self):
        expected = (date('20240229181956'), date('20240229123456'), Decimal('63844806896123'))
        self.assertEqual(len(clocks.BUILTINS), 3)
        for (ru, _, en), value in zip(clocks.BUILTINS, expected):
            for name in (ru, en, ru.lower(), ru.upper(), ru.swapcase(), en.swapcase()):
                with self.subTest(name=name):
                    self.assertEqual(self.vm.execute(name + '()'), value)
                    self.assertIs(self.vm.execute('TypeOf(' + name + '())'), type_of(value))
                    self.assertEqual(self.vm.execute('ValueToStringInternal(' + name + '())'), write(value))

    def test_bad_arity_omissions_and_types_do_not_read_clock(self):
        for name in NAMES:
            for suffix in ('(0)', '(1, 2)', '(Undefined)', '(Null)', '(True)', '("UTC")', '(,)', '(,0)'):
                with self.subTest(expression=name + suffix):
                    before = self.sample.call_count
                    with self.assertRaises(BSLError):
                        self.vm.execute(name + suffix)
                    self.assertEqual(self.sample.call_count, before)

    def test_direct_python_functions_accept_no_arguments(self):
        for function in FUNCTIONS:
            for arguments in ((None,), (Decimal(0),), (None, None)):
                with self.subTest(function=function.__name__, arguments=arguments), self.assertRaises(TypeError):
                    function(*arguments)

    def test_failed_assignment_and_handler_leave_interpreter_usable(self):
        for name in NAMES:
            with self.subTest(name=name):
                self.vm.execute('saved = 7; caught = False; description = ""; Try saved = '
                                + name + '(0); Except caught = True; description = ErrorDescription(); EndTry;')
                self.assertTrue(self.vm.execute('caught'))
                self.assertEqual(self.vm.execute('saved'), Decimal(7))
                self.assertTrue(self.vm.execute('description'))
                self.assertEqual(self.vm.execute('ErrorDescription()'), '')
        self.assertEqual(self.vm.execute('CurrentUniversalDate()'), date('20240229123456'))

    def test_out_of_range_failures_include_source_location_and_recover(self):
        for name in ('CurrentUniversalDate', 'CurrentUniversalDateInMilliseconds'):
            with self.subTest(name=name), patch.object(clocks, '_read_time_ns', return_value=MIN_NS - 1):
                with self.assertRaises(BSLError) as caught:
                    self.vm.execute('saved = 7;\nsaved = ' + name + '();', 'clock.bsl')
                self.assertEqual(caught.exception.source, 'clock.bsl')
                self.assertEqual(caught.exception.line, 2)
                self.assertEqual(self.vm.execute('saved'), Decimal(7))
                self.vm.execute('caught = False; Try saved = ' + name
                                + '(); Except caught = True; EndTry;')
                self.assertTrue(self.vm.execute('caught'))
        self.assertEqual(self.vm.execute('CurrentUniversalDate()'), date('20240229123456'))

    def test_host_localtime_failure_is_catchable_and_does_not_disable_utc(self):
        with patch.object(clocks.time, 'localtime', side_effect=OSError('host conversion failed')):
            self.vm.execute('saved = 7; caught = False; Try saved = CurrentDate(); '
                            'Except caught = True; EndTry;')
            self.assertTrue(self.vm.execute('caught'))
            self.assertEqual(self.vm.execute('saved'), Decimal(7))
            self.assertEqual(self.vm.execute('CurrentUniversalDate()'), date('20240229123456'))

    def test_eval_execute_and_user_routines_preserve_clock_calls(self):
        self.vm.execute('''
            Function PickClock() Return CurrentUniversalDate(); EndFunction
            picked = PickClock(); local = Eval("ТекущаяДата()"); saved = Undefined;
            Execute("saved = ТекущаяУниверсальнаяДатаВМиллисекундах();");
        ''')
        self.assertEqual(self.vm.execute('picked'), date('20240229123456'))
        self.assertEqual(self.vm.execute('local'), date('20240229181956'))
        self.assertEqual(self.vm.execute('saved'), Decimal('63844806896123'))
        self.assertEqual(self.sample.call_count, 3)
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm._execute_depth[0], 0)
        self.assertEqual(self.vm._eval_depth[0], 0)

    def test_dynamic_error_recovery_preserves_saved_variable_and_frames(self):
        for dynamic in ('Eval', 'Execute'):
            body = 'CurrentDate(0)' if dynamic == 'Eval' else 'saved = CurrentDate(0);'
            call = dynamic + '("' + body + '")'
            statement = 'saved = ' + call + ';' if dynamic == 'Eval' else call + ';'
            self.vm.execute('saved = 7; caught = False; Try ' + statement
                            + ' Except caught = True; EndTry;')
            self.assertTrue(self.vm.execute('caught'))
            self.assertEqual(self.vm.execute('saved'), Decimal(7))
            self.assertIsNone(self.vm.locals)
            self.assertEqual(self.vm._execute_depth[0], 0)
            self.assertEqual(self.vm._eval_depth[0], 0)

    def test_registration_overrides_are_per_alias_and_interpreter(self):
        for ru, _, en in clocks.BUILTINS:
            self.vm.register_function(en, lambda: 'override')
            self.assertEqual(self.vm.execute(en + '()'), 'override')
            self.assertNotEqual(self.vm.execute(ru + '()'), 'override')
            self.assertNotEqual(Interpreter().execute(en + '()'), 'override')

    def test_bom_imported_routines_have_clock_builtins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'helper.bsl').write_text('''
                Function PickClock() Export Return CurrentUniversalDate(); EndFunction
                Function PickMilliseconds() Export
                    Return ТекущаяУниверсальнаяДатаВМиллисекундах();
                EndFunction
            ''', encoding='utf-8-sig')
            self.vm.execute('// #Import helper.bsl\npicked = helper.PickClock(); '
                            'milliseconds = helper.PickMilliseconds();', str(root / 'main.bsl'))
        self.assertEqual(self.vm.execute('picked'), date('20240229123456'))
        self.assertEqual(self.vm.execute('milliseconds'), Decimal('63844806896123'))

    def test_clock_results_keep_existing_arithmetic_and_collection_semantics(self):
        self.vm.execute('''
            utc = CurrentUniversalDate(); local = CurrentDate();
            milliseconds = CurrentUniversalDateInMilliseconds();
            items = New Array; items.Add(utc); items.Add(milliseconds);
            fixed = New FixedArray(items); map = New Map;
            map.Insert(utc, "date"); map.Insert(milliseconds, "number");
            map.Insert(CurrentUniversalDate(), "replacement"); frozen = New FixedMap(map);
            record = New Structure("Local,UTC,Milliseconds", local, utc, milliseconds);
            restored = ValueFromStringInternal(ValueToStringInternal(record));
        ''')
        self.assertEqual(self.vm.execute('local - utc'), Decimal(20700))
        self.assertEqual(self.vm.execute('(utc + 0.0001) - utc'), Decimal('0.0001'))
        self.assertEqual(self.vm.execute('milliseconds % 1000'), Decimal(123))
        self.assertEqual(self.vm.execute('WeekDay(utc)'), Decimal(4))
        self.assertEqual(self.vm.execute('BegOfMonth(utc)'), date('20240201000000'))
        self.assertEqual(self.vm.execute('fixed.Find(utc)'), Decimal(0))
        self.assertEqual(self.vm.execute('fixed.Find(milliseconds)'), Decimal(1))
        self.assertEqual(self.vm.execute('map.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('frozen[utc]'), 'replacement')
        self.assertEqual(self.vm.execute('frozen[milliseconds]'), 'number')
        for name in ('Local', 'UTC', 'Milliseconds'):
            self.assertTrue(self.vm.execute('(record.' + name + ' = restored.' + name + ')'))

    def test_scalars_and_all_nested_collection_codecs_restore_clock_values(self):
        values = [function() for function in FUNCTIONS]
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(equal(read(write(value)), value))
                self.assertTrue(value_is_filled(value))
                self.assertEqual(to_string(value), self.vm.execute('String(ValueFromStringInternal("'
                                                                 + write(value).replace('"', '""') + '"))'))
                for container in (array(value), BSLFixedArray(array(value)),
                                  BSLStructure('Clock', value), BSLFixedStructure('Clock', value),
                                  mapping((value, value)), BSLFixedMap(mapping((value, value))),
                                  BSLKeyAndValue(value, value)):
                    with self.subTest(container=type(container).__name__):
                        self.assertEqual(write(read(write(container))), write(container))
        nested = BSLStructure('Values,Map', BSLFixedArray(array(*values)),
                              BSLFixedMap(mapping((values[0], array(values[1], values[2])))))
        restored = read(write(nested))
        self.assertEqual(restored.get('Values').items, tuple(values))
        self.assertEqual(restored.get('Map').get(values[0]).items, values[1:])

    def test_year_one_clock_results_are_known_unfilled_values(self):
        with patch.object(clocks, '_read_time_ns', return_value=MIN_NS), \
                patch.object(clocks.time, 'localtime', return_value=(1, 1, 1, 0, 0, 0)):
            for function in FUNCTIONS:
                value = function()
                self.assertFalse(value_is_filled(value))
                self.assertEqual(read(write(value)), value)
                if type(value) is BSLDate:
                    self.assertIs(value.require_known(), value)
                    self.assertFalse(value.boundary)
                    self.assertIs(type_of(value), BSLType.DATE)
                    self.assertEqual(value.ticks, 0)


class ConfiguredClockTests(unittest.TestCase):
    """Standalone timezone override, not a measured native clock contract."""

    def test_explicit_zone_affects_only_local_clock_and_uses_sample_season(self):
        for stamp, offset in (('20240229123456', 3600), ('20240701123456', 7200)):
            sample = datetime.strptime(stamp, '%Y%m%d%H%M%S')
            seconds = int((sample - UNIX_EPOCH).total_seconds())
            with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'Europe/Warsaw'}), \
                    patch.object(clocks, '_read_time_ns', return_value=seconds * 10**9):
                self.assertEqual(clocks.current_universal_date(), date(stamp))
                self.assertEqual(date_difference(clocks.current_date(), date(stamp)), offset)
                self.assertEqual(clocks.current_universal_date_in_milliseconds(),
                                 (seconds + clocks._UNIX_EPOCH_SECONDS) * 1000)

    def test_invalid_explicit_zone_is_not_hidden_or_used_by_utc_clocks(self):
        from yadinassi.timezones import TimezoneConfigurationError
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': '../UTC'}), \
                patch.object(clocks, '_read_time_ns', return_value=0):
            with self.assertRaisesRegex(TimezoneConfigurationError, 'YADINASSI_TIMEZONE'):
                clocks.current_date()
            self.assertEqual(clocks.current_universal_date(), date('19700101000000'))
            self.assertEqual(clocks.current_universal_date_in_milliseconds(),
                             clocks._UNIX_EPOCH_SECONDS * 1000)


if __name__ == '__main__':
    unittest.main()
