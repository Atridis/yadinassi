"""Twenty focused internal snapshot tests; local policies, not native proofs."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import value_storage as snapshot
from yadinassi.dates import BSLDate
from yadinassi.file_io import BSLBinaryData
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.structures import BSLFixedStructure, BSLStructure
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.values import BSLArray, BSLFixedArray, NULL

def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


def fixed_array(*values):
    # Deliberately construct an existing fixed payload without invoking the
    # public constructor, which recursively freezes direct mutable arrays.
    result = object.__new__(BSLFixedArray)
    result.items = tuple(values)
    return result


def roundtrip(value):
    return snapshot.restore(snapshot.capture(value))


class SnapshotDraftTests(unittest.TestCase):
    def test_01_scalar_type_isolation(self):
        for source in (None, NULL, False, True, Decimal("0"), Decimal("1.25")):
            with self.subTest(source=source):
                result = roundtrip(source)
                self.assertIs(type(result), type(source))
                self.assertEqual(result, source)
        self.assertIsNot(type(roundtrip(False)), type(roundtrip(Decimal("0"))))

    def test_02_unicode_text_code_units(self):
        value = "A\U0001f600\ud800\x00\n"
        self.assertEqual(roundtrip(value), value)

    def test_03_exact_date_and_invalid_internal_state(self):
        for source in (BSLDate(12345), BSLDate(0, True)):
            result = roundtrip(source)
            self.assertEqual((result.ticks, result.boundary), (source.ticks, source.boundary))
        invalid = BSLDate(0)
        object.__setattr__(invalid, "ticks", -1)
        with self.assertRaises(ValueError):
            snapshot.capture(invalid)

    def test_04_uuid_and_invalid_internal_state(self):
        source = BSLUUID("01234567-89ab-4cde-8f01-23456789abcd")
        self.assertEqual(roundtrip(source).text, source.text)
        object.__setattr__(source, "text", "not-a-uuid")
        with self.assertRaises(ValueError):
            snapshot.capture(source)

    def test_05_binary_bytes_and_new_object(self):
        for data in (b"", b"\x00\xff\x80abc"):
            source = BSLBinaryData.from_bytes(data)
            saved = snapshot.capture(source)
            source._data = b"changed-after-capture"
            result = snapshot.restore(saved)
            self.assertIsNot(result, source)
            self.assertEqual(result._data, data)

    def test_06_mutable_array_types_and_order(self):
        result = roundtrip(array(Decimal(1), array("x"), array()))
        self.assertIs(type(result), BSLArray)
        self.assertEqual(result.items[0], Decimal(1))
        self.assertIs(type(result.items[1]), BSLArray)
        self.assertEqual(result.items[1].items, ["x"])
        self.assertEqual(result.items[2].items, [])

    def test_07_fixed_array_retains_direct_child_types(self):
        source = fixed_array(array("mutable"), fixed_array("fixed"))
        result = roundtrip(source)
        self.assertIs(type(result), BSLFixedArray)
        self.assertIs(type(result.items), tuple)
        self.assertIs(type(result.items[0]), BSLArray)
        self.assertIs(type(result.items[1]), BSLFixedArray)
        self.assertEqual(result.items[0].items, ["mutable"])

    def test_08_structure_spelling_and_case(self):
        source = BSLStructure("Name,Другой", Decimal(1), "x")
        result = roundtrip(source)
        self.assertEqual(result.get("name"), Decimal(1))
        self.assertEqual(result.get("ДРУГОЙ"), "x")
        self.assertEqual([entry[0] for entry in result._items.values()], ["Name", "Другой"])

    def test_09_fixed_structure_and_nested_mutability(self):
        source = BSLFixedStructure(BSLStructure("Child", array("x")))
        result = roundtrip(source)
        self.assertIs(type(result), BSLFixedStructure)
        with self.assertRaises(ValueError):
            result.set("Child", None)
        self.assertIs(type(result.get("Child")), BSLArray)
        result.get("Child").items.append("y")
        self.assertEqual(source.get("Child").items, ["x"])

    def test_10_map_scalar_and_identity_keys(self):
        source = BSLMap()
        identity_key = array("key")
        source.insert(True, "bool")
        source.insert(Decimal(1), "number")
        source.insert(identity_key, "object")
        result = roundtrip(source)
        self.assertEqual(result.get(True), "bool")
        self.assertEqual(result.get(Decimal(1)), "number")
        restored_key = next(key for key, value in result._items.values() if value == "object")
        self.assertIsNot(restored_key, identity_key)
        self.assertEqual(result.get(restored_key), "object")
        self.assertIsNone(result.get(identity_key))

    def test_11_fixed_map_type_and_rebuilt_identity_key(self):
        mutable = BSLMap()
        key = array(Decimal(1))
        mutable.insert(key, "value")
        result = roundtrip(BSLFixedMap(mutable))
        self.assertIs(type(result), BSLFixedMap)
        restored_key = next(iter(result._items.values()))[0]
        self.assertEqual(result.get(restored_key), "value")
        self.assertIsNone(result.get(key))
        with self.assertRaises(ValueError):
            result.set(restored_key, "changed")

    def test_12_source_mutation_after_capture(self):
        child = array("before")
        source = BSLStructure("Child", child)
        saved = snapshot.capture(source)
        child.items[0] = "after"
        source.insert("Added", True)
        result = snapshot.restore(saved)
        self.assertEqual(result.get("Child").items, ["before"])
        self.assertFalse(result.property("Added"))

    def test_13_restores_are_independent_draft_policy(self):
        saved = snapshot.capture(array(array("x")))
        first = snapshot.restore(saved)
        second = snapshot.restore(saved)
        self.assertIsNot(first, second)
        self.assertIsNot(first.items[0], second.items[0])
        first.items[0].items.append("changed")
        self.assertEqual(second.items[0].items, ["x"])

    def test_14_shared_objects_copy_per_occurrence(self):
        child = array("x")
        mapping = BSLMap()
        mapping.insert(child, child)
        binary = BSLBinaryData.from_bytes(b"x")
        result = roundtrip(array(child, child))
        self.assertIsNot(result.items[0], result.items[1])
        result.items[0].items.append("changed")
        self.assertEqual(result.items[1].items, ["x"])
        restored_map = roundtrip(mapping)
        key, value = next(iter(restored_map._items.values()))
        self.assertIsNot(key, value)
        self.assertIs(restored_map.get(key), value)
        restored_binary = roundtrip(array(binary, binary))
        self.assertIsNot(restored_binary.items[0], restored_binary.items[1])

    def test_15_cycles_rejected_without_mutating_sources(self):
        direct = array()
        direct.items.append(direct)
        left, right = array(), BSLStructure()
        left.items.append(right)
        right.insert("Back", left)
        for source in (direct, left):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(source)
        self.assertIs(direct.items[0], direct)
        self.assertIs(right.get("Back"), left)
        self.assertEqual(roundtrip(array("valid")).items, ["valid"])

    def test_16_hostile_objects_and_subclasses_no_callbacks(self):
        calls = []
        class HostileMeta(type):
            def __eq__(cls, other):
                calls.append("type-eq")
                raise AssertionError("metaclass callback")
        class Hostile(metaclass=HostileMeta):
            def __getattribute__(self, name):
                calls.append("attribute")
                raise AssertionError("object callback")
        class ArraySubclass(BSLArray):
            def __getattribute__(self, name):
                calls.append("array-attribute")
                raise AssertionError("subclass callback")
        for value in (Hostile(), object.__new__(ArraySubclass)):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(value)
        self.assertEqual(calls, [])

    def test_17_invalid_internals_and_hostile_map_token(self):
        bad_array = array()
        bad_array.items = ()
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.capture(bad_array)
        calls = []
        class HostileToken:
            def __hash__(self):
                return 1
            def __eq__(self, other):
                calls.append("eq")
                raise AssertionError("token comparison callback")
        mapping = BSLMap()
        mapping._items = {(Decimal, HostileToken()): (Decimal(1), "x")}
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.capture(mapping)
        self.assertEqual(calls, [])
        mapping._items = {(Decimal, Decimal("NaN")): (Decimal(1), "x")}
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.capture(mapping)

    def test_18_node_and_depth_budgets(self):
        with patch.object(snapshot, "MAX_NODES", 4):
            self.assertEqual(roundtrip(array(None, None, None)).items,
                             [None, None, None])
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(array(None, None, None, None))
        with patch.object(snapshot, "MAX_DEPTH", 2):
            self.assertEqual(roundtrip(array(array("x"))).items[0].items, ["x"])
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(array(array(array("x"))))

    def test_19_cumulative_text_and_binary_budgets(self):
        with patch.object(snapshot, "MAX_TEXT_UNITS", 4):
            self.assertEqual(roundtrip(array("\U0001f600", "ab")).items, ["\U0001f600", "ab"])
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(array("\U0001f600", "abc"))
        with patch.object(snapshot, "MAX_BINARY_BYTES", 4):
            accepted = array(BSLBinaryData.from_bytes(b"ab"), BSLBinaryData.from_bytes(b"cd"))
            self.assertEqual(roundtrip(accepted).items[1]._data, b"cd")
            rejected = array(BSLBinaryData.from_bytes(b"abc"), BSLBinaryData.from_bytes(b"de"))
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(rejected)

    def test_20_decimal_limits_and_unsupported_runtime(self):
        for value in (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity")):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(value)
        with patch.object(snapshot, "MAX_NUMBER_DIGITS", 3):
            self.assertEqual(roundtrip(Decimal("123")), Decimal("123"))
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(Decimal("1234"))
        with patch.object(snapshot, "MAX_TOTAL_NUMBER_DIGITS", 4):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(array(Decimal("123"), Decimal("45")))
        with patch.object(snapshot, "_CDecimal", None):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.capture(Decimal("1"))

    def test_21_missing_required_exact_host_fields(self):
        for kind in (BSLDate, BSLUUID, BSLBinaryData, BSLArray, BSLFixedArray,
                     BSLStructure, BSLFixedStructure, BSLMap, BSLFixedMap,
                     snapshot.BSLValueStorage):
            value = object.__new__(kind)
            with self.subTest(kind=kind.__name__):
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.capture(value)
        missing_boundary = object.__new__(BSLDate)
        object.__setattr__(missing_boundary, "ticks", 0)
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.capture(missing_boundary)
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.BSLValueStorage.get(object.__new__(snapshot.BSLValueStorage))
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.restore(object.__new__(snapshot.Snapshot))


if __name__ == "__main__":
    unittest.main()
