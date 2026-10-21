"""Codec regressions grounded in the owner's 1C 8.3.27.2342 outputs.

NativeEvidenceTests reads, but never creates or rewrites, the committed native
records. SafeSubsetTests describes Yadinassi's defensive model; those checks do
not claim native acceptance, rejection, cycle behavior, or resource limits.
"""

from tests.native_observations import (read_observation, inverse_stream, assert_snapshot,
                                       assert_type_inverse, assert_nested, extract_payload)

from decimal import Decimal
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, serialization
from yadinassi.dates import BSLDate
from yadinassi.xml_processing import XML_STRING_PROCESSING
from yadinassi.round_modes import BSLRoundMode, ROUND_MODES
from yadinassi.search_directions import BSLSearchDirection, SEARCH_DIRECTIONS
from yadinassi.sort_directions import BSLSortDirection
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.serialization import value_from_string_internal as read
from yadinassi.serialization import value_to_string_internal as write
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_tables import BSLValueTable
from yadinassi.value_lists import BSLValueList
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, NULL, equal, to_string


def table_family_samples():
    vm = Interpreter()
    vm.execute('table = New ValueTable; columns = table.Columns; '
               'columns.Add("Имя"); columns.Add("Число", New TypeDescription("Number")); '
               'For i = 1 To 3 Do row = table.Add(); row.Имя = "row" + String(i); row.Число = i; EndDo;')
    table = vm.variables['table']
    return [('table', table), ('columns', table.columns),
            ('column', table.columns.items[0]), ('row', table.rows[0])]


def index_family_samples():
    table = BSLValueTable()
    table.columns.add('Key')
    table.columns.add('Second')
    index = table.indexes.add('Key,Second')
    return [('collection', table.indexes), ('index', index)]


def list_family_samples():
    values = BSLValueList()
    item = values.add(Decimal(10), 'first', True)
    # The item holds a weak reference: the fixture must retain its live owner.
    class Samples(list):
        pass
    samples = Samples([('empty', BSLValueList()), ('item', item)])
    samples.owner = values
    return samples


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests/fixtures/native_windows"
FORMAT_ERROR = "Ошибка преобразования: Ошибка формата потока"
ARRAY_GUID = "51e7a0d2-530b-11d4-b98a-008048da3034"
TYPE_GUIDS = {
    "Undefined": "ee8d3e7c-f930-4a76-8aad-4ff9083a6ea6",
    "Boolean": "5d4125ad-f6e7-4313-be32-f71d0ab60915",
    "Number": "b0be78f2-0ee6-4d31-a3bb-77dd32ba5bec",
    "String": "9b6abf8b-0173-48e5-b0a0-83b21fcf63c5",
    "Array": ARRAY_GUID,
    "Structure": "4238019d-7e49-4fc9-91db-b6b951d5cf8e",
    "Map": "3d48feae-a9c6-4c5a-a099-9eb6477630c6",
    "FixedArray": "4500381b-db30-4a10-9db4-990038032acf",
    "FixedStructure": "3ee983d7-ace7-40f9-bb7e-2e916fcddd56",
    "FixedMap": "220455ea-6c85-4513-996f-bbe79ed07774",
    "KeyAndValue": "850afa6f-5244-482f-9729-d78ec65ff607",
    "Type": "d47d59f8-73f0-481c-8b5e-f6384c0a4804",
    "RoundMode": "32c82ccd-fef3-4070-beb5-b9c52afc781d",
    "EnumRoundMode": "a47c4665-311c-405a-828e-0c5a3ca3bdda",
}


TYPE_FAMILY_EXPRESSIONS = (
    ('description.default.en', 'New TypeDescription'),
    ('number.default.en', 'New NumberQualifiers'),
    ('string.default.en', 'New StringQualifiers'),
    ('date.default.en', 'New DateQualifiers'),
    ('binary.default.en', 'New BinaryDataQualifiers'),
    ('allowedsign.namespace', 'AllowedSign'),
    ('allowedsign.any', 'AllowedSign.Any'),
    ('allowedlength.namespace', 'AllowedLength'),
    ('allowedlength.variable', 'AllowedLength.Variable'),
    ('datefractions.namespace', 'DateFractions'),
    ('datefractions.datetime', 'DateFractions.DateTime'),
)


