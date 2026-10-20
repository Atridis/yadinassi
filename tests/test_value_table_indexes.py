"""Index behavior transcribed from owner commit 3b2fa58484f9dfbd6d296b7f11c373fef184dca5.

The 35 original records plus five owner supplement records (eea37ff099b5)
are genuine Windows 8.3.27.2342 observations.
Resource, hashing, and mutation-invariant checks below are local safety tests,
not additional claims about unobserved native ordering.
"""
from decimal import Decimal as D, Inexact, Rounded, localcontext
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.dates import BSLDate
from yadinassi.structures import BSLStructure
from yadinassi.type_qualifiers import BSLAllowedSign, BSLNumberQualifiers
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.value_tables import (BSLCollectionIndex, BSLCollectionIndexes,
                                   BSLValueTable, _index_token)
from yadinassi.values import BSLArray, BSLFixedArray, BSLObject, BSLType, NULL, equal


def sample():
    table = BSLValueTable()
    for name in ('Key', 'Second', 'Amount'):
        table.columns.add(name)
    for number in (1, 2):
        row = table.add()
        row.set_member('Key', 'a')
        row.set_member('Second', D(number))
        row.set_member('Amount', D(number))
    return table


def supplement_sample():
    table = BSLValueTable()
    for name in ('Key', 'Second', 'Amount'):
        table.columns.add(name)
    for number in (1, 2, 3):
        row = table.add()
        row.set_member('Key', 'a')
        row.set_member('Second', D(1))
        row.set_member('Amount', D(number))
    return table


def names(table):
    return [list(index) for index in table.indexes]


def found(table, **filters):
    selection = BSLStructure()
    for name, value in filters.items():
        selection.insert(name, value)
    return table.find_rows(selection).items


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


