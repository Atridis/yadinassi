"""Internal-codec unit/model checks; not fabricated native golden outputs."""

from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import subprocess
import sys
import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi import serialization, type_values
from yadinassi.serialization import value_from_string_internal, value_to_string_internal
from yadinassi.values import BSLType, to_string


ROOT = Path(__file__).resolve().parents[1]


class InternalSerializationTests(unittest.TestCase):
    def test_numeric_canonical_model(self):
        for source, payload in [('0', '0'), ('-0.000', '0'), ('1.23000', '1.23'),
                                ('-1000.50', '-1000.5'), ('1E+5', '100000'),
                                ('1E-5', '0.00001'), ('100.000', '100')]:
            with self.subTest(source=source):
                self.assertEqual(value_to_string_internal(Decimal(source)), '{"N",' + payload + '}')

    def test_bilingual_case_insensitive_functions(self):
        vm = Interpreter()
        for name in ['ЗначениеВСтрокуВнутр', 'зНаЧеНиЕвСтРоКуВнУтР',
                     'ValueToStringInternal', 'vAlUeToStRiNgInTeRnAl']:
            with self.subTest(name=name):
                self.assertEqual(vm.execute(f'{name}(1000.25)'), '{"N",1000.25}')

    def test_serialization_retains_stored_digits_beyond_presentation(self):
        value = Decimal('0.' + '1' * 540)
        self.assertEqual(value_to_string_internal(value), '{"N",0.' + '1' * 540 + '}')
        self.assertEqual(to_string(value), '0,' + '1' * 324)
        self.assertEqual(value.as_tuple().exponent, -540)
        self.assertEqual(value_to_string_internal(Decimal('1234.5')), '{"N",1234.5}')
        self.assertEqual(to_string(Decimal('1234.5')), '1\u00a0234,5')

    def test_serialization_is_independent_of_decimal_context(self):
        value = Decimal('1234567890123456789012345678901234567890.123456789')
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.clear_flags()
            for signal in context.traps:
                context.traps[signal] = True
            self.assertEqual(value_to_string_internal(value), '{"N",1234567890123456789012345678901234567890.123456789}')
            self.assertFalse(any(context.flags.values()))

    def test_number_resource_boundary_before_fixed_point_expansion(self):
        for value in [Decimal('1E-4096'), Decimal('1E+4095')]:
            self.assertTrue(value_to_string_internal(value).startswith('{"N",'))
        for value in [Decimal('1E-4097'), Decimal('1E+4096'), Decimal('1E+999999999')]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    value_to_string_internal(value)
        # Insignificant zeros and the sign/exponent of zero do not enlarge payloads.
        self.assertEqual(value_to_string_internal(Decimal('-0E+999999999')), '{"N",0}')
        self.assertEqual(value_to_string_internal(Decimal('1.' + '0' * 5000)), '{"N",1}')

    def test_nonfinite_numbers_are_rejected_without_decimal_operations(self):
        for text in ['NaN', 'sNaN', 'Infinity', '-Infinity']:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, 'конечное число'):
                    value_to_string_internal(Decimal(text))

    def test_every_runtime_type_has_an_explicit_disjoint_policy(self):
        codecs = set(serialization._SERIALIZERS)
        pending = set(serialization._AWAITING_NATIVE)
        self.assertFalse(codecs & pending)
        self.assertEqual(codecs | pending, set(BSLType))
        self.assertEqual(codecs | pending, {kind for _, kind, _ in type_values._VALUE_TYPES})

    def test_pending_types_are_not_misrepresented_as_native_refusals(self):
        vm = Interpreter()
        expressions = ['Undefined', 'True', 'False', '"text"', 'New Array',
                       'New FixedArray(New Array)', 'New Structure',
                       'New FixedStructure(New Structure)', 'New Map',
                       'New FixedMap(New Map)', 'Type("Number")']
        vm.execute('s = New Structure("Key", 1); For Each pair In s Do EndDo;')
        expressions.append('pair')
        observed = set()
        for expression in expressions:
            with self.subTest(expression=expression):
                observed.add(type_values.type_of(vm.execute(expression)))
                with self.assertRaisesRegex(BSLRuntimeError, 'пока не поддерживается в Yadinassi; ожидается проверка на 1С'):
                    vm.execute(f'ValueToStringInternal({expression})')
        self.assertEqual(observed, serialization._AWAITING_NATIVE)

    def test_host_values_and_subclasses_do_not_fall_back_to_reflection(self):
        class Host:
            def __str__(self):
                self.fail_if_called = True
                raise AssertionError('Host str must not be called')
        class NumberSubclass(Decimal):
            def as_tuple(self):
                raise AssertionError('Subclass hook must not be called')
        for value in [Host(), NumberSubclass('1'), 1, 1.5, [], {}, object()]:
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(TypeError):
                    value_to_string_internal(value)

    def test_arity_errors_are_catchable_and_recovery_is_preserved(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute('''
            Try
                ValueToStringInternal();
            Except
                Message("missing");
            EndTry;
            Try
                ЗначениеВСтрокуВнутр(1, 2);
            Except
                Message("extra");
            EndTry;
            Message(ValueToStringInternal(1));
        ''')
        self.assertEqual(output, ['missing', 'extra', '{"N",1}'])

    def test_cli_stdout_is_internal_payload_not_localized_number(self):
        result = subprocess.run([sys.executable, '-m', 'yadinassi', '-c',
                                 'Message(ValueToStringInternal(1234.500)); Message(1234.500);'],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout.splitlines(), ['{"N",1234.5}', '1\u00a0234,5'])


class InternalDeserializationTests(unittest.TestCase):
    def test_canonical_numbers_roundtrip_without_loss_or_coercion(self):
        for text in ['0', '1', '-1', '1234.5', '-0.125', '0.' + '1' * 540,
                     '9' * 4096, '-0.' + '0' * 4095 + '1']:
            with self.subTest(length=len(text), prefix=text[:20]):
                payload = '{"N",' + text + '}'
                value = value_from_string_internal(payload)
                self.assertIs(type(value), Decimal)
                self.assertEqual(value, Decimal(text))
                self.assertEqual(value_to_string_internal(value), payload)

    def test_bilingual_case_insensitive_aliases_and_type(self):
        vm = Interpreter()
        for name in ['ЗначениеИзСтрокиВнутр', 'зНаЧеНиЕиЗсТрОкИвНуТр',
                     'ValueFromStringInternal', 'vAlUeFrOmStRiNgInTeRnAl']:
            with self.subTest(name=name):
                value = vm.execute(f'{name}(ValueToStringInternal(1234.5))')
                self.assertIs(type(value), Decimal)
                self.assertEqual(value, Decimal('1234.5'))

    def test_context_does_not_round_or_trap_exact_parse(self):
        payload = '{"N",12345678901234567890.123456789}'
        with localcontext() as context:
            context.prec = 1
            context.clear_flags()
            for signal in context.traps:
                context.traps[signal] = True
            self.assertEqual(value_to_string_internal(value_from_string_internal(payload)), payload)
            self.assertFalse(any(context.flags.values()))

    def test_unverified_alternate_and_malformed_forms_are_explicitly_pending(self):
        # These are implementation boundaries, NOT native acceptance/error goldens.
        for text in ['', ' {"N",1}', '{"N",1} ', '{"N", 1}', '{"N",+1}',
                     '{"N",01}', '{"N",-0}', '{"N",1.0}', '{"N",1e3}',
                     '{"N",.5}', '{"N",1.}', '{"N",NaN}', '{"N",Infinity}',
                     '{"N",١}', '{"N",1,5}', '{"N",1}garbage', '{"S","x"}',
                     '{"Unknown",1}', '{"N",{"N",1}}', '{"N",1}\x00',
                     '__import__("os").system("echo unsafe")']:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, 'формат пока не поддерживается в Yadinassi'):
                    value_from_string_internal(text)

    def test_resource_limits_precede_regex_and_decimal_construction(self):
        for text in ['x' * 100000, '{"N",' + '1' * 4097 + '}',
                     '{"N",0.' + '0' * 4096 + '1}']:
            with self.subTest(length=len(text)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    value_from_string_internal(text)

    def test_only_exact_strings_are_accepted_without_host_hooks(self):
        class HostString(str):
            def __len__(self):
                raise AssertionError('Host length must not be called')
        for value in [None, True, Decimal(1), 1, b'{"N",1}', HostString('{"N",1}')]:
            with self.subTest(kind=type(value).__name__):
                with self.assertRaisesRegex(TypeError, 'ожидается строка'):
                    value_from_string_internal(value)

    def test_errors_leave_assigned_value_unchanged_and_console_recovers(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute('''
            value = 7;
            Try
                value = ValueFromStringInternal("unknown");
            Except
                Message("caught");
            EndTry;
            Message(value);
            Message(ValueFromStringInternal(ValueToStringInternal(1234.5)));
            Try
                ValueFromStringInternal();
            Except
                Message("arity");
            EndTry;
        ''')
        self.assertEqual(output, ['caught', '7', '1\u00a0234,5', 'arity'])


if __name__ == '__main__':
    unittest.main()
