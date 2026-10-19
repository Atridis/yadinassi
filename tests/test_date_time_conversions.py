"""Bounded fixed-offset Date conversion contracts, not native probe evidence.

The documented GMT grammar grounds this subset. Fraction rejection, overflow,
missing/default zones and defensive checks are implementation limits; these
checks do not claim unmeasured native 1C parity.
"""

from datetime import datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.date_time_conversions import BUILTINS, to_local_time, to_universal_time
from yadinassi.dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange, date
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.serialization import value_from_string_internal as read, value_to_string_internal as write
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLType

ROOT = Path(__file__).resolve().parents[1]
ALIASES = ((to_local_time, ('ToLocalTime', 'МестноеВремя')),
           (to_universal_time, ('ToUniversalTime', 'УниверсальноеВремя')))


def canonical(value):
    return (f'{value.year:04}{value.month:02}{value.day:02}'
            f'{value.hour:02}{value.minute:02}{value.second:02}')


def quote(value):
    return '"' + value.replace('"', '""') + '"'


class FixedOffsetConversionTests(unittest.TestCase):
    def test_all_minute_offsets_match_independent_gregorian_oracle_and_inverse(self):
        samples = (datetime(1, 1, 2), datetime(9999, 12, 30, 23, 59, 59),
                   datetime(1900, 3, 1), datetime(2000, 2, 29, 23, 59, 59),
                   datetime(2023, 12, 31, 12, 34, 56), datetime(2024, 3, 1))
        for minutes in range(-1439, 1440):
            hours, remainder = divmod(abs(minutes), 60)
            zone = f'GMT{"-" if minutes < 0 else "+"}{hours:02}:{remainder:02}'
            for sample in samples:
                source = date(canonical(sample))
                with self.subTest(minutes=minutes, sample=sample):
                    local = to_local_time(source, zone)
                    universal = to_universal_time(source, zone)
                    self.assertEqual(local, date(canonical(sample + timedelta(minutes=minutes))))
                    self.assertEqual(universal, date(canonical(sample - timedelta(minutes=minutes))))
                    self.assertEqual(to_universal_time(local, zone), source)
                    self.assertEqual(to_local_time(universal, zone), source)
                    for result in (local, universal):
                        self.assertIs(type(result), BSLDate)
                        self.assertFalse(result.boundary)
                        self.assertEqual(result.ticks % TICKS_PER_SECOND, 0)
                    self.assertEqual(source, date(canonical(sample)))

    def test_hour_forms_padding_and_both_signs_of_zero(self):
        source = date('20240229123456')
        for hours in range(24):
            for sign, multiplier in (('+', 1), ('-', -1)):
                for zone in (f'GMT{sign}{hours}', f'GMT{sign}{hours:02}',
                             f'GMT{sign}{hours}:00', f'GMT{sign}{hours:02}:00'):
                    with self.subTest(zone=zone):
                        expected = BSLDate(source.ticks + multiplier * hours * 3600 * TICKS_PER_SECOND)
                        self.assertEqual(to_local_time(source, zone), expected)
                        self.assertEqual(to_universal_time(expected, zone), source)
        for value in (BSLDate(0), BSLDate(MAX_TICKS)):
            for zone in ('GMT+0', 'GMT-0', 'GMT+00:00', 'GMT-00:00'):
                for function, _ in ALIASES:
                    self.assertEqual(function(value, zone), value)

    def test_exact_endpoint_arrival_and_one_second_overflow(self):
        for minutes in (1, 59, 60, 330, 1439):
            hours, remainder = divmod(minutes, 60)
            delta = minutes * 60 * TICKS_PER_SECOND
            for sign in ('+', '-'):
                zone = f'GMT{sign}{hours}:{remainder:02}'
                for function, _ in ALIASES:
                    forward = (function is to_local_time) == (sign == '+')
                    source = BSLDate(MAX_TICKS - delta if forward else delta)
                    target = BSLDate(MAX_TICKS if forward else 0)
                    with self.subTest(function=function.__name__, zone=zone):
                        self.assertEqual(function(source, zone), target)
                        overflow = BSLDate(source.ticks + (TICKS_PER_SECOND if forward else -TICKS_PER_SECOND))
                        with self.assertRaises(UnsupportedDateRange):
                            function(overflow, zone)
                        with self.assertRaises(UnsupportedDateRange):
                            function(target, zone)

    def test_invalid_grammar_is_not_normalized_or_guessed(self):
        zones = ('', 'GMT', 'UTC', 'UTC+1', '+01:00', 'GMT1', 'gmt+1', 'GmT+1',
                 ' GMT+1', 'GMT+1 ', 'GMT+1\n', 'GMT+1\r\n', 'GMT+1\x00',
                 'GMT++1', 'GMT+-1', 'GMT−1', 'GMT＋1', 'GMT+١', 'GMT+１',
                 'GMT+1:٠٠', 'GMT+001', 'GMT+1:0', 'GMT+1:000', 'GMT+1:',
                 'GMT+:00', 'GMT+1.5', 'GMT+1:30:00', 'GMT+24', 'GMT-24:00',
                 'GMT+23:60', 'GMT-0:99', 'GMT+99', 'GMT+1\t',
                 'Europe/Warsaw', 'America/New_York', 'Central European Standard Time',
                 'GMT+' + '0' * 10000, 'GMT+1\nGMT+2')
        for zone in zones:
            for function, _ in ALIASES:
                with self.subTest(zone=zone[:80], function=function.__name__), \
                        self.assertRaises((TypeError, ValueError)):
                    function(date('20240229'), zone)

    def test_exact_types_no_coercion_and_no_default_zone(self):
        class DateSubclass(BSLDate):
            pass

        class StringSubclass(str):
            pass

        class Coercible:
            def __str__(self):
                raise AssertionError('implicit coercion attempted')

        values = (None, False, True, 0, 1.0, Decimal(0), '20240229',
                  datetime(2024, 2, 29), [], {}, Coercible(), DateSubclass(0))
        zones = (None, False, True, 0, 1.0, Decimal(1), [], {},
                 date('20240229'), Coercible(), StringSubclass('GMT+1'))
        for function, _ in ALIASES:
            for value in values:
                with self.subTest(value_type=type(value), function=function.__name__), \
                        self.assertRaises((TypeError, ValueError)):
                    function(value, 'GMT+1')
            for zone in zones:
                with self.subTest(zone_type=type(zone), function=function.__name__), \
                        self.assertRaises((TypeError, ValueError)):
                    function(date('20240229'), zone)
            with self.assertRaises((TypeError, ValueError)):
                function(date('20240229'))

    def test_fractions_and_opaque_boundaries_are_rejected_even_for_zero_offset(self):
        for function, _ in ALIASES:
            for zone in ('GMT+0', 'GMT-0:00', 'GMT+23:59', 'GMT-23:59'):
                for ticks in (1, 9999, date('20240229').ticks + 1234, MAX_TICKS - 1):
                    with self.subTest(ticks=ticks, zone=zone), self.assertRaises((TypeError, ValueError)):
                        function(BSLDate(ticks), zone)
                for ticks in (0, MAX_TICKS):
                    with self.assertRaises(UnsupportedDateRange):
                        function(BSLDate(ticks, boundary=True), zone)

    def test_host_clock_timezone_and_decimal_context_are_irrelevant(self):
        source = date('20240229235959')
        environment = {'TZ': 'Invalid/HostZone', 'YADINASSI_TIMEZONE': 'Invalid/ConfiguredZone'}
        with patch.dict(os.environ, environment), \
                patch('time.localtime', side_effect=AssertionError('host localtime used')), \
                patch('time.gmtime', side_effect=AssertionError('host gmtime used')), \
                patch('time.mktime', side_effect=AssertionError('host mktime used')), \
                patch('time.time', side_effect=AssertionError('host time used')), \
                patch('time.time_ns', side_effect=AssertionError('host time_ns used')), \
                patch('yadinassi.timezones._load_zone', side_effect=AssertionError('named zone used')), \
                localcontext() as context:
            context.prec = 1
            context.Emin = -1
            context.Emax = 1
            context.traps[Inexact] = context.traps[Rounded] = True
            for function, zone in ((to_local_time, 'GMT+0:01'), (to_universal_time, 'GMT-0:01')):
                self.assertEqual(function(source, zone), date('20240301000059'))
            for function, _ in ALIASES:
                self.assertEqual(function(BSLDate(MAX_TICKS), 'GMT+0'), BSLDate(MAX_TICKS))
                with self.assertRaises((TypeError, ValueError)):
                    function(source)
            self.assertEqual({key: os.environ[key] for key in environment}, environment)
            self.assertFalse(context.flags[Inexact])
            self.assertFalse(context.flags[Rounded])

    def test_existing_date_type_and_nested_serialization_are_preserved(self):
        value = to_local_time(date('20240229235959'), 'GMT+1')
        self.assertIs(type_of(value), BSLType.DATE)
        self.assertEqual(write(value), '{"D",20240301005959}')
        items = BSLArray()
        items.add(value)
        mapping = BSLMap()
        mapping.insert(value, value)
        containers = (items, BSLFixedArray(items), BSLStructure('When', value),
                      BSLFixedStructure('When', value), mapping, BSLFixedMap(mapping),
                      BSLKeyAndValue(value, value))
        for container in containers:
            with self.subTest(container=type(container).__name__):
                self.assertEqual(write(read(write(container))), write(container))
        nested = BSLStructure('Items,Mapping', BSLFixedArray(items), BSLFixedMap(mapping))
        self.assertEqual(write(read(write(nested))), write(nested))
        self.assertEqual(read(write(mapping)).get(value), value)


class FixedOffsetRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('source = Date(2024,2,29,23,59,59);')

    def test_bilingual_aliases_case_variants_and_registration(self):
        for function, names in ALIASES:
            for name in names:
                self.assertIn((names[1], function, names[0]), BUILTINS)
                for spelling in (name, name.swapcase()):
                    self.assertEqual(self.vm.execute(spelling + '(source,"GMT+1:30")'),
                                     function(date('20240229235959'), 'GMT+1:30'))
        self.vm.register_function('ToLocalTime', lambda *args: 'override')
        self.assertEqual(self.vm.execute('ToLocalTime(source,"GMT+1")'), 'override')
        self.assertEqual(self.vm.execute('МестноеВремя(source,"GMT+1")'), date('20240301005959'))
        self.assertEqual(Interpreter().execute('ToLocalTime(Date(2024,2,29),"GMT+1")'), date('20240229010000'))

    def test_invalid_types_defaults_fractions_and_arities_are_catchable(self):
        suffixes = ('()', '(source)', '(source,Undefined)', '(source,Null)',
                    '(source,"Europe/Warsaw")', '(source,"GMT+24")', '(source,"gmt+1")',
                    '(source,0)', '(source,True)', '(source,New Array)',
                    '(source,"GMT+1",0)', '(,"GMT+1")', '(Undefined,"GMT+1")',
                    '(Null,"GMT+1")', '(0,"GMT+1")', '("20240229","GMT+1")',
                    '(source+0.0001,"GMT+0")', '(source-0.0001,"GMT-1")',
                    '(Date(1,1,1),"GMT-23:59")', '(Date(9999,12,31,23,59,59),"GMT+23:59")')
        for _, names in ALIASES:
            for name in names:
                for suffix in suffixes:
                    expression = name + suffix
                    # Overflow direction is reversed for UniversalTime; both extrema
                    # therefore get explicit direction-specific coverage below.
                    if name in ALIASES[1][1] and suffix in suffixes[-2:]:
                        continue
                    with self.subTest(expression=expression):
                        self.assert_caught(expression)
        self.assert_caught('ToUniversalTime(Date(1,1,1),"GMT+1")')
        self.assert_caught('УниверсальноеВремя(Date(9999,12,31,23,59,59),"GMT-1")')
        for ticks in (0, MAX_TICKS):
            self.vm.variables['opaque'] = BSLDate(ticks, boundary=True)
            for _, names in ALIASES:
                for name in names:
                    self.assert_caught(name + '(opaque,"GMT+0")')
        self.assertEqual(self.vm.execute('ToLocalTime(source,"GMT+1")'), date('20240301005959'))

    def test_trailing_omission_retains_existing_parser_limit(self):
        for _, names in ALIASES:
            for name in names:
                with self.assertRaises(BSLError):
                    self.vm.execute(name + '(source,)')

    def assert_caught(self, expression):
        self.vm.execute('saved = 7; caught = False; Try saved = ' + expression
                        + '; Except caught = True; EndTry;')
        self.assertIs(self.vm.execute('caught'), True, expression)
        self.assertEqual(self.vm.execute('saved'), Decimal(7))

    def test_arguments_evaluate_once_and_source_stays_unchanged(self):
        self.vm.execute('''Var calls;
Function PickDate(Val value) calls = calls + 1; Return value; EndFunction
Function PickZone() calls = calls + 10; Return "GMT+1"; EndFunction
calls = 0; result = ToLocalTime(PickDate(source), PickZone());''')
        self.assertEqual(self.vm.execute('calls'), Decimal(11))
        self.assertEqual(self.vm.execute('result'), date('20240301005959'))
        self.assertEqual(self.vm.execute('source'), date('20240229235959'))

    def test_eval_execute_and_collection_roundtrip(self):
        expression = 'МестноеВремя(source,"GMT+1")'
        self.assertEqual(self.vm.execute('Eval(' + quote(expression) + ')'), date('20240301005959'))
        self.vm.execute('saved = Undefined; Execute(' + quote('saved = ' + expression + ';') + ');')
        self.assertEqual(self.vm.execute('saved'), date('20240301005959'))
        self.vm.execute('''record = New Structure("When", saved);
restored = ValueFromStringInternal(ValueToStringInternal(record));
map = New Map; map.Insert(saved, "present");''')
        self.assertEqual(self.vm.execute('restored.When'), date('20240301005959'))
        self.assertEqual(self.vm.execute('map[ToLocalTime(source,"GMT+1")]'), 'present')
        for dynamic in ('Eval', 'Execute'):
            expression = 'ToLocalTime(source,"Europe/Warsaw")'
            body = expression if dynamic == 'Eval' else 'saved = ' + expression + ';'
            call = dynamic + '(' + quote(body) + ')'
            if dynamic == 'Eval':
                self.assert_caught(call)
            else:
                self.vm.execute('saved = 7; caught = False; Try ' + call
                                + '; Except caught = True; EndTry;')
                self.assertTrue(self.vm.execute('caught'))
                self.assertEqual(self.vm.execute('saved'), Decimal(7))
            self.assertIsNone(self.vm.locals)
            self.assertEqual(self.vm._execute_depth[0], 0)
        self.assertEqual(self.vm.execute('ToUniversalTime(restored.When,"GMT+1")'), date('20240229235959'))


