"""Owner-observed qualifier codecs and separate defensive-stream boundaries.

The committed native values.out is read-only evidence. Malformed-input and
resource-budget tests below establish our bounded model, not new native claims.
"""

from tests.native_observations import (read_observation, inverse_stream, assert_snapshot,
                                       assert_type_inverse, assert_nested, extract_payload)

from decimal import Decimal, ROUND_DOWN, Rounded, localcontext
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, serialization, type_values
from yadinassi.errors import BSLRuntimeError
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_qualifiers import (
    ALLOWED_LENGTHS, ALLOWED_SIGNS, DATE_FRACTIONS,
    BSLAllowedLength, BSLAllowedLengths, BSLAllowedSign, BSLAllowedSigns,
    BSLBinaryDataQualifiers, BSLDateFractions, BSLDateFractionsNamespace,
    BSLDateQualifiers, BSLNumberQualifiers, BSLStringQualifiers,
)
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLObject, BSLType, equal, to_string


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'integrational_tests/output/values.out'
TYPE_IDS = {
    BSLType.NUMBER_QUALIFIERS: 'f6f6ce00-392c-49ed-8c6e-4e0295fd4051',
    BSLType.STRING_QUALIFIERS: 'a5e1773c-a947-455a-a2f7-c51736d3f2de',
    BSLType.DATE_QUALIFIERS: 'e73e1337-53df-4b30-a78c-ee1e8cf30fc0',
    BSLType.BINARY_DATA_QUALIFIERS: '73315712-166d-400d-adaf-287bd8f41b8d',
    BSLType.ALLOWED_SIGN: '9c4a8801-ff83-40d7-96d7-cc2b85430fbe',
    BSLType.ALLOWED_SIGNS: 'eb851bfe-cc2a-4d16-84a4-e480da76672d',
    BSLType.ALLOWED_LENGTH: '3e4a7ff2-82a0-40ee-9000-3e83a3191b71',
    BSLType.ALLOWED_LENGTHS: '2f7878c0-bc8a-4820-a3b9-6bf1111ae5b0',
    BSLType.DATE_FRACTIONS: '8089abb5-ff39-4414-8252-c0dcef1c3d6b',
    BSLType.DATE_FRACTIONS_NAMESPACE: '83f71799-efb3-4984-a19b-6ed4f3cbc691',
}
ENUM_ITEMS = (
    (BSLAllowedSign.ANY, BSLType.ALLOWED_SIGN, '0'),
    (BSLAllowedSign.NONNEGATIVE, BSLType.ALLOWED_SIGN, '1'),
    (BSLAllowedLength.FIXED, BSLType.ALLOWED_LENGTH, '0'),
    (BSLAllowedLength.VARIABLE, BSLType.ALLOWED_LENGTH, '1'),
    (BSLDateFractions.DATE, BSLType.DATE_FRACTIONS, '1'),
    (BSLDateFractions.TIME, BSLType.DATE_FRACTIONS, '2'),
    (BSLDateFractions.DATE_TIME, BSLType.DATE_FRACTIONS, '3'),
)
NAMESPACE_ITEMS = (
    (ALLOWED_SIGNS, BSLType.ALLOWED_SIGNS),
    (ALLOWED_LENGTHS, BSLType.ALLOWED_LENGTHS),
    (DATE_FRACTIONS, BSLType.DATE_FRACTIONS_NAMESPACE),
)
QUALIFIER_CLASSES = (
    (BSLNumberQualifiers, BSLType.NUMBER_QUALIFIERS, 'NumberQualifiers'),
    (BSLStringQualifiers, BSLType.STRING_QUALIFIERS, 'StringQualifiers'),
    (BSLDateQualifiers, BSLType.DATE_QUALIFIERS, 'DateQualifiers'),
    (BSLBinaryDataQualifiers, BSLType.BINARY_DATA_QUALIFIERS, 'BinaryDataQualifiers'),
)


def array(*values):
    result = BSLArray()
    for value in values:
        result.add(value)
    return result