def type_family_samples():
    vm = Interpreter()
    return [(label, vm.execute(expression)) for label, expression in TYPE_FAMILY_EXPRESSIONS]


def normalize_transport(text):
    """Only the launcher's CR/LF normalization, never payload whitespace."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


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


def scalar_array():
    return array(None, False, True, Decimal("12.5"), 'а,"б"')


def collection_samples():
    return {
        "array": scalar_array(),
        "fixed-array": BSLFixedArray(scalar_array()),
        "structure": BSLStructure("Код,Пустое", Decimal(7)),
        "fixed-structure": BSLFixedStructure("Код,Пустое", Decimal(7)),
        "map": mapping(("ключ", Decimal(7))),
        "fixed-map": BSLFixedMap(mapping(("ключ", Decimal(7)))),
    }


TYPED_ENTRIES = (
    (None, "undefined"), (False, "boolean"), (Decimal(0), "number"),
    ("0", "string"), (BSLType.NUMBER, "type"),
)


class NativeEvidenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        # Checkout/launcher line endings are transport. Compact scalar CR/LF
        # are escaped at this stage and must only be decoded afterward.
        cls.outputs = {
            name: normalize_transport((OUTPUT / (name + ".out")).read_bytes().decode("utf-8"))
            for name in ("numbers", "strings", "collections", "dates", "values")
        }

    def native(self, suite, label):
        return extract_payload(self.outputs[suite], label)

    def assert_native_payload(self, suite, label, value):
        expected = self.native(suite, label + ".payload")
        actual = write(value)
        self.assertEqual(normalize_transport(actual), expected)
        self.assertEqual(self.native(suite, label + ".roundtrip.type"), "true")
        restored = read(actual)
        self.assertIs(type(restored), type(value))
        return restored

    def test_native_primitive_tags_and_values(self):
        samples = {
            "internal.undefined": None,
            "internal.boolean.false": False,
            "internal.boolean.true": True,
            "internal.string.empty": "",
            "internal.string.ascii": "abc",
            "internal.string.spaces": "  а  ",
            "internal.string.quotes": 'Он сказал "да".',
            "internal.string.delimiters": "{N,1},[x];\\path\\",
            "internal.string.tab": "а\tб",
            "internal.string.unicode": "Ёж🙂е́",
            "internal.string.error-text": "error",
            "internal.string.multiline": "первая\nвторая",
        }
        for label, value in samples.items():
            with self.subTest(label=label):
                self.assertEqual(self.assert_native_payload("strings", label, value), value)
                self.assertEqual(self.native("strings", label + ".roundtrip.value"), "true")
        self.assertEqual(write(None), '{"U"}')
        self.assertEqual(write(False), '{"B",0}')
        self.assertEqual(write(True), '{"B",1}')
        self.assertNotEqual(write(False), write(Decimal(0)))

    def test_native_string_escaping_is_utf16_not_json(self):
        expected = '{"S","Ёж"\\d83d"\\de42е́"}'
        self.assertEqual(self.native("strings", "internal.string.unicode.payload"), expected)
        self.assertEqual(write("Ёж🙂е́"), expected)
        self.assertEqual(read(expected), "Ёж🙂е́")
        self.assertEqual(write('Он сказал "да".'), '{"S","Он сказал ""да""."}')
        self.assertEqual(write("{N,1},[x];\\path\\"), '{"S","{N,1},[x];\\path\\"}')
        # Transport erased the newline distinction, but the native length did
        # not: 8 wrapper characters + 6 + LF + 6 = 21 UTF-16 units.
        multiline = write("первая\nвторая")
        self.assertEqual(multiline, '{"S","первая\nвторая"}')
        self.assertEqual(len(multiline), int(self.native("strings", "internal.string.multiline.length")))

    def test_native_numeric_payloads_are_not_presentation(self):
        samples = {
            "zero": "0", "negative-zero": "-0.000", "one": "1",
            "negative": "-12.5", "grouping-boundary": "1234.5",
            "trailing-zeroes": "13.1000", "small": "1e-28",
            "large": "1e27", "exact-fraction": "1.2345678901234567890123456789",
            "third": "0.333333333333333333333333333",
            "ten-thirds": "3.333333333333333333333333333", "scaled-residual": "-3",
        }
        for name, text in samples.items():
            with self.subTest(name=name):
                value = Decimal(text)
                self.assertEqual(self.assert_native_payload("numbers", "internal.number." + name, value), value)
        self.assertEqual(write(Decimal("1234.5")), '{"N",1234.5}')
        self.assertEqual(to_string(Decimal("1234.5")), "1\u00a0234,5")

    def test_all_native_type_guids(self):
        search_types = {BSLType.SEARCH_DIRECTION, BSLType.SEARCH_DIRECTIONS,
                        BSLType.SORT_DIRECTION, BSLType.DATE, BSLType.NULL,
                        BSLType.XML_STRING_PROCESSING_MANAGER}
        family_types = {type_of(value) for _, value in
                        [*type_family_samples(), *table_family_samples(), *index_family_samples(), *list_family_samples()]}
        self.assertEqual({type_by_name(name) for name in TYPE_GUIDS} | search_types | family_types,
                         set(serialization._CODECS))
        sort_snapshot = read_observation(self.native('collections', 'table.list.sort.enum.asc-codec'))
        self.assertEqual(write(BSLType.SORT_DIRECTION), sort_snapshot.get('TypeWrite'))
        self.assertIs(read(sort_snapshot.get('TypeWrite')), BSLType.SORT_DIRECTION)
        for label, value in list_family_samples():
            snapshot = read_observation(self.native('collections', 'table.list.codec.' + label))
            self.assertEqual(write(type_of(value)), snapshot.get('TypeWrite'))
            self.assertIs(read(snapshot.get('TypeWrite')), type_of(value))
        for label, value in type_family_samples():
            snapshot = read_observation(self.native('values', 'types.' + label))
            payload = snapshot.get('TypeWrite')
            self.assertEqual(write(type_of(value)), payload)
            self.assertIs(read(payload), type_of(value))
        for label, value in table_family_samples():
            snapshot = read_observation(self.native('collections', 'table.codec.' + label))
            self.assertEqual(write(type_of(value)), snapshot.get('TypeWrite'))
            self.assertIs(read(snapshot.get('TypeWrite')), type_of(value))
        for label, value in index_family_samples():
            snapshot = read_observation(self.native('collections', 'table.indexes.codec.' + label))
            self.assertEqual(write(type_of(value)), snapshot.get('TypeWrite'))
            self.assertIs(read(snapshot.get('TypeWrite')), type_of(value))
        # The namespace has a TypeOf/codec identity but both Type(name) calls
        # fail natively. Check its observed record directly, without an alias.
        for value, label in [(BSLType.SEARCH_DIRECTION, 'search.enum.begin.type'),
                             (BSLType.SEARCH_DIRECTIONS, 'search.enum.namespace.type')]:
            payload = self.native('strings', label)
            self.assertEqual(write(value), payload)
            self.assertIs(read(payload), value)
        manager_types = read(self.native('values', 'xml.manager.types'))
        for name in ('RU', 'EN'):
            self.assertIs(manager_types.get(name), BSLType.XML_STRING_PROCESSING_MANAGER)
            self.assertEqual(write(manager_types.get(name)),
                             '{"T",8f646b4e-fc39-44c7-85a2-c2eb39cdf361}')
        payload = self.native('values', 'null.type.name')
        self.assertEqual(payload, '{"T",af40a278-63bc-478e-91a8-19e0d16b10b5}')
        self.assertEqual(write(type_by_name('Null')), payload)
        self.assertIs(read(payload), BSLType.NULL)
        payload = self.native('dates', 'date.codec.type-ru')
        self.assertEqual(write(BSLType.DATE), payload)
        self.assertIs(read(payload), BSLType.DATE)
        for name, guid in TYPE_GUIDS.items():
            with self.subTest(name=name):
                value = type_by_name(name)
                payload = '{"T",' + guid + '}'
                if name in ("RoundMode", "EnumRoundMode"):
                    case = "numbers"
                    label = "round.enum-type" if name == "RoundMode" else "round.namespace-type"
                    result_label = label + ".roundtrip"
                else:
                    case, label = "collections", "internal.type." + name
                    result_label = label + ".roundtrip.value"
                self.assertEqual(self.native(case, label + ".payload"), payload)
                self.assertEqual(write(value), payload)
                self.assertIs(read(payload), value)
                self.assertEqual(self.native(case, result_label), "true")

    def test_empty_collection_guids_and_layout(self):
        samples = {
            "array": BSLArray(), "structure": BSLStructure(), "map": BSLMap(),
            "fixed-array": BSLFixedArray(BSLArray()),
            "fixed-structure": BSLFixedStructure(),
            "fixed-map": BSLFixedMap(BSLMap()),
        }
        aliases = {"array": "Array", "structure": "Structure", "map": "Map",
                   "fixed-array": "FixedArray", "fixed-structure": "FixedStructure", "fixed-map": "FixedMap"}
        for name, value in samples.items():
            with self.subTest(name=name):
                expected = '{"#",' + TYPE_GUIDS[aliases[name]] + ',\n{0}\n}'
                self.assertEqual(normalize_transport(write(value)), expected)
                restored = self.assert_native_payload("collections", "internal." + name + ".empty", value)
                self.assertEqual(len(list(restored)), 0)
                self.assertIsNot(restored, value)

    def test_populated_collections_preserve_types_and_observed_layout(self):
        for name, value in collection_samples().items():
            with self.subTest(name=name):
                suffix = ".scalars" if name in {"array", "fixed-array"} else ".populated"
                label = "internal." + name + suffix
                restored = self.assert_native_payload("collections", label, value)
                self.assertEqual(len(list(restored)), len(list(value)))
                self.assertEqual(normalize_transport(write(restored)), self.native("collections", label + ".roundtrip.payload"))

    def test_all_runtime_value_types_preserve_native_readback_behavior(self):
        family = type_family_samples()
        table_family = table_family_samples()
        index_family = index_family_samples()
        list_family = list_family_samples()
        list_labels = {type_of(value): label for label, value in list_family}
        table_labels = {type_of(value): label for label, value in table_family}
        index_labels = {type_of(value): label for label, value in index_family}
        family_labels = {type_of(value): label for label, value in family}
        samples = [NULL, None, False, BSLDate(0), Decimal("12.5"), "Ёж🙂е́", BSLType.NUMBER,
                   BSLKeyAndValue("Ключ", Decimal(7)), *collection_samples().values(),
                   BSLRoundMode.ROUND15_AS10, BSLRoundMode.ROUND15_AS20, ROUND_MODES,
                   BSLSearchDirection.FROM_BEGIN, BSLSearchDirection.FROM_END, SEARCH_DIRECTIONS,
                   BSLSortDirection.ASC, BSLSortDirection.DESC,
                   XML_STRING_PROCESSING, *[value for _, value in family],
                   *[value for _, value in table_family], *[value for _, value in index_family],
                   *[value for _, value in list_family]]
        self.assertEqual({type_of(value) for value in samples}, set(serialization._CODECS))
        for value in samples:
            with self.subTest(kind=type_of(value)):
                payload = write(value)
                restored = read(payload)
                family_label = family_labels.get(type_of(value))
                if family_label is not None:
                    snapshot = read_observation(self.native('values', 'types.' + family_label))
                    self.assertEqual(payload, snapshot.get('Write'))
                    self.assertEqual(write(restored), inverse_stream(snapshot))
                    self.assertIs(type_of(restored), snapshot.get('ReadType'))
                elif type_of(value) in table_labels:
                    snapshot = read_observation(self.native('collections', 'table.codec.' + table_labels[type_of(value)]))
                    self.assertEqual(payload, snapshot.get('Write'))
                    self.assertEqual(write(restored), inverse_stream(snapshot))
                    self.assertIs(type_of(restored), snapshot.get('ReadType'))
                elif type_of(value) in index_labels:
                    snapshot = read_observation(self.native(
                        'collections', 'table.indexes.codec.' + index_labels[type_of(value)]))
                    self.assertEqual(payload, snapshot.get('Write'))
                    self.assertEqual(write(restored), inverse_stream(snapshot))
                    self.assertIsNone(restored)
                    self.assertEqual(str(type_of(restored)), snapshot.get('ReadType'))
                elif type_of(value) in list_labels:
                    snapshot = read_observation(self.native(
                        'collections', 'table.list.codec.' + list_labels[type_of(value)]))
                    self.assertEqual(payload, snapshot.get('Write'))
                    self.assertEqual(write(restored), inverse_stream(snapshot))
                    self.assertEqual(str(type_of(restored)), snapshot.get('ReadType'))
                elif value is ROUND_MODES:
                    self.assertIsNone(restored)
                    self.assertEqual(payload, self.native("numbers", "round.namespace.payload"))
                    self.assertEqual(write(restored), self.native("numbers", "round.namespace.read.payload"))
                elif value is XML_STRING_PROCESSING:
                    self.assertIsNone(restored)
                    self.assertEqual(payload, read(self.native("values", "xml.manager.write")))
                    self.assertEqual(write(restored), self.native("values", "xml.manager.inverse"))
                elif value is SEARCH_DIRECTIONS:
                    self.assertIsNone(restored)
                    self.assertEqual(payload, self.native('strings', 'search.enum.namespace.payload'))
                    self.assertEqual(write(restored), self.native('strings', 'search.enum.namespace.readback'))
                elif type(value) is BSLSortDirection:
                    label = 'asc' if value is BSLSortDirection.ASC else 'desc'
                    snapshot = read_observation(self.native(
                        'collections', 'table.list.sort.enum.' + label + '-codec'))
                    self.assertEqual(payload, snapshot.get('Write'))
                    self.assertEqual(write(restored), inverse_stream(snapshot))
                    self.assertEqual(type_of(restored) is type_of(value), snapshot.get('ReadType'))
                    self.assertEqual(equal(restored, value), snapshot.get('ReadEqual'))
                else:
                    self.assertIs(type(restored), type(value))
                    self.assertEqual(write(restored), payload)  # These maps have only one entry.

    def test_key_and_value_from_all_four_native_container_kinds(self):
        samples = {
            "structure": BSLStructure("Ключ", Decimal(7)),
            "fixed-structure": BSLFixedStructure("Ключ", Decimal(7)),
            "map": mapping(("ключ", Decimal(7))),
            "fixed-map": BSLFixedMap(mapping(("ключ", Decimal(7)))),
        }
        for name, container in samples.items():
            with self.subTest(name=name):
                pair = next(iter(container))
                restored = self.assert_native_payload("collections", "internal.key-and-value." + name, pair)
                self.assertIs(type(restored), BSLKeyAndValue)
                self.assertEqual(restored.key, pair.key)
                self.assertEqual(restored.value, pair.value)
                self.assertEqual(to_string(restored), "КлючИЗначение")

    def test_repeated_references_restore_as_independent_values(self):
        originals, copies = collection_samples(), collection_samples()
        for name, original in originals.items():
            with self.subTest(name=name):
                repeated, independent = array(original, original), array(original, copies[name])
                repeated_label = "internal." + name + ".repeated-reference"
                independent_label = "internal." + name + ".independent-equal"
                restored = self.assert_native_payload("collections", repeated_label, repeated)
                self.assert_native_payload("collections", independent_label, independent)
                self.assertEqual(write(repeated), write(independent))
                left, right = restored.items
                self.assertIsNot(left, original)
                self.assertIsNot(left, right)
                self.assertFalse(equal(left, right))
                self.assertEqual(self.native("collections", repeated_label + ".restored-pair-equal"), "false")
                if name in {"array", "structure", "map"}:
                    before = write(right)
                    if name == "array":
                        left.add("roundtrip-change")
                    else:
                        left.insert("RoundtripChange", True)
                    self.assertEqual(write(right), before)
                    self.assertEqual(self.native("collections", repeated_label + ".shared-after-change"), "false")

    def test_observed_map_order_is_not_canonical_sorting(self):
        # These particular native observations establish reversal for the
        # tested insertion sequences, not a portable canonical map order.
        for name, entries in (("typed-keys", TYPED_ENTRIES),
                              ("typed-keys-again", TYPED_ENTRIES),
                              ("reverse-insertion", tuple(reversed(TYPED_ENTRIES)))):
            with self.subTest(name=name):
                label = "internal.map." + name
                value = mapping(*entries)
                restored = self.assert_native_payload("collections", label, value)
                self.assertEqual(len(list(restored)), 5)
                for key, expected in TYPED_ENTRIES:
                    self.assertEqual(restored.get(key), expected)
                self.assertEqual(normalize_transport(write(restored)), self.native("collections", label + ".roundtrip.payload"))
                self.assertNotEqual(write(restored), write(value))
                self.assertEqual(write(read(write(restored))), write(value))

    def test_structure_order_and_key_spelling_are_preserved(self):
        for name, value in (("order-ab", BSLStructure("А,б", Decimal(1), Decimal(2))),
                            ("order-ba", BSLStructure("б,А", Decimal(2), Decimal(1)))):
            with self.subTest(name=name):
                label = "internal.structure." + name
                restored = self.assert_native_payload("collections", label, value)
                self.assertEqual([pair.key for pair in restored], [pair.key for pair in value])
                self.assertEqual(write(restored), write(value))

    def test_native_nested_mutable_and_fixed_shapes(self):
        record = BSLStructure("Код,Пустое", Decimal(7))
        nested = array(record,
                       BSLFixedStructure("Массив,Словарь", scalar_array(), mapping(("ключ", Decimal(7)))),
                       BSLFixedMap(mapping(*TYPED_ENTRIES)))
        restored = self.assert_native_payload("collections", "internal.array.nested", nested)
        self.assertIs(type(restored.items[0]), BSLStructure)
        self.assertIs(type(restored.items[1]), BSLFixedStructure)
        self.assertIs(type(restored.items[2]), BSLFixedMap)
        self.assertEqual(restored.items[0].get("Код"), Decimal(7))
        self.assertIsNone(restored.items[0].get("Пустое"))
        self.assertIs(type(restored.items[1].get("Массив")), BSLArray)
        self.assertEqual(restored.items[1].get("Массив").items[4], 'а,"б"')
        self.assertEqual(restored.items[1].get("Словарь").get("ключ"), Decimal(7))
        for key, expected in TYPED_ENTRIES:
            self.assertEqual(restored.items[2].get(key), expected)
        self.assertEqual(normalize_transport(write(restored)), self.native("collections", "internal.array.nested.roundtrip.payload"))

    def test_native_accepted_reader_variants(self):
        samples = {
            "canonical": ('{"N",1}', "1"),
            "outer-space": (' {"N",1} ', "1"),
            "inner-space": ('{ "N" , 1 }', "1"),
            "trailing-garbage": ('{"N",1}x', "1"),
            "plus": ('{"N",+1}', "1"),
            "leading-zero": ('{"N",01}', "1"),
            "trailing-zero": ('{"N",1.2300}', "1.23"),
            "negative-zero": ('{"N",-0.000}', "0"),
            "comma-fraction": ('{"N",1,5}', "1"),
        }
        for name, (payload, expected) in samples.items():
            with self.subTest(name=name):
                value = read(payload)
                self.assertIs(type(value), Decimal)
                self.assertEqual(value, Decimal(expected))
                self.assertEqual(self.native("numbers", "internal.read." + name + ".type"), "Число")
                self.assertEqual(to_string(value), self.native("numbers", "internal.read." + name + ".value"))
        self.assertIsNone(read('{"n",1}'))
        self.assertEqual(self.native("numbers", "internal.read.lowercase-tag.value"), "")

    def test_native_malformed_reader_error_core(self):
        for name, payload in (("empty", ""), ("bare-number", "1"),
                              ("truncated", '{"N",1'), ("unknown-tag", '{"UNKNOWN",1}'),
                              ("exponent", '{"N",1e2}'), ("nan", '{"N",NaN}')):
            with self.subTest(name=name):
                # Module names, source paths and line numbers are execution
                # context. Only the observed stream-format error is portable.
                label = "internal.read." + name
                diagnostic = self.native("numbers", label + ".error")
                if diagnostic == "error":
                    # Portable probe revision: real-1C category marker replaces
                    # its environment-specific module/line wrapper.
                    self.assertEqual(self.native("numbers", label + ".error.stream-format"), "true")
                else:
                    self.assertTrue(diagnostic.endswith(FORMAT_ERROR))
                with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(payload)

    def test_interpreter_aliases_and_error_recovery_with_full_value_support(self):
        vm = Interpreter()
        for writer, reader in (("ValueToStringInternal", "ValueFromStringInternal"),
                               ("ЗначениеВСтрокуВнутр", "ЗначениеИзСтрокиВнутр"),
                               ("vAlUeToStRiNgInTeRnAl", "зНаЧеНиЕиЗсТрОкИвНуТр")):
            with self.subTest(writer=writer):
                value = vm.execute(f'{reader}({writer}(New Structure("Ключ", "Ёж🙂")))')
                self.assertIs(type(value), BSLStructure)
                self.assertEqual(value.get("Ключ"), "Ёж🙂")
        output = []
        Interpreter(output.append).execute('''
            value = 7;
            Try
                value = ValueFromStringInternal("invalid");
            Except
                Message("caught");
            EndTry;
            Message(value);
            Message(ValueToStringInternal(True));
        ''')
        self.assertEqual(output, ["caught", "7", '{"B",1}'])


class SafeSubsetTests(unittest.TestCase):
    """Defensive implementation boundaries, deliberately not native goldens."""

    def test_surrogate_halves_preserve_utf16_units_in_the_model(self):
        # Native evidence establishes the pair escaping; lone-surrogate support
        # is a consistency property of the existing UTF-16 string model.
        for value in ("\ud83d", "\ude42", "x\ud83dy", "\ud83d\ude42"):
            with self.subTest(units=ascii(value)):
                restored = read(write(value))
                self.assertEqual(restored.encode("utf-16-le", "surrogatepass"),
                                 value.encode("utf-16-le", "surrogatepass"))

    def test_nested_host_objects_are_not_stringified_or_reflected(self):
        class Host:
            def __str__(self):
                raise AssertionError("Host string hook must not run")

            def __repr__(self):
                raise AssertionError("Host repr hook must not run")

        host = Host()
        for value in (array(host), BSLStructure("Key", host), mapping((host, Decimal(1))),
                      BSLKeyAndValue("Key", host)):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(TypeError):
                    write(value)

    def test_unknown_guids_and_malformed_shapes_fail_safely(self):
        payloads = [
            '{"T",00000000-0000-0000-0000-000000000000}',
            '{"#",00000000-0000-0000-0000-000000000000,{0}}',
            '{"#",' + ARRAY_GUID + ',{-1}}',
            '{"#",' + ARRAY_GUID + ',{2,{"N",1}}}',
            '{"#",' + ARRAY_GUID + ',{0,{"N",1}}}',
            '{"S","unterminated}', '{"S","x"\\zzzz"}',
            '__import__("os").system("echo unsafe")',
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    read(payload)

    def test_cycles_fail_without_recursion_or_partial_state(self):
        cyclic_array = array()
        cyclic_array.add(cyclic_array)
        cyclic_record = BSLStructure()
        cyclic_record.insert("Self", cyclic_record)
        cyclic_map = mapping()
        cyclic_map.insert("Self", cyclic_map)
        for value in (cyclic_array, cyclic_record, cyclic_map):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(ValueError):
                    write(value)
                # A failed walk must not poison subsequent independent writes.
                self.assertEqual(write(Decimal(1)), '{"N",1}')

    def test_input_depth_nodes_and_numbers_have_explicit_work_budgets(self):
        deep = '{"N",1}'
        for _ in range(1000):
            deep = '{"#",' + ARRAY_GUID + ',{1,' + deep + '}}'
        many = '{"#",' + ARRAY_GUID + ',{10001,' + ','.join(['{"U"}'] * 10001) + '}}'
        payloads = [" " * (1024 * 1024 + 1), deep, many,
                    '{"N",' + '1' * 4097 + '}',
                    '{"N",0.' + '0' * 4096 + '1}']
        for payload in payloads:
            with self.subTest(length=len(payload), prefix=payload[:40]):
                with self.assertRaisesRegex(ValueError, "предел ресурсов Yadinassi"):
                    read(payload)

    def test_writer_depth_nodes_and_size_have_explicit_work_budgets(self):
        deep = Decimal(1)
        for _ in range(1000):
            deep = array(deep)
        for value in (deep, array(*([None] * 10001)), "x" * (1024 * 1024 + 1)):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "предел ресурсов Yadinassi"):
                    write(value)


class NativeFixtureTransportTests(unittest.TestCase):
    """Checkout simulation and synthetic escaping checks, not new native output."""

    def test_legacy_fixture_loading_accepts_lf_crlf_and_lone_cr_checkouts(self):
        original_read = Path.read_bytes
        NativeEvidenceTests.setUpClass()
        baseline = dict(NativeEvidenceTests.outputs)
        self.addCleanup(NativeEvidenceTests.setUpClass)
        for newline in (b"\r\n", b"\r"):
            def checkout_bytes(path):
                data = original_read(path)
                if path.parent == OUTPUT and path.suffix == '.out':
                    data = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                    return data.replace(b'\n', newline)
                return data
            with self.subTest(newline=newline), patch.object(Path, 'read_bytes', checkout_bytes):
                NativeEvidenceTests.setUpClass()
                self.assertEqual(NativeEvidenceTests.outputs, baseline)
                # Exercise actual legacy multiline stream comparisons too.
                probe = NativeEvidenceTests('test_native_primitive_tags_and_values')
                probe.test_native_primitive_tags_and_values()

    def test_outer_transport_normalization_precedes_compact_escape_decoding(self):
        intrinsic = '{"S","first\r\nsecond\rthird\nfourth\\n"}'
        escaped = write(intrinsic).replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n')
        logical = 'sample: [value=' + escaped + ']\nnext: [{"N",1}]\n'
        for transported in (logical, logical.replace('\n', '\r\n'),
                            logical.replace('\n', '\r'),
                            logical.replace(']\nnext', ']\r\nnext').replace('1}]\n', '1}]\r')):
            with self.subTest(transported=transported):
                normalized = normalize_transport(transported)
                self.assertEqual(normalized, logical)
                decoded = read_observation(extract_payload(normalized, 'sample'))
                self.assertEqual(decoded, intrinsic)
                self.assertIn('first\r\nsecond\rthird\nfourth\\n', decoded)


if __name__ == "__main__":
    unittest.main()
