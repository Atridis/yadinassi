"""Native Pattern evidence, including the owner's qualified receiver supplement.

Malformed-shape rejection and generalized field values are our explicit bounded
model. They are not asserted as additional native acceptance/rejection evidence.
"""

from tests.native_observations import (read_observation, inverse_stream, assert_snapshot,
                                       assert_type_inverse, assert_nested, extract_payload)

from decimal import Decimal, ROUND_DOWN, Rounded, localcontext
from itertools import combinations
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, serialization
from yadinassi.errors import BSLRuntimeError
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import (
    BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
    BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers, BSLStringQualifiers,
)
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, equal, to_string


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'tests/fixtures/native_windows/values.out'
GUID = 'f5c65050-3bbb-11d5-b988-0050bae0a95d'


def array(*items):
    result = BSLArray()
    for item in items:
        result.add(item)
    return result


def frame(body):
    return '{"#",' + GUID + ',' + body + '}'


def canonical_pattern(tags):
    body = '{"Pattern"'
    for tag in tags:
        body += ',\n{"' + tag + '"}'
    body += '\n}' if tags else '}'
    return '{"#",' + GUID + ',\n' + body + '\n}'


class TypeDescriptionNativeCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = NATIVE.read_bytes()
        cls.native = cls.original.decode('utf-8-sig')

    def record(self, label, prefix='types'):
        return read_observation(extract_payload(self.native, prefix + '.' + label))

    def test_all_whole_description_snapshot_fields_match_native(self):
        snapshots = {
            'description.default.en': BSLTypeDescription(),
            'description.default.ru': BSLTypeDescription(),
            'description.configured': BSLTypeDescription('String,Number,Date,Boolean'),
            'description.ctor.empty': BSLTypeDescription(''),
            'description.ctor.spaces': BSLTypeDescription(' Строка , Число '),
            'description.ctor.duplicates': BSLTypeDescription('String,Number,String'),
            'description.ctor.array': BSLTypeDescription(
                array(BSLType.STRING, BSLType.NUMBER, BSLType.STRING)),
            'description.ctor.undefined': BSLTypeDescription(None),
            'description.ctor.null': BSLTypeDescription('Null'),
            'description.ctor.undefined-type': BSLTypeDescription('Undefined'),
            'description.copy.add-remove': BSLTypeDescription(
                BSLTypeDescription('String,Number'), 'Date', 'String'),
        }
        self.assertEqual(len(snapshots), 11)
        for label, value in snapshots.items():
            with self.subTest(label=label):
                native = self.record(label)
                restored = read(write(value))
                assert_snapshot(self, native, value)
        self.assertEqual(NATIVE.read_bytes(), self.original)

    def test_native_type_identity_and_bilingual_names(self):
        payload = '{"T",' + GUID + '}'
        self.assertIs(self.record('description.type.names'), True)
        for name in ('TypeDescription', 'typedescription', 'TYPEDESCRIPTION',
                     'ОписаниеТипов', 'ОПИСАНИЕТИПОВ', 'описаниетипов'):
            self.assertIs(type_by_name(name), BSLType.TYPE_DESCRIPTION)
        self.assertIs(type_of(BSLTypeDescription()), BSLType.TYPE_DESCRIPTION)
        self.assertEqual(write(BSLType.TYPE_DESCRIPTION), payload)
        self.assertIs(read(payload), BSLType.TYPE_DESCRIPTION)
        self.assertIs(type_of(read(payload)), BSLType.TYPE)

    def test_qualified_supplement_preserves_exact_native_frames_and_scalar_fields(self):
        base = BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(5), Decimal(2)))
        full = BSLTypeDescription('Number,String,Date',
                                  BSLNumberQualifiers(Decimal(5), Decimal(2), BSLAllowedSign.NONNEGATIVE),
                                  BSLStringQualifiers(Decimal(4), BSLAllowedLength.FIXED),
                                  BSLDateQualifiers(BSLDateFractions.TIME),
                                  BSLBinaryDataQualifiers(Decimal(8), BSLAllowedLength.FIXED))
        cases = [
            ('qualifiers.full', full),
            ('qualifiers.copy', BSLTypeDescription(base)),
            ('qualifiers.override', BSLTypeDescription(
                base, None, None, BSLNumberQualifiers(Decimal(3), Decimal(1)))),
            ('qualifiers.date-only', BSLTypeDescription(
                'Date', None, None, BSLDateQualifiers(BSLDateFractions.DATE))),
        ]
        cases = [(label, value, self.record(label, 'types-extra')) for label, value in cases]
        defaults = self.record('qualifiers.default', 'types-extra')
        cases += [('qualifiers.default.Empty', BSLTypeDescription(), defaults.get('Empty')),
                  ('qualifiers.default.Scalars', BSLTypeDescription('Boolean,String,Date,Number'),
                   defaults.get('Scalars'))]
        for label, value, native in cases:
            with self.subTest(label=label):
                self.assertEqual(write(value), native.get('Write'))
                restored = read(native.get('Write'))
                self.assertEqual(write(restored), inverse_stream(native))
                self.assertIs(type_of(restored), native.get('ReadType'))
                self.assertTrue(equal(value, restored))
                expected_fields = {'write', 'readtype', 'numberdigits', 'numberfractiondigits',
                                   'numbersign', 'stringlength', 'stringallowedlength',
                                   'datefractions', 'binarylength', 'binaryallowedlength'}
                if native.property('ReadWriteEqual'):
                    expected_fields.add('readwriteequal')
                    if native.get('ReadWriteEqual') is False:
                        expected_fields.add('readwrite')
                else:
                    expected_fields.add('readwrite')
                self.assertEqual(set(native._items), expected_fields)
                for item in (value, restored):
                    n, s, d, b = (item.number_qualifiers, item.string_qualifiers,
                                  item.date_qualifiers, item.binary_data_qualifiers)
                    fields = {'NumberDigits': n.digits, 'NumberFractionDigits': n.fraction_digits,
                              'NumberSign': n.allowed_sign, 'StringLength': s.length,
                              'StringAllowedLength': s.allowed_length, 'DateFractions': d.date_fractions,
                              'BinaryLength': b.length, 'BinaryAllowedLength': b.allowed_length}
                    for field, actual in fields.items():
                        self.assertEqual(actual, native.get(field), (label, field))
        self.assertEqual(write(full),
                         '{"#",' + GUID + ',\n{"Pattern",\n{"S",4,0},\n'
                         '{"D","T"},\n{"N",5,2,1}\n}\n}')
        self.assertEqual(NATIVE.read_bytes(), self.original)


