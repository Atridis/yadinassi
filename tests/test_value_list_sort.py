"""ValueList sort expectations from authenticated owner commit 3172627.

The real checkpoint is read, never rewritten or synthesized. Additional
host/resource/unsupported tests describe local safety limits, not native errors.
"""

from decimal import Decimal as D, Inexact, Rounded, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter, value_list_sort
from yadinassi.dates import BSLDate
from yadinassi.maps import BSLMap
from yadinassi.search_directions import BSLSearchDirection
from yadinassi.sort_directions import BSLSortDirection as Direction
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, BSLType, NULL


ROOT = Path(__file__).resolve().parents[1]


def list_for(*values, presentations=None):
    result = BSLValueList()
    for index, value in enumerate(values):
        result.add(value, str(index) if presentations is None else presentations[index],
                   index == 0)
    return result


def order(owner, original):
    positions = {id(item): index for index, item in enumerate(original)}
    return [positions[id(item)] for item in owner.items]


class NativeValueListSortTests(unittest.TestCase):
    def test_all_27_native_observations_exactly(self):
        source = (ROOT / "integrational_tests/tests/collections.bsl").read_text(encoding="utf-8-sig")
        outputs = []
        vm = Interpreter(outputs.append)
        vm.execute(source.split("#Область МассивыИСтруктуры", 1)[0])
        observations = source.split("// Начало наблюдений сортировки списка.\n", 1)[1]
        observations = observations.split("// Конец наблюдений сортировки списка.\n", 1)[0]
        vm.execute(observations)
        expected = (ROOT / "tests/fixtures/native_windows/collections.out").read_text(encoding="utf-8")
        start = expected.index("table.list.sort.enum.identity:")
        end = expected.index("table.list.sort.checkpoint.complete: [ok]", start)
        end += len("table.list.sort.checkpoint.complete: [ok]\n")
        self.assertEqual("\n".join(outputs) + "\n", expected[start:end])
        self.assertEqual(len(outputs), 28)
        self.assertEqual(outputs[-1], "table.list.sort.checkpoint.complete: [ok]")

    def assert_orders(self, values, ascending, descending, *, presentation=False):
        for direction, expected in ((None, ascending), (Direction.ASC, ascending),
                                    (Direction.DESC, descending)):
            with self.subTest(direction=direction, presentation=presentation):
                owner = list_for(*values, presentations=values if presentation else None)
                original = list(owner.items)
                method = owner.sort_by_presentation if presentation else owner.sort_by_value
                self.assertIsNone(method(direction))
                self.assertEqual(order(owner, original), expected)

    def test_scalar_and_object_family_orders(self):
        cases = (
            ((D("2.1"), D(-1), D("2.10"), D(0), D(-1)),
             [1, 4, 3, 0, 2], [0, 2, 3, 1, 4]),
            ((True, False, True, False), [1, 3, 0, 2], [0, 2, 1, 3]),
            ((BSLDate(20), BSLDate(10), BSLDate(0), BSLDate(10)),
             [2, 1, 3, 0], [0, 1, 3, 2]),
            (("2", BSLDate(0), D(2), True, None, NULL, False, D(0)),
             [4, 5, 6, 3, 7, 2, 0, 1], [1, 0, 2, 7, 3, 6, 5, 4]),
            ((NULL, None, NULL, None), [1, 3, 0, 2], [0, 2, 1, 3]),
            ((BSLType.STRING, BSLType.NUMBER, BSLType.STRING), [0, 2, 1], [1, 0, 2]),
            ((Direction.DESC, Direction.ASC, Direction.DESC), [1, 0, 2], [0, 2, 1]),
        )
        for values, asc, desc in cases:
            self.assert_orders(values, asc, desc)
        array = BSLArray()
        self.assert_orders((array, BSLStructure(), array, BSLArray()), [0, 2, 3, 1], [1, 0, 2, 3])

    def test_value_and_presentation_use_different_string_relations(self):
        values = "a|A|á|a |a-1|a1|a10|a2|ё|е|Е|Ё".split("|")
        self.assert_orders(values, [0, 1, 3, 2, 4, 5, 6, 7, 9, 10, 8, 11],
                           [8, 11, 9, 10, 7, 6, 5, 4, 2, 0, 1, 3])
        self.assert_orders(values, [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 8, 11],
                           [11, 8, 10, 9, 7, 6, 5, 4, 3, 2, 1, 0], presentation=True)

    def test_native_unicode_and_canonical_ties_in_both_modes(self):
        values = "я|😀|😁|𐀀|\ue000|é|é|ß|SS|İ|i".split("|")
        for presentation in (False, True):
            self.assert_orders(values, [2, 5, 6, 10, 9, 8, 7, 0, 3, 4, 1],
                               [1, 4, 3, 0, 7, 8, 9, 10, 5, 6, 2],
                               presentation=presentation)

    def test_presentation_duplicates_and_blank_do_not_fall_back_to_value(self):
        self.assert_orders(("b", "a", "b", "a"), [1, 3, 0, 2], [0, 2, 1, 3],
                           presentation=True)
        for direction, expected in ((None, [0, 2, 3, 1]), (Direction.DESC, [1, 0, 2, 3])):
            owner = list_for(D(30), D(10), D(20), D(10), presentations=("", "15", "", ""))
            original = list(owner.items)
            owner.sort_by_presentation(direction)
            self.assertEqual(order(owner, original), expected)

    def test_identity_ids_owner_fields_and_id_history_preserved(self):
        for presentation in (False, True):
            owner = list_for(D(30), D(10), D(20), D(10))
            removed = owner.items[1]
            owner.delete(D(1))
            owner.insert(D(0), D(15), "x", True)
            original = list(owner.items)
            ids = [item.get_id() for item in original]
            fields = [(item.value, item.presentation, item.check) for item in original]
            container, by_id, next_id = owner.items, owner._by_id, owner._next_id
            method = owner.sort_by_presentation if presentation else owner.sort_by_value
            method(Direction.DESC)
            method()
            self.assertEqual(order(owner, original), [1, 2, 3, 0] if presentation else [3, 0, 2, 1])
            self.assertIs(owner.items, container)
            self.assertIs(owner._by_id, by_id)
            self.assertEqual(owner._next_id, next_id)
            self.assertEqual(removed.get_id(), D(-1))
            for item, identifier, fields_before in zip(original, ids, fields):
                self.assertIs(item._owner_ref(), owner)
                self.assertEqual(item.get_id(), identifier)
                self.assertIs(owner.find_by_id(identifier), item)
                self.assertIs(owner.items[int(owner.index_of(item))], item)
                self.assertEqual((item.value, item.presentation, item.check), fields_before)
            self.assertEqual(owner.add(D(99)).get_id(), D(next_id))


