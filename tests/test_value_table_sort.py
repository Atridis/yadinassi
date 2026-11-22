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
from yadinassi.collections import plain_table_storage, value_table_collation as sort_collation
from yadinassi.temporal.dates import BSLDate
from yadinassi.collections.maps import BSLMap
from yadinassi.collections.value_tables import BSLValueTable, BSLValueTableColumnCollection
from yadinassi.collections.value_table_sort import _value_key
from yadinassi.types.values import BSLArray, BSLType, NULL
from yadinassi.collections.structures import BSLStructure

ROOT = Path(__file__).resolve().parents[1]


def table_for(*values):
    table = BSLValueTable()
    table.columns.add('Key')
    for value in values:
        table.add().set_member('Key', value)
    return table


_ASC = [2, 4, 6, 1, 3, 5]
_ORIGINAL = [1, 2, 3, 4, 5, 6]
NATIVE_CASES = [
    ('base', 'Key', 'omitted', 'ok', _ASC),
    ('base', 'Key Desc', 'omitted', 'ok', [1, 3, 5, 2, 4, 6]),
    ('base', 'Key Asc,Second Desc', 'omitted', 'ok', [2, 4, 6, 5, 1, 3]),
    ('base', 'Key Убыв, Second Возр', 'russian', 'ok', [1, 3, 5, 4, 6, 2]),
    ('base', ' key desc , SECOND asc ', 'omitted', 'ok', [1, 3, 5, 4, 6, 2]),
    ('base', 'Key,Key Desc', 'omitted', 'ok', _ASC),
    ('base', '', 'omitted', 'error', _ORIGINAL),
    ('base', 'Key,Missing', 'omitted', 'error', _ORIGINAL),
    ('base', 'Key Sideways', 'omitted', 'ok', _ASC),
    ('base', 'Key,,Second', 'omitted', 'ok', [4, 6, 2, 1, 3, 5]),
    ('base', 'Key,', 'omitted', 'ok', _ASC),
    ('base', None, 'omitted', 'error', _ORIGINAL),
    ('base', 'Key', 'undefined', 'ok', _ASC),
    ('base', 'Key', 'invalid', 'error', _ORIGINAL),
    ('empty', 'Key', 'omitted', 'ok', []),
    ('locale', 'Key', 'omitted', 'ok', [14,15,6,7,9,8,10,11,12,13,2,4,3,5,1,17,16]),
    ('locale', 'Key Desc', 'omitted', 'ok', [16,1,17,3,5,2,4,13,12,11,10,8,6,7,9,15,14]),
    ('mixed', 'Key', 'omitted', 'ok', [4,12,6,11,7,3,13,8,2,14,9,1,15,10,5]),
    ('mixed', 'Key Desc', 'omitted', 'ok', [5,10,1,15,9,2,14,8,3,13,7,6,11,4,12]),
    ('objects', 'Key', 'omitted', 'ok', [2,4,1,3,6,5]),
    ('base', 'Key', 'missing', 'error', _ORIGINAL),
    ('singleton', 'Key', 'omitted', 'ok', [1]),
    # Supplement owner commit 6e8d31f, original output unmodified.
    ('utf16-boundary', 'Key', 'omitted', 'ok', [3,1,4,5,2]),
    ('utf16-boundary', 'Key Desc', 'omitted', 'ok', [2,5,4,1,3]),
]


# Only exact order differs intentionally; all four cases still run in Light.
ADVISORY_ORDER_CASES = frozenset({
    ('locale', 'Key', 'omitted'),
    ('locale', 'Key Desc', 'omitted'),
    ('utf16-boundary', 'Key', 'omitted'),
    ('utf16-boundary', 'Key Desc', 'omitted'),
})


def sort_probe_source():
    source = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
    return source.split('#Область МассивыИСтруктуры', 1)[0]


def observe_native_case(check, vm, case):
    dataset, order, comparator, status, expected = case
    arg = 'Неопределено' if order is None else '"' + order + '"'
    result = vm.execute(f'СортировкаТаблицыПробы("{dataset}", {arg}, "{comparator}")')
    check.assertEqual(result['Status'], status)
    actual = list(result['Order'])
    if case[:3] in ADVISORY_ORDER_CASES:
        check.assertTrue(all(type(identifier) in (int, D) for identifier in actual))
        check.assertCountEqual(actual, expected)
        first_index = actual.index(1)
    else:
        check.assertEqual(actual, expected)
        first_index = expected.index(1) if expected else None
    check.assertEqual(result['FirstID'], 1 if expected else None)
    check.assertEqual(result['FirstIndex'], first_index)
    check.assertEqual(result['SameRow'], True if expected else None)
    return actual


class NativeSortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vm = Interpreter()
        cls.addClassCleanup(cls.vm.close)
        cls.vm.execute(sort_probe_source())

    def test_all_24_native_observations(self):
        for case in NATIVE_CASES:
            dataset, order, comparator = case[:3]
            with self.subTest(dataset=dataset, order=order, comparator=comparator):
                observe_native_case(self, self.vm, case)

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

    def test_pinned_collation_helper_checks_limits_before_work(self):
        with patch.object(sort_collation, '_collator', side_effect=AssertionError('unbounded collation')):
            with self.assertRaises(ValueError):
                sort_collation.caseless_string_key('a' * 4097)
            with patch.object(sort_collation, 'MAX_NORMALIZED_LENGTH', 5):
                with self.assertRaisesRegex(ValueError, 'нормализации'):
                    sort_collation.caseless_string_key('á' * 3)
        self.assertEqual(sort_collation.caseless_string_key('á'),
                         sort_collation.caseless_string_key('a\u0301'))
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

    def test_mixed_families_and_invalid_comparator_reject_atomically(self):
        for values in ((D(2), D(1), BSLArray()), (BSLArray(), D(1)),
                       (BSLType.NUMBER, None), (NULL, BSLStructure())):
            for order in ('Key', 'Key Desc'):
                with self.subTest(values=values, order=order):
                    table = table_for(*values)
                    rows = list(table.rows)
                    with self.assertRaisesRegex(NotImplementedError, 'sorting opaque values'):
                        table.sort(order)
                    self.assertEqual(table.rows, rows)
                    for row, value in zip(rows, values):
                        self.assertIs(row.get_member('Key'), value)
                        self.assertIs(row.owner(), table)
        for comparator, error, message in (
                (D(1), TypeError, 'numeric sort comparator'),
                (NULL, NotImplementedError, 'custom comparator'),
                (False, NotImplementedError, 'custom comparator'),
                (BSLStructure(), NotImplementedError, 'custom comparator')):
            with self.subTest(comparator=comparator):
                table = table_for(D(2), D(1))
                rows = list(table.rows)
                with self.assertRaisesRegex(error, message):
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
        for row, snapshot in zip(rows, cells):
            self.assertEqual(tuple(row.cells), tuple(snapshot))
            for column, value in snapshot.items():
                self.assertIs(row.cells[column], value)
            self.assertIs(row.owner(), table)

    def test_rejected_local_boundaries_are_atomic(self):
        for value, error, message in (
                (D('NaN'), ValueError, 'nonfinite sort value'),
                (D('Infinity'), ValueError, 'nonfinite sort value'),
                (BSLDate(0, True), NotImplementedError, 'sorting unknown dates'),
                (BSLMap(), NotImplementedError, 'sorting opaque values'),
                (object(), NotImplementedError, 'sorting opaque values')):
            with self.subTest(value=repr(value)):
                table = table_for(D(2), D(1), value)
                before = list(table.rows)
                with self.assertRaisesRegex(error, message):
                    table.sort('Key')
                self.assertEqual(table.rows, before)
                self.assertIs(before[2].get_member('Key'), value)

    def test_lightweight_public_sort_accepts_nonlegacy_text_and_large_numbers(self):
        # These are local semantics, not new locale/emoji observations.
        strings = ('中', 'a\t', '😂', 'a😀', '😁a', '\ue000x', '\ud800',
                   'x' * 4097, 'a\u0301')
        table = table_for(*strings)
        table.sort('Key')
        self.assertEqual([row.get_member('Key') for row in table.rows], sorted(strings))
        large, small = D('1e5000'), D('-1e5000')
        table = table_for(large, D(0), small)
        rows = list(table.rows)
        table.sort('Key')
        self.assertEqual(table.rows, [rows[2], rows[1], rows[0]])
        self.assertIs(rows[0].get_member('Key'), large)
        self.assertIs(rows[2].get_member('Key'), small)

    def test_repeated_tokens_share_resolved_columns_and_key_projections(self):
        table = table_for(D(1), D(2), D(2), D(1), D(2))
        table.columns.add('Other')
        rows = list(table.rows)
        for row, value in zip(rows, (D(2), D(2), D(1), D(1), D(1))):
            row.set_member('Other', value)
        # Casefolded aliases select the same schema offsets. The conflicting
        # later directions do not override the first or discard Other.
        order = 'kEy Desc, Other Asc' + ',KEY Asc,OTHER Desc' * 2048
        with patch.object(BSLValueTableColumnCollection, 'find',
                          side_effect=AssertionError('linear schema scan')), \
             patch.object(plain_table_storage, '_sort_value',
                          wraps=plain_table_storage._sort_value) as project:
            table.sort(order)
        self.assertEqual(project.call_count, 2 * len(rows))
        self.assertEqual(list(map(id, table.rows)), [id(rows[i]) for i in (2, 4, 1, 3, 0)])

    def test_duplicate_and_empty_tokens_keep_first_direction_and_validate_syntax(self):
        table = table_for(D(1), D(2), D(1))
        rows = list(table.rows)
        # More tokens than the retired quota, with one distinct key.
        table.sort('Key Desc' + ',,KEY Asc' * 9000 + ',')
        self.assertEqual(list(map(id, table.rows)), [id(rows[i]) for i in (1, 0, 2)])
        before = list(map(id, table.rows))
        for order, message in (('Key,Key Asc extra', 'invalid sort order'),
                               ('Key,,Missing', 'column not found')):
            with self.subTest(order=order), self.assertRaisesRegex(ValueError, message):
                table.sort(order)
            self.assertEqual(list(map(id, table.rows)), before)

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

    def test_lightweight_sort_preserves_trailing_spaces(self):
        table = table_for('a', 'a' + ' ' * 4096)
        short, long = table.rows
        table.sort('Key Desc')
        self.assertEqual(table.rows,[long, short])
        table.sort('Key Asc')
        self.assertEqual(table.rows,[short, long])

    def test_all_columns_validate_before_any_mutation(self):
        class Opaque:
            def __lt__(self, other):
                raise AssertionError('host comparison called')
            def __eq__(self, other):
                raise AssertionError('host equality called')

        table = table_for(D(2), D(1))
        table.columns.add('Other')
        opaque = Opaque()
        table.rows[0].set_member('Other', opaque)
        before = list(table.rows)
        with self.assertRaisesRegex(NotImplementedError, 'sorting opaque values'):
            table.sort('Key, Other')
        self.assertEqual(list(map(id, table.rows)), list(map(id, before)))
        self.assertIs(before[0].get_member('Other'), opaque)

    def test_unsupported_values_in_unused_columns_do_not_matter(self):
        table = table_for(D(2), D(1))
        table.columns.add('Other')
        table.rows[0].set_member('Other', BSLMap())
        table.sort('Key')
        self.assertEqual([row.get_member('Key') for row in table.rows], [D(1), D(2)])


