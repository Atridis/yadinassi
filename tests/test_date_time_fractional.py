"""Fractional fixed-GMT conversion, grounded in native run 39758795625.

The source-bound replay covers the 84 native Number observations and marker.
The other tests exercise their bounded local generalization and integration;
all-offset algebra, invalid inputs and range guards are not new native evidence.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal, Inexact, Rounded, localcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.date_time_conversions import to_local_time, to_universal_time
from yadinassi.dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange, date
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.serialization import value_from_string_internal as read, value_to_string_internal as write
from yadinassi.structures import BSLFixedStructure, BSLStructure
from yadinassi.type_values import type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLType


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/dates.bsl'
FIXTURE = ROOT / 'tests/fixtures/fixed_gmt_fractional_linux.json'
FRACTIONS = (1, 4999, 5000, 9999)
ALIASES = ((to_local_time, ('ToLocalTime', 'МестноеВремя'), 1),
           (to_universal_time, ('ToUniversalTime', 'УниверсальноеВремя'), -1))
ZONES = (('GMT+0', 0), ('GMT+5:30', 19800), ('GMT-3:45', -13500))


def quote(text):
    return '"' + text.replace('"', '""') + '"'


class NativeFractionalGMTEvidenceTests(unittest.TestCase):
    maxDiff = None

    def test_source_bound_native_checkpoint_and_unchanged_historical_prefix(self):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(fixture['native_run'], 39758795625)
        self.assertEqual(fixture['runtime_version'], '8.3.27.1508')
        self.assertEqual(fixture['server_and_managed_client_message_count'], 185)
        source = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(source.encode('utf-8')).hexdigest(), fixture['source_sha256'])
        output = []
        Interpreter(output.append).execute(source, str(SOURCE))
        self.assertEqual(len(output), 185)
        records = fixture['records']
        self.assertEqual(len(records), 85)
        self.assertTrue(all('[{"N",' in record for record in records[:-1]))
        self.assertEqual(records[-1], 'date.gmt-fraction.checkpoint.complete: [ok]')
        self.assertEqual(output[100:], records)
        actual = '\n'.join(output) + '\n'
        self.assertEqual(hashlib.sha256(actual.encode('utf-8')).hexdigest(), fixture['full_output_sha256'])
        historical = (ROOT / 'tests/fixtures/native_windows/dates.out').read_text(encoding='utf-8-sig')
        self.assertEqual('\n'.join(output[:100]) + '\n', historical)


class FractionalFixedOffsetTests(unittest.TestCase):
    def test_observed_fractions_both_directions_crossings_and_exact_date_type(self):
        for base in (date('20240229235959'), date('20240301000000')):
            for fraction in FRACTIONS:
                source = BSLDate(base.ticks + fraction)
                for zone, seconds in ZONES:
                    for function, _, direction in ALIASES:
                        with self.subTest(base=base.ticks, fraction=fraction, zone=zone,
                                          function=function.__name__):
                            result = function(source, zone)
                            self.assertIs(type(result), BSLDate)
                            self.assertIs(type_of(result), BSLType.DATE)
                            self.assertEqual(result.ticks, source.ticks + direction * seconds * TICKS_PER_SECOND)
                            self.assertEqual(result.ticks % TICKS_PER_SECOND, fraction)
                            self.assertFalse(result.boundary)
                            self.assertEqual(source.ticks, base.ticks + fraction)
                            inverse = to_universal_time if direction == 1 else to_local_time
                            self.assertEqual(inverse(result, zone), source)
                for function, _, _ in ALIASES:
                    self.assertEqual(function(source, 'GMT-0:00'), source)
                with self.assertRaises(FrozenInstanceError):
                    source.ticks = 0

    def test_all_legal_minute_offsets_preserve_fraction_and_inverse_as_local_invariant(self):
        # Exhaustive offset coverage is a local integer-tick invariant, not a
        # claim that every offset was measured on the native platform.
        base = date('20240229235959').ticks
        for minutes in range(-1439, 1440):
            hours, remainder = divmod(abs(minutes), 60)
            zone = f'GMT{"-" if minutes < 0 else "+"}{hours:02}:{remainder:02}'
            delta = minutes * 60 * TICKS_PER_SECOND
            with self.subTest(minutes=minutes):
                for fraction in FRACTIONS:
                    source = BSLDate(base + fraction)
                    local = to_local_time(source, zone)
                    universal = to_universal_time(source, zone)
                    self.assertEqual(local.ticks, source.ticks + delta)
                    self.assertEqual(universal.ticks, source.ticks - delta)
                    self.assertEqual(local.ticks % TICKS_PER_SECOND, fraction)
                    self.assertEqual(universal.ticks % TICKS_PER_SECOND, fraction)
                    self.assertEqual(to_universal_time(local, zone), source)
                    self.assertEqual(to_local_time(universal, zone), source)
                    self.assertEqual(source.ticks, base + fraction)

    def test_fractional_range_edges_retain_existing_closed_tick_envelope(self):
        for function, _, direction in ALIASES:
            for minutes in (1, 330, 1439):
                hours, remainder = divmod(minutes, 60)
                delta = minutes * 60 * TICKS_PER_SECOND
                positive = f'GMT+{hours}:{remainder:02}'
                negative = f'GMT-{hours}:{remainder:02}'
                up, down = (positive, negative) if direction == 1 else (negative, positive)
                for fraction in FRACTIONS:
                    with self.subTest(function=function.__name__, minutes=minutes, fraction=fraction):
                        self.assertEqual(function(BSLDate(MAX_TICKS - delta - fraction), up),
                                         BSLDate(MAX_TICKS - fraction))
                        self.assertEqual(function(BSLDate(delta + fraction), down), BSLDate(fraction))
                        for value, zone in ((BSLDate(MAX_TICKS - delta + fraction), up),
                                            (BSLDate(delta - fraction), down)):
                            with self.assertRaises(UnsupportedDateRange):
                                function(value, zone)
                            self.assertFalse(value.boundary)
            for ticks in (1, MAX_TICKS - 1):
                self.assertEqual(function(BSLDate(ticks), 'GMT-0:00'), BSLDate(ticks))
            for ticks in (0, MAX_TICKS):
                with self.assertRaises(UnsupportedDateRange):
                    function(BSLDate(ticks, boundary=True), 'GMT+0')
        # This feature does not extend the final supported second by 9999 ticks.
        with self.assertRaises(ValueError):
            BSLDate(MAX_TICKS + 1)

    def test_fractional_conversion_ignores_decimal_context_host_clock_and_timezone(self):
        base = date('20240229235959')
        source = BSLDate(base.ticks + 4999)
        vm = Interpreter()
        vm.variables.update(source=source, base=base)
        environment = {'TZ': 'Invalid/HostZone', 'YADINASSI_TIMEZONE': 'Invalid/ConfiguredZone'}
        with patch.dict(os.environ, environment), \
                patch('time.localtime', side_effect=AssertionError('host localtime used')), \
                patch('time.gmtime', side_effect=AssertionError('host gmtime used')), \
                patch('time.mktime', side_effect=AssertionError('host mktime used')), \
                patch('time.time', side_effect=AssertionError('host clock used')), \
                patch('time.time_ns', side_effect=AssertionError('host clock used')), \
                patch('yadinassi.timezones._load_zone', side_effect=AssertionError('named zone used')), \
                localcontext() as context:
            context.prec = 1
            context.Emin = -1
            context.Emax = 1
            context.traps[Inexact] = context.traps[Rounded] = True
            for function, _, direction in ALIASES:
                self.assertEqual(function(source, 'GMT+5:30').ticks,
                                 source.ticks + direction * 19800 * TICKS_PER_SECOND)
                self.assertEqual(function(BSLDate(1), 'GMT+0').ticks, 1)
                self.assertEqual(function(BSLDate(MAX_TICKS - 1), 'GMT-0:00').ticks, MAX_TICKS - 1)
                with self.assertRaises(ValueError):
                    function(source)
            self.assertEqual(vm.execute('МестноеВремя(source,"GMT+5:30") - base'), Decimal('19800.4999'))
            self.assertEqual(vm.execute('ToUniversalTime(source,"GMT-3:45") - base'), Decimal('13500.4999'))
            self.assertEqual({key: os.environ[key] for key in environment}, environment)
            self.assertFalse(context.flags[Inexact])
            self.assertFalse(context.flags[Rounded])

    def test_collections_keep_fractional_identity_but_internal_codec_is_explicitly_lossy(self):
        source = BSLDate(date('20240229235959').ticks + 4999)
        value = to_local_time(source, 'GMT+5:30')
        whole = BSLDate(value.ticks - 4999)
        self.assertEqual(write(value), '{"D",20240301052959}')
        self.assertEqual(read(write(value)), whole)
        self.assertNotEqual(read(write(value)), value)
        items = BSLArray()
        items.add(value)
        mapping = BSLMap()
        mapping.insert(value, value)
        for container in (items, BSLFixedArray(items)):
            self.assertIs(container.get(Decimal(0)), value)
            self.assertEqual(read(write(container)).get(Decimal(0)), whole)
        for container in (BSLStructure('When', value), BSLFixedStructure('When', value)):
            self.assertIs(container.get('When'), value)
            self.assertEqual(read(write(container)).get('When'), whole)
        for container in (mapping, BSLFixedMap(mapping)):
            self.assertIs(container.get(BSLDate(value.ticks)), value)
            self.assertIsNone(container.get(whole))
            restored = read(write(container))
            self.assertEqual(restored.get(whole), whole)
            self.assertIsNone(restored.get(value))
        self.assertEqual(to_universal_time(value, 'GMT+5:30'), source)
        self.assertEqual(to_universal_time(read(write(value)), 'GMT+5:30').ticks, source.ticks - 4999)


class FractionalFixedOffsetRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('base = Date(2024,2,29,23,59,59); source = base + 0.0001;')
        self.source = BSLDate(date('20240229235959').ticks + 1)

    def assert_caught(self, expression):
        self.vm.execute('saved = 7; caught = False; Try saved = ' + expression
                        + '; Except caught = True; EndTry;')
        self.assertIs(self.vm.execute('caught'), True, expression)
        self.assertEqual(self.vm.execute('saved'), Decimal(7))
        self.assertEqual(self.vm.execute('source'), self.source)

    def test_bilingual_case_variants_preserve_fractional_ticks(self):
        for function, names, _ in ALIASES:
            for name in names:
                for spelling in (name, name.swapcase()):
                    for zone in ('GMT+5:30', 'GMT-3:45', 'GMT-0:00'):
                        with self.subTest(spelling=spelling, zone=zone):
                            self.assertEqual(self.vm.execute(spelling + '(source,' + quote(zone) + ')'),
                                             function(self.source, zone))
        self.assertEqual(self.vm.execute('source'), self.source)

    def test_fractional_invalid_inputs_and_range_failures_are_catchable(self):
        # Broad grammar/arity/type matrices remain in test_date_time_conversions.
        suffixes = ('(source)', '(source,Undefined)', '(source,0)', '(source,"gmt+1")',
                    '(source,"GMT+24")', '(source,"Europe/Warsaw")',
                    '(0.0001,"GMT+0")', '(source,"GMT+0",0)')
        for _, names, _ in ALIASES:
            for name in names:
                for suffix in suffixes:
                    with self.subTest(expression=name + suffix):
                        self.assert_caught(name + suffix)
        for expression in ('ToLocalTime(Date(1,1,1)+0.0001,"GMT-0:01")',
                           'ToUniversalTime(Date(1,1,1)+0.0001,"GMT+0:01")',
                           'МестноеВремя(Date(9999,12,31,23,59,59)-0.0001,"GMT+0:01")',
                           'УниверсальноеВремя(Date(9999,12,31,23,59,59)-0.0001,"GMT-0:01")'):
            self.assert_caught(expression)
        self.assertEqual(self.vm.execute('ToLocalTime(source,"GMT+0")'), self.source)

    def test_eval_execute_single_evaluation_and_recovery_preserve_fraction(self):
        self.vm.execute('''Var calls;
Function PickDate(Val value) calls = calls + 1; Return value; EndFunction
Function PickZone() calls = calls + 10; Return "GMT+5:30"; EndFunction
calls = 0;
''')
        expression = 'МестноеВремя(PickDate(source),PickZone())'
        expected = BSLDate(self.source.ticks + 19800 * TICKS_PER_SECOND)
        self.assertEqual(self.vm.execute('Eval(' + quote(expression) + ')'), expected)
        self.assertEqual(self.vm.execute('calls'), Decimal(11))
        self.vm.execute('saved = Undefined; Execute(' + quote('saved = ' + expression + ';') + ');')
        self.assertEqual(self.vm.execute('saved'), expected)
        self.assertEqual(self.vm.execute('calls'), Decimal(22))
        self.vm.execute('record = New Structure("When", saved); '
                        'restored = ValueFromStringInternal(ValueToStringInternal(record)); '
                        'map = New Map; map.Insert(saved,"present");')
        self.assertEqual(self.vm.execute('map[ToLocalTime(source,"GMT+5:30")]'), 'present')
        self.assertEqual(self.vm.execute('record.When - restored.When'), Decimal('0.0001'))
        self.assert_caught('Eval(' + quote('ToLocalTime(source,"Europe/Warsaw")') + ')')
        self.vm.execute('caught = False; Try Execute('
                        + quote('saved = ToUniversalTime(source);')
                        + '); Except caught = True; EndTry;')
        self.assertIs(self.vm.execute('caught'), True)
        self.assertEqual(self.vm.execute('saved'), Decimal(7))
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm._execute_depth[0], 0)
        self.assertEqual(self.vm.execute('ToUniversalTime(record.When,"GMT+5:30")'), self.source)


class FractionalFixedOffsetCLITests(unittest.TestCase):
    def run_cli(self, *args, stdin=None, cwd=ROOT):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(filter(None, (str(ROOT), environment.get('PYTHONPATH'))))
        return subprocess.run([sys.executable, '-m', 'yadinassi', *args], input=stdin,
                              capture_output=True, encoding='utf-8', cwd=cwd, env=environment, timeout=15)

    def test_command_uses_numeric_observations_not_lossy_date_stream(self):
        program = '''base = Date(2024,2,29,23,59,59); source = base + 0.4999;
Message(ValueToStringInternal(ToLocalTime(source,"GMT+5:30") - base));
Message(ValueToStringInternal(УниверсальноеВремя(source,"GMT-3:45") - base));
Message(ValueToStringInternal(ToUniversalTime(ToLocalTime(source,"GMT+5:30"),"GMT+5:30") - source));
Message(ValueToStringInternal(source - base));'''
        result = self.run_cli('-c', program)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, '{"N",19800.4999}\n{"N",13500.4999}\n{"N",0}\n{"N",0.4999}\n', ''))

    def test_bom_import_dynamic_call_and_caught_failure(self):
        module = '''Function Shift(Val value) Export
Return Eval("МестноеВремя(value,""GMT+5:30"")");
EndFunction
Function Failure(Val value) Export
Return ToUniversalTime(value);
EndFunction
'''
        main = '''// #Импорт Смещение.bsl
base = Date(2024,2,29,23,59,59); source = base + 0.9999;
Message(ValueToStringInternal(Смещение.Shift(source) - base));
Try Смещение.Failure(source); Except Message("caught"); EndTry;
Message(ValueToStringInternal(ToUniversalTime(Смещение.Shift(source),"GMT+5:30") - base));
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            (directory / 'Смещение.bsl').write_text(module, encoding='utf-8-sig')
            (directory / 'Основное.bsl').write_text(main, encoding='utf-8-sig')
            result = self.run_cli('Основное.bsl', cwd=directory)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, '{"N",19800.9999}\ncaught\n{"N",0.9999}\n', ''))

    def test_console_recovers_without_losing_fractional_source(self):
        result = self.run_cli(stdin='source = Date(2024,2,29) + 0.0001;\n'
                              'ToLocalTime(source)\n'
                              'ValueToStringInternal(ToLocalTime(source,"GMT-0:00") - Date(2024,2,29))\n'
                              '/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, '{"N",0.0001}\n'))
        self.assertIn('<консоль>:1:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
