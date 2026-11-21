"""Internal-codec unit/model checks; not fabricated native golden outputs."""

from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import subprocess
import sys
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.formats.storage import serialization
from yadinassi.types import type_values
from yadinassi.formats.storage.serialization import value_from_string_internal, value_to_string_internal
from yadinassi.types.values import BSLType, to_string


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

    def test_direct_bsl_pair_roundtrip_uses_language_codec(self):
        # Canonical host pair codecs have separate positive native coverage in
        # test_serialization_native; direct values use the BSL service adapter.
        for constructor, setup in (
                ('New Structure("Key", 7)', ''),
                ('New Map', 'A.Insert("Key",7);')):
            for prepared in (False, True):
                with self.subTest(constructor=constructor, prepared=prepared):
                    vm=Interpreter();self.addCleanup(vm.close)
                    source=('A='+constructor+';'+setup+
                            'For Each P In A Do EndDo;'
                            'S=ValueToStringInternal(P);Q=ValueFromStringInternal(S);'
                            'K=Q.Key;V=Q.Value;T=TypeOf(Q);')
                    if prepared: vm.execute_prepared(vm.prepare(source))
                    else: vm.execute(source)
                    self.assertEqual(vm.variables['k'], 'Key')
                    self.assertEqual(vm.variables['v'], 7)
                    self.assertIs(vm.variables['t'], BSLType.KEY_AND_VALUE)
                    from yadinassi.collections.structures import BSLKeyAndValue
                    self.assertEqual(vm.variables['s'],
                                     value_to_string_internal(BSLKeyAndValue('Key', Decimal(7))))

    def test_bsl_nested_mutable_collections_roundtrip_without_aliases(self):
        source = (
            'A=New Array; M=New Map; T=New Structure("Value", 7); '
            'M.Insert("Key", T); A.Add(M); A.Add(12); '
            'S=ValueToStringInternal(A); R=ValueFromStringInternal(S); '
            'T.Value=22; Copy=R[0].Get("Key"); N=Copy.Value; I=R[1]; '
            'Stable=ValueToStringInternal(R)=S;')
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter()
                self.addCleanup(vm.close)
                if prepared:
                    vm.execute_prepared(vm.prepare(source))
                else:
                    vm.execute(source)
                self.assertEqual((vm.variables['n'], vm.variables['i']), (7, 12))
                self.assertIs(vm.variables['stable'], True)

    def test_exact_native_collections_keep_existing_wire_bytes(self):
        from yadinassi.collections.maps import BSLMap
        from yadinassi.collections.structures import BSLStructure
        from yadinassi.execution.codegen.experimental_naked_structure import new_structure
        from yadinassi.execution.direct.python_direct_plain_array import PlainArray
        from yadinassi.execution.direct.python_direct_plain_map import PlainMap
        from yadinassi.types.values import BSLArray

        native = PlainMap()
        native[3] = new_structure('Ёж', 7)  # Native integer key and field.
        model = BSLMap()
        model.insert(Decimal(3), BSLStructure('Ёж', Decimal(7)))
        boxed = BSLArray()
        boxed.items = [model, Decimal(9), True]
        direct = PlainArray([native, 9, True])
        data = value_to_string_internal(direct)
        self.assertEqual(data, value_to_string_internal(boxed))
        self.assertEqual(value_to_string_internal(value_from_string_internal(data)), data)

    def test_native_map_cycles_and_non_codec_keys_remain_unsupported(self):
        from yadinassi.execution.direct.python_direct_plain_map import PlainMap
        value = PlainMap()
        value['self'] = value
        with self.assertRaisesRegex(ValueError, 'циклические'):
            value_to_string_internal(value)
        value.clear()
        value[1.5] = 'valid Python key, no internal number representation'
        with self.assertRaisesRegex(TypeError, 'ключ'):
            value_to_string_internal(value)

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

    def test_every_runtime_type_has_explicit_codec_and_identifier(self):
        self.assertEqual(serialization._CODECS | serialization._UNSUPPORTED_CODEC_TYPES, set(BSLType))
        self.assertFalse(serialization._CODECS & serialization._UNSUPPORTED_CODEC_TYPES)
        self.assertEqual(set(serialization._TYPE_IDS), set(serialization._CODECS))
        self.assertEqual(serialization._CODECS | serialization._UNSUPPORTED_CODEC_TYPES,
                         {kind for _, kind, _ in type_values._VALUE_TYPES} | type_values._CONDITIONAL_VALUE_TYPES)

    def test_every_implemented_type_has_native_readback_behavior(self):
        vm = Interpreter()
        expressions = ['New UUID("01234567-89ab-4cde-8f01-23456789abcd")', 'Null', 'Date(1,1,1)', 'Undefined', 'True', 'False', '0', '"text"', 'New Array',
                       'New FixedArray(New Array)', 'New Structure',
                       'New FixedStructure(New Structure)', 'New Map',
                       'New FixedMap(New Map)', 'Type("Number")',
                       'RoundMode.Round15as10', 'RoundMode.Round15as20', 'RoundMode',
                       'SearchDirection.FromBegin', 'SearchDirection.FromEnd', 'SearchDirection',
                       'SortDirection.Asc', 'SortDirection.Desc',
                       'XMLStringProcessing', 'New TypeDescription',
                       'New NumberQualifiers', 'New StringQualifiers',
                       'New DateQualifiers', 'New BinaryDataQualifiers',
                       'AllowedSign', 'AllowedSign.Any', 'AllowedSign.Nonnegative',
                       'AllowedLength', 'AllowedLength.Fixed', 'AllowedLength.Variable',
                       'DateFractions', 'DateFractions.Date', 'DateFractions.Time',
                       'DateFractions.DateTime']
        vm.execute('s = New Structure("Key", 1); For Each pair In s Do EndDo;')
        expressions.append('pair')
        vm.execute('table = New ValueTable; columns = table.Columns; '
                   'column = columns.Add("A"); row = table.Add();')
        vm.execute('indexes = table.Indexes; index = indexes.Add("A");')
        expressions.extend(['table', 'columns', 'column', 'row', 'indexes', 'index'])
        vm.execute('values = New ValueList; item = values.Add(10, "first", True);')
        expressions.extend(['values', 'item'])
        observed = set()
        for expression in expressions:
            with self.subTest(expression=expression):
                original = vm.execute(expression)
                if expression in ('New Array', 'New Structure', 'New Map'):
                    # Interpreter TypeOf admits exact mutable direct shapes;
                    # the Python metadata registry describes the boxed types.
                    kind = vm.execute(f'TypeOf({expression})')
                    if type(original) is list:
                        # Bare lists belong to the trusted direct caller, not
                        # the public Python value_to_string_internal API.
                        stream = vm.execute(f'ValueToStringInternal({expression})')
                    else:
                        stream = value_to_string_internal(original)
                else:
                    kind = type_values.type_of(original)
                    stream = value_to_string_internal(original)
                restored = value_from_string_internal(stream)
                if kind in (BSLType.ROUND_MODES, BSLType.SEARCH_DIRECTIONS,
                            BSLType.XML_STRING_PROCESSING_MANAGER,
                            BSLType.NUMBER_QUALIFIERS, BSLType.STRING_QUALIFIERS,
                            BSLType.DATE_QUALIFIERS, BSLType.BINARY_DATA_QUALIFIERS,
                            BSLType.ALLOWED_SIGNS, BSLType.ALLOWED_LENGTHS,
                            BSLType.DATE_FRACTIONS_NAMESPACE, BSLType.VALUE_TABLE_ROW,
                            BSLType.VALUE_TABLE_COLUMN, BSLType.VALUE_TABLE_COLUMN_COLLECTION,
                            BSLType.COLLECTION_INDEXES, BSLType.COLLECTION_INDEX):
                    # Native qualifier/namespace records read as Undefined, unlike their Types.
                    self.assertIsNone(restored)
                    self.assertIs(type_values.type_of(restored), BSLType.UNDEFINED)
                else:
                    self.assertIs(type_values.type_of(restored), kind)
                observed.add(kind)
        self.assertEqual(observed, set(serialization._CODECS))

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

    def test_malformed_or_unimplemented_forms_are_rejected_safely(self):
        # Some cases are native observations; others are explicit safety boundaries.
        for text in ['', '{"N",1e3}', '{"N",.5}', '{"N",1.}', '{"N",NaN}',
                     '{"N",Infinity}', '{"N",١}', '{"Unknown",1}',
                     '{"N",{"N",1}}', '__import__("os").system("echo unsafe")']:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, serialization.FORMAT_ERROR):
                    value_from_string_internal(text)

    def test_resource_limits_precede_regex_and_decimal_construction(self):
        for text in ['x' * (serialization._MAX_TEXT + 1), '{"N",' + '1' * 4097 + '}',
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
