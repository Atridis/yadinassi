"""Item/list string and lazy-cache observations from owner 87723a25/4a3f55f8.

The final five cases were measured on Linux 8.3.27.1508, not Windows
8.3.27.2342. Applying their cache mechanism to the shared runtime is an
inference; the earlier Windows observations remain independently replayed.

Native records are read, never generated or replaced. Resource and host-boundary
tests describe Yadinassi limits, not additional native 1C observations.
"""
from scripts.native_historical_replay import without_field_reference_probes, without_descriptor_map_probes

from decimal import Decimal as D
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.native_observations import extract_payload, read_observation
from yadinassi import Interpreter, serialization, value_lists
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, NULL, to_string


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrational_tests/tests/collections.bsl"
OUTPUT = ROOT / "tests/fixtures/native_windows/collections.out"

# Genuine Docker evidence, not expectations synthesized from this interpreter.
# https://github.com/Atridis/yadinassi/actions/runs/39591770740
# Synthetic merge 5f2add07d8fe47b1ad75eb56cb493d3a8f9cce39, tree
# 2429435d2fdc3ccc0082882a4d3359e6092abe54, PR head
# 49243b22b54c53a15f8bc7be0b80dc6ef3dc0a57.
# Complete collections.out SHA256:
# e0b9443ec4dddbe1e91956232435a02f4cd8d3ec69b3593e479eae1848d357bb
FINAL_LINUX_SOURCE_SHA256 = (
    "908ccf338cff45f07182fbfa376e2d5045d3ed9248b0f216f6ac09cb97faf0e6")


def final_linux_observations():
    """Literal fields/texts from the five recorded cases, with repeated shapes."""
    def snapshot(value, presentation, *, separated=False):
        rows = [[value, presentation, False, D(0)]]
        if separated:
            rows.append(["", "", False, D(1)])
        return {"Count": D(len(rows)), "Items": rows}

    empty = {}
    for name, text in (("Value", ""), ("Cleared", ""), ("Separated", "; ")):
        separated = name == "Separated"
        empty[name] = {
            "Prepare": "ok", "Before": snapshot("", "", separated=separated),
            "Warm": {"Status": "ok", "Text": text}, "ValueStatus": "ok",
            "ValueState": snapshot("A", "", separated=separated),
            "ValueText": {"Status": "ok", "Text": text},
            "PresentationStatus": "ok",
            "PresentationState": snapshot("A", "B", separated=separated),
            "PresentationText": {"Status": "ok", "Text": text},
            "ItemAfter": {"Status": "ok", "Text": "B"},
        }
    sorts = {}
    for name in ("Value", "Presentation"):
        sorts[name] = {
            "Prepare": "ok", "Initial": snapshot(D(7), "start"),
            "Warm": {"Status": "ok", "Text": "start"},
            "PendingStatus": "ok", "Before": snapshot(D(7), "pending"),
            "Status": "ok", "AfterAction": snapshot(D(7), "pending"),
            "BetweenStatus": "ok", "Between": snapshot(D(7), "between"),
            "First": {"Status": "ok", "Text": "start"},
            "AfterStatus": "ok", "After": snapshot(D(7), "after"),
            "Second": {"Status": "ok", "Text": "start"},
        }
    return {"empty-result": empty, "short-sorts": sorts}


def plain(value):
    if type(value) is BSLArray:
        return [plain(item) for item in value.items]
    if type(value) is BSLStructure:
        return {pair.key: plain(pair.value) for pair in value}
    return value


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


def state(owner):
    return {"Count": owner.count(),
            "Items": [[item.value, item.presentation, item.check, item.get_id()]
                      for item in owner.items]}


def from_state(snapshot):
    owner = BSLValueList()
    for value, presentation, check, identifier in snapshot["Items"]:
        item = owner.add(value, presentation, check)
        assert item.get_id() == identifier
    return owner


class NativeValueListStringRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = OUTPUT.read_text(encoding="utf-8")

    def record(self, group):
        return plain(read_observation(
            extract_payload(self.native, "table.list.string-cache." + group),
            compact=True))

    def assert_text(self, owner, record):
        before = state(owner)
        items, lookup = owner.items, owner._by_id
        identities = tuple(map(id, owner.items))
        revision, next_id = owner._revision, owner._next_id
        self.assertEqual(record["Status"], "ok")
        self.assertEqual(str(owner), record["Text"])
        self.assertEqual(state(owner), before)
        self.assertIs(owner.items, items)
        self.assertIs(owner._by_id, lookup)
        self.assertEqual(tuple(map(id, owner.items)), identities)
        self.assertEqual((owner._revision, owner._next_id), (revision, next_id))

    def set_fields(self, owner, snapshot):
        self.assertEqual(owner.count(), snapshot["Count"])
        for item, row in zip(owner.items, snapshot["Items"]):
            self.assertEqual(item.get_id(), row[3])
            for field, value in zip(("Value", "Presentation", "Check"), row[:3]):
                item.set_member(field, value)
        self.assertEqual(state(owner), snapshot)

    def test_complete_original_string_and_cache_source_blocks_match_native(self):
        source = SOURCE.read_text(encoding="utf-8-sig")
        for start, end, first, last in (
                ("// Начало наблюдений строкового представления списка.\n",
                 "// Конец наблюдений строкового представления списка.\n",
                 "table.list.string.empty:",
                 "table.list.string.checkpoint.complete: [ok]\n"),
                ("// Начало уточняющих наблюдений кэша строки списка.\n",
                 "// Конец уточняющих наблюдений кэша строки списка.\n",
                 "table.list.string-cache.initialize:",
                 "table.list.string-cache.checkpoint.complete: [ok]\n")):
            with self.subTest(first=first):
                output = []
                vm = Interpreter(output.append)
                vm.execute(source.split("#Область МассивыИСтруктуры", 1)[0])
                vm.execute(source.split(start, 1)[1].split(end, 1)[0])
                begin = self.native.index(first)
                finish = self.native.index(last, begin) + len(last)
                self.assertEqual("\n".join(output) + "\n", self.native[begin:finish])

    def test_parsed_native_initialization_records(self):
        records = self.record("initialize")
        self.assertEqual(len(records), 5)
        for name, record in records.items():
            with self.subTest(name=name):
                owner = BSLValueList()
                item = owner.add(D(7), "" if name.startswith("Value") else "start")
                self.set_fields(owner, record["Middle"])
                if record["Trigger"] != "not-run":
                    value = item.value if name.endswith("Scalar") else item
                    self.assertEqual(to_string(value), record["Trigger"]["Text"])
                    self.assertIsNone(owner._text_cache)
                self.set_fields(owner, record["Before"])
                self.assert_text(owner, record["First"])
                self.set_fields(owner, record["After"])
                self.assertEqual(str(item), record["ItemAfter"]["Text"])
                self.assert_text(owner, record["Second"])

    def test_parsed_native_structural_and_control_records(self):
        actions = {
            "Add": lambda x: x.add(D(50), "new"),
            "Insert": lambda x: x.insert(D(0), D(50), "new"),
            "Delete": lambda x: x.delete(D(1)),
            "Clear": lambda x: x.clear(),
            "LoadValues": lambda x: x.load_values(array(D(70), D(80))),
            "LoadEmpty": lambda x: x.load_values(array()),
            "Move": lambda x: x.move(D(0), D(1)),
            "MoveNoop": lambda x: x.move(D(0), D(0)),
            "SortValue": lambda x: x.sort_by_value(),
            "SortPresentation": lambda x: x.sort_by_presentation(),
            "SortValueNoop": lambda x: x.sort_by_value(),
            "SortPresentationNoop": lambda x: x.sort_by_presentation(),
            "FillChecks": lambda x: x.fill_checks(True),
            "DeleteError": lambda x: x.delete(D(-1)),
        }
        seen = []
        for group in ("structural", "controls"):
            for name, record in self.record(group).items():
                with self.subTest(name=name):
                    seen.append(name)
                    owner = from_state(record["Initial"])
                    self.assert_text(owner, record["Warm"])
                    self.set_fields(owner, record["Before"])
                    if record["Status"] == "error":
                        with self.assertRaises(IndexError):
                            actions[name](owner)
                    else:
                        actions[name](owner)
                    self.assertEqual(state(owner), record["AfterAction"])
                    self.set_fields(owner, record["Between"])
                    self.assert_text(owner, record["First"])
                    self.set_fields(owner, record["After"])
                    self.assert_text(owner, record["Second"])
        self.assertEqual(set(seen), set(actions))

    def test_parsed_native_empty_and_copy_records(self):
        record = self.record("empty")
        owner = from_state(record["Before"])
        self.assert_text(owner, record["Warm"])
        item = owner.add(D(7), "first")
        self.assertEqual(state(owner), record["AfterAction"])
        self.set_fields(owner, record["FirstState"])
        self.assert_text(owner, record["First"])
        self.set_fields(owner, record["After"])
        self.assertEqual(str(item), record["ItemAfter"]["Text"])
        self.assert_text(owner, record["Second"])

        record = self.record("copy")
        owner = BSLValueList()
        item = owner.add(D(7), "start")
        self.assert_text(owner, record["Warm"])
        self.set_fields(owner, record["Before"])
        original_cache = owner._text_cache
        copied = owner.copy()
        self.assertIs(owner._text_cache, original_cache)
        self.assertIsNone(copied._text_cache)
        self.assertIsNot(copied.items[0], item)
        self.assertEqual(state(owner), record["SourceAfter"])
        self.assertEqual(state(copied), record["CopyAfter"])
        self.set_fields(copied, record["Between"])
        self.assert_text(copied, record["First"])
        self.assert_text(owner, record["Source"])
        self.assertEqual(str(item), record["SourceItem"]["Text"])
        self.set_fields(copied, record["After"])
        self.assert_text(copied, record["Second"])