def opaque_items():
    return (
        (BSLNumberQualifiers(), BSLType.NUMBER_QUALIFIERS),
        (BSLNumberQualifiers(Decimal(5), Decimal(2), BSLAllowedSign.NONNEGATIVE),
         BSLType.NUMBER_QUALIFIERS),
        (BSLStringQualifiers(), BSLType.STRING_QUALIFIERS),
        (BSLStringQualifiers(Decimal(4), BSLAllowedLength.FIXED),
         BSLType.STRING_QUALIFIERS),
        (BSLDateQualifiers(), BSLType.DATE_QUALIFIERS),
        (BSLDateQualifiers(BSLDateFractions.DATE), BSLType.DATE_QUALIFIERS),
        (BSLBinaryDataQualifiers(), BSLType.BINARY_DATA_QUALIFIERS),
        (BSLBinaryDataQualifiers(Decimal(4), BSLAllowedLength.FIXED),
         BSLType.BINARY_DATA_QUALIFIERS),
    ) + NAMESPACE_ITEMS


class QualifierNativeCodecEvidenceTests(unittest.TestCase):
    """Compare each captured snapshot field with unchanged owner output."""

    @classmethod
    def setUpClass(cls):
        cls.original = NATIVE.read_bytes()
        cls.native = cls.original.decode('utf-8-sig')

    def record(self, label):
        return read_observation(extract_payload(self.native, 'types.' + label))

    def test_all_standalone_snapshot_fields_match_native(self):
        values = {
            'number': (BSLNumberQualifiers(),
                       BSLNumberQualifiers(Decimal(5), Decimal(2), BSLAllowedSign.NONNEGATIVE)),
            'string': (BSLStringQualifiers(),
                       BSLStringQualifiers(Decimal(4), BSLAllowedLength.FIXED)),
            'date': (BSLDateQualifiers(), BSLDateQualifiers(BSLDateFractions.DATE)),
            'binary': (BSLBinaryDataQualifiers(),
                       BSLBinaryDataQualifiers(Decimal(4), BSLAllowedLength.FIXED)),
        }
        snapshots = {family + '.' + suffix: value
                     for family, (default, configured) in values.items()
                     for suffix, value in [('default.en', default), ('default.ru', default),
                                           ('configured', configured)]}
        snapshots.update({
            'allowedsign.namespace': ALLOWED_SIGNS,
            'allowedsign.any': BSLAllowedSign.ANY,
            'allowedsign.nonnegative': BSLAllowedSign.NONNEGATIVE,
            'allowedlength.namespace': ALLOWED_LENGTHS,
            'allowedlength.fixed': BSLAllowedLength.FIXED,
            'allowedlength.variable': BSLAllowedLength.VARIABLE,
            'datefractions.namespace': DATE_FRACTIONS,
            'datefractions.date': BSLDateFractions.DATE,
            'datefractions.time': BSLDateFractions.TIME,
            'datefractions.datetime': BSLDateFractions.DATE_TIME,
        })
        self.assertEqual(len(snapshots), 22)
        for label, value in snapshots.items():
            with self.subTest(label=label):
                native = self.record(label)
                kind = type_of(value)
                restored = read(write(value))
                assert_snapshot(self, native, value)
        self.assertEqual(NATIVE.read_bytes(), self.original)

    def test_native_named_type_aliases(self):
        pairs = [(name, kind.value, family + '.type.names')
                 for (cls, kind, name), family in zip(QUALIFIER_CLASSES,
                                                      ('number', 'string', 'date', 'binary'))]
        pairs += [('AllowedSign', 'ДопустимыйЗнак', 'allowedsign.type-name'),
                  ('AllowedLength', 'ДопустимаяДлина', 'allowedlength.type-name'),
                  ('DateFractions', 'ЧастиДаты', 'datefractions.type-name')]
        for english, russian, label in pairs:
            with self.subTest(label=label):
                self.assertIs(self.record(label), True)
                self.assertIs(type_by_name(english), type_by_name(russian))