class FixedOffsetCLITests(unittest.TestCase):
    PROGRAM = '''source = Date(2024,2,29,23,59,59);
Message(ValueToStringInternal(МестноеВремя(source,"GMT+1")));
Message(ValueToStringInternal(ToUniversalTime(source,"GMT-0:01")));
Try ToLocalTime(source); Except Message("caught"); EndTry;
Message(ValueToStringInternal(ToUniversalTime(ToLocalTime(source,"GMT+23:59"),"GMT+23:59")));
'''
    OUTPUT = '{"D",20240301005959}\n{"D",20240301000059}\ncaught\n{"D",20240229235959}\n'

    def run_cli(self, *args, stdin=None, cwd=ROOT):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(filter(None, (str(ROOT), environment.get('PYTHONPATH'))))
        return subprocess.run([sys.executable, '-m', 'yadinassi', *args], input=stdin,
                              capture_output=True, encoding='utf-8', cwd=cwd, env=environment, timeout=15)

    def test_command_aliases_bom_file_stdin_console(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'Смещение.bsl'
            source.write_text(self.PROGRAM, encoding='utf-8-sig')
            cases = [((flag, self.PROGRAM), None) for flag in ('-c', '-с', '--command')]
            cases += [((str(source),), None), ((source.name,), None), (('-',), self.PROGRAM),
                      ((), self.PROGRAM + '/exit\n')]
            for args, stdin in cases:
                with self.subTest(args=args):
                    result = self.run_cli(*args, stdin=stdin, cwd=directory)
                    self.assertEqual((result.returncode, result.stdout, result.stderr), (0, self.OUTPUT, ''))

    def test_bom_import_eval_and_catchable_error_recovery(self):
        module = '''Function Shift(Val value = '20240229235959') Export
Return Eval("ToLocalTime(value,""GMT+1"")");
EndFunction
Function Failure() Export
Return ToUniversalTime(Date(1,1,1),"GMT+1");
EndFunction
'''
        main = '''// #Импорт Смещение.bsl
Message(ValueToStringInternal(Смещение.Shift()));
Try Смещение.Failure(); Except Message("caught"); EndTry;
Message(ValueToStringInternal(Смещение.Shift()));
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'Смещение.bsl').write_text(module, encoding='utf-8-sig')
            source = directory / 'Основное.bsl'
            source.write_text(main, encoding='utf-8-sig')
            result = self.run_cli(source.name, cwd=directory)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, '{"D",20240301005959}\ncaught\n{"D",20240301005959}\n', ''))
            source.write_text('// #Импорт Смещение.bsl\nСмещение.Failure();\n', encoding='utf-8-sig')
            result = self.run_cli(str(source), cwd=directory)
            self.assertEqual((result.returncode, result.stdout), (1, ''))
            self.assertIn(str(directory / 'Смещение.bsl') + ':5:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_uncaught_error_diagnostics_and_console_recovery(self):
        code = 'saved = Date(2024,2,29);\nsaved = ToLocalTime(saved);\n'
        result = self.run_cli('-c', code)
        self.assertEqual((result.returncode, result.stdout), (1, ''))
        self.assertIn('<команда>:2:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        result = self.run_cli(stdin=code + 'ValueToStringInternal(ToLocalTime(saved,"GMT+1"))\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, '{"D",20240229010000}\n'))
        self.assertIn('<консоль>:1:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
