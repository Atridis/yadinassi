"""Observed rounding enum identities and codecs; not native golden outputs."""

from decimal import Decimal, ROUND_DOWN, localcontext
import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.numeric.round_modes import BSLRoundMode, BSLRoundModes, ROUND_MODES
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal, value_to_string_internal,
)
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, equal, to_string


MODE_ID = '32c82ccd-fef3-4070-beb5-b9c52afc781d'
NAMESPACE_ID = 'a47c4665-311c-405a-828e-0c5a3ca3bdda'


class RoundModeValueTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        # Exercise the object boundary independently of global-name binding.
        self.vm.variables['modes'] = ROUND_MODES

    def test_exactly_two_opaque_enum_identities(self):
        self.assertEqual(list(BSLRoundMode), [BSLRoundMode.ROUND15_AS10,
                                            BSLRoundMode.ROUND15_AS20])
        for mode in BSLRoundMode:
            self.assertTrue(equal(mode, mode))
            for other in [None, False, True, Decimal(0), Decimal(1), 0, 1,
                          to_string(mode), ROUND_MODES, BSLType.ROUND_MODE]:
                with self.subTest(mode=mode.name, other=other):
                    self.assertFalse(equal(mode, other))
                    self.assertFalse(equal(other, mode))
        self.assertFalse(equal(BSLRoundMode.ROUND15_AS10, BSLRoundMode.ROUND15_AS20))

    def test_namespace_members_are_bilingual_and_case_insensitive(self):
        for name, expected in [
                ('Окр15как10', BSLRoundMode.ROUND15_AS10),
                ('Round15as10', BSLRoundMode.ROUND15_AS10),
                ('Окр15как20', BSLRoundMode.ROUND15_AS20),
                ('Round15as20', BSLRoundMode.ROUND15_AS20)]:
            for spelling in [name, name.upper(), name.lower(), name.swapcase()]:
                with self.subTest(name=spelling):
                    self.assertIs(ROUND_MODES.get_member(spelling), expected)
                    self.assertIs(self.vm.execute('modes.' + spelling), expected)

    def test_native_presentations_and_type_identities(self):
        for mode, presentation in [
                (BSLRoundMode.ROUND15_AS10, 'Округлять 15 как 10'),
                (BSLRoundMode.ROUND15_AS20, 'Округлять 15 как 20')]:
            with self.subTest(mode=mode.name):
                self.assertEqual(to_string(mode), presentation)
                self.assertIs(type_of(mode), BSLType.ROUND_MODE)
                self.assertEqual(to_string(type_of(mode)), 'РежимОкругления')
        self.assertEqual(to_string(ROUND_MODES), 'ПеречислениеРежимОкругления')
        self.assertIs(type_of(ROUND_MODES), BSLType.ROUND_MODES)
        self.assertIs(type_of(type_of(ROUND_MODES)), BSLType.TYPE)
        self.assertIsNot(BSLType.ROUND_MODE, BSLType.ROUND_MODES)
        for name in ['RoundMode', 'roundmode', 'ROUNDMODE', 'РежимОкругления']:
            self.assertIs(type_by_name(name), BSLType.ROUND_MODE)
        self.assertIs(type_by_name('ПЕРЕЧИСЛЕНИЕРЕЖИМОКРУГЛЕНИЯ'), BSLType.ROUND_MODES)

    def test_namespace_english_alias_uses_official_type_name_metadata(self):
        # EDT's v8.3.8 types/$Enum$RoundMode.type declares EnumRoundMode and
        # ПеречислениеРежимОкругления. This tests that official alias mapping,
        # not a native Type(string) probe result.
        for name in ['EnumRoundMode', 'enumroundmode', 'ENUMROUNDMODE']:
            with self.subTest(name=name):
                self.assertIs(type_by_name(name), BSLType.ROUND_MODES)
                self.assertIs(self.vm.execute('Type("' + name + '")'), BSLType.ROUND_MODES)

    def test_namespace_properties_are_read_only_and_do_not_reflect_host_attributes(self):
        for name in ['__class__', '__dict__', 'get_member', 'get_method',
                     'set_member', 'name', 'value', 'ROUND15_AS10',
                     'Round15as30', 'Окр15как30']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    ROUND_MODES.get_member(name)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('modes.' + name)
        for name in ['Round15as10', 'Окр15как20', 'unknown']:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'недоступно для записи'):
                    ROUND_MODES.set_member(name, None)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('modes.' + name + ' = 1;')
        self.assertIs(ROUND_MODES.get_member('Round15as10'), BSLRoundMode.ROUND15_AS10)

    def test_modes_and_namespace_have_no_accidental_operators_or_methods(self):
        self.vm.execute('mode = modes.Round15as10;')
        for expression in [
                'mode.Name', 'mode.Value', 'mode.__class__', 'mode[0]',
                'mode()', 'mode.Get()', 'mode < mode', 'mode <= mode',
                'mode > mode', 'mode >= mode', 'mode + 1', '-mode',
                'Not mode', 'Boolean(mode)', 'Number(mode)',
                'modes[0]', 'modes()', 'modes.Round15as10()',
                'modes.Get()', 'modes.Count()', 'modes + 1',
                'modes < modes', 'Boolean(modes)', 'Number(modes)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        for code in ['For Each value In mode Do EndDo;',
                     'If mode Then Message(1); EndIf;',
                     'If modes Then Message(1); EndIf;']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)

    def test_modes_are_storable_findable_and_typed_map_keys(self):
        self.vm.execute('''
            values = New Array;
            values.Add(modes.Round15as10); values.Add(modes.Окр15как20);
            Message(values.Find(modes.Окр15как10));
            Message(values.Find(modes.Round15as20));
            Message(values.Find(0) = Undefined);
            fixed = New FixedArray(values);
            record = New Structure("Mode", fixed[0]);
            Message(record.Mode = modes.Round15as10);
            map = New Map;
            map[modes.Round15as10] = "ten"; map[modes.Round15as20] = "twenty";
            map[0] = "zero"; map[1] = "one";
            map[False] = "false"; map[True] = "true";
            map.Insert(modes.Окр15как10, "updated");
            Message(map.Count()); Message(map[record.Mode]);
            Message(map[modes.Окр15как20]); Message(map[0]);
            Message(map[1]); Message(map[False]); Message(map[True]);
            map.Delete(modes.Окр15как20);
            Message(map.Get(modes.Round15as20) = Undefined);
        ''')
        self.assertEqual(self.output, ['0', '1', 'Да', 'Да', '6', 'updated',
                                      'twenty', 'zero', 'one', 'false', 'true', 'Да'])

    def test_host_namespace_subclasses_are_not_reflected_or_serialized(self):
        class NamespaceSubclass(BSLRoundModes):
            def __str__(self):
                raise AssertionError('Host presentation must not be called')

        value = NamespaceSubclass()
        with self.assertRaises(TypeError):
            type_of(value)
        with self.assertRaises(TypeError):
            value_to_string_internal(value)