class ValueListSortBoundaryTests(unittest.TestCase):
    def assert_atomic_rejection(self, owner, method, *args):
        original = list(owner.items)
        container, by_id = owner.items, owner._by_id
        revision, next_id = owner._revision, owner._next_id
        with self.assertRaises((ValueError, TypeError)):
            method(*args)
        self.assertEqual(order(owner, original), list(range(len(original))))
        self.assertIs(owner.items, container)
        self.assertIs(owner._by_id, by_id)
        self.assertEqual((owner._revision, owner._next_id), (revision, next_id))

    def test_direction_is_only_undefined_or_exact_sort_direction(self):
        class Host:
            def __eq__(self, other):
                raise AssertionError("host equality")
            def __str__(self):
                raise AssertionError("host string")
        for invalid in (D(0), D(1), 0, 1, "Asc", True, NULL,
                        BSLSearchDirection.FROM_BEGIN, Host()):
            for empty in (False, True):
                owner = BSLValueList() if empty else list_for(D(2), D(1))
                for method in (owner.sort_by_value, owner.sort_by_presentation):
                    self.assert_atomic_rejection(owner, method, invalid)

    def test_empty_singleton_and_repeat(self):
        for values in ((), (D(7),), (D(2), D(1), D(2))):
            for presentation in (False, True):
                owner = list_for(*values)
                method = owner.sort_by_presentation if presentation else owner.sort_by_value
                method(Direction.DESC)
                method()
                original = list(owner.items)
                method()
                self.assertEqual(owner.items, original)

    def test_unobserved_families_and_types_reject_even_singletons(self):
        unsupported = (BSLMap(), BSLType.ARRAY, BSLType.BOOLEAN, BSLType.SORT_DIRECTION,
                       BSLSearchDirection.FROM_END, BSLValueList())
        for value in unsupported:
            for leading in ((), (D(2), D(1))):
                owner = list_for(*leading, value)
                self.assert_atomic_rejection(owner, owner.sort_by_value)
        for values in ((None, BSLArray()), (BSLArray(), BSLType.STRING),
                       (BSLType.STRING, Direction.ASC), (Direction.ASC, D(0)),
                       (BSLStructure(), NULL)):
            owner = list_for(*values)
            self.assert_atomic_rejection(owner, owner.sort_by_value)

    def test_host_values_and_subclasses_never_invoke_hooks(self):
        class Host:
            def __str__(self):
                raise AssertionError("host string")
            def __eq__(self, other):
                raise AssertionError("host equality")
            def __lt__(self, other):
                raise AssertionError("host ordering")
            def __hash__(self):
                raise AssertionError("host hash")
        class HostString(str, Host):
            pass
        class HostDecimal(D, Host):
            pass
        class HostArray(BSLArray, Host):
            pass
        class HostStructure(BSLStructure, Host):
            pass
        class HostDate(BSLDate, Host):
            pass
        for value in (Host(), HostString("a"), HostDecimal(1), HostArray(),
                      HostStructure(), HostDate(0), 1, 1.0):
            owner = list_for(D(2), D(1), None)
            owner.items[-1].value = value  # Deliberate host API corruption.
            self.assert_atomic_rejection(owner, owner.sort_by_value)
        owner = list_for(D(2), D(1))
        owner.items[-1].presentation = HostString("a")
        self.assert_atomic_rejection(owner, owner.sort_by_presentation)
        class HostItem(BSLValueListItem):
            @property
            def value(self):
                raise AssertionError("host property")
        owner.items[-1] = object.__new__(HostItem)
        self.assert_atomic_rejection(owner, owner.sort_by_value)

    def test_only_empty_objects_are_supported_without_content_traversal(self):
        array, structure = BSLArray(), BSLStructure()
        owner = list_for(array, structure, BSLArray())
        original = list(owner.items)
        with patch.object(BSLArray, "__str__", side_effect=AssertionError("object string")):
            owner.sort_by_value()
        self.assertEqual(order(owner, original), [0, 2, 1])
        array.items = [array, object()]
        owner = list_for(BSLStructure(), array)
        self.assert_atomic_rejection(owner, owner.sort_by_value)
        self.assertIs(array.items[0], array)
        structure = BSLStructure("Value", object())
        owner = list_for(structure)
        self.assert_atomic_rejection(owner, owner.sort_by_value)
        class HostContainer:
            def __bool__(self):
                raise AssertionError("host boolean")
            def __len__(self):
                raise AssertionError("host length")
            def __iter__(self):
                raise AssertionError("host iteration")
        for value in (BSLArray(), BSLStructure()):
            if type(value) is BSLArray:
                value.items = HostContainer()
            else:
                value._items = HostContainer()
            owner = list_for(value)
            self.assert_atomic_rejection(owner, owner.sort_by_value)

    def test_selected_key_only_is_validated(self):
        owner = list_for(BSLMap(), BSLType.ARRAY, presentations=("b", "a"))
        original = list(owner.items)
        owner.sort_by_presentation()
        self.assertEqual(order(owner, original), [1, 0])
        owner = list_for(D(2), D(1), presentations=("中", "😂"))
        owner.sort_by_value()
        self.assertEqual([item.value for item in owner.items], [D(1), D(2)])

    def test_unicode_and_numeric_local_boundaries_are_atomic(self):
        unsupported = ("中", "!", "a\t", "a\n", "😂", "a😀", "😁a", "\ue000x",
                       "éx", "é ", "éx", "ßa", "İx", "\ud800", "x" * 4097)
        for value in unsupported:
            for presentation in (False, True):
                owner = list_for("b", "a", value, presentations=("b", "a", value))
                method = owner.sort_by_presentation if presentation else owner.sort_by_value
                self.assert_atomic_rejection(owner, method)
        for value in (D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"),
                      D("1e5000"), D("1e-5000"), D("0e5000"), D("9" * 4097),
                      BSLDate(0, True)):
            owner = list_for(D(2), D(1), None)
            owner.items[-1].value = value
            self.assert_atomic_rejection(owner, owner.sort_by_value)

    def test_all_resource_limits_are_checked_before_commit(self):
        for presentation in (False, True):
            for constant, limit in (("_MAX_SORT_ITEMS", 1), ("_MAX_SORT_TEXT", 3),
                                    ("_MAX_KEY_WEIGHTS", 1)):
                owner = list_for("bb", "aa", presentations=("bb", "aa"))
                method = owner.sort_by_presentation if presentation else owner.sort_by_value
                with patch.object(value_list_sort, constant, limit):
                    self.assert_atomic_rejection(owner, method)
            owner = list_for("áá", "aa", presentations=("áá", "aa"))
            method = owner.sort_by_presentation if presentation else owner.sort_by_value
            with patch.object(value_list_sort.collation, "MAX_NORMALIZED_LENGTH", 3):
                self.assert_atomic_rejection(owner, method)

    def test_pinned_collation_failure_is_atomic(self):
        for presentation in (False, True):
            owner = list_for("b", "a", presentations=("b", "a"))
            method = owner.sort_by_presentation if presentation else owner.sort_by_value
            with patch.object(value_list_sort.collation, "_collator",
                              side_effect=ValueError("missing/corrupt pinned table")):
                self.assert_atomic_rejection(owner, method)

    def test_string_length_budget_includes_spaces_before_trimming(self):
        owner = list_for("a" + " " * 4095, "A")
        original = list(owner.items)
        owner.sort_by_value(Direction.DESC)
        self.assertEqual(owner.items, original)
        owner.items[0].value += " "
        self.assert_atomic_rejection(owner, owner.sort_by_value)

    def test_numeric_keys_do_not_round_or_depend_on_host_decimal_context(self):
        values = (D("1.000000000000000000000000000001"), D("-0"), D("0"),
                  D("1.000000000000000000000000000000"))
        owner = list_for(*values)
        original = list(owner.items)
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = context.traps[Rounded] = True
            owner.sort_by_value()
        self.assertEqual(order(owner, original), [1, 2, 3, 0])
        for item, value in zip(original, values):
            self.assertIs(item.value, value)

    def test_local_iteration_guard_after_sort_and_survives_failed_sort(self):
        owner = list_for(D(2), D(1))
        iterator = iter(owner)
        next(iterator)
        self.assert_atomic_rejection(owner, owner.sort_by_value, D(0))
        self.assertIs(next(iterator), owner.items[1])
        iterator = iter(owner)
        owner.sort_by_value()
        with self.assertRaisesRegex(ValueError, "активного обхода"):
            next(iterator)

    def test_total_order_and_stability_for_reordered_inputs(self):
        values = ["a", "A", "a ", "á", "a1", "a10", "a2", "е", "Е", "ё", "Ё",
                  "é", "é", "SS", "ß", "İ", "i", "😁", "😀"]
        for presentation in (False, True):
            keys = [value_list_sort._string_key(value, [0, 0], by_presentation=presentation)
                    for value in values]
            for a in keys:
                for b in keys:
                    self.assertEqual(int(a < b) + int(a == b) + int(a > b), 1)
                    for c in keys:
                        if a <= b and b <= c:
                            self.assertLessEqual(a, c)
            for indices in (list(range(len(values))), list(reversed(range(len(values)))),
                            list(range(0, len(values), 2)) + list(range(1, len(values), 2))):
                for direction in (Direction.ASC, Direction.DESC):
                    ordered_values = [values[i] for i in indices]
                    owner = list_for(*ordered_values, presentations=ordered_values)
                    original = list(owner.items)
                    method = owner.sort_by_presentation if presentation else owner.sort_by_value
                    method(direction)
                    expected = sorted(range(len(indices)), key=lambda i: keys[indices[i]],
                                      reverse=direction is Direction.DESC)
                    self.assertEqual(order(owner, original), expected)


class ValueListSortRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('values = New ValueList; first = values.Add(2, "b"); '
                        'second = values.Add(1, "a");')

    def test_bilingual_case_insensitive_procedures(self):
        self.vm.execute("values.СОРТИРОВАТЬПОЗНАЧЕНИЮ();")
        self.assertTrue(self.vm.execute("(values.Get(0) = second)"))
        self.vm.execute("values.sOrTbYvAlUe(SortDirection.Desc);")
        self.assertTrue(self.vm.execute("(values.Get(0) = first)"))
        self.vm.execute("values.СортироватьПоПредставлению(Неопределено);")
        self.assertTrue(self.vm.execute("(values.Get(0) = second)"))
        self.vm.execute("values.SORTBYPRESENTATION(НаправлениеСортировки.Убыв);")
        self.assertTrue(self.vm.execute("(values.Get(0) = first)"))

    def test_arity_and_procedure_expressions_reject_without_mutation(self):
        self.vm.execute("Var touches; touches = 0; "
                        "Function Touch() touches = touches + 1; Return SortDirection.Desc; EndFunction")
        for method in ("SortByValue", "SortByPresentation", "СортироватьПоЗначению",
                       "СортироватьПоПредставлению"):
            for code in (f"values.{method}(SortDirection.Asc, 1);",
                         f"answer = values.{method}();",
                         f"answer = values.{method}(Touch());"):
                with self.assertRaises(BSLError):
                    self.vm.execute(code)
                self.assertTrue(self.vm.execute("(values.Get(0) = first)"))
                self.assertEqual(self.vm.execute("touches"), D(0))

    def test_unsupported_value_and_invalid_direction_are_catchable(self):
        self.vm.execute("caught = False; Try values.SortByValue(0); Except caught = True; EndTry;")
        self.assertTrue(self.vm.execute("caught"))
        self.assertTrue(self.vm.execute("(values.Get(0) = first)"))
        self.vm.execute('values.Add(New Map); caught = False; '
                        'Try values.SortByValue(); Except caught = True; EndTry;')
        self.assertTrue(self.vm.execute("caught"))
        self.assertTrue(self.vm.execute("(values.Get(0) = first)"))


if __name__ == "__main__":
    unittest.main()
