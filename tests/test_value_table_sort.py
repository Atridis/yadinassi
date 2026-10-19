"""Sort regressions transcribed from authenticated owner commit d933a9d.

Native source: PR64 collections.out blob 6645f7fa667dfe498cef9109fb7b42078dfb9c43,
Windows 8.3.27.2342 ru_RU server. Other tests exercise local safety policy, not
invented native error outputs.
"""
from decimal import Decimal as D, Inexact, Rounded, localcontext
from pathlib import Path
from hashlib import sha256
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi import value_table_collation as sort_collation
from yadinassi.dates import BSLDate
from yadinassi.maps import BSLMap
from yadinassi.value_tables import BSLValueTable, BSLValueTableColumn
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.value_table_sort import _value_key
from yadinassi.values import BSLArray, BSLType, NULL
from yadinassi.structures import BSLStructure

ROOT = Path(__file__).resolve().parents[1]


def table_for(*values):
    table = BSLValueTable()
    table.columns.add('Key')
    for value in values:
        table.add().set_member('Key', value)
    return table


class NativeSortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vm = Interpreter()
        source = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        cls.vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])

    def test_all_24_native_observations(self):
        asc = [2, 4, 6, 1, 3, 5]
        original = [1, 2, 3, 4, 5, 6]
        cases = [
            ('base', 'Key', 'omitted', 'ok', asc),
            ('base', 'Key Desc', 'omitted', 'ok', [1, 3, 5, 2, 4, 6]),
            ('base', 'Key Asc,Second Desc', 'omitted', 'ok', [2, 4, 6, 5, 1, 3]),
            ('base', 'Key Убыв, Second Возр', 'russian', 'ok', [1, 3, 5, 4, 6, 2]),
            ('base', ' key desc , SECOND asc ', 'omitted', 'ok', [1, 3, 5, 4, 6, 2]),
            ('base', 'Key,Key Desc', 'omitted', 'ok', asc),
            ('base', '', 'omitted', 'error', original),
            ('base', 'Key,Missing', 'omitted', 'error', original),
            ('base', 'Key Sideways', 'omitted', 'ok', asc),
            ('base', 'Key,,Second', 'omitted', 'ok', [4, 6, 2, 1, 3, 5]),
            ('base', 'Key,', 'omitted', 'ok', asc),
            ('base', None, 'omitted', 'error', original),
            ('base', 'Key', 'undefined', 'ok', asc),
            ('base', 'Key', 'invalid', 'error', original),
            ('empty', 'Key', 'omitted', 'ok', []),
            ('locale', 'Key', 'omitted', 'ok', [14,15,6,7,9,8,10,11,12,13,2,4,3,5,1,17,16]),
            ('locale', 'Key Desc', 'omitted', 'ok', [16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,15,14]),
            ('mixed', 'Key', 'omitted', 'ok', [4,12,6,11,7,3,13,8,2,14,9,1,15,10,5]),
            ('mixed', 'Key Desc', 'omitted', 'ok', [5,10,1,15,9,2,14,8,3,13,7,6,11,4,12]),
            ('objects', 'Key', 'omitted', 'ok', [2,4,1,3,6,5]),
            ('base', 'Key', 'missing', 'error', original),
            ('singleton', 'Key', 'omitted', 'ok', [1]),
            # Supplement owner commit 6e8d31f, original output unmodified.
            ('utf16-boundary', 'Key', 'omitted', 'ok', [3,1,4,5,2]),
            ('utf16-boundary', 'Key Desc', 'omitted', 'ok', [2,5,4,1,3]),
        ]
        for dataset, order, comparator, status, expected in cases:
            with self.subTest(dataset=dataset, order=order, comparator=comparator):
                arg = 'Неопределено' if order is None else '"' + order + '"'
                result = self.vm.execute(f'СортировкаТаблицыПробы("{dataset}", {arg}, "{comparator}")')
                self.assertEqual(result.get_member('Status'), status)
                self.assertEqual(result.get_member('Order').items, expected)
                self.assertEqual(result.get_member('FirstID'), 1 if expected else None)
                self.assertEqual(result.get_member('FirstIndex'), expected.index(1) if expected else None)
                self.assertEqual(result.get_member('SameRow'), True if expected else None)

    def test_pinned_dataset_and_license_are_exact(self):
        data_dir = ROOT / 'yadinassi/data'
        data = (data_dir / sort_collation.TABLE_NAME).read_bytes()
        self.assertEqual(len(data), 1_655_669)
        self.assertEqual(sha256(data).hexdigest(),
                         'b6e440cff4c0b71215bb8a12dd64d56c95b5c973097377697a388ba7289b085d')
        self.assertIn(b'\n@version 6.0.0\n', data)
        self.assertNotIn(b'\r', data)
        license_data = (data_dir / 'LICENSE-Unicode.txt').read_bytes()
        self.assertEqual(sha256(license_data).hexdigest(),
                         'e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96')
        self.assertIn(b'UNICODE LICENSE V3', license_data)

    def test_corrupt_missing_and_wrong_version_tables_fail_closed(self):
        data = (ROOT / 'yadinassi/data' / sort_collation.TABLE_NAME).read_bytes()
        bad_version = data.replace(b'@version 6.0.0', b'@version 6.0.1')
        try:
            for replacement in (b'!' + data[1:], data.replace(b'\n', b'\r\n')):
                sort_collation._collator.cache_clear()
                with patch.object(Path, 'read_bytes', return_value=replacement):
                    with self.assertRaisesRegex(ValueError, 'изменена'):
                        sort_collation._collator()
            sort_collation._collator.cache_clear()
            # Even with a deliberately updated checksum, the version guard
            # independently rejects data bearing a different DUCET version.
            with patch.object(Path, 'read_bytes', return_value=bad_version), \
                 patch.object(sort_collation, 'TABLE_SHA256', sha256(bad_version).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'изменена'):
                    sort_collation._collator()
            sort_collation._collator.cache_clear()
            with patch.object(Path, 'read_bytes', side_effect=FileNotFoundError):
                with self.assertRaisesRegex(ValueError, 'недоступна'):
                    sort_collation._collator()
        finally:
            sort_collation._collator.cache_clear()

    def test_normalization_limits_precede_collation_work(self):
        with patch.object(sort_collation, '_collator', side_effect=AssertionError('unbounded collation')):
            with self.assertRaises(ValueError):
                sort_collation.caseless_string_key('a' * 4097)
            with patch.object(sort_collation, 'MAX_NORMALIZED_LENGTH', 5):
                with self.assertRaisesRegex(ValueError, 'нормализации'):
                    sort_collation.caseless_string_key('á' * 3)
        self.assertEqual(sort_collation.caseless_string_key('á'),
                         sort_collation.caseless_string_key('a\u0301'))
        # Canonical helper equivalence does not silently expand the public
        # Sort repertoire to arbitrary combining-mark sequences.
        table = table_for('b', 'a\u0301')
        rows = list(table.rows)
        with self.assertRaises(ValueError):
            table.sort('Key')
        self.assertEqual(table.rows, rows)
        for value in ('a', 'b', 'я', '😀'):
            sort_collation.caseless_string_key(value)
        self.assertLessEqual(sort_collation._collator.cache_info().currsize, 1)

    def test_supported_keys_obey_comparator_laws(self):
        # Implementation invariants, not additional native golden observations.
        scalar = [None, NULL, False, True, D('-1'), D('-0'), D('0'), D('2'),
                  '', ' ', '!', 'a', 'A', 'a ', 'á', 'a-1', 'a1', 'a10',
                  'a2', 'е', 'Е', 'Ё', 'ё', 'я', 'Я', '😀', '😁', '\U00010000', '\ue000', BSLDate(0),
                  BSLDate(10000)]
        objects = [BSLArray(), BSLArray(), BSLStructure(), BSLStructure(),
                   BSLType.STRING, BSLType.NUMBER]
        for values in (scalar, objects):
            keys = [_value_key(value, [0, 0])[1] for value in values]
            for a in keys:
                self.assertEqual(a, a)
                self.assertFalse(a < a)
                for b in keys:
                    self.assertEqual(int(a < b) + int(a == b) + int(a > b), 1)
                    self.assertEqual(a < b, b > a)
                    for c in keys:
                        if a <= b and b <= c:
                            self.assertLessEqual(a, c)
                        if a == b:
                            self.assertEqual(a < c, b < c)
                            self.assertEqual(c < a, c < b)
            for indices in (list(range(len(values))), list(reversed(range(len(values)))),
                            list(range(0, len(values), 2)) + list(range(1, len(values), 2))):
                for descending in (False, True):
                    table = table_for(*(values[i] for i in indices))
                    rows = list(table.rows)
                    expected = sorted(range(len(rows)), key=lambda i: keys[indices[i]], reverse=descending)
                    table.sort('Key Desc' if descending else 'Key')
                    self.assertEqual(table.rows, [rows[i] for i in expected])

    def test_mixed_families_and_invalid_comparator_reject_atomically(self):
        for values in ((D(2), D(1), BSLArray()), (BSLArray(), D(1)),
                       (BSLType.NUMBER, None), (NULL, BSLStructure())):
            for order in ('Key', 'Key Desc'):
                table = table_for(*values)
                rows = list(table.rows)
                cells = [row.cells for row in rows]
                with self.assertRaisesRegex(ValueError, 'смешанный'):
                    table.sort(order)
                self.assertEqual(table.rows, rows)
                for row, cell in zip(rows, cells):
                    self.assertIs(row.cells, cell)
                    self.assertIs(row.owner(), table)
        for comparator in (D(1), NULL, False, BSLStructure()):
            table = table_for(D(2), D(1))
            rows = list(table.rows)
            with self.assertRaises(TypeError):
                table.sort('Key', comparator)
            self.assertEqual(table.rows, rows)

    def test_identity_and_schema_are_preserved(self):
        table = table_for(D(2), D(1), D(2))
        rows = list(table.rows)
        container = table.rows
        columns = list(table.columns)
        cells = [row.cells for row in rows]
        self.assertIsNone(table.sort('Key Desc'))
        self.assertIs(table.rows, container)
        self.assertEqual(table.rows, [rows[0], rows[2], rows[1]])
        self.assertEqual(list(table.columns), columns)
        for row, cell in zip(rows, cells):
            self.assertIs(row.cells, cell)
            self.assertIs(row.owner(), table)

    def test_rejected_local_boundaries_are_atomic(self):
        for unsupported in ('中', 'a\t', '😂', 'a😀', '😁a', '\ue000x', '\ud800', 'x' * 4097,
                            D('NaN'), D('Infinity'), D('1e5000'), BSLDate(0, True), BSLMap(), object()):
            with self.subTest(value=repr(unsupported)):
                table = table_for(D(2), D(1), unsupported)
                before = list(table.rows)
                with self.assertRaises((ValueError, TypeError)):
                    table.sort('Key')
                self.assertEqual(table.rows, before)
        table = table_for(D(1), BSLArray())
        with self.assertRaisesRegex(ValueError, 'смешанный'):
            table.sort('Key')

    def test_repeated_tokens_do_not_scan_schema_per_token(self):
        class CountedColumns(list):
            visits = 0
            def __iter__(self):
                for column in super().__iter__():
                    self.visits += 1
                    yield column
        table = BSLValueTable()
        # Build a maximal valid schema directly so setup does not exercise the
        # unrelated duplicate-name validation in Columns.Add.
        description = BSLTypeDescription()
        table.columns.items = CountedColumns(
            BSLValueTableColumn(table, f'C{i}', description, '', D(0))
            for i in range(4096))
        with patch.object(table.columns, 'find', side_effect=AssertionError('linear lookup')):
            table.sort(','.join(['c4095 Desc'] + ['C4095 Asc'] * 4095))
        self.assertEqual(table.columns.items.visits, 4096)
        self.assertEqual(table.rows, [])

    def test_order_token_budget_counts_duplicates_and_empty_chunks(self):
        for order in ('Key,Key,Key,Key', 'Key,,,'):
            table = table_for(D(2), D(1))
            rows = list(table.rows)
            with patch('yadinassi.value_table_sort._MAX_SORT_TOKENS', 3):
                with self.assertRaisesRegex(ValueError, 'элементов списка'):
                    table.sort(order)
            self.assertEqual(table.rows, rows)
        table = table_for(D(2), D(1))
        with patch('yadinassi.value_table_sort._MAX_SORT_TOKENS', 3):
            table.sort('Key,,')
        self.assertEqual([row.get_member('Key') for row in table.rows], [D(1), D(2)])

    def test_resource_limits_are_precommit(self):
        for constant, limit in (('_MAX_SORT_CELLS', 1), ('_MAX_SORT_TEXT', 3), ('_MAX_KEY_WEIGHTS', 1)):
            table = table_for('bb', 'aa')
            before = list(table.rows)
            with patch('yadinassi.value_table_sort.' + constant, limit):
                with self.assertRaises(ValueError):
                    table.sort('Key')
            self.assertEqual(table.rows, before)

    def test_numeric_sort_does_not_round_or_mutate_values(self):
        values = [D('1.000000000000000000000000000001'), D('-0'),
                  D('0'), D('1.000000000000000000000000000000')]
        table = table_for(*values)
        original = list(table.rows)
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            table.sort('Key')
        self.assertEqual(table.rows, [original[1], original[2], original[3], original[0]])
        for row, value in zip(original, values):
            self.assertIs(row.get_member('Key'), value)

    def test_string_length_limit_includes_trailing_spaces(self):
        table = table_for('a' + ' ' * 4095, 'A')
        original = list(table.rows)
        table.sort('Key Desc')
        self.assertEqual(table.rows, original)
        table.rows[0].set_member('Key', 'a' + ' ' * 4096)
        with self.assertRaises(ValueError):
            table.sort('Key')
        self.assertEqual(table.rows, original)

    def test_all_columns_validate_before_any_mutation(self):
        table = table_for(D(2), D(1))
        table.columns.add('Other')
        table.rows[0].set_member('Other', '中')
        before = list(table.rows)
        with self.assertRaises(ValueError):
            table.sort('Key, Other')
        self.assertEqual(table.rows, before)

    def test_unsupported_values_in_unused_columns_do_not_matter(self):
        table = table_for(D(2), D(1))
        table.columns.add('Other')
        table.rows[0].set_member('Other', BSLMap())
        table.sort('Key')
        self.assertEqual([row.get_member('Key') for row in table.rows], [D(1), D(2)])


if __name__ == '__main__':
    unittest.main()