class QualifierTypePolicyTests(unittest.TestCase):
    def test_new_runtime_types_have_distinct_complete_codec_policies(self):
        self.assertEqual(len(TYPE_IDS), 10)
        self.assertEqual(len(set(TYPE_IDS.values())), 10)
        self.assertEqual(set(serialization._CODECS), set(BSLType))
        self.assertEqual(set(serialization._TYPE_IDS), set(BSLType))
        self.assertEqual(set(BSLType), {kind for _, kind, _ in type_values._VALUE_TYPES})
        for kind, identifier in TYPE_IDS.items():
            self.assertEqual(serialization._TYPE_IDS[kind], identifier)
        for value, kind in opaque_items():
            self.assertIs(type_of(value), kind)
        for value, kind, _ in ENUM_ITEMS:
            self.assertIs(type_of(value), kind)

    def test_named_types_are_bilingual_and_case_insensitive(self):
        pairs = [(name, kind) for _, kind, name in QUALIFIER_CLASSES]
        pairs += [('AllowedSign', BSLType.ALLOWED_SIGN),
                  ('AllowedLength', BSLType.ALLOWED_LENGTH),
                  ('DateFractions', BSLType.DATE_FRACTIONS)]
        for name, kind in pairs:
            for spelling in (name, name.lower(), name.upper(), kind.value,
                             kind.value.lower(), kind.value.upper()):
                with self.subTest(spelling=spelling):
                    self.assertIs(type_by_name(spelling), kind)
                    self.assertIs(type_of(kind), BSLType.TYPE)
                    self.assertEqual(to_string(kind), kind.value)

    def test_namespace_names_are_not_invented_from_display_or_english_labels(self):
        for name in ('EnumAllowedSign', 'AllowedSigns', BSLType.ALLOWED_SIGNS.value,
                     'EnumAllowedLength', 'AllowedLengths', BSLType.ALLOWED_LENGTHS.value,
                     'EnumDateFractions', 'DateFractionsNamespace',
                     BSLType.DATE_FRACTIONS_NAMESPACE.value,
                     'NumberQualifiers ', ' NumberQualifiers'):
            for spelling in (name, name.lower(), name.upper()):
                with self.subTest(spelling=spelling), self.assertRaisesRegex(
                        ValueError, 'Тип не поддерживается'):
                    type_by_name(spelling)

    def test_host_subclasses_and_metaclass_hooks_are_not_considered_bsl_types(self):
        def hook(*args):
            raise AssertionError('Host hook must not run')

        class HostMeta(type):
            __eq__ = hook
            __hash__ = hook

        class Host(BSLObject, metaclass=HostMeta):
            __str__ = hook

        samples = [Host()]
        for cls in (BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers,
                    BSLBinaryDataQualifiers, BSLAllowedSigns, BSLAllowedLengths,
                    BSLDateFractionsNamespace):
            host_class = type('Host' + cls.__name__, (cls,), {'__str__': hook})
            samples.append(host_class())
        for value in samples:
            for operation in (type_of, write):
                with self.subTest(kind=type(value).__name__, operation=operation.__name__), \
                        self.assertRaises(TypeError):
                    operation(value)