class DirectScalarSortTests(unittest.TestCase):
    def test_python_string_type_order_and_stable_ties(self):
        # An independent BSL fixture: explicit expected original row IDs,
        # not keys computed by either implementation's comparator.
        values = ('"a"', '1', 'Null', 'Date(2024,1,1)', 'Undefined',
                  'True', '"A"', '-1', '1.0', 'False', 'Date(2023,1,1)',
                  '"a"', '"á"')
        for direction, expected in (
                ('Asc', [4, 2, 9, 5, 7, 1, 8, 6, 0, 11, 12, 10, 3]),
                ('Desc', [3, 10, 12, 0, 11, 6, 1, 8, 7, 5, 9, 2, 4])):
            with self.subTest(direction=direction):
                vm = Interpreter()
                self.addCleanup(vm.close)
                source = 'T=New ValueTable; T.Columns.Add("Key");'
                vm.execute(source + ''.join(f'R=T.Add(); R.Key={value};' for value in values))
                table = vm.variables['t']
                rows = list(table.rows)
                vm.execute(f'T.Sort("Key {direction}");')
                self.assertEqual(list(map(id, table.rows)), [id(rows[i]) for i in expected])


    def test_opaque_keys_are_unsupported_without_reordering_rows(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; T.Columns.Add("Key");'
                   'R=T.Add(); R.Key=2; R=T.Add(); R.Key=1;'
                   'R=T.Add(); R.Key=New Structure;')
        table = vm.variables['t']
        before = list(map(id, table.rows))
        with self.assertRaisesRegex(NotImplementedError, 'sorting opaque values is not supported'):
            vm.execute('T.Sort("Key Asc");')
        self.assertEqual(list(map(id, table.rows)), before)


if __name__ == '__main__':
    unittest.main()
