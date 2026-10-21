"""Explicit-target sort regressions, not a claim about all Linux/1C versions.

Native evidence: Linux amd64 8.3.27.1508, ru_RU, UTC, collections.out at
commit 66ba9dd9f6c96e41c2f4e25394846fe3aa2750b5, run 39567834362 attempt 1,
artifact 12330791968. Original file: 440106 bytes, SHA-256
9e79c371c74fc0b2f7b9f12c391bf66f635ec3890878d4b8f6b2c72d0f4e9b2d.
https://github.com/Atridis/yadinassi/actions/runs/39567834362
The probe source is integrational_tests/tests/collections.bsl at that commit.

The 48 compact expected tuples below were extracted from the 96 exact native
"target-probes.v1.sort.*" records after independently checking the file digest,
status=ok, identity=true and byte-identical IDs for pass1/pass2 of every case.
Every tuple is asserted on BOTH consecutive sorts. Inputs are reconstructed
from the BSL probe's key literals and insertion rules, without using the sorter
or its pivot/partition rules to generate expected orders. The record checksum
covers all 96 original labelled records, not a local sort prediction.

Tests under ModelSafetyTests are synthetic correctness/resource checks, not
additional native observations. Native equivalence beyond the observed lengths
15..18 is unverified; the API retains its existing size/resource limits.
"""
from decimal import Decimal as D, Inexact, Rounded, localcontext
from hashlib import sha256
from itertools import product
from pathlib import Path
from random import Random
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi import native_target_sort as model
from yadinassi.dates import BSLDate
from yadinassi.maps import BSLMap
from yadinassi.native_targets import (
    LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context,
)
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList
from yadinassi.value_table_sort import _string_key
from yadinassi.value_tables import BSLValueTable
from yadinassi.values import BSLArray, NULL

