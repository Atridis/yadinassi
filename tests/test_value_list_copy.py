"""Copy history expectations from genuine owner commit 06012006.

These tests read native output, never generate it. Resource rejection tests
describe interpreter safety boundaries, not native 1C resource limits.
"""

from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, value_lists
from yadinassi.sort_directions import BSLSortDirection as Direction
from yadinassi.value_lists import BSLValueList
from yadinassi.values import BSLArray


ROOT = Path(__file__).resolve().parents[1]


def base():
    result = BSLValueList()
    result.add(D(30), "b", True)
    result.add(D(10), "c", False)
    result.add(D(20), "a", True)
    return result


def deleted_reordered():
    result = base()
    result.add(D(40), "d", False)
    result.delete(D(3))
    result.delete(D(1))
    result.move(D(1), D(-1))
    return result


def fields(owner):
    return [(item.value, item.presentation, item.check) for item in owner]


class ValueListCopyTests(unittest.TestCase):
    def test_all_ten_native_observations_exactly(self):
        source = (ROOT / "integrational_tests/tests/collections.bsl").read_text(encoding="utf-8-sig")
        output = []
        vm = Interpreter(output.append)
        vm.execute(source.split("#Область МассивыИСтруктуры", 1)[0])
        body = source.split("// Начало наблюдений копирования списка.\n", 1)[1]
        vm.execute(body.split("// Конец наблюдений копирования списка.\n", 1)[0])
        expected = (ROOT / "tests/fixtures/native_windows/collections.out").read_text(encoding="utf-8")
        start = expected.index("table.list.copy.fresh-empty:")
        marker = "table.list.copy.checkpoint.complete: [ok]\n"
        end = expected.index(marker, start) + len(marker)
        self.assertEqual("\n".join(output) + "\n", expected[start:end])
        self.assertEqual(len(output), 11)
        self.assertEqual(output[-1], "table.list.copy.checkpoint.complete: [ok]")

    def assert_copy(self, source, source_ids, source_next):
        originals = list(source)
        before = fields(source)
        self.assertEqual([item.get_id() for item in originals], source_ids)
        other = source.copy()
        copied = list(other)
        self.assertIsNot(other, source)
        self.assertEqual(list(source), originals)
        self.assertEqual(fields(source), before)
        self.assertEqual(fields(other), before)
        self.assertEqual([item.get_id() for item in source], source_ids)
        self.assertEqual([item.get_id() for item in other], list(range(len(originals))))
        for item in copied:
            self.assertTrue(all(item is not original for original in originals))
        for owner in (source, other):
            for item in owner:
                self.assertIs(owner.find_by_id(item.get_id()), item)
            for identifier in range(6):
                expected = next((item for item in owner if item.get_id() == identifier), None)
                self.assertIs(owner.find_by_id(D(identifier)), expected)
        self.assertEqual(source.add(D(50), "source-next").get_id(), source_next)
        self.assertEqual(len(other.items), len(originals))
        self.assertEqual(other.add(D(60), "copy-next").get_id(), len(originals))
        self.assertEqual(len(source.items), len(originals) + 1)
        return other

    def test_fresh_controls(self):
        self.assert_copy(BSLValueList(), [], 0)
        self.assert_copy(base(), [0, 1, 2], 3)

    def test_both_sorts_and_directions_preserve_current_field_order(self):
        for method, direction, ids in (
                ("sort_by_value", None, [1, 2, 0]),
                ("sort_by_value", Direction.DESC, [0, 2, 1]),
                ("sort_by_presentation", None, [2, 0, 1]),
                ("sort_by_presentation", Direction.DESC, [1, 0, 2])):
            with self.subTest(method=method, direction=direction):
                source = base()
                getattr(source, method)(direction)
                self.assert_copy(source, ids, 3)

    def test_deleted_reordered_ids_and_high_water_are_not_inherited(self):
        self.assert_copy(deleted_reordered(), [2, 0], 4)

    def test_cleared_empty_and_refilled_sources_keep_their_own_history(self):
        source = base()
        source.clear()
        self.assert_copy(source, [], 3)
        source = base()
        source.clear()
        source.add(D(20), "b", False)
        source.add(D(10), "a", True)
        self.assert_copy(source, [3, 4], 5)

    def test_historical_nested_value_is_shared_but_item_fields_are_independent(self):
        nested = BSLArray()
        nested.add(D(1))
        source = BSLValueList()
        source.add(D(10), "z", False)
        saved = source.add(nested, "b", True)
        source.add(D(20), "a", False)
        source.delete(D(0))
        source.sort_by_presentation()
        other = self.assert_copy(source, [2, 1], 3)
        copied = other.get(D(1))
        self.assertIsNot(copied, saved)
        self.assertIs(copied.value, nested)
        copied.value.add(D(2))
        self.assertEqual(saved.value.items, [D(1), D(2)])
        copied.set_member("Value", D(77))
        copied.set_member("Presentation", "copy")
        copied.set_member("Check", False)
        self.assertEqual((saved.value, saved.presentation, saved.check), (nested, "b", True))
        self.assertEqual(fields(other)[1], (D(77), "copy", False))

    def test_bilingual_dispatch_keeps_distinct_owners_and_live_lookups(self):
        for method in ("Copy", "Скопировать"):
            with self.subTest(method=method):
                vm = Interpreter()
                vm.execute('source = New ValueList; source.Add(30, "b", True); '
                           'source.Add(10, "c"); source.Add(20, "a", True); '
                           'source.Add(40, "d"); source.Delete(3); source.Delete(1); '
                           'source.Move(1, -1); '
                           f'copied = source.{method}();')
                for owner, ids in (("source", [2, 0]), ("copied", [0, 1])):
                    for position, identifier in enumerate(ids):
                        self.assertEqual(vm.execute(f'{owner}[{position}].GetID()'), D(identifier))
                        self.assertTrue(vm.execute(
                            f'({owner}.НайтиПоИдентификатору({identifier}) = {owner}[{position}])'))
                self.assertFalse(vm.execute('(source[0] = copied[0])'))
                self.assertEqual(vm.execute('source.Add(50).GetID()'), D(4))
                self.assertEqual(vm.execute('copied.Добавить(60).ПолучитьИдентификатор()'), D(2))

    def test_local_copy_budgets_reject_without_source_mutation(self):
        source = deleted_reordered()
        originals, before = list(source), fields(source)
        lookup, next_id, revision = dict(source._by_id), source._next_id, source._revision
        for limit in ("_MAX_ITEMS", "_MAX_ID"):
            with self.subTest(limit=limit), patch.object(value_lists, limit, 1):
                message = "предел ресурсов" if limit == "_MAX_ITEMS" else "идентификаторов"
                with self.assertRaisesRegex(ValueError, message):
                    source.copy()
            self.assertEqual(list(source), originals)
            self.assertEqual(fields(source), before)
            self.assertEqual(source._by_id, lookup)
            self.assertEqual((source._next_id, source._revision), (next_id, revision))

    def test_source_id_budget_does_not_block_fresh_copy_allocation(self):
        source = deleted_reordered()
        with patch.object(value_lists, "_MAX_ID", 4):
            with self.assertRaisesRegex(ValueError, "идентификаторов"):
                source.add(D(50))
            other = source.copy()
            self.assertEqual([item.get_id() for item in other], [0, 1])
            self.assertEqual(other.add(D(60)).get_id(), D(2))
        self.assertEqual(source.add(D(50)).get_id(), D(4))


if __name__ == "__main__":
    unittest.main()