class NativeIndexTests(unittest.TestCase):
    def test_identity_iteration_access_and_readonly_methods(self):
        table = sample()
        collection = table.get_member('Indexes')
        self.assertIs(collection, table.get_member('Индексы'))
        self.assertIsInstance(collection, BSLCollectionIndexes)
        index = collection.get_method('Добавить')('Key,Second')
        self.assertIsInstance(index, BSLCollectionIndex)
        self.assertEqual(str(collection), 'ИндексыКоллекции')
        self.assertEqual(str(index), 'Key, Second')
        self.assertIs(next(iter(collection)), index)
        self.assertIs(collection.get_index(D(0)), index)
        self.assertEqual(collection.get_method('Количество')(), D(1))
        self.assertEqual(index.get_index(D('0.9')), 'Key')
        self.assertEqual(index.get_index(D(1)), 'Second')
        self.assertFalse(equal(collection, sample().indexes))
        self.assertFalse(equal(index, table.indexes.add('key,SECOND')))
        for argument in (D(-1), D(2), '0', None):
            with self.subTest(argument=argument), self.assertRaises((TypeError, ValueError, IndexError)):
                index.get_index(argument)
        for receiver, method in ((collection, 'Get'), (index, 'Count')):
            with self.assertRaises(ValueError):
                receiver.get_method(method)
        with self.assertRaises(ValueError):
            index.set_index(D(0), 'Amount')
        with self.assertRaises(ValueError):
            collection.set_index(D(0), index)
        with self.assertRaises(ValueError):
            table.set_member('Indexes', collection)

    def test_add_normalizes_names_and_preserves_duplicates(self):
        for specification, expected in (
                ('Key', ['Key']), ('key', ['Key']),
                (' Key , Second ', ['Key', 'Second']),
                ('Second,Key', ['Second', 'Key']),
                ('Key,Key', ['Key', 'Key']), ('Key,', ['Key']),
                ('Key,,Second', ['Key', 'Second']), ('', []), (None, [])):
            with self.subTest(specification=specification):
                table = sample()
                index = table.indexes.add(specification)
                self.assertEqual(list(index), expected)
                self.assertEqual(names(table), [expected])
        table = sample()
        self.assertEqual(list(table.indexes.add()), [])
        for value in ('Key,Missing', D(1)):
            with self.assertRaises((TypeError, ValueError)):
                table.indexes.add(value)
        self.assertEqual(names(table), [[]])

    def test_delete_selectors_detach_without_blanking(self):
        for selector in (D(0), D('0.5'), '0', 'object'):
            with self.subTest(selector=selector):
                table = sample()
                index = table.indexes.add('Key,Second')
                table.indexes.add('Amount')
                table.indexes.delete(index if selector == 'object' else selector)
                self.assertEqual(names(table), [['Amount']])
                self.assertEqual(list(index), ['Key', 'Second'])
                self.assertEqual(index._keys, {})
                self.assertEqual(index._buckets, {})
                with self.assertRaises(ValueError):
                    table.indexes.delete(index)
        table = sample()
        index = table.indexes.add('Key')
        foreign = sample().indexes.add('Key')
        for selector in (D(-1), D(1), None, foreign):
            with self.assertRaises((TypeError, ValueError, IndexError)):
                table.indexes.delete(selector)
            self.assertEqual(list(table.indexes), [index])
        with self.assertRaises(TypeError):
            table.indexes.delete()

    def test_clear_blanks_saved_names_preserving_arity(self):
        table = sample()
        saved = table.indexes.add('Key,Second')
        table.indexes.add('Amount')
        table.indexes.clear()
        table.indexes.clear()
        self.assertEqual(names(table), [])
        self.assertEqual(list(saved), ['', ''])
        self.assertEqual(saved.get_index(D(0)), '')
        self.assertEqual(len(table.rows), 2)

    def test_column_lifecycle_and_table_clear(self):
        table = sample()
        saved = table.indexes.add('Key,Second')
        table.columns.get(D(0)).set_member('Name', 'Renamed')
        self.assertEqual(list(saved), ['Renamed', 'Second'])
        self.assertIs(table.find('a', 'renamed'), table.rows[0])
        table.columns.move('Renamed', D(2))
        self.assertEqual([column.name for column in table.columns], ['Second', 'Amount', 'Renamed'])
        self.assertEqual(list(saved), ['Renamed', 'Second'])
        table.columns.delete('Renamed')
        self.assertEqual(list(saved), ['Second'])
        table.clear()
        self.assertEqual(names(table), [['Second']])
        self.assertEqual(table.rows, [])
        table.columns.clear()
        self.assertEqual(names(table), [[]])
        self.assertEqual(list(saved), [])

    def test_groupby_removes_indexes_and_blanks_saved_index(self):
        table = sample()
        saved = table.indexes.add('Key,Second')
        table.indexes.add('Amount')
        table.group_by('Key,Second', 'Amount')
        self.assertEqual(names(table), [])
        self.assertEqual(list(saved), ['', ''])
        table.group_by('Key', 'Amount')
        self.assertEqual([list(row) for row in table], [['a', D(3)]])

    def test_full_copy_and_observed_projection_are_independent(self):
        table = sample()
        index = table.indexes.add('Key,Second')
        copied = table.copy()
        self.assertEqual(names(copied), [['Key', 'Second']])
        self.assertIsNot(copied.indexes, table.indexes)
        self.assertIsNot(copied.indexes.items[0], index)
        self.assertIs(copied.indexes.items[0].columns[0], copied.columns.items[0])
        self.assertEqual([list(row) for row in copied], [list(row) for row in table])
        self.assertEqual(names(table.copy(None, 'Key')), [])
        self.assertEqual(names(table.copy_columns('Key')), [])
        copied.columns.get(D(0)).set_member('Name', 'CopiedKey')
        self.assertEqual(list(index), ['Key', 'Second'])
        self.assertEqual(names(copied), [['CopiedKey', 'Second']])

    def test_search_reinserts_changed_key_and_composite_property_order(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Key')
        first, second = table.rows
        self.assertEqual(found(table, Key='a'), [first, second])
        self.assertIs(table.find('a', 'Key'), first)
        self.assertEqual(found(table, Key='a', Second=D(1)), [first])
        self.assertEqual(found(table, Second=D(1), Key='a'), [first])
        first.set_member('Key', 'b')
        self.assertEqual(found(table, Key='a'), [second])
        self.assertIs(table.find('a', 'Key'), second)
        first.set_index('Key', 'a')
        self.assertEqual(found(table, Key='a'), [second, first])
        self.assertIs(table.find('a', 'Key'), second)
        self.assertEqual(table.rows, [first, second])
        self.assertEqual(table.index_of(second), D(1))

    def test_search_row_add_delete_and_bulk_mutations(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Key')
        first, second = table.rows
        third = table.add()
        third.set(D(0), 'a')
        third.set_member('Second', D(3))
        third.set_member('Amount', D(3))
        self.assertEqual(found(table, Key='a'), [first, second, third])
        table.delete(first)
        self.assertEqual(found(table, Key='a'), [second, third])
        table.fill_values('b', 'Key')
        self.assertEqual(found(table, Key='a'), [])
        self.assertIsNone(table.find('a', 'Key'))
        table.load_column(array('a', 'a'), 'Key')
        self.assertEqual(found(table, Key='a'), [second, third])
        self.assertIs(table.find('a', 'Key'), second)
        table.clear()
        self.assertEqual(found(table, Key='a'), [])
        last = table.add()
        last.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [last])

    def test_composite_prefix_search_after_sort_uses_table_order(self):
        table = sample()
        table.indexes.add('Key,Second')
        first, second = table.rows
        table.sort('Second Desc')
        self.assertEqual(found(table, Key='a'), [second, first])
        self.assertIs(table.find('a', 'Key'), second)

    def test_native_supplement_same_key_and_bulk_reinsertion_order(self):
        table = supplement_sample()
        table.indexes.add('Key')
        first, second, third = table.rows
        self.assertEqual(found(table, Key='a'), [first, second, third])
        first.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [second, third, first])
        self.assertIs(table.find('a', 'Key'), second)
        second.set_member('Second', D(2))
        self.assertEqual(found(table, Key='a'), [second, third, first])
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        table.fill_values('a', 'Key')
        self.assertEqual(found(table, Key='a'), [first, second, third])
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [second, third, first])
        table.load_column(array('a', 'a', 'a'), 'Key')
        self.assertEqual(found(table, Key='a'), [first, second, third])
        self.assertIs(table.find('a', 'Key'), first)
        self.assertEqual(table.rows, [first, second, third])

    def test_native_supplement_sort_and_move_reset_index_order(self):
        table = supplement_sample()
        table.indexes.add('Key')
        first, second, third = table.rows
        with patch('yadinassi.value_tables._index_token', wraps=_index_token) as tokenize:
            table.sort('Amount Desc')
        self.assertEqual(tokenize.call_count, 0)
        self.assertEqual(table.rows, [third, second, first])
        self.assertEqual(found(table, Key='a'), [third, second, first])
        for columns in (None, 'Key', 'Second,Key'):
            self.assertIs(table.find('a', columns), third)
        with patch('yadinassi.value_tables._index_token', wraps=_index_token) as tokenize:
            table.move(third, D(2))
        self.assertEqual(tokenize.call_count, 0)
        self.assertEqual(table.rows, [second, first, third])
        self.assertEqual(found(table, Key='a'), [second, first, third])
        for columns in (None, 'Key', 'Second,Key'):
            self.assertIs(table.find('a', columns), second)

    def test_native_supplement_uses_first_exact_definition_and_no_partial_index(self):
        table = supplement_sample()
        old = table.indexes.add('Key')
        first, second, third = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [second, third, first])
        self.assertEqual(found(table, Key='a', Second=D(1)), [first, second, third])
        composite = table.indexes.add('Key,Second')
        table.indexes.add('Key')
        self.assertEqual(found(table, Key='a'), [second, third, first])
        self.assertEqual(found(table, Key='a', Second=D(1)), [first, second, third])
        self.assertEqual(found(table, Second=D(1), Key='a'), [first, second, third])
        table.indexes.delete(old)
        self.assertEqual(found(table, Key='a'), [first, second, third])
        table.indexes.delete(composite)
        self.assertEqual(found(table, Key='a', Second=D(1)), [first, second, third])

    def test_native_supplement_explicit_all_field_and_complete_index_projections_drop_indexes(self):
        table = supplement_sample()
        for definition in ('Key,Second', 'Key', 'Amount'):
            table.indexes.add(definition)
        for columns in ('Second,Key,Amount', 'Second,Key', 'Key'):
            copied = table.copy(None, columns)
            self.assertEqual(names(copied), [])
            self.assertEqual([column.name for column in copied.columns], columns.split(','))
            self.assertEqual(names(table.copy_columns(columns)), [])
        self.assertEqual(names(table.copy_columns()), [])
        copied = table.copy()
        self.assertEqual(names(copied), [['Key', 'Second'], ['Key'], ['Amount']])
        copied.columns.get(D(0)).set_member('Name', 'Renamed')
        self.assertEqual(names(copied), [['Renamed', 'Second'], ['Renamed'], ['Amount']])
        self.assertEqual(names(table), [['Key', 'Second'], ['Key'], ['Amount']])

    def test_native_supplement_detached_links_and_cleared_text(self):
        table = supplement_sample()
        saved = table.indexes.add('Key,Second')
        table.indexes.delete(saved)
        self.assertEqual(str(saved), 'Key, Second')
        table.columns.get(D(0)).set_member('Name', 'Renamed')
        self.assertEqual(list(saved), ['Renamed', 'Second'])
        table.columns.delete('Second')
        self.assertEqual(list(saved), ['Renamed', ''])
        self.assertEqual(saved.get_index(D(1)), '')
        self.assertEqual(str(saved), 'Renamed, ')
        for operation in ('clear', 'group'):
            with self.subTest(operation=operation):
                table = supplement_sample()
                saved = table.indexes.add('Key,Second')
                if operation == 'clear':
                    table.indexes.clear()
                else:
                    table.group_by('Key', 'Amount')
                self.assertEqual(list(saved), ['', ''])
                self.assertEqual(saved.get_index(D(0)), '')
                self.assertEqual(saved.get_index(D(1)), '')
                with self.assertRaisesRegex(ValueError, 'очищен'):
                    str(saved)
                table.columns.get(D(0)).set_member('Name', 'Renamed')
                table.columns.delete('Second' if operation == 'clear' else 'Amount')
                self.assertEqual(list(saved), ['', ''])
                with self.assertRaises(ValueError):
                    str(saved)

    def test_interpreter_surface_and_omitted_add(self):
        vm = Interpreter()
        vm.execute('t = New ValueTable(); t.Columns.Add("Key"); '
                   'indexes = t.Indexes; i = indexes.Add("Key"); '
                   'indexes.Add(); indexes.Add(Undefined);')
        self.assertTrue(vm.execute('(t.Индексы = indexes)'))
        self.assertTrue(vm.execute('(indexes[0] = i)'))
        self.assertEqual(vm.execute('i[0.9]'), 'Key')
        self.assertEqual(vm.execute('indexes.Count()'), D(3))
        for expression in ('indexes.Get(0)', 'i.Count()', 'i["0"]',
                           'New CollectionIndexes()', 'New CollectionIndex()'):
            with self.assertRaises(BSLError):
                vm.execute(expression)
        for statement in ('indexes[0] = i;', 'i[0] = "Key";', 't.Indexes = indexes;'):
            with self.assertRaises(BSLError):
                vm.execute(statement)


