"""Default-state ValueList core backed by owner f41b3c9 observations.

These are unit expectations, not generated or replacement native output.
Explicit unsupported/resource guards are Yadinassi boundaries, not 1C claims.
"""

from decimal import Decimal, localcontext
import gc
import unittest
from unittest.mock import patch

from yadinassi import value_lists
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, NULL, equal


D = Decimal


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


def base():
    result = BSLValueList()
    result.add(D(10), "first", True)
    result.add(D(20), "second", False)
    return result


def fields(value):
    return [(item.value, item.presentation, item.check) for item in value]


class ValueListTests(unittest.TestCase):
    def test_empty_default_properties_and_types(self):
        values = BSLValueList()
        self.assertEqual(values.count(), D(0))
        self.assertEqual(list(values), [])
        self.assertEqual(str(values), "")
        description = values.get_member("ValueType")
        self.assertIs(type(description), BSLTypeDescription)
        self.assertEqual(description.types, ())
        self.assertIsNone(values.get_member("ДоступныеЗначения"))
        self.assertIs(type_of(values), BSLType.VALUE_LIST)
        for english, russian, presentation, kind in (
                ("ValueList", "СписокЗначений", "Список значений", BSLType.VALUE_LIST),
                ("ValueListItem", "ЭлементСпискаЗначений", "Элемент списка значений",
                 BSLType.VALUE_LIST_ITEM)):
            self.assertIs(type_by_name(english.upper()), kind)
            self.assertIs(type_by_name(russian.lower()), kind)
            self.assertEqual(str(kind), presentation)
            with self.assertRaises(ValueError):
                type_by_name(presentation)

    def test_get_index_and_iteration_preserve_item_identity(self):
        values = base()
        first = values.get(D(0))
        self.assertIs(values.get_index(D(0)), first)
        self.assertIs(next(iter(values)), first)
        self.assertIs(type_of(first), BSLType.VALUE_LIST_ITEM)
        self.assertTrue(equal(first, first))
        self.assertFalse(equal(first, base().get(D(0))))
        self.assertEqual(str(first), "first")
        self.assertEqual(str(values), "first; second")

    def test_add_defaults_and_optional_metadata(self):
        values = BSLValueList()
        values.add()
        values.add(None)
        values.add(D(10))
        values.add("Я😀", "строка", True)
        self.assertEqual(fields(values), [
            (None, "", False), (None, "", False), (D(10), "", False),
            ("Я😀", "строка", True),
        ])

    def test_add_metadata_conversions_and_atomic_failure(self):
        for presentation, check, expected in (
                (D(7), False, ("7", False)),
                (None, False, ("", False)),
                ("x", D(1), ("x", True))):
            values = base()
            values.add(D(30), presentation, check)
            self.assertEqual(fields(values)[-1], (D(30), *expected))
        values = base()
        before = fields(values)
        with self.assertRaises(ValueError):
            values.add(D(30), "x", "bad")
        self.assertEqual(fields(values), before)
        self.assertEqual(values.add(D(40)).get_id(), D(2))

    def test_insert_boundaries_and_observed_conversions(self):
        for selector, expected in (
                (D(0), [30, 10, 20]), (D(2), [10, 20, 30]),
                (D("0.9"), [30, 10, 20]), ("1", [10, 30, 20]),
                (True, [10, 30, 20])):
            values = base()
            inserted = values.insert(selector, D(30))
            self.assertEqual([item.value for item in values], [D(x) for x in expected])
            self.assertEqual(inserted.get_id(), D(2))
        for selector in (D(-1), D(3), None):
            values = base()
            with self.assertRaises((TypeError, ValueError, IndexError)):
                values.insert(selector, D(30))
            self.assertEqual([item.value for item in values], [D(10), D(20)])
            self.assertEqual(values.add(D(40)).get_id(), D(2))

    def test_get_conversions_and_bounds(self):
        values = base()
        self.assertIs(values.get(D("0.9")), values.items[0])
        self.assertIs(values.get("1"), values.items[1])
        for selector in (D(-1), D(2), None):
            with self.assertRaises((TypeError, ValueError, IndexError)):
                values.get(selector)
        for selector in (D(-1), D(2)):
            with self.assertRaises(IndexError):
                values.get_index(selector)
        for selector in ("1", True, D("0.9")):
            with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
                values.get_index(selector)

    def test_collection_slots_are_read_only(self):
        values = base()
        before = fields(values)
        for replacement in (D(7), base().get(D(0))):
            with self.assertRaises(ValueError):
                values.set_index(D(0), replacement)
        self.assertEqual(fields(values), before)

    def test_bilingual_item_properties(self):
        values = base()
        item = values.get(D(0))
        item.set_member("ЗнАчЕнИе", "new")
        item.set_member("Представление", "имя")
        item.set_member("Пометка", False)
        self.assertEqual([item.get_member(key) for key in
                          ("Value", "Presentation", "Check")], ["new", "имя", False])
        self.assertEqual(fields(values)[0], ("new", "имя", False))

    def test_presentation_and_check_conversion_boundaries(self):
        values = base()
        item = values.get(D(0))
        for candidate, expected in ((D(7), "7"), (None, ""), ("", "")):
            item.set_member("Presentation", candidate)
            self.assertEqual(item.presentation, expected)
        for candidate, expected in ((D(1), True), (D(0), False)):
            item.set_member("Check", candidate)
            self.assertIs(item.check, expected)
        for candidate in ("bad", None):
            with self.assertRaises(ValueError):
                item.set_member("Check", candidate)
            self.assertIs(item.check, False)

    def test_fill_checks_validates_before_mutation(self):
        values = base()
        for candidate, expected in ((True, True), (False, False), (D(1), True)):
            values.fill_checks(candidate)
            self.assertEqual([item.check for item in values], [expected, expected])
        values = base()
        before = fields(values)
        for candidate in ("bad", None):
            with self.assertRaises(ValueError):
                values.fill_checks(candidate)
            self.assertEqual(fields(values), before)

    def test_find_is_typed_case_sensitive_and_reference_based(self):
        nested = array()
        inputs = [D(1), "1", True, False, None, NULL, "Alpha", "alpha", nested]
        values = BSLValueList()
        for value in inputs:
            values.add(value)
        values.add(D(1), "duplicate")
        for index, value in enumerate(inputs):
            self.assertIs(values.find_by_value(value), values.items[index])
        self.assertIsNone(values.find_by_value(array()))
        self.assertIsNone(values.find_by_value(D(999)))
        self.assertIsNot(values.find_by_value(D(1)), values.find_by_value(True))

    def test_index_of_rejects_nonitems_and_handles_foreign(self):
        values = base()
        first = values.get(D(0))
        self.assertEqual(values.index_of(first), D(0))
        foreign_owner = base()
        self.assertEqual(values.index_of(foreign_owner.get(D(0))), D(-1))
        for candidate in (D(0), None):
            with self.assertRaises(TypeError):
                values.index_of(candidate)

    def test_delete_index_conversions_and_atomic_failures(self):
        for selector, remaining in ((D(1), D(10)), (D("0.9"), D(20)), ("1", D(10))):
            values = base()
            values.delete(selector)
            self.assertEqual([item.value for item in values], [remaining])
        for selector in (D(-1), D(2), None):
            values = base()
            with self.assertRaises((TypeError, ValueError, IndexError)):
                values.delete(selector)
            self.assertEqual([item.value for item in values], [D(10), D(20)])

    def test_delete_foreign_or_already_deleted_item(self):
        values = base()
        saved = values.get(D(0))
        foreign_owner = base()
        with self.assertRaises(ValueError):
            values.delete(foreign_owner.get(D(0)))
        values.delete(saved)
        self.assertEqual([item.value for item in values], [D(20)])
        with self.assertRaises(ValueError):
            values.delete(saved)
        self.assertEqual([item.value for item in values], [D(20)])

    def test_move_index_item_and_observed_conversions(self):
        for selector, offset, expected in (
                (D(0), D(1), [20, 10]), (D(1), D(-1), [20, 10]),
                (D("0.9"), D(1), [20, 10]), (D(0), D("0.9"), [10, 20]),
                ("0", D(1), [20, 10]), (D(0), "1", [20, 10])):
            values = base()
            values.move(selector, offset)
            self.assertEqual([item.value for item in values], [D(x) for x in expected])
        values = base()
        saved = values.get(D(0))
        values.move(saved, D(1))
        self.assertIs(values.get(D(1)), saved)

    def test_move_outside_list_is_atomic(self):
        for selector, offset in ((D(0), D(-1)), (D(1), D(1)),
                                 (D(0), D(3)), (D(1), D(-3)), (None, D(1))):
            values = base()
            before = fields(values)
            with self.assertRaises((TypeError, ValueError, IndexError)):
                values.move(selector, offset)
            self.assertEqual(fields(values), before)

    def test_foreign_move_with_two_items_moves_first_without_changing_foreign(self):
        values, foreign_owner = base(), base()
        original = list(values)
        foreign_before = fields(foreign_owner)
        self.assertEqual(values.get(D(0)).get_id(), foreign_owner.get(D(0)).get_id())
        values.move(foreign_owner.get(D(0)), D(1))
        self.assertEqual(list(values), [original[1], original[0]])
        self.assertEqual(fields(foreign_owner), foreign_before)
        self.assertEqual([item.get_id() for item in values], [D(1), D(0)])

    def test_four_foreign_move_controls_match_owner_supplement(self):
        for case in ("different-value", "reordered", "missing-id", "deleted"):
            with self.subTest(case=case):
                values = base()
                values.add(D(30), "third")
                original = list(values)
                foreign_owner = BSLValueList()
                foreign_owner.add(D(100), "foreign-first")
                foreign = foreign_owner.add(D(200), "foreign-second")
                foreign_owner.add(D(300), "foreign-third")
                if case == "reordered":
                    foreign_owner.move(foreign, D(-1))
                elif case == "missing-id":
                    foreign = foreign_owner.add(D(400), "foreign-fourth")
                    foreign_owner.move(foreign, D(-3))
                elif case == "deleted":
                    foreign_owner.delete(foreign)
                expected_id, expected_index = {
                    "different-value": (1, 1), "reordered": (1, 0),
                    "missing-id": (3, 0), "deleted": (-1, -1),
                }[case]
                self.assertEqual(foreign.get_id(), D(expected_id))
                self.assertEqual(foreign_owner.index_of(foreign), D(expected_index))
                foreign_before = fields(foreign_owner)
                values.move(foreign, D(1))
                self.assertEqual(list(values), [original[1], original[0], original[2]])
                self.assertEqual(fields(values), [(D(20), "second", False),
                                                 (D(10), "first", True),
                                                 (D(30), "third", False)])
                self.assertEqual(fields(foreign_owner), foreign_before)
                self.assertEqual(foreign.get_id(), D(expected_id))
                self.assertEqual(foreign_owner.index_of(foreign), D(expected_index))

    def test_foreign_move_unobserved_offsets_and_target_sizes_are_atomic_guards(self):
        foreign_owner = base()
        foreign = foreign_owner.get(D(0))
        foreign_before = fields(foreign_owner)
        for offset in (D(-1), D(0), D(2), D("0.9"), D("1.9"), "1", True, None,
                       D("NaN"), D("sNaN"), D("Infinity")):
            values = base()
            before = fields(values)
            with self.assertRaisesRegex(ValueError, "сдвиг чужого элемента.*пока не поддерживается"):
                values.move(foreign, offset)
            self.assertEqual(fields(values), before)
            self.assertEqual(fields(foreign_owner), foreign_before)
        for count in (0, 1, 4):
            values = BSLValueList()
            for index in range(count):
                values.add(D(index))
            before = fields(values)
            with self.assertRaisesRegex(ValueError, "сдвиг чужого элемента.*пока не поддерживается"):
                values.move(foreign, D(1))
            self.assertEqual(fields(values), before)
            self.assertEqual(fields(foreign_owner), foreign_before)
        del foreign_owner
        gc.collect()
        values = base()
        before = fields(values)
        with self.assertRaisesRegex(ValueError, "сдвиг чужого элемента.*пока не поддерживается"):
            values.move(foreign, D(1))
        self.assertEqual(fields(values), before)

    def test_deleted_own_item_is_not_treated_as_foreign(self):
        values = base()
        saved = values.get(D(0))
        values.delete(saved)
        values.add(D(30))  # Two-item target still must reject its own deleted item.
        before = fields(values)
        with self.assertRaises(ValueError):
            values.move(saved, D(1))
        self.assertEqual(fields(values), before)

    def test_ids_stay_stable_through_insert_and_move(self):
        values = base()
        saved = values.get(D(0))
        self.assertEqual(saved.get_id(), D(0))
        values.insert(D(0), D(30))
        values.move(saved, D(1))
        self.assertEqual(saved.get_id(), D(0))
        self.assertIs(values.find_by_id(D(0)), saved)
        self.assertEqual(values.index_of(saved), D(2))
        self.assertEqual(values.add(D(40)).get_id(), D(3))

    def test_find_by_id_handles_missing_and_observed_conversions(self):
        values, foreign_owner = base(), base()
        first = values.get(D(0))
        self.assertIs(values.find_by_id(foreign_owner.get(D(0)).get_id()), first)
        for selector in (D("0.9"), "0"):
            self.assertIs(values.find_by_id(selector), first)
        for selector in (D(999), D(-1)):
            self.assertIsNone(values.find_by_id(selector))

    def test_deleted_and_cleared_items_remain_writable_with_invalid_id(self):
        for clear in (False, True):
            values = base()
            saved = values.get(D(0))
            if clear:
                values.clear()
                values.clear()
            else:
                values.delete(saved)
            self.assertEqual(saved.get_id(), D(-1))
            self.assertIsNone(values.find_by_id(D(0)))
            self.assertEqual(values.index_of(saved), D(-1))
            self.assertEqual((saved.value, saved.presentation, saved.check), (D(10), "first", True))
            saved.set_member("Value", D(99))
            saved.set_member("Presentation", "detached")
            saved.set_member("Check", False)
            self.assertEqual((saved.value, saved.presentation, saved.check),
                             (D(99), "detached", False))
            self.assertEqual(values.add(D(40)).get_id(), D(2))

    def test_discarded_owner_get_id_is_explicitly_unobserved(self):
        values = base()
        saved = values.get(D(0))
        del values
        gc.collect()
        with self.assertRaisesRegex(ValueError, "после освобождения списка"):
            saved.get_id()
        self.assertEqual((saved.value, saved.presentation, saved.check), (D(10), "first", True))
        saved.set_member("Value", D(99))
        self.assertEqual(saved.value, D(99))
        values = base()
        saved = values.get(D(0))
        values.delete(saved)
        del values
        gc.collect()
        self.assertEqual(saved.get_id(), D(-1))

    def test_standalone_reader_hook_preserves_wire_fields_without_assuming_get_id(self):
        nested = array(D(1))
        for identifier in (-1, 0, 7):
            item = BSLValueListItem._from_stream(identifier, nested, "decoded", True)
            self.assertEqual(item._id, identifier)
            self.assertTrue(item._decoded_standalone)
            self.assertFalse(item._detached)
            self.assertIsNone(item._owner_ref())
            self.assertIs(item.value, nested)
            self.assertEqual(item.presentation, "decoded")
            self.assertIs(item.check, True)
            self.assertIs(type_of(item), BSLType.VALUE_LIST_ITEM)
            with self.assertRaisesRegex(ValueError, "отдельно восстановленного элемента"):
                item.get_id()
        values = base()
        self.assertFalse(values.get(D(0))._decoded_standalone)
        self.assertEqual(values.get(D(0)).get_id(), D(0))

    def test_negative_fraction_and_fractional_text_conversions_are_bounded(self):
        values = base()
        before = fields(values)
        for selector in (D("-0.9"), "-0.9", "0.9"):
            for action in (lambda: values.get(selector), lambda: values.insert(selector, D(30)),
                           lambda: values.delete(selector), lambda: values.move(selector, D(1)),
                           lambda: values.move(D(0), selector), lambda: values.find_by_id(selector)):
                with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
                    action()
                self.assertEqual(fields(values), before)

    def test_copy_has_independent_items_and_shared_nested_values(self):
        nested = array(D(1))
        values = BSLValueList()
        first = values.add(nested, "nested", True)
        values.add(D(20), "second", False)
        other = values.copy()
        copied = other.get(D(0))
        self.assertIsNot(values, other)
        self.assertIsNot(first, copied)
        self.assertIs(first.value, copied.value)
        self.assertEqual(copied.get_id(), D(0))
        copied.set_member("Presentation", "copy")
        copied.value.add(D(2))
        other.delete(D(1))
        self.assertEqual(fields(values), [(nested, "nested", True), (D(20), "second", False)])
        self.assertEqual(nested.items, [D(1), D(2)])
        self.assertEqual(other.count(), D(1))

    def test_load_replaces_items_defaults_metadata_and_preserves_id_history(self):
        nested = array(D(1))
        values = BSLValueList()
        old = values.add(nested, "nested", True)
        values.add(D(20), "second")
        source = array(nested, None)
        values.load_values(source)
        loaded = values.get(D(0))
        self.assertIsNot(loaded, old)
        self.assertIs(loaded.value, nested)
        self.assertEqual(loaded.get_id(), D(2))
        self.assertEqual(old.get_id(), D(-1))
        self.assertEqual((old.value, old.presentation, old.check), (nested, "nested", True))
        nested.add(D(2))
        source.add(D(30))
        self.assertEqual(fields(values), [(nested, "", False), (None, "", False)])
        self.assertEqual(values.add(D(40)).get_id(), D(4))

    def test_invalid_load_is_atomic_and_empty_load_detaches(self):
        values = base()
        before = fields(values)
        saved = values.get(D(0))
        for source in (None, "bad", BSLFixedArray(array()), array(object())):
            with self.assertRaises((TypeError, ValueError)):
                values.load_values(source)
            self.assertEqual(fields(values), before)
            self.assertEqual(saved.get_id(), D(0))
        values.load_values(array())
        self.assertEqual(values.count(), D(0))
        self.assertEqual(saved.get_id(), D(-1))
        self.assertEqual(values.add(D(40)).get_id(), D(2))

    def test_unload_has_independent_outer_and_shared_nested_values(self):
        values = BSLValueList()
        nested = array(D(1))
        values.add(nested, "nested", True)
        values.add(D(20), "second")
        other = values.unload_values()
        self.assertIs(type(other), BSLArray)
        self.assertIs(other.items[0], nested)
        other.add(D(30))
        other.items[0].add(D(2))
        self.assertEqual(values.count(), D(2))
        self.assertEqual(nested.items, [D(1), D(2)])
        self.assertEqual(other.items, [nested, D(20), D(30)])

    def test_unobserved_object_presentations_are_guarded(self):
        values = BSLValueList()
        item = values.add(BSLArray())
        for value in (item, values):
            with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
                str(value)

    def test_scalar_item_and_list_fallbacks_are_supported(self):
        values = BSLValueList()
        item = values.add(D(10))
        self.assertEqual(str(item), "10")
        self.assertEqual(str(values), "10")

    def test_active_iteration_rejects_unobserved_structural_changes(self):
        values = base()
        iterator = iter(values)
        self.assertIs(next(iterator), values.items[0])
        values.add(D(30))
        with self.assertRaisesRegex(ValueError, "активного обхода"):
            next(iterator)
        self.assertEqual(len(list(values)), 3)
        iterator = iter(values)
        values.clear()
        with self.assertRaises(ValueError):
            next(iterator)

    def test_limits_fail_before_mutation_or_id_consumption(self):
        values = base()
        before = fields(values)
        with patch.object(value_lists, "_MAX_ITEMS", 2):
            with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                values.add(D(30))
            with self.assertRaises(ValueError):
                values.load_values(array(D(1), D(2), D(3)))
        self.assertEqual(fields(values), before)
        self.assertEqual(values.add(D(40)).get_id(), D(2))
        with patch.object(value_lists, "_MAX_ID", 3):
            with self.assertRaisesRegex(ValueError, "идентификаторов"):
                values.add(D(50))

    def test_text_and_numeric_budgets_are_bounded_and_context_independent(self):
        values = base()
        before = fields(values)
        with patch.object(value_lists, "_MAX_TEXT", 4):
            for value, presentation in (("longer", ""), (None, "longer")):
                with self.assertRaises(ValueError):
                    values.add(value, presentation)
            with self.assertRaises(ValueError):
                str(values)
        for selector in (D("1e1000000"), D("NaN"), D("Infinity"), "1" * 5000):
            with self.assertRaises(ValueError):
                values.get(selector)
        self.assertEqual(fields(values), before)
        with localcontext() as context:
            context.prec = 1
            for signal in context.traps:
                context.traps[signal] = True
            self.assertIs(values.get(D("0.999999999999999999999")), values.items[0])
            self.assertIs(values.get("1"), values.items[1])

    def test_host_hooks_and_unexposed_properties_are_not_called(self):
        class Hostile:
            def __str__(self):
                raise AssertionError("host string called")

            def __eq__(self, other):
                raise AssertionError("host equality called")

            def __int__(self):
                raise AssertionError("host integer called")

        values = base()
        hostile = Hostile()
        for call in (lambda: values.add(hostile), lambda: values.add(None, hostile),
                     lambda: values.find_by_value(hostile), lambda: values.get(hostile),
                     lambda: values.fill_checks(hostile)):
            with self.assertRaises((TypeError, ValueError)):
                call()
        for name in ("items", "_by_id", "__dict__", "Picture", "SortByValue", "ChooseItem"):
            with self.assertRaises(ValueError):
                values.get_member(name)
        for name in ("ValueType", "AvailableValues"):
            with self.assertRaises(ValueError):
                values.set_member(name, None)
        for name in ("_id", "_owner_ref", "Picture", "__dict__"):
            with self.assertRaises(ValueError):
                values.items[0].get_member(name)


if __name__ == "__main__":
    unittest.main()