class LinuxFinalValueListStringTests(unittest.TestCase):
    def test_final_source_groups_match_recorded_linux_fields_and_texts(self):
        source_bytes = SOURCE.read_bytes().replace(b"\r\n", b"\n")
        # The Linux capture predates only these new, unconfirmed probes.
        source_bytes = without_field_reference_probes(without_descriptor_map_probes(source_bytes.decode("utf-8"))).encode("utf-8")
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(),
                         FINAL_LINUX_SOURCE_SHA256)
        source = source_bytes.decode("utf-8-sig")
        output = []
        vm = Interpreter(output.append, native_target="linux-8.3.27.1508")
        vm.execute(source.split("#Область МассивыИСтруктуры", 1)[0])
        start = "// Начало заключительных наблюдений пустой строки кэша списка.\n"
        end = "// Конец заключительных наблюдений пустой строки кэша списка.\n"
        vm.execute(source.split(start, 1)[1].split(end, 1)[0])
        self.assertEqual(len(output), 3)
        self.assertEqual(output[-1], "table.list.string-cache.final.complete: [ok]")
        text = "\n".join(output) + "\n"
        for group, expected in final_linux_observations().items():
            with self.subTest(group=group):
                actual = plain(read_observation(extract_payload(
                    text, "table.list.string-cache." + group), compact=True))
                self.assertEqual(actual, expected)