class IndexSafetyTests(unittest.TestCase):
    def test_key_tokens_obey_existing_typed_equality_law(self):
        shared = array('x')
        fixed = BSLFixedArray(shared)
        values = [None, NULL, False, True, D(0), D('-0.00'), D(1), D('1.00'),
                  '', 'a', 'A', 'a ', BSLDate(0), BSLDate(0), BSLDate(10),
                  BSLType.STRING, BSLType.NUMBER,
                  BSLTypeDescription('String'), BSLTypeDescription('String'),
                  BSLTypeDescription('Number'), shared, shared, array('x'),
                  fixed, fixed, BSLFixedArray(shared), BSLStructure('A', D(1)),
                  BSLAllowedSign.ANY, BSLAllowedSign.NONNEGATIVE,
                  BSLNumberQualifiers(), BSLNumberQualifiers()]
        for left in values:
            for right in values:
                with self.subTest(left=left, right=right):
                    self.assertEqual(_index_token(left) == _index_token(right), equal(left, right))
                    if equal(left, right):
                        self.assertEqual(hash(_index_token(left)), hash(_index_token(right)))

    def test_mixed_values_keep_distinct_buckets(self):
        table = BSLValueTable()
        table.columns.add('Key')
        values = [None, NULL, False, True, D(0), D(1), '1', 'a', 'A', array(1)]
        for value in values:
            table.add().set_member('Key', value)
        table.indexes.add('Key')
        for value, expected in zip(values, table.rows):
            self.assertEqual(found(table, Key=value), [expected])
        self.assertEqual(found(table, Key=D('1.00')), [table.rows[5]])
        self.assertEqual(found(table, Key=array(1)), [])

    def test_index_and_key_resource_failures_are_atomic(self):
        table = sample()
        with patch('yadinassi.value_tables._MAX_INDEXES', 1):
            saved = table.indexes.add('Key')
            with self.assertRaisesRegex(ValueError, 'ресурсов'):
                table.indexes.add('Second')
            self.assertEqual(list(table.indexes), [saved])
        with patch('yadinassi.value_tables._MAX_INDEX_COLUMNS', 2):
            with self.assertRaisesRegex(ValueError, 'предел'):
                table.indexes.add('Key,,Second')
            with self.assertRaisesRegex(ValueError, 'ресурсов'):
                table.indexes.add('Key,Second')
        with patch('yadinassi.value_tables._MAX_INDEX_CELLS', 2):
            with self.assertRaisesRegex(ValueError, 'ресурсов'):
                table.add()
            self.assertEqual(len(table.rows), 2)
            with self.assertRaisesRegex(ValueError, 'ресурсов'):
                table.indexes.add('Second')
        old = table.rows[0].get_member('Key')
        for value in (D('NaN'), D('Infinity'), D('1e4097'), D((0, (1,) * 4097, 0))):
            with self.assertRaises(ValueError):
                table.rows[0].set_member('Key', value)
            self.assertEqual(table.rows[0].get_member('Key'), old)
            self.assertEqual(found(table, Key='a'), table.rows)
        with patch('yadinassi.value_tables._MAX_TEXT', 3):
            with self.assertRaisesRegex(ValueError, 'ресурсов'):
                table.rows[0].set_member('Key', 'xxxx')
        self.assertEqual(found(table, Key='a'), table.rows)

    def test_aggregate_key_content_budget_is_atomic_and_released(self):
        table = sample()
        with patch('yadinassi.value_tables._MAX_INDEX_UNITS', 4):
            index = table.indexes.add('Key')
            second = table.indexes.add('Second')
            self.assertEqual(index._units + second._units, 4)
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.rows[0].set_member('Key', 'long')
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.indexes.add('Amount')
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.add()
            self.assertEqual(names(table), [['Key'], ['Second']])
            self.assertEqual(len(table.rows), 2)
            self.assertEqual(found(table, Key='a'), table.rows)
            table.indexes.delete(second)
            table.rows[0].set_member('Key', 'abc')
            self.assertEqual(index._units, 4)
            table.delete(table.rows[0])
            self.assertEqual(index._units, 1)
            table.clear()
            self.assertEqual(index._units, 0)
            table.add().set_member('Key', 'abcd')
            self.assertEqual(index._units, 4)

    def test_bulk_work_guard_counts_compound_width_and_duplicate_selections(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Key')
        table.rows[0].set_member('Key', 'b')
        table.rows[0].set_member('Key', 'a')
        before = [list(row) for row in table]
        order = found(table, Key='a')
        with patch('yadinassi.value_tables._MAX_INDEX_WORK', 8):
            # Two rows * ((1 + 3) Key work + (1 + 2) Second work).
            with self.assertRaisesRegex(ValueError, 'предел работы'):
                table.fill_values('z', 'Key,Second')
            with self.assertRaisesRegex(ValueError, 'предел работы'):
                table.fill_values('z', 'Key,Key')
            self.assertEqual([list(row) for row in table], before)
            self.assertEqual(found(table, Key='a'), order)
        with patch('yadinassi.value_tables._MAX_INDEX_WORK', 7):
            with self.assertRaisesRegex(ValueError, 'предел работы'):
                table.load_column(array('b', 'b'), 'Key')
            self.assertEqual([list(row) for row in table], before)
            self.assertEqual(found(table, Key='a'), order)

    def test_equal_decimal_rewrite_refreshes_cost_and_live_representative(self):
        table = BSLValueTable()
        for name in ('A', 'B', 'C'):
            table.columns.add(name)
        row = table.add()
        row.set_member('A', D(1))
        row.set_member('B', 'x')
        row.set_member('C', 'xxxx')
        with patch('yadinassi.value_tables._MAX_INDEX_UNITS', 6):
            index = table.indexes.add('A,B')
            row.set_member('A', D('1.000'))
            self.assertEqual(index._units, 5)
            self.assertIs(next(iter(index._buckets)), index._keys[row])
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.indexes.add('C')
            row.set_member('A', D(1))
            self.assertEqual(index._units, 2)
            self.assertIs(next(iter(index._buckets)), index._keys[row])
            table.indexes.add('C')
            table.columns.delete('B')
            self.assertEqual(found(table, A=D(1)), [row])
            self.assertEqual(names(table), [['A'], ['C']])
        other = table.add()
        other.set_member('A', D('1.00'))
        table.delete(row)
        self.assertIs(next(iter(index._buckets)), index._keys[other])
        self.assertEqual(index._units, 3)

    def test_column_delete_preflights_all_index_changes(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Amount')
        before = [list(row) for row in table]
        with patch('yadinassi.value_tables._MAX_INDEX_UNITS', 1):
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.columns.delete('Second')
        self.assertEqual(names(table), [['Key', 'Second'], ['Amount']])
        self.assertEqual([column.name for column in table.columns], ['Key', 'Second', 'Amount'])
        self.assertEqual([list(row) for row in table], before)
        self.assertEqual(found(table, Key='a', Second=D(1)), [table.rows[0]])

    def test_bulk_content_budget_failures_preserve_every_cell_and_bucket_order(self):
        table = sample()
        table.indexes.add('Key')
        table.rows[0].set_member('Key', 'b')
        table.rows[0].set_member('Key', 'a')
        before = [list(row) for row in table]
        order = found(table, Key='a')
        with patch('yadinassi.value_tables._MAX_INDEX_UNITS', 4):
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.fill_values('xxx', 'Key')
            with self.assertRaisesRegex(ValueError, 'содержимого ключей'):
                table.load_column(array('xx', 'xxx'), 'Key')
            self.assertEqual([list(row) for row in table], before)
            self.assertEqual(found(table, Key='a'), order)
            table.fill_values('xx', 'Key')
            self.assertEqual(table.indexes.items[0]._units, 4)

    def test_bulk_work_counts_repeated_long_key_content(self):
        table = sample()
        table.rows[0].set_member('Second', D('1' * 100))
        table.indexes.add('Key,Second')
        before = [list(row) for row in table]
        with patch('yadinassi.value_tables._MAX_INDEX_WORK', 50):
            with self.assertRaisesRegex(ValueError, 'предел работы'):
                table.fill_values('z', 'Key')
            with self.assertRaisesRegex(ValueError, 'предел работы'):
                table.load_column(array('z'), 'Key')
        self.assertEqual([list(row) for row in table], before)
        self.assertEqual(found(table, Key='a', Second=D('1' * 100)), [table.rows[0]])

    def test_duplicate_field_lookup_is_bounded_only_when_order_ambiguous(self):
        table = sample()
        saved = table.indexes.add('Key,Key')
        self.assertEqual(list(saved), ['Key', 'Key'])
        self.assertEqual(found(table, Key='a'), table.rows)
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        with self.assertRaisesRegex(ValueError, 'повторными колонками'):
            found(table, Key='a')
        for columns in ('Key', None, ''):
            with self.assertRaisesRegex(ValueError, 'повторными колонками'):
                table.find('a', columns)
        self.assertEqual(list(saved), ['Key', 'Key'])
        self.assertEqual(table.rows, [first, second])
        # A normal exact index can establish the same result independently.
        table = sample()
        table.indexes.add('Key')
        table.indexes.add('Key,Key')
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [second, first])

    def test_empty_definitions_never_supply_rows_for_a_predicate(self):
        table = sample()
        for _ in range(3):
            table.indexes.add()
        self.assertEqual(found(table), [])
        self.assertEqual(found(table, Key='a'), table.rows)
        self.assertIs(table.find('a', 'Key'), table.rows[0])
        self.assertTrue(all(not index._keys and not index._buckets for index in table.indexes))

    def test_indexed_nonappend_insert_is_reserved_before_mutation(self):
        table = sample()
        table.indexes.add('Key')
        first, second = table.rows
        first.set_member('Key', 'a')
        before = [list(row) for row in table]
        for position in (D(0), D(1), D('0.9')):
            with self.assertRaisesRegex(ValueError, 'не в конец'):
                table.insert(position)
            self.assertEqual([list(row) for row in table], before)
            self.assertEqual(found(table, Key='a'), [second, first])
        last = table.insert(D(len(table.rows)))
        self.assertIs(table.rows[-1], last)
        table.indexes.clear()
        inserted = table.insert(D(1))
        self.assertIs(table.rows[1], inserted)

    def test_indexed_copy_empty_column_string_is_reserved(self):
        table = sample()
        saved = table.indexes.add('Key')
        with self.assertRaisesRegex(ValueError, 'пустым списком'):
            table.copy(None, '')
        self.assertEqual(list(table.indexes), [saved])
        self.assertEqual(names(table.copy()), [['Key']])
        self.assertEqual(names(table.copy(None, 'Key,Second,Amount')), [])
        table.indexes.clear()
        self.assertEqual([list(row) for row in table.copy(None, '')], [list(row) for row in table])

    def test_implicit_find_is_reserved_only_when_candidate_first_rows_diverge(self):
        for single_column in (False, True):
            with self.subTest(single_column=single_column):
                table = sample()
                if single_column:
                    table.columns.delete('Second')
                    table.columns.delete('Amount')
                table.indexes.add('Key')
                first, second = table.rows
                self.assertIs(table.find('a'), first)
                self.assertIs(table.find('a', ''), first)
                first.set_member('Key', 'a')
                self.assertIs(table.find('a', 'Key'), second)
                for columns in (None, ''):
                    with self.assertRaisesRegex(ValueError, 'без списка колонок'):
                        table.find('a', columns)
                self.assertEqual(table.rows, [first, second])
                self.assertEqual(found(table, Key='a'), [second, first])
                table.sort('Key')
                self.assertIs(table.find('a'), first)
                self.assertIs(table.find('a', ''), first)
                self.assertIsNone(table.find('missing'))

    def test_failed_key_creation_does_not_install_partial_index(self):
        table = sample()
        table.rows[1].set_member('Key', D('NaN'))
        with self.assertRaises(ValueError):
            table.indexes.add('Key')
        self.assertEqual(names(table), [])
        self.assertEqual(table.indexes._budget(), None)

    def test_host_equality_is_not_guessed_or_invoked(self):
        class Host(BSLObject):
            def __eq__(self, other):
                raise AssertionError('arbitrary host equality called')
        with self.assertRaisesRegex(ValueError, 'тип ключа'):
            _index_token(Host())
        class Meta(type):
            def __eq__(self, other):
                raise AssertionError('arbitrary metaclass equality called')
            def __hash__(self):
                raise AssertionError('arbitrary metaclass hash called')
        class Unknown(metaclass=Meta):
            pass
        with self.assertRaisesRegex(ValueError, 'тип ключа'):
            _index_token(Unknown())

    def test_decimal_keys_work_under_hostile_context(self):
        table = sample()
        table.indexes.add('Second')
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            table.rows[0].set_member('Second', D('123456789.000'))
            self.assertEqual(found(table, Second=D('123456789')), [table.rows[0]])
            self.assertFalse(context.flags[Inexact])
            self.assertFalse(context.flags[Rounded])

    def test_failed_groupby_preserves_index_and_lookup(self):
        table = sample()
        saved = table.indexes.add('Key')
        with self.assertRaises(ValueError):
            table.group_by('Key', 'Key')
        self.assertEqual(list(table.indexes), [saved])
        self.assertEqual(list(saved), ['Key'])
        self.assertEqual(found(table, Key='a'), table.rows)

    def test_groupby_does_not_rebuild_indexes_for_each_removed_column(self):
        table = BSLValueTable()
        for i in range(80):
            table.columns.add(f'C{i}')
        for i in range(80):
            table.add().set_member('C0', D(i))
        table.indexes.add(','.join(column.name for column in table.columns))
        with patch('yadinassi.value_tables._index_token', wraps=_index_token) as tokenize:
            table.group_by('C0')
        self.assertEqual(tokenize.call_count, 0)
        self.assertEqual(names(table), [])
        self.assertEqual(len(table.rows), 80)
        self.assertEqual([column.name for column in table.columns], ['C0'])

    def test_random_mutations_preserve_membership_without_assuming_order(self):
        import random
        rng = random.Random(1729)
        table = sample()
        for definition in ('Key', 'Second', 'Key,Second', 'Key,Key', ''):
            table.indexes.add(definition)
        values = [None, NULL, False, D(0), D(1), 'a', 'b']
        for iteration in range(200):
            operation = rng.randrange(5)
            if not table.rows or operation == 0:
                row = table.add()
                row.set_index('Key', rng.choice(values))
                row.set_index('Second', rng.choice(values))
            elif operation == 1:
                table.delete(rng.choice(table.rows))
            elif operation == 2:
                row = rng.choice(table.rows)
                row.set(D(rng.randrange(2)), rng.choice(values))
            elif operation == 3:
                table.load_column(array(*(rng.choice(values) for _ in table.rows)), 'Key')
            else:
                table.fill_values(rng.choice(values), 'Second')
            for index in table.indexes:
                if not index.columns:
                    self.assertEqual(index._keys, {})
                    continue
                self.assertEqual(index._units, sum(
                    len(value) if kind is str else len(value.as_tuple().digits)
                    if kind is D else 1 for key in index._keys.values() for kind, value in key))
                self.assertEqual(set(index._keys), set(table.rows))
                for row in table.rows:
                    self.assertEqual(index._keys[row], index._key(row))
                    self.assertIn(row, index._buckets[index._key(row)])
            for value in values:
                actual = found(table, Key=value)
                expected = [row for row in table.rows if equal(row.get_member('Key'), value)]
                self.assertEqual(set(actual), set(expected))
                self.assertEqual(len(actual), len(expected))

    def test_only_current_rows_remain_referenced(self):
        table = sample()
        index = table.indexes.add('Key')
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        table.delete(first)
        self.assertNotIn(first, index._keys)
        self.assertEqual([row for bucket in index._buckets.values() for row in bucket], [second])
        table.clear()
        self.assertEqual(index._keys, {})
        self.assertEqual(index._buckets, {})


if __name__ == '__main__':
    unittest.main()