ROOT = Path(__file__).resolve().parents[1]
KEYS = "я|е|Ё|Е|ё|a|A|á|a |a-1|a1|a10|a2| |!|😀|Я|A".split("|")
RANKS = (10, 8, 9, 8, 9, 2, 2, 3, 2, 4, 5, 6, 7, 0, 1, 11, 10, 2)
INSERTIONS = ('forward', 'reverse', 'interleaved')
ORDERS = {
    'asc': 'Key Asc',
    'desc': 'Key Desc',
    'asc-id-desc': 'Key Asc, ID Desc',
    'desc-id-asc': 'Key Desc, ID Asc',
}
NATIVE_ORDERS = {
    (15, 'forward', 'asc'): (14,15,6,7,9,8,10,11,12,13,2,4,3,5,1),
    (15, 'forward', 'desc'): (1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (15, 'forward', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1),
    (15, 'forward', 'desc-id-asc'): (1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (15, 'reverse', 'asc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1),
    (15, 'reverse', 'desc'): (1,5,3,4,2,13,12,11,10,8,9,7,6,15,14),
    (15, 'reverse', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1),
    (15, 'reverse', 'desc-id-asc'): (1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (15, 'interleaved', 'asc'): (14,15,7,9,6,8,10,11,12,13,4,2,3,5,1),
    (15, 'interleaved', 'desc'): (1,3,5,4,2,13,12,11,10,8,7,9,6,15,14),
    (15, 'interleaved', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1),
    (15, 'interleaved', 'desc-id-asc'): (1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (16, 'forward', 'asc'): (14,15,6,7,9,8,10,11,12,13,2,4,3,5,1,16),
    (16, 'forward', 'desc'): (16,1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (16, 'forward', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1,16),
    (16, 'forward', 'desc-id-asc'): (16,1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (16, 'reverse', 'asc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1,16),
    (16, 'reverse', 'desc'): (16,1,5,3,4,2,13,12,11,10,8,9,7,6,15,14),
    (16, 'reverse', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1,16),
    (16, 'reverse', 'desc-id-asc'): (16,1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (16, 'interleaved', 'asc'): (14,15,7,9,6,8,10,11,12,13,4,2,3,5,1,16),
    (16, 'interleaved', 'desc'): (16,1,3,5,4,2,13,12,11,10,8,7,9,6,15,14),
    (16, 'interleaved', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1,16),
    (16, 'interleaved', 'desc-id-asc'): (16,1,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (17, 'forward', 'asc'): (14,15,6,7,9,8,10,11,12,13,2,4,5,3,1,17,16),
    (17, 'forward', 'desc'): (16,1,17,3,5,2,4,13,12,11,10,8,7,9,6,15,14),
    (17, 'forward', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,17,1,16),
    (17, 'forward', 'desc-id-asc'): (16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (17, 'reverse', 'asc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,1,17,16),
    (17, 'reverse', 'desc'): (16,1,17,5,3,4,2,13,12,11,10,8,9,7,6,15,14),
    (17, 'reverse', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,17,1,16),
    (17, 'reverse', 'desc-id-asc'): (16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (17, 'interleaved', 'asc'): (14,15,7,9,6,8,10,11,12,13,2,4,3,5,17,1,16),
    (17, 'interleaved', 'desc'): (16,1,17,3,5,4,2,13,12,11,10,8,9,7,6,15,14),
    (17, 'interleaved', 'asc-id-desc'): (14,15,9,7,6,8,10,11,12,13,4,2,5,3,17,1,16),
    (17, 'interleaved', 'desc-id-asc'): (16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,15,14),
    (18, 'forward', 'asc'): (14,15,18,9,6,7,8,10,11,12,13,4,2,5,3,1,17,16),
    (18, 'forward', 'desc'): (16,17,1,3,5,2,4,13,12,11,10,8,9,7,6,18,15,14),
    (18, 'forward', 'asc-id-desc'): (14,15,18,9,7,6,8,10,11,12,13,4,2,5,3,17,1,16),
    (18, 'forward', 'desc-id-asc'): (16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,18,15,14),
    (18, 'reverse', 'asc'): (14,15,18,9,7,6,8,10,11,12,13,2,4,5,3,1,17,16),
    (18, 'reverse', 'desc'): (16,17,1,5,3,4,2,13,12,11,10,8,9,7,6,18,15,14),
    (18, 'reverse', 'asc-id-desc'): (14,15,18,9,7,6,8,10,11,12,13,4,2,5,3,17,1,16),
    (18, 'reverse', 'desc-id-asc'): (16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,18,15,14),
    (18, 'interleaved', 'asc'): (14,15,6,7,9,18,8,10,11,12,13,2,4,5,3,17,1,16),
    (18, 'interleaved', 'desc'): (16,1,17,3,5,2,4,13,12,11,10,8,18,6,9,7,15,14),
    (18, 'interleaved', 'asc-id-desc'): (14,15,18,9,7,6,8,10,11,12,13,4,2,5,3,17,1,16),
    (18, 'interleaved', 'desc-id-asc'): (16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,18,15,14),
}


def input_ids(size, insertion):
    if insertion == 'forward':
        return list(range(1, size + 1))
    if insertion == 'reverse':
        return list(range(size, 0, -1))
    # The source probe lists odd IDs upwards, then even IDs downwards.
    return [i for i in list(range(1, 19, 2)) + list(range(18, 0, -2)) if i <= size]


def table_for(values):
    table = BSLValueTable()
    table.columns.add('Key')
    for value in values:
        table.add().set_member('Key', value)
    return table


def probe_table(size, insertion):
    table = table_for([])
    table.columns.add('ID')
    original = {}
    for identifier in input_ids(size, insertion):
        row = table.add()
        row.set_member('Key', KEYS[identifier - 1])
        row.set_member('ID', D(identifier))
        original[identifier] = row
    return table, original


class NativeTargetSortTests(unittest.TestCase):
    def test_fixture_covers_all_96_exact_native_records(self):
        expected_cases = set(product(range(15, 19), INSERTIONS, ORDERS))
        self.assertEqual(set(NATIVE_ORDERS), expected_cases)
        records = []
        for size, insertion, mode in product(range(15, 19), INSERTIONS, ORDERS):
            expected = NATIVE_ORDERS[size, insertion, mode]
            self.assertEqual(sorted(expected), list(range(1, size + 1)))
            for repeat in (1, 2):
                ids = ','.join(map(str, expected))
                records.append(
                    f'target-probes.v1.sort.{size}.{insertion}.{mode}.pass{repeat}: '
                    f'[ok;identity={{"B",1}};ids={ids}]\n')
        self.assertEqual(len(records), 96)
        self.assertEqual(sha256(''.join(records).encode()).hexdigest(),
                         '21dca6f846b661aa119eb54a5b056a1f2bf05834b8d30c933ff92a69f36b5876')

    def test_unchanged_uca6_ranks(self):
        keys = [_string_key(key, [0, 0]) for key in KEYS]
        unique = sorted(set(keys))
        self.assertEqual(tuple(unique.index(key) for key in keys), RANKS)

    def test_all_96_native_orders_and_row_identity(self):
        observed = 0
        with target_context(LINUX_8_3_27_1508):
            for (size, insertion, mode), expected in NATIVE_ORDERS.items():
                table, original = probe_table(size, insertion)
                container = table.rows
                columns = list(table.columns)
                cells = {i: row.cells for i, row in original.items()}
                for repeat in (1, 2):
                    with self.subTest(size=size, insertion=insertion, mode=mode, repeat=repeat):
                        self.assertIsNone(table.sort(ORDERS[mode]))
                        observed += 1
                        actual = tuple(int(row.get_member('ID')) for row in table.rows)
                        self.assertEqual(actual, expected)
                        self.assertIs(table.rows, container)
                        self.assertEqual(list(table.columns), columns)
                        for identifier, row in zip(actual, table.rows):
                            self.assertIs(row, original[identifier])
                            self.assertIs(row.cells, cells[identifier])
                            self.assertIs(row.owner(), table)
                            self.assertEqual(row.get_member('Key'), KEYS[identifier - 1])
        self.assertEqual(observed, 96)

    def test_original_two_locale_checkpoints_through_interpreter(self):
        vm = Interpreter(native_target=LINUX_8_3_27_1508)
        source = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])
        for mode in ('asc', 'desc'):
            with self.subTest(mode=mode):
                result = vm.execute(
                    f'СортировкаТаблицыПробы("locale", "{ORDERS[mode]}", "omitted")')
                expected = NATIVE_ORDERS[17, 'forward', mode]
                self.assertEqual(result.get_member('Status'), 'ok')
                self.assertEqual(result.get_member('Order').items, list(expected))
                self.assertEqual(result.get_member('FirstID'), 1)
                self.assertEqual(result.get_member('FirstIndex'), expected.index(1))
                self.assertIs(result.get_member('SameRow'), True)

    def test_default_and_explicit_windows_orders_remain_stable(self):
        # Stable order is independently derived, not replaced by Linux tuples.
        for selected in (None, WINDOWS_8_3_27_2342):
            for size, insertion, mode in NATIVE_ORDERS:
                table, original = probe_table(size, insertion)
                key = lambda i: (
                    -RANKS[i - 1] if mode.startswith('desc') else RANKS[i - 1],
                    -i if mode == 'asc-id-desc' else i if mode == 'desc-id-asc' else 0,
                )
                expected = sorted(input_ids(size, insertion), key=key)
                with self.subTest(target=selected, size=size, insertion=insertion, mode=mode):
                    if selected is None:
                        table.sort(ORDERS[mode])
                    else:
                        with target_context(selected):
                            table.sort(ORDERS[mode])
                    self.assertEqual(table.rows, [original[i] for i in expected])

    def test_value_list_sort_is_not_changed_by_table_target(self):
        owner = BSLValueList()
        values = [D(i % 3) for i in range(64)]
        for value in values:
            owner.add(value)
        original = list(owner.items)
        with target_context(LINUX_8_3_27_1508):
            owner.sort_by_value()
        expected = sorted(range(len(values)), key=values.__getitem__)
        self.assertEqual(owner.items, [original[i] for i in expected])

    def test_rejected_inputs_and_comparators_are_still_atomic(self):
        bad = ('中', 'a\t', '😂', 'a😀', '😁a', '\ue000x', '\ud800', 'x' * 4097,
               D('NaN'), D('Infinity'), D('1e5000'), BSLDate(0, True), BSLMap(), object())
        with target_context(LINUX_8_3_27_1508):
            for value in bad:
                table = table_for([D(2), D(1), value])
                before = list(table.rows)
                with self.subTest(value=repr(value)), self.assertRaises((TypeError, ValueError)):
                    table.sort('Key')
                self.assertEqual(table.rows, before)
            for values in ([D(1), BSLArray()], [BSLArray(), D(1)], [NULL, BSLStructure()]):
                table = table_for(values)
                before = list(table.rows)
                with self.assertRaisesRegex(ValueError, 'смешанный'):
                    table.sort('Key')
                self.assertEqual(table.rows, before)
            for comparator in (D(1), NULL, False, BSLStructure()):
                table = table_for([D(2), D(1)])
                before = list(table.rows)
                with self.assertRaises(TypeError):
                    table.sort('Key', comparator)
                self.assertEqual(table.rows, before)
            for order in ('', 'Key,Missing', 'Key Asc extra', None):
                table = table_for([D(2), D(1)])
                before = list(table.rows)
                with self.assertRaises((TypeError, ValueError)):
                    table.sort(order)
                self.assertEqual(table.rows, before)

    def test_every_column_and_resource_limit_precedes_sorting(self):
        with target_context(LINUX_8_3_27_1508), patch(
                'yadinassi.value_table_sort.introsort', side_effect=AssertionError('must not sort')):
            for constant, limit, order in (
                ('_MAX_SORT_CELLS', 1, 'Key'),
                ('_MAX_SORT_TEXT', 3, 'Key'),
                ('_MAX_KEY_WEIGHTS', 1, 'Key'),
                ('_MAX_SORT_TOKENS', 3, 'Key,,,')
            ):
                table = table_for(['bb', 'aa'])
                before = list(table.rows)
                with self.subTest(constant=constant):
                    with patch('yadinassi.value_table_sort.' + constant, limit):
                        with self.assertRaises(ValueError):
                            table.sort(order)
                self.assertEqual(table.rows, before)
            table = table_for([D(2), D(1)])
            table.columns.add('Other')
            table.rows[0].set_member('Other', '中')
            before = list(table.rows)
            with self.assertRaises(ValueError):
                table.sort('Key, Other')
            self.assertEqual(table.rows, before)

    def test_sort_stage_failure_does_not_commit_private_row_order(self):
        table, original = probe_table(18, 'forward')
        container = table.rows
        before = list(table.rows)

        def fail_after_mutation(rows, less):
            self.assertIsNot(rows, container)
            rows.reverse()
            raise RuntimeError('synthetic sort failure')

        with target_context(LINUX_8_3_27_1508), patch(
                'yadinassi.value_table_sort.introsort', side_effect=fail_after_mutation):
            with self.assertRaisesRegex(RuntimeError, 'synthetic sort failure'):
                table.sort('Key')
        self.assertIs(table.rows, container)
        self.assertEqual(table.rows, before)
        for identifier, row in original.items():
            self.assertIs(row.owner(), table)
            self.assertEqual(row.get_member('Key'), KEYS[identifier - 1])

    def test_numeric_keys_keep_precision_and_identity(self):
        values = [D('1.000000000000000000000000000001'), D('-0'),
                  D('0'), D('1.000000000000000000000000')]
        table = table_for(values)
        original = list(table.rows)
        with target_context(LINUX_8_3_27_1508), localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            table.sort('Key')
        self.assertEqual(table.rows, [original[i] for i in (1, 2, 3, 0)])
        for row, value in zip(original, values):
            self.assertIs(row.get_member('Key'), value)

    def test_larger_multicolumn_table_has_no_eighteen_row_cap(self):
        # Synthetic comparator integration, not native evidence for 257 rows.
        rng = Random(23827)
        values = [D(rng.randrange(11)) for _ in range(257)]
        table = table_for(values)
        table.columns.add('Second')
        table.columns.add('ID')
        original = list(table.rows)
        pairs = []
        for index, row in enumerate(original):
            second = D(rng.randrange(7))
            row.set_member('Second', second)
            row.set_member('ID', D(index))
            pairs.append((values[index], -second, index))
        expected = sorted(range(len(original)), key=pairs.__getitem__)
        with target_context(LINUX_8_3_27_1508):
            table.sort('Key Asc, Second Desc, ID Asc')
        self.assertEqual(table.rows, [original[i] for i in expected])


class ModelSafetyTests(unittest.TestCase):
    """General algorithm checks below are NOT extra native-1C observations."""

    def assert_bounded_model(self, keys):
        comparisons = 0
        ids = list(range(len(keys)))

        def less(a, b):
            nonlocal comparisons
            comparisons += 1
            return keys[a] < keys[b]

        model.introsort(ids, less)
        self.assertEqual(sorted(ids), list(range(len(keys))))
        self.assertEqual([keys[i] for i in ids], sorted(keys))
        # A deliberately loose structural guard, not a native timing limit.
        self.assertLessEqual(comparisons, 40 * max(1, len(keys)) * max(1, len(keys).bit_length()))
        repeated = list(range(len(keys)))
        model.introsort(repeated, lambda a, b: keys[a] < keys[b])
        self.assertEqual(repeated, ids)

    def test_general_correctness_bounded_work_and_determinism(self):
        rng = Random(83271508)
        for size in (0, 1, 2, 15, 16, 17, 18, 19, 31, 32, 33, 127, 256, 1024, 4096):
            cases = {
                'ascending': list(range(size)),
                'descending': list(range(size, 0, -1)),
                'equal': [0] * size,
                'sawtooth': [i % 5 for i in range(size)],
                'organ-pipe': [min(i, size - i) for i in range(size)],
                'random': [rng.randrange(max(1, size // 4)) for _ in range(size)],
            }
            for name, keys in cases.items():
                with self.subTest(size=size, pattern=name):
                    self.assert_bounded_model(keys)

    def test_actual_adversarial_input_reaches_heap_fallback(self):
        size = 4096
        # No forced depth or fake partition: this deterministic pattern reaches
        # the real depth budget and exercises heapsort within normal introsort.
        keys = [min(i, size - i) for i in range(size)]
        with patch.object(model, '_heap_sort', wraps=model._heap_sort) as heap:
            self.assert_bounded_model(keys)
        self.assertGreater(heap.call_count, 0)

    def test_heap_fallback_sorts_only_its_span_and_preserves_objects(self):
        rng = Random(1508)
        for size in (0, 1, 2, 3, 16, 17, 128, 1024):
            values = [(rng.randrange(5), i) for i in range(size)]
            left, right = object(), object()
            items = [left] + values + [right]
            model._heap_sort(items, 1, size + 1, lambda a, b: a[0] < b[0])
            self.assertIs(items[0], left)
            self.assertIs(items[-1], right)
            self.assertEqual([x[0] for x in items[1:-1]], sorted(x[0] for x in values))
            self.assertEqual({id(x) for x in items[1:-1]}, {id(x) for x in values})

    def test_lexicographic_comparator_not_implicit_input_id_breaks_ties(self):
        values = list(range(64))
        model.introsort(values, lambda a, b: False)
        self.assertNotEqual(values, list(range(64)))
        self.assertEqual(sorted(values), list(range(64)))


if __name__ == '__main__':
    unittest.main()