class QualifierCodecTests(unittest.TestCase):
    def test_exact_native_enum_ordinals_restore_canonical_members(self):
        for value, kind, ordinal in ENUM_ITEMS:
            with self.subTest(value=value):
                payload = '{"#",' + TYPE_IDS[kind] + ',' + ordinal + '}'
                self.assertEqual(write(value), payload)
                self.assertIs(read(payload), value)
                self.assertIs(type_of(read(payload)), kind)
                self.assertTrue(equal(read(payload), value))

    def test_default_configured_and_namespace_payloads_restore_undefined(self):
        for value, kind in opaque_items():
            with self.subTest(value=value, kind=kind):
                payload = '{"#",' + TYPE_IDS[kind] + '}'
                self.assertEqual(write(value), payload)
                self.assertIsNone(read(payload))
                self.assertIs(type_of(read(payload)), BSLType.UNDEFINED)
                self.assertEqual(write(read(payload)), '{"U"}')
                self.assertFalse(equal(value, read(payload)))

    def test_every_type_frame_roundtrips_including_opaque_object_types(self):
        for kind, identifier in TYPE_IDS.items():
            with self.subTest(kind=kind):
                payload = '{"T",' + identifier + '}'
                self.assertEqual(write(kind), payload)
                self.assertIs(read(payload), kind)
                self.assertIs(type_of(read(payload)), BSLType.TYPE)

    def test_enum_indices_reject_unobserved_values_and_coercions(self):
        for kind, valid in [(BSLType.ALLOWED_SIGN, ('0', '1')),
                            (BSLType.ALLOWED_LENGTH, ('0', '1')),
                            (BSLType.DATE_FRACTIONS, ('1', '2', '3'))]:
            invalid = ['', '-1', '-0', '+0', '+1', '+2', '+3', '00', '01', '02', '03',
                       '0.0', '1.0', '2.0', '3.0', '1e0', 'NaN', 'Infinity', 'true',
                       '٠', '１', '"0"', '"1"', '"2"', '"3"', '{}', '{0}',
                       '{"N",1}', '{"B",1}', '{"U"}', '1,1', '1' * 10000,
                       '1\x00', '__import__("os")']
            invalid += [str(index) for index in range(5) if str(index) not in valid]
            for body in invalid:
                payload = '{"#",' + TYPE_IDS[kind] + ',' + body + '}'
                with self.subTest(kind=kind, body=body[:40]), self.assertRaisesRegex(
                        ValueError, FORMAT_ERROR):
                    read(payload)

    def test_exact_tags_guids_and_shapes_are_required(self):
        for kind, identifier in TYPE_IDS.items():
            bad = ['{"#","' + identifier + '"}',
                   '{"#","' + identifier + '",1}',
                   '{"#",' + identifier.upper() + '}',
                   '{"#",' + identifier.upper() + ',1}',
                   '{"T",' + identifier.upper() + '}',
                   '{"T","' + identifier + '"}',
                   '{"T",' + identifier + ',1}',
                   '{"t",' + identifier + '}',
                   '{"#",' + identifier + ',{"U"}}',
                   '{"#",' + identifier + ',{"Pattern"}}']
            if kind in (BSLType.ALLOWED_SIGN, BSLType.ALLOWED_LENGTH, BSLType.DATE_FRACTIONS):
                bad.append('{"#",' + identifier + '}')
            else:
                bad += ['{"#",' + identifier + ',1}', '{"#",' + identifier + ',{}}',
                        '{"#",' + identifier + ',{0}}', '{"#",' + identifier + ',""}']
            for payload in bad:
                with self.subTest(kind=kind, payload=payload), self.assertRaisesRegex(
                        ValueError, FORMAT_ERROR):
                    read(payload)
        with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
            read('{"#",00000000-0000-0000-0000-000000000000,1}')

    def test_every_record_truncation_is_catchable_and_next_read_recovers(self):
        values = [value for value, _ in opaque_items()]
        values += [value for value, _, _ in ENUM_ITEMS] + list(TYPE_IDS)
        for value in values:
            payload = write(value)
            for end in range(len(payload)):
                with self.subTest(kind=type_of(value), end=end), self.assertRaisesRegex(
                        ValueError, FORMAT_ERROR):
                    read(payload[:end])
            self.assertIs(read(payload), None if type_of(value) in serialization._OPAQUE_TYPES
                          else value)

    def test_enum_and_type_identities_survive_containers_without_numeric_key_collisions(self):
        values = [value for value, _, _ in ENUM_ITEMS] + list(TYPE_IDS)
        items = array(*values)
        names = ['Item' + str(index) for index in range(len(values))]
        record = BSLStructure(','.join(names), *values)
        mapping = BSLMap()
        for index, value in enumerate(values + [Decimal(0), Decimal(1), Decimal(2),
                                               Decimal(3), False, True]):
            mapping.insert(value, str(index))
        self.assertEqual(len(mapping._items), len(values) + 6)
        for original in (items, BSLFixedArray(items), record, BSLFixedStructure(record),
                         mapping, BSLFixedMap(mapping), BSLKeyAndValue(values[0], values[-1])):
            with self.subTest(kind=type_of(original)):
                restored = read(write(original))
                self.assertIs(type_of(restored), type_of(original))
                if type(original) in (BSLMap, BSLFixedMap):
                    self.assertEqual(len(restored._items), len(mapping._items))
                    for key, expected in mapping._items.values():
                        self.assertEqual(restored.get(key), expected)
                elif type(original) in (BSLStructure, BSLFixedStructure):
                    for name, expected in zip(names, values):
                        self.assertIs(restored.get(name), expected)
                elif type(original) is BSLKeyAndValue:
                    self.assertIs(restored.key, values[0])
                    self.assertIs(restored.value, values[-1])
                else:
                    self.assertEqual(len(restored.items), len(values))
                    for actual, expected in zip(restored.items, values):
                        self.assertIs(actual, expected)

    def test_opaque_values_disappear_without_affecting_neighbors_or_type_frames(self):
        for value, kind in opaque_items():
            with self.subTest(kind=kind):
                items = array(BSLAllowedSign.ANY, value, kind, BSLDateFractions.TIME)
                expected = [BSLAllowedSign.ANY, None, kind, BSLDateFractions.TIME]
                for original in (items, BSLFixedArray(items)):
                    self.assertEqual(list(read(write(original)).items), expected)
                record = BSLStructure('Before,Value,Kind,After', *items.items)
                for original in (record, BSLFixedStructure(record)):
                    restored = read(write(original))
                    for name, item in zip(('Before', 'Value', 'Kind', 'After'), expected):
                        self.assertIs(restored.get(name), item)
                mapping = BSLMap()
                for name, item in zip(('Before', 'Value', 'Kind', 'After'), items.items):
                    mapping.insert(name, item)
                for original in (mapping, BSLFixedMap(mapping)):
                    restored = read(write(original))
                    for name, item in zip(('Before', 'Value', 'Kind', 'After'), expected):
                        self.assertIs(restored.get(name), item)
                pair = read(write(BSLKeyAndValue(kind, value)))
                self.assertIs(pair.key, kind)
                self.assertIsNone(pair.value)

    def test_resource_limits_include_opaque_enum_and_type_nodes(self):
        values = [value for value, _ in opaque_items()]
        values += [value for value, _, _ in ENUM_ITEMS] + list(TYPE_IDS)
        for value in values:
            payload = write(value)
            with patch.object(serialization, '_MAX_TEXT', len(payload)):
                self.assertEqual(write(value), payload)
                read(payload)
            with patch.object(serialization, '_MAX_TEXT', len(payload) - 1):
                for operation, argument in ((write, value), (read, payload)):
                    with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                        operation(argument)
        allowed = array(BSLNumberQualifiers(), BSLDateFractions.DATE)
        rejected = array(BSLNumberQualifiers(), BSLDateFractions.DATE, DATE_FRACTIONS)
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_NODES', 3):
            self.assertEqual(write(allowed), allowed_payload)
            self.assertEqual(read(allowed_payload).items, [None, BSLDateFractions.DATE])
            for operation, argument in ((write, rejected), (read, rejected_payload)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)
        allowed, rejected = array(array(DATE_FRACTIONS)), array(array(array(DATE_FRACTIONS)))
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_DEPTH', 2):
            self.assertEqual(write(allowed), allowed_payload)
            read(allowed_payload)
            for operation, argument in ((write, rejected), (read, rejected_payload)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)

    def test_decimal_context_is_unchanged_on_codec_success_and_rejection(self):
        values = [value for value, _ in opaque_items()]
        values += [value for value, _, _ in ENUM_ITEMS] + list(TYPE_IDS)
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.flags[Rounded] = True
            for signal in context.traps:
                context.traps[signal] = True
            before = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            for value in values:
                read(write(array(value, Decimal('1.23456789'))))
            with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read('{"#",' + TYPE_IDS[BSLType.DATE_FRACTIONS] + ',1.0}')
            after = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            self.assertEqual(after, before)

    def test_bad_frames_are_bsl_catchable_preserve_assignment_and_do_not_poison_vm(self):
        output = []
        vm = Interpreter(output.append)
        bad_frames = [
            '{"#",' + TYPE_IDS[BSLType.ALLOWED_SIGN] + ',2}',
            '{"#",' + TYPE_IDS[BSLType.DATE_FRACTIONS] + ',0}',
            '{"#",' + TYPE_IDS[BSLType.NUMBER_QUALIFIERS] + ',0}',
        ]
        vm.execute('result = 7;')
        for payload in bad_frames:
            vm.variables['payload'] = payload
            vm.execute('''
                Try result = ValueFromStringInternal(payload);
                Except Message("caught"); EndTry;
                Message(result);
            ''')
        self.assertEqual(output, ['caught', '7'] * len(bad_frames))
        vm.variables['payload'] = write(BSLAllowedSign.NONNEGATIVE)
        self.assertIs(vm.execute('ValueFromStringInternal(payload)'), BSLAllowedSign.NONNEGATIVE)
        vm.variables['payload'] = bad_frames[0]
        with self.assertRaises(BSLRuntimeError):
            vm.execute('ValueFromStringInternal(payload)')


if __name__ == '__main__':
    unittest.main()