class ValueListStringBoundaryTests(unittest.TestCase):
    def test_actual_join_budget_includes_fallbacks_and_exact_separators(self):
        cases = (
            ((), ""),
            (("",), ""),
            (("abcd",), "abcd"),
            (("", "ab", ""), "; ab; "),
            (("Я😀", "a\nb"), "Я😀; a\nb"),
            ((None, NULL), "<Пустое значение>; <Пустое значение>"),
            ((D("1234.5"), D("1234.5")), "1\u00a0234,5; 1\u00a0234,5"),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                owner = BSLValueList()
                for value in values:
                    owner.add(value)
                with patch.object(value_lists, "_MAX_TEXT", len(expected)):
                    self.assertEqual(str(owner), expected)
                    self.assertEqual(str(owner), expected)
                if expected:
                    cached = owner._text_cache
                    with patch.object(value_lists, "_MAX_TEXT", len(expected) - 1):
                        with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                            str(owner)
                    self.assertIs(owner._text_cache, cached)
                    other = owner.copy()
                    with patch.object(value_lists, "_MAX_TEXT", len(expected) - 1):
                        with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                            str(other)
                    self.assertIsNone(other._text_cache)
                    self.assertEqual(str(other), expected)

    def test_budget_rejects_before_later_items_and_does_not_cache_partial_text(self):
        owner = BSLValueList()
        for value in ("aa", "bb", "cc"):
            owner.add(value)
        rendered = []
        original = BSLValueListItem.__str__
        def tracked(item):
            rendered.append(item)
            return original(item)
        with patch.object(BSLValueListItem, "__str__", tracked):
            with patch.object(value_lists, "_MAX_TEXT", 5):
                with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                    str(owner)
        self.assertEqual(rendered, owner.items[:2])
        self.assertIsNone(owner._text_cache)
        owner.items[0].set_member("Value", "")
        self.assertEqual(str(owner), "; bb; cc")

    def test_item_count_budget_applies_to_cold_and_warm_conversion(self):
        owner = BSLValueList()
        owner.add("a")
        owner.add("b")
        with patch.object(value_lists, "_MAX_ITEMS", 1):
            with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                str(owner)
        self.assertIsNone(owner._text_cache)
        with patch.object(value_lists, "_MAX_ITEMS", 2):
            self.assertEqual(str(owner), "a; b")
        cached = owner._text_cache
        with patch.object(value_lists, "_MAX_ITEMS", 1):
            with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                str(owner)
        self.assertIs(owner._text_cache, cached)

    def test_failed_rebuild_does_not_publish_stale_or_partial_text(self):
        owner = BSLValueList()
        item = owner.add(D(7))
        self.assertEqual(str(owner), "7")
        old_cache = owner._text_cache
        owner.add(BSLArray())
        with self.assertRaises(ValueError):
            str(owner)
        self.assertIs(owner._text_cache, old_cache)
        self.assertNotEqual(owner._text_cache[0], owner._revision)
        item.set_member("Value", D(9))
        owner.items[1].set_member("Presentation", "safe")
        self.assertEqual(str(owner), "9; safe")
        self.assertNotEqual(owner._text_cache, old_cache)

    def test_failed_value_render_is_not_cached_and_labels_can_recover(self):
        cycle = BSLArray()
        cycle.items.append(cycle)
        for value in (cycle, BSLValueList(), D("1e1000000000")):
            owner = BSLValueList()
            owner.add("prefix")
            item = owner.add(value)
            before = state(owner)
            with self.assertRaises(ValueError):
                str(owner)
            self.assertIsNone(owner._text_cache)
            self.assertEqual(state(owner), before)
            item.set_member("Presentation", "safe")
            self.assertEqual(str(owner), "prefix; safe")

    def test_cold_host_items_values_and_containers_cannot_invoke_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError("host string")
            def __iter__(self):
                raise AssertionError("host iteration")
            def __len__(self):
                raise AssertionError("host length")
            def __eq__(self, other):
                raise AssertionError("host equality")
        class HostItem(BSLValueListItem):
            __str__ = Hostile.__str__
        class HostList(list):
            __iter__ = Hostile.__iter__
            __len__ = Hostile.__len__
        owner = BSLValueList()
        item = owner.add("safe")
        for value in (Hostile(), HostItem(owner, 0, "safe")):
            owner.items = [value]
            with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
                str(owner)
            self.assertIsNone(owner._text_cache)
        owner.items = HostList([item])
        with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
            str(owner)
        owner.items = [item]
        item.value = Hostile()
        with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
            str(owner)
        item.presentation = "label"
        self.assertEqual(str(owner), "label")

    def test_warm_nonempty_cache_does_not_render_current_fields(self):
        owner = BSLValueList()
        item = owner.add(D(7))
        self.assertEqual(str(owner), "7")
        item.set_member("Value", BSLArray())
        item.set_member("Presentation", "")
        item.set_member("Check", True)
        with patch.object(BSLValueListItem, "__str__",
                          side_effect=AssertionError("warm item rendering")):
            self.assertEqual(str(owner), "7")
        self.assertEqual(owner.count(), D(1))
        self.assertEqual(item.get_id(), D(0))

    def test_empty_results_remain_cached_until_structural_change(self):
        for name, expected in (("Value", ""), ("Cleared", ""), ("Separated", "; ")):
            with self.subTest(name=name):
                owner = BSLValueList()
                item = owner.add("", "label" if name == "Cleared" else "")
                if name == "Cleared":
                    item.set_member("Presentation", "")
                if name == "Separated":
                    owner.add("")
                self.assertEqual(str(owner), expected)
                cached = owner._text_cache
                item.set_member("Value", "A")
                self.assertEqual(str(owner), expected)
                item.set_member("Presentation", "B")
                self.assertEqual(str(owner), expected)
                self.assertIs(owner._text_cache, cached)
                self.assertEqual(str(item), "B")
                owner.add("new")
                self.assertEqual(str(owner), "B; ; new" if name == "Separated" else "B; new")
                owner.clear()
                self.assertEqual(str(owner), "")
                owner.load_values(array())
                self.assertEqual(str(owner), "")

    def test_warm_empty_cache_never_renders_changed_fields(self):
        owner = BSLValueList()
        item = owner.add("")
        self.assertEqual(str(owner), "")
        item.set_member("Value", BSLArray())
        cached = owner._text_cache
        with patch.object(value_lists, "_MAX_TEXT", 0), patch.object(
                BSLValueListItem, "__str__", side_effect=AssertionError("warm render")):
            self.assertEqual(str(owner), "")
        self.assertIs(owner._text_cache, cached)

    def test_successful_singleton_sorts_preserve_warm_text_and_revision_policy(self):
        for method in ("sort_by_value", "sort_by_presentation"):
            with self.subTest(method=method):
                owner = BSLValueList()
                item = owner.add(D(7), "start")
                getattr(owner, method)()
                self.assertIsNone(owner._text_cache)
                self.assertEqual(str(owner), "start")
                item.set_member("Presentation", "pending")
                iterator = iter(owner)
                revision = owner._revision
                fields = state(owner)
                getattr(owner, method)()
                self.assertEqual(owner._revision, revision + 1)
                self.assertEqual(state(owner), fields)
                self.assertEqual(owner._text_cache, (owner._revision, "start"))
                with self.assertRaisesRegex(ValueError, "активного обхода"):
                    next(iterator)
                item.set_member("Presentation", "between")
                self.assertEqual(str(owner), "start")
                item.set_member("Presentation", "after")
                self.assertEqual(str(owner), "start")
                self.assertEqual(str(item), "after")
                getattr(owner, method)()
                with patch.object(value_lists, "_MAX_TEXT", 4):
                    with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                        str(owner)
                owner.add(D(8), "new")
                self.assertEqual(str(owner), "after; new")

    def test_singleton_sorts_do_not_revive_stale_caches_or_prime_cold_ones(self):
        for method in ("sort_by_value", "sort_by_presentation"):
            with self.subTest(method=method):
                owner = BSLValueList()
                item = owner.add(D(7), "old")
                owner.add(D(8), "removed")
                self.assertEqual(str(owner), "old; removed")
                owner.delete(D(1))
                stale = owner._text_cache
                item.set_member("Presentation", "current")
                getattr(owner, method)()
                self.assertIs(owner._text_cache, stale)
                self.assertNotEqual(owner._text_cache[0], owner._revision)
                self.assertEqual(str(owner), "current")

    def test_singleton_sort_failed_validation_preserves_cache_and_iterator(self):
        for method in ("sort_by_value", "sort_by_presentation"):
            with self.subTest(method=method):
                owner = BSLValueList()
                item = owner.add(D(7), "old")
                self.assertEqual(str(owner), "old")
                cached = owner._text_cache
                revision, iterator = owner._revision, iter(owner)
                with self.assertRaises(TypeError):
                    getattr(owner, method)("invalid")
                if method == "sort_by_value":
                    item.set_member("Value", D("1e1000000000"))
                else:
                    item.set_member("Presentation", "outside\nalphabet")
                fields = state(owner)
                with self.assertRaises(ValueError):
                    getattr(owner, method)()
                self.assertEqual(state(owner), fields)
                self.assertIs(owner._text_cache, cached)
                self.assertEqual(owner._revision, revision)
                self.assertIs(next(iterator), item)
                self.assertEqual(str(owner), "old")

    def test_local_failed_mutations_preserve_valid_cache_and_id_state(self):
        owner = BSLValueList()
        item = owner.add(D(7), "first")
        owner.add(D(8), "second")
        self.assertEqual(str(owner), "first; second")
        item.set_member("Presentation", "pending")
        operations = (
            lambda: owner.add(object()),
            lambda: owner.insert(D(-1), D(0)),
            lambda: owner.delete(D(-1)),
            lambda: owner.load_values(array(object())),
            lambda: owner.move(D(0), D(3)),
            lambda: owner.sort_by_value("invalid"),
            lambda: owner.sort_by_presentation("invalid"),
        )
        for operation in operations:
            before, cached = state(owner), owner._text_cache
            revision, next_id = owner._revision, owner._next_id
            with self.assertRaises((ValueError, TypeError, IndexError)):
                operation()
            self.assertEqual(state(owner), before)
            self.assertEqual((owner._revision, owner._next_id), (revision, next_id))
            self.assertIs(owner._text_cache, cached)
            self.assertEqual(str(owner), "first; second")

    def test_rendering_changes_only_private_cache_and_never_invalidates_iteration(self):
        owner = BSLValueList()
        owner.add(D(7))
        owner.add(D(8))
        before = {key: value for key, value in owner.__dict__.items()
                  if key != "_text_cache"}
        items = [item.__dict__.copy() for item in owner.items]
        iterator = iter(owner)
        self.assertIs(next(iterator), owner.items[0])
        self.assertEqual(str(owner), "7; 8")
        self.assertIs(next(iterator), owner.items[1])
        with self.assertRaises(StopIteration):
            next(iterator)
        self.assertEqual({key: value for key, value in owner.__dict__.items()
                          if key != "_text_cache"}, before)
        self.assertEqual([item.__dict__ for item in owner.items], items)
        for name in ("_text_cache", "_revision"):
            with self.assertRaises(ValueError):
                owner.get_member(name)

    def test_private_cache_is_not_serialized_or_primed_by_wire_conversion(self):
        owner = BSLValueList()
        item = owner.add(D(7))
        before = serialization.value_to_string_internal(owner)
        self.assertIsNone(owner._text_cache)
        self.assertEqual(str(owner), "7")
        cached = owner._text_cache
        self.assertEqual(serialization.value_to_string_internal(owner), before)
        item.set_member("Value", D(9))
        current = serialization.value_to_string_internal(owner)
        self.assertIs(owner._text_cache, cached)
        self.assertEqual(str(owner), "7")
        restored = serialization.value_from_string_internal(current)
        self.assertIsNone(restored._text_cache)
        self.assertEqual(serialization.value_to_string_internal(restored), current)
        self.assertEqual(state(restored), state(owner))


if __name__ == "__main__":
    unittest.main()