class RoundModeCodecTests(unittest.TestCase):
    def test_observed_enum_payloads_roundtrip_to_canonical_identities(self):
        for mode, index in [(BSLRoundMode.ROUND15_AS10, '0'),
                            (BSLRoundMode.ROUND15_AS20, '1')]:
            with self.subTest(mode=mode.name):
                payload = '{"#",' + MODE_ID + ',' + index + '}'
                self.assertEqual(value_to_string_internal(mode), payload)
                self.assertIs(value_from_string_internal(payload), mode)
                self.assertIs(type_of(value_from_string_internal(payload)), BSLType.ROUND_MODE)

    def test_observed_enum_type_payload_roundtrips(self):
        payload = '{"T",' + MODE_ID + '}'
        self.assertEqual(value_to_string_internal(BSLType.ROUND_MODE), payload)
        self.assertIs(value_from_string_internal(payload), BSLType.ROUND_MODE)

    def test_observed_namespace_payload_reads_back_as_undefined(self):
        payload = '{"#",' + NAMESPACE_ID + '}'
        self.assertEqual(value_to_string_internal(ROUND_MODES), payload)
        restored = value_from_string_internal(payload)
        self.assertIsNone(restored)
        self.assertIs(type_of(restored), BSLType.UNDEFINED)
        self.assertEqual(to_string(restored), '')
        self.assertEqual(value_to_string_internal(restored), '{"U"}')
        self.assertFalse(equal(restored, ROUND_MODES))

    def test_observed_namespace_type_payload_roundtrips(self):
        payload = '{"T",' + NAMESPACE_ID + '}'
        self.assertEqual(value_to_string_internal(BSLType.ROUND_MODES), payload)
        self.assertIs(value_from_string_internal(payload), BSLType.ROUND_MODES)

    def test_namespace_reader_requires_exact_observed_record_shape(self):
        for payload in ['{"#","' + NAMESPACE_ID + '"}',
                        '{"#",' + NAMESPACE_ID.upper() + '}',
                        '{"#",' + NAMESPACE_ID + ',0}',
                        '{"#",' + NAMESPACE_ID + ',{}}',
                        '{"#",' + NAMESPACE_ID + ',{"U"}}',
                        '{"T",' + NAMESPACE_ID + ',0}',
                        '{"t",' + NAMESPACE_ID + '}']:
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                value_from_string_internal(payload)

    def test_enum_reader_rejects_malformed_payloads_without_coercion(self):
        for body in ['', '2', '-1', '-0', '+0', '+1', '00', '01',
                     '0.0', '1.0', '1e0', 'NaN', 'Infinity', 'true',
                     '٠', '１', '"0"', '"1"', '{}', '{0}',
                     '{"N",0}', '{"B",1}', '0,1', '1' * 10000]:
            payload = '{"#",' + MODE_ID + ',' + body + '}'
            with self.subTest(body=body[:40]), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                value_from_string_internal(payload)
        for payload in ['{"#",' + MODE_ID + '}',
                        '{"#","' + MODE_ID + '",0}',
                        '{"#",' + MODE_ID.upper() + ',0}',
                        '{"T",' + MODE_ID + ',0}',
                        '{"#",' + NAMESPACE_ID + ',0}',
                        '{"#",' + NAMESPACE_ID + ',{}}']:
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                value_from_string_internal(payload)

    def test_codecs_leave_host_decimal_context_untouched(self):
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.clear_flags()
            for signal in context.traps:
                context.traps[signal] = True
            for mode in BSLRoundMode:
                self.assertIs(value_from_string_internal(value_to_string_internal(mode)), mode)
            self.assertIs(value_from_string_internal(value_to_string_internal(BSLType.ROUND_MODE)),
                          BSLType.ROUND_MODE)
            self.assertEqual(value_to_string_internal(ROUND_MODES), '{"#",' + NAMESPACE_ID + '}')
            self.assertIsNone(value_from_string_internal(value_to_string_internal(ROUND_MODES)))
            self.assertIs(value_from_string_internal(value_to_string_internal(BSLType.ROUND_MODES)),
                          BSLType.ROUND_MODES)
            self.assertFalse(any(context.flags.values()))

    def test_namespace_transform_preserves_adjacent_enum_and_type_values(self):
        values = BSLArray()
        values.add(ROUND_MODES)
        values.add(BSLRoundMode.ROUND15_AS20)
        values.add(BSLType.ROUND_MODES)
        for original in [values, BSLFixedArray(values)]:
            restored = value_from_string_internal(value_to_string_internal(original))
            self.assertIs(type_of(restored), type_of(original))
            self.assertIsNone(restored.items[0])
            self.assertIs(restored.items[1], BSLRoundMode.ROUND15_AS20)
            self.assertIs(restored.items[2], BSLType.ROUND_MODES)

    def test_enum_identity_survives_collection_and_map_roundtrips(self):
        values = BSLArray()
        for mode in BSLRoundMode:
            values.add(mode)
        for original in [values, BSLFixedArray(values)]:
            restored = value_from_string_internal(value_to_string_internal(original))
            self.assertIs(type_of(restored), type_of(original))
            for left, right in zip(original.items, restored.items):
                self.assertIs(left, right)
        mapping = BSLMap()
        for key, value in [(BSLRoundMode.ROUND15_AS10, 'ten'),
                           (BSLRoundMode.ROUND15_AS20, 'twenty'),
                           (Decimal(0), 'zero'), (Decimal(1), 'one'),
                           (False, 'false'), (True, 'true')]:
            mapping.insert(key, value)
        for original in [mapping, BSLFixedMap(mapping)]:
            restored = value_from_string_internal(value_to_string_internal(original))
            self.assertIs(type_of(restored), type_of(original))
            self.assertEqual(len(restored._items), 6)
            for key, value in mapping._items.values():
                self.assertEqual(restored.get(key), value)


if __name__ == '__main__':
    unittest.main()