class TypeDescriptionCodecPolicyTests(unittest.TestCase):
    def test_canonical_primitive_subsets_and_null_inverse(self):
        # Generalizations within the known grammar, separate from native probes.
        scalars = ((BSLType.BOOLEAN, 'B'), (BSLType.STRING, 'S'),
                   (BSLType.DATE, 'D'), (BSLType.NUMBER, 'N'))
        subsets = [subset for size in range(5) for subset in combinations(scalars, size)]
        subsets.append(((BSLType.NULL, 'L'),))
        for subset in subsets:
            kinds, tags = tuple(kind for kind, _ in subset), tuple(tag for _, tag in subset)
            with self.subTest(tags=tags):
                original = BSLTypeDescription(array(*reversed(kinds)))
                payload = canonical_pattern(tags)
                self.assertEqual(write(original), payload)
                restored = read(payload)
                self.assertIs(type(restored), BSLTypeDescription)
                self.assertIsNot(restored, original)
                self.assertEqual(restored.types, kinds)
                self.assertTrue(equal(restored, original))
                self.assertEqual(write(restored), payload)
                self.assertEqual(restored.number_qualifiers.digits, Decimal(0))
                self.assertEqual(restored.number_qualifiers.fraction_digits, Decimal(0))
                self.assertIs(restored.number_qualifiers.allowed_sign, BSLAllowedSign.ANY)
                self.assertEqual(restored.string_qualifiers.length, Decimal(0))
                self.assertIs(restored.string_qualifiers.allowed_length, BSLAllowedLength.VARIABLE)
                self.assertIs(restored.date_qualifiers.date_fractions, BSLDateFractions.DATE_TIME)
                self.assertEqual(restored.binary_data_qualifiers.length, Decimal(0))
                self.assertIs(restored.binary_data_qualifiers.allowed_length, BSLAllowedLength.VARIABLE)

    def test_explicit_normalized_default_qualifiers_use_the_unqualified_codec(self):
        value = BSLTypeDescription('Number,String,Date', BSLNumberQualifiers(Decimal(0), Decimal(2)),
                                   BSLStringQualifiers(Decimal(0), BSLAllowedLength.FIXED),
                                   BSLDateQualifiers(BSLDateFractions.DATE_TIME),
                                   BSLBinaryDataQualifiers(Decimal(0), BSLAllowedLength.FIXED))
        self.assertEqual(write(value), canonical_pattern(('S', 'D', 'N')))
        self.assertTrue(equal(read(write(value)), value))

    def test_qualifiers_for_absent_types_are_not_silently_erased(self):
        qualifiers = (
            (BSLNumberQualifiers(Decimal(5)), None, None),
            (BSLNumberQualifiers(Decimal(5), Decimal(2)), None, None),
            (BSLNumberQualifiers(Decimal(0), Decimal(0), BSLAllowedSign.NONNEGATIVE), None, None),
            (None, BSLStringQualifiers(Decimal(4)), None),
            (None, BSLStringQualifiers(Decimal(4), BSLAllowedLength.FIXED), None),
            (None, None, BSLDateQualifiers(BSLDateFractions.DATE)),
            (None, None, BSLDateQualifiers(BSLDateFractions.TIME)),
        )
        for source in ('', 'Boolean', 'Null'):
            for settings in qualifiers:
                with self.subTest(source=source, settings=settings):
                    with self.assertRaisesRegex(ValueError, 'при отсутствии этого типа'):
                        BSLTypeDescription(source, *settings)
                    for qualifier in settings:
                        if qualifier is not None:
                            self.assertIsNone(read(write(qualifier)))
        self.assertEqual(write(BSLTypeDescription('Number')), canonical_pattern(('N',)))

    def test_known_qualified_field_grammar_generalizes_within_constructor_budgets(self):
        # These field values are model checks, not newly asserted native cases.
        for digits, fraction, sign in ((3, 0, BSLAllowedSign.ANY),
                                      (39, 10, BSLAllowedSign.NONNEGATIVE),
                                      (4096, 4096, BSLAllowedSign.ANY),
                                      (0, 0, BSLAllowedSign.NONNEGATIVE)):
            original = BSLTypeDescription('Number', BSLNumberQualifiers(
                Decimal(digits), Decimal(fraction), sign))
            expected = '{"N",' + str(digits) + ',' + str(fraction) + ',' + str(sign.value) + '}'
            self.assertIn(expected, write(original))
            self.assertEqual(read(write(original)), original)
        for length in (1, 4, 1000000):
            for mode in (BSLAllowedLength.FIXED, BSLAllowedLength.VARIABLE):
                original = BSLTypeDescription('String', None,
                                              BSLStringQualifiers(Decimal(length), mode))
                self.assertIn('{"S",' + str(length) + ',' + str(mode.value) + '}', write(original))
                self.assertEqual(read(write(original)), original)
        for fraction, entry in ((BSLDateFractions.DATE, '{"D","D"}'),
                                (BSLDateFractions.TIME, '{"D","T"}'),
                                (BSLDateFractions.DATE_TIME, '{"D"}')):
            original = BSLTypeDescription('Date', None, None, BSLDateQualifiers(fraction))
            self.assertIn(entry, write(original))
            self.assertEqual(read(write(original)), original)

    def test_malformed_qualified_unknown_and_noncanonical_patterns_are_rejected(self):
        bodies = ['', '"Pattern"', 'Pattern', '0', '{0}', '{}', '{"pattern"}',
                  '{Pattern}', '{{"Pattern"}}', '{"Pattern",0}', '{"Pattern","N"}',
                  '{"Pattern",{"N",5,2}}', '{"Pattern",{"N",0,0,0}}',
                  '{"Pattern",{"N",{"N",5}}}', '{"Pattern",{"S",4}}',
                  '{"Pattern",{"D",1}}', '{"Pattern",{"B",1}}',
                  '{"Pattern",{"U"}}', '{"Pattern",{"T",' + GUID + '}}',
                  '{"Pattern",{"#",' + GUID + '}}', '{"Pattern",{"Unknown"}}',
                  '{"Pattern",{"n"}}', '{"Pattern",{N}}', '{"Pattern",{}}',
                  '{"Pattern",{"N"},{"N"}}', '{"Pattern",{"N"},{"S"}}',
                  '{"Pattern",{"L"},{"N"}}', '{"Pattern",{"N"},{"L"}}',
                  '{"Pattern",{"B"},{"S"},{"D"},{"N"},{"L"}}',
                  '{"Pattern",{"S"},1}', '{"Pattern",{"S"}},0']
        for body in bodies:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(frame(body))
        for payload in ('{"#",' + GUID + '}', '{"#","' + GUID + '",{"Pattern"}}',
                        '{"#",' + GUID.upper() + ',{"Pattern"}}',
                        '{"T",' + GUID + ',{"Pattern"}}'):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(payload)

    def test_qualified_fields_reject_coercion_noncanonical_defaults_and_out_of_budget_counts(self):
        invalid_counts = ('-1', '-0', '+1', '01', '1.0', '1e0', '١', '１',
                          '"1"', '{"N",1}', 'NaN', 'Infinity')
        for token in invalid_counts:
            for entry in ('{"N",' + token + ',0,0}', '{"N",5,' + token + ',0}',
                          '{"S",' + token + ',0}'):
                with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(frame('{"Pattern",' + entry + '}'))
        for entry in ('{"N",0,0,0}', '{"N",0,1,1}', '{"N",2,3,0}', '{"N",4097,0,0}',
                      '{"S",0,0}', '{"S",0,1}', '{"S",1000001,0}',
                      '{"D","DT"}', '{"D","DateTime"}', '{"D",D}',
                      '{"D","d"}', '{"D","t"}', '{"D",1}', '{"D",2}', '{"D",3}'):
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(frame('{"Pattern",' + entry + '}'))
        for token in ('-1', '2', '+1', '01', '1.0', '"1"', '{"N",1}'):
            for entry in ('{"N",5,2,' + token + '}', '{"S",4,' + token + '}'):
                with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(frame('{"Pattern",' + entry + '}'))
        for entry in ('{"N",' + '1' * 10000 + ',0,0}', '{"S",' + '1' * 10000 + ',0}'):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                read(frame('{"Pattern",' + entry + '}'))

    def test_scalar_description_map_keys_preserve_value_lookup_through_codecs(self):
        # Native run 39815192778 measured descriptor keys in mutable/fixed maps.
        # Exact native payloads and the full matrix live in the runtime tests.
        value = BSLTypeDescription('Number')
        mapping = BSLMap()
        mapping.insert(value, 'value')
        equivalent = BSLTypeDescription('Number')
        self.assertEqual(mapping.get(equivalent), 'value')
        for original in (mapping, BSLFixedMap(mapping)):
            restored = read(write(original))
            self.assertIs(type(restored), type(original))
            self.assertEqual(restored.get(equivalent), 'value')
            self.assertEqual(len(restored._items), 1)
        # The same supported descriptor grammar applies in a key position.
        for kind in (BSLType.MAP, BSLType.FIXED_MAP):
            payload = ('{"#",' + serialization._TYPE_IDS[kind] + ',{1,{' + write(value) +
                       ',{"S","value"}}}}')
            restored = read(payload)
            self.assertIs(type_of(restored), kind)
            self.assertEqual(restored.get(equivalent), 'value')
        mapping.delete(equivalent)
        self.assertIsNone(mapping.get(value))
        self.assertEqual(len(mapping._items), 0)

    def test_truncations_are_catchable_without_poisoning_the_next_read(self):
        for tags in ((), ('L',), ('S', 'N'), ('B', 'S', 'D', 'N')):
            payload = canonical_pattern(tags)
            for end in range(len(payload)):
                with self.subTest(tags=tags, end=end), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(payload[:end])
            self.assertEqual(write(read(payload)), payload)
            # Preserve the already-established first-complete-record policy.
            self.assertEqual(write(read(payload + ' trailing text')), payload)

    def test_type_descriptions_survive_supported_collection_values(self):
        first, second = BSLTypeDescription('String,Number'), BSLTypeDescription('Null')
        items = array(first, second, BSLType.TYPE_DESCRIPTION)
        record = BSLStructure('First,Second,Kind', *items.items)
        mapping = BSLMap()
        mapping.insert('first', first)
        mapping.insert('second', second)
        mapping.insert('kind', BSLType.TYPE_DESCRIPTION)
        for original in (items, BSLFixedArray(items), record, BSLFixedStructure(record),
                         mapping, BSLFixedMap(mapping), BSLKeyAndValue(first, second)):
            restored = read(write(original))
            self.assertIs(type_of(restored), type_of(original))
            if type(original) in (BSLMap, BSLFixedMap):
                self.assertEqual(len(restored._items), 3)
                self.assertEqual(restored.get('first'), first)
                self.assertEqual(restored.get('second'), second)
                self.assertIs(restored.get('kind'), BSLType.TYPE_DESCRIPTION)
            elif type(original) in (BSLStructure, BSLFixedStructure):
                self.assertEqual(restored.get('First'), first)
                self.assertEqual(restored.get('Second'), second)
                self.assertIs(restored.get('Kind'), BSLType.TYPE_DESCRIPTION)
            elif type(original) is BSLKeyAndValue:
                self.assertEqual(restored.key, first)
                self.assertEqual(restored.value, second)
            else:
                self.assertEqual(list(restored.items), list(items.items))

    def test_reader_returns_independent_type_lists_and_qualifiers(self):
        payload = canonical_pattern(('S', 'N'))
        first, second = read(payload), read(payload)
        types = first.get_types()
        types.items.clear()
        self.assertEqual(first.types, (BSLType.STRING, BSLType.NUMBER))
        self.assertEqual(second.types, first.types)
        self.assertIsNot(first.number_qualifiers, second.number_qualifiers)
        self.assertIsNot(first.string_qualifiers, second.string_qualifiers)
        self.assertIsNot(first.date_qualifiers, second.date_qualifiers)
        self.assertIsNot(first.binary_data_qualifiers, second.binary_data_qualifiers)
        self.assertEqual(write(first), payload)
        self.assertEqual(write(second), payload)

    def test_host_subclasses_do_not_trigger_reflection_or_qualified_properties(self):
        class HostDescription(BSLTypeDescription):
            def __str__(self):
                raise AssertionError('Host presentation must not run')

            @property
            def types(self):
                raise AssertionError('Host types must not be accessed')

        value = object.__new__(HostDescription)
        with self.assertRaises(TypeError):
            type_of(value)
        with self.assertRaises(TypeError):
            write(value)

    def test_text_node_and_depth_budgets_cover_descriptions(self):
        value = BSLTypeDescription('Number,String,Date,Boolean')
        payload = write(value)
        with patch.object(serialization, '_MAX_TEXT', len(payload)):
            self.assertEqual(write(value), payload)
            read(payload)
        with patch.object(serialization, '_MAX_TEXT', len(payload) - 1):
            for operation, argument in ((write, value), (read, payload)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)
        allowed, rejected = array(value, value), array(value, value, value)
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        # Each Pattern entry is metadata; token and value budgets both remain bounded.
        with patch.object(serialization, '_MAX_NODES', 4):
            self.assertEqual(write(allowed), allowed_payload)
            self.assertEqual(len(read(allowed_payload).items), 2)
        with patch.object(serialization, '_MAX_NODES', 3):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                write(rejected)
            with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                read(rejected_payload)
        allowed, rejected = array(array(value)), array(array(array(value)))
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_DEPTH', 2):
            self.assertEqual(write(allowed), allowed_payload)
            read(allowed_payload)
            for operation, argument in ((write, rejected), (read, rejected_payload)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)

    def test_codec_and_unsupported_guard_preserve_decimal_context(self):
        value = BSLTypeDescription('String,Number')
        qualified = BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(5), Decimal(2)))
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.flags[Rounded] = True
            for signal in context.traps:
                context.traps[signal] = True
            before = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            self.assertEqual(read(write(value)), value)
            self.assertEqual(read(write(qualified)), qualified)
            with self.assertRaisesRegex(ValueError, 'при отсутствии этого типа'):
                BSLTypeDescription('Boolean', qualified.number_qualifiers)
            with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(frame('{"Pattern",{"N",5,2}}'))
            after = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            self.assertEqual(after, before)

    def test_qualified_codec_and_bad_inverse_are_bsl_catchable(self):
        output = []
        vm = Interpreter(output.append)
        value = BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(5)))
        vm.variables['description'] = value
        vm.variables['payload'] = frame('{"Pattern",{"N",5,2}}')
        vm.execute('''
            result = 7;
            Try result = ValueFromStringInternal(payload);
            Except Message("malformed"); EndTry;
            Message(result);
            result = ValueFromStringInternal(ValueToStringInternal(description));
        ''')
        self.assertEqual(output, ['malformed', '7'])
        self.assertEqual(vm.variables['result'], value)
        with self.assertRaises(BSLRuntimeError):
            vm.execute('ValueFromStringInternal(payload)')
        vm.variables['payload'] = canonical_pattern(('S', 'N'))
        self.assertEqual(vm.execute('ValueFromStringInternal(payload)').types,
                         (BSLType.STRING, BSLType.NUMBER))


if __name__ == '__main__':
    unittest.main()
