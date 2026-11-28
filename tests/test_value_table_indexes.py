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
from yadinassi.temporal.dates import BSLDate
from yadinassi.collections.structures import BSLStructure
from yadinassi.types.type_qualifiers import BSLAllowedSign, BSLNumberQualifiers
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.collections.value_tables import (BSLCollectionIndex, BSLCollectionIndexes,
                                   BSLValueTable, _index_token)
from yadinassi.types.values import BSLArray, BSLFixedArray, BSLObject, BSLType, NULL, equal


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
                self.assertEqual(table._search.declarations, {(2,)})
                self.assertEqual(table._search.cache, {})
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
        copied_index = copied.indexes.get_index(D(0))
        self.assertIsNot(copied_index, index)
        self.assertIs(copied_index._columns[0], copied.columns.items[0])
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
        with patch('yadinassi.collections.value_tables._index_token', wraps=_index_token) as tokenize:
            table.sort('Amount Desc')
        self.assertEqual(tokenize.call_count, 0)
        self.assertEqual(table.rows, [third, second, first])
        self.assertEqual(found(table, Key='a'), [third, second, first])
        for columns in (None, 'Key', 'Second,Key'):
            self.assertIs(table.find('a', columns), third)
        with patch('yadinassi.collections.value_tables._index_token', wraps=_index_token) as tokenize:
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

    def test_direct_table_bulk_operations_preserve_groups_and_totals(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; T.Columns.Add("Key"); T.Columns.Add("Amount"); '
                   'T.Add(); T.Add(); T.ЗаполнитьЗначения("same","Key"); '
                   'A=New Array; A.Add(2); A.Add(3); T.ЗагрузитьКолонку(A,"Amount"); '
                   'T.Свернуть("Key","Amount"); N=T.Count(); Result=T[0].Amount;')
        self.assertEqual(vm.variables['n'], 1)
        self.assertEqual(vm.variables['result'], 5)

    def test_direct_table_copies_distinguish_schema_from_rows(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; T.Columns.Add("Key"); T.Columns.Add("Amount"); '
                   'T.Add().Key="first"; T.Indexes.Add("Key"); '
                   'A=T.CopyColumns(); B=T.СкопироватьКолонки("Amount"); C=T.Скопировать(); N=C.Indexes.Count();')
        a, b, c = (vm.variables[k] for k in ('a', 'b', 'c'))
        self.assertEqual([column.name for column in a.columns.items], ['Key', 'Amount'])
        self.assertEqual([column.name for column in b.columns.items], ['Amount'])
        self.assertEqual((a.count(), b.count(), c.count()), (0, 0, 1))
        self.assertEqual((names(a), names(b), names(c)), ([], [], [['Key']]))
        self.assertEqual(c.get(0).get_member('Key'), 'first')
        self.assertEqual(vm.variables['n'], 1)
        vm.variables['t']._bounded_slice_read = True
        for source in ('R=T.CopyColumns();', 'R=T.Copy();'):
            with self.subTest(source=source), self.assertRaisesRegex(BSLError, "bounded table slice"):
                vm.execute(source)
        self.assertNotIn('r', vm.variables)

    def test_bsl_implicit_column_copy_preserves_only_independent_declarations(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; T.Columns.Add("Key"); T.Columns.Add("Amount"); '
                   'R=T.Add(); R.Key="first"; R.Amount=1; '
                   'R=T.Add(); R.Key="second"; R.Amount=2; '
                   'T.Indexes.Add("Key"); T.Indexes.Add("Key"); T.Indexes.Add(); '
                   'First=New Structure("Key","first"); Warm=T.FindRows(First); '
                   'C=T.Copy(); S=T.Copy(First); P=T.Copy(,"Key,Amount"); Q=T.CopyColumns();')
        source, full, selected, projected, columns_only = (vm.variables[k] for k in ('t','c','s','p','q'))
        self.assertTrue(source._search.cache)
        for copy, count in ((full,2),(selected,1)):
            self.assertEqual(len(copy.rows),count)
            self.assertEqual(names(copy),[['Key'],['Key'],[]])
            self.assertEqual(copy._search.declarations,{(0,)})
            self.assertFalse(copy._search.cache)
            self.assertEqual(copy._search.builds,0)
            self.assertIsNot(copy.indexes.get_index(D(0)),source.indexes.get_index(D(0)))
        self.assertEqual(names(projected),[])
        self.assertEqual(names(columns_only),[])
        vm.execute('C.Columns[0].Name="Renamed"; '
                   'Match=C.FindRows(New Structure("Renamed","first")); '
                   'C[0].Renamed="changed"; StillSource=T.FindRows(First);')
        self.assertEqual(names(full),[['Renamed'],['Renamed'],[]])
        self.assertEqual(names(source),[['Key'],['Key'],[]])
        self.assertIs(vm.variables['match'].items[0],full.rows[0])
        self.assertIs(vm.variables['stillsource'].items[0],source.rows[0])
        self.assertEqual(source.rows[0].get_member('Key'),'first')
        self.assertEqual(selected.rows[0].get_member('Key'),'first')

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

    def test_invalid_declarations_are_atomic_and_cache_eviction_is_not_a_quota(self):
        table = sample()
        table.columns.add('Extra')
        first, second = table.rows
        saved = table.indexes.add('Key')
        self.assertEqual(found(table, Key='a'), [first, second])
        warmed = table._search.cache[(0,)]
        for bad in ('Key,Missing', True):
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                table.indexes.add(bad)
            self.assertEqual(list(table.indexes), [saved])
            self.assertIs(table._search.cache[(0,)], warmed)
        keys = [('Second',), ('Amount',), ('Extra',), ('Key', 'Second'),
                ('Key', 'Amount'), ('Key', 'Extra'), ('Second', 'Amount'),
                ('Second', 'Extra'), ('Amount', 'Extra')]
        for fields in keys:
            table.indexes.add(','.join(fields))
        self.assertEqual(table._search.builds, 1)
        self.assertEqual(names(table), [['Key']] + [list(fields) for fields in keys])
        keys_with_values = {'Key': 'a', 'Second': D(1), 'Amount': D(1), 'Extra': None}
        for fields in keys:
            expected = [first, second] if set(fields) <= {'Key', 'Extra'} else [first]
            self.assertEqual(found(table, **{name: keys_with_values[name] for name in fields}), expected)
        self.assertLessEqual(len(table._search.cache), 8)
        self.assertIsNot(table._search.cache.get((0,)), warmed)
        self.assertEqual(len(table._search.declarations), 10)
        # Eviction changes retention, never public index state or epoch results.
        last = table.add()
        long_key = 'x' * 4097
        large_number = D('1e4097')
        last.set_member('Key', long_key)
        last.set_member('Second', large_number)
        self.assertEqual(found(table, Key=long_key, Second=large_number), [last])
        self.assertEqual(found(table, Key='a'), [first, second])
        self.assertEqual(len(table._search.declarations), 10)

    def test_key_replacement_and_row_removal_keep_other_declarations_live(self):
        table = sample()
        index = table.indexes.add('Key')
        second_index = table.indexes.add('Second')
        first, second = table.rows
        self.assertEqual(found(table, Key='a'), [first, second])
        self.assertEqual(found(table, Second=D(1)), [first])
        warmed = table._search.cache.copy()

        long_key = 'long' * 32
        first.set_member('Key', long_key)
        self.assertIs(table._search.cache[(0,)], warmed[(0,)])
        self.assertEqual(found(table, Key=long_key), [first])
        self.assertEqual(found(table, Key='a'), [second])
        self.assertEqual(found(table, Second=D(1)), [first])
        self.assertEqual(list(table.indexes), [index, second_index])

        table.indexes.delete(second_index)
        table.delete(first)
        self.assertEqual(found(table, Key=long_key), [])
        self.assertEqual(found(table, Key='a'), [second])
        table.clear()
        self.assertEqual(found(table, Key='a'), [])
        replacement = table.add()
        replacement.set_member('Key', long_key)
        self.assertEqual(found(table, Key=long_key), [replacement])
        self.assertEqual(list(table.indexes), [index])

    def test_failed_bulk_column_selection_preserves_cells_and_index_order(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Key')
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        before = [list(row) for row in table]
        self.assertEqual(found(table, Key='a'), [second, first])

        for operation in (lambda: table.fill_values('z', 'Key,Missing'),
                          lambda: table.load_column(array('b', 'b'), 'Missing')):
            with self.assertRaisesRegex(ValueError, 'column not found'):
                operation()
            self.assertEqual([list(row) for row in table], before)
            self.assertEqual(found(table, Key='a'), [second, first])
            self.assertEqual(found(table, Key='a', Second=D(1)), [first])

        table.fill_values('z', 'Key,Key')
        self.assertEqual(found(table, Key='a'), [])
        self.assertEqual(found(table, Key='z'), [first, second])
        self.assertEqual(found(table, Key='z', Second=D(1)), [first])
        self.assertEqual([row.get_member('Second') for row in table], [D(1), D(2)])

    def test_equal_decimal_rewrite_refreshes_lazy_positions_and_live_value(self):
        table = BSLValueTable()
        for name in ('A', 'B', 'C'):
            table.columns.add(name)
        row = table.add()
        row.set_member('A', D(1))
        row.set_member('B', 'x')
        row.set_member('C', 'xxxx')
        index = table.indexes.add('A,B')
        self.assertEqual(found(table, A=D(1), B='x'), [row])
        warmed = table._search.cache[(0, 1)]
        value = D('1.000')
        row.set_member('A', value)
        self.assertIs(row.get_member('A'), value)
        self.assertIs(table._search.cache[(0, 1)], warmed)  # No eager buckets rebuilt.
        self.assertEqual(found(table, A=D(1), B='x'), [row])
        self.assertIsNot(table._search.cache[(0, 1)], warmed)
        self.assertEqual(tuple(table._search.cache[(0, 1)].buckets.values()), ((0,),))
        table.indexes.add('C')
        table.columns.delete('B')
        self.assertEqual(list(index), ['A'])
        self.assertEqual(names(table), [['A'], ['C']])
        other = table.add()
        other.set_member('A', D('1.00'))
        table.delete(row)
        self.assertEqual(found(table, A=D(1)), [other])
        self.assertEqual(tuple(table._search.cache[(0,)].buckets.values()), ((0,),))

    def test_column_delete_preflights_and_remaps_warmed_index_positions(self):
        table = sample()
        compound = table.indexes.add('Key,Second')
        amount = table.indexes.add('Amount')
        first, second = table.rows
        before = [list(row) for row in table]
        self.assertEqual(found(table, Key='a', Second=D(1)), [first])
        self.assertEqual(found(table, Amount=D(2)), [second])

        with self.assertRaisesRegex(ValueError, 'column not found'):
            table.columns.delete('Missing')
        self.assertEqual(list(table.indexes), [compound, amount])
        self.assertEqual([list(row) for row in table], before)
        self.assertEqual(found(table, Key='a', Second=D(1)), [first])
        self.assertEqual(found(table, Amount=D(2)), [second])

        table.columns.delete('Second')
        self.assertEqual(names(table), [['Key'], ['Amount']])
        self.assertEqual(list(table.indexes), [compound, amount])
        self.assertEqual(table._search.declarations, {(0,), (1,)})
        self.assertEqual([list(row) for row in table], [['a', D(1)], ['a', D(2)]])
        self.assertEqual(found(table, Key='a'), [first, second])
        self.assertEqual(found(table, Amount=D(2)), [second])

    def test_invalid_bulk_argument_shapes_preserve_cells_and_warmed_bucket_order(self):
        table = sample()
        table.indexes.add('Key')
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        before = [list(row) for row in table]
        self.assertEqual(found(table, Key='a'), [second, first])
        warmed = table._search.cache[(0,)]

        for operation in (lambda: table.fill_values('xxx', array('Key')),
                          lambda: table.load_column(('xx', 'xxx'), 'Key')):
            with self.assertRaises(TypeError):
                operation()
            self.assertEqual([list(row) for row in table], before)
            self.assertEqual(found(table, Key='a'), [second, first])
            self.assertIs(table._search.cache[(0,)], warmed)

        table.load_column(array('xx', 'xxx'), 'Key')
        self.assertEqual(found(table, Key='xx'), [first])
        self.assertEqual(found(table, Key='xxx'), [second])
        self.assertEqual(found(table, Key='a'), [])
        self.assertEqual([list(row) for row in table], [['xx', D(1), D(1)], ['xxx', D(2), D(2)]])

    def test_bulk_writes_preserve_unselected_long_compound_keys(self):
        table = sample()
        first, second = table.rows
        long_number = D('1' * 100)
        first.set_member('Second', long_number)
        table.indexes.add('Key,Second')
        self.assertEqual(found(table, Key='a', Second=long_number), [first])

        table.fill_values('z', 'Key')
        self.assertEqual(found(table, Key='a', Second=long_number), [])
        self.assertEqual(found(table, Second=long_number, Key='z'), [first])
        self.assertEqual(found(table, Key='z', Second=D(2)), [second])
        table.load_column(array('written'), 'Key')
        self.assertEqual(found(table, Key='written', Second=long_number), [first])
        self.assertEqual(found(table, Key='z', Second=long_number), [])
        self.assertEqual(found(table, Key='z', Second=D(2)), [second])
        self.assertIs(first.get_member('Second'), long_number)

    def test_duplicate_fields_are_preserved_but_do_not_supply_a_distinct_lookup(self):
        table = sample()
        saved = table.indexes.add('Key,Key')
        self.assertEqual(list(saved), ['Key', 'Key'])
        self.assertEqual(found(table, Key='a'), table.rows)
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [first, second])
        for columns in ('Key', None, ''):
            self.assertIs(table.find('a', columns), first)
        self.assertEqual(table._search.builds, 0)
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
        self.assertEqual(names(table), [[], [], []])
        self.assertEqual(table._search.declarations, set())
        self.assertEqual(table._search.cache, {})
        self.assertEqual(table._search.builds, 0)

    def test_indexed_insert_updates_positions_without_reordering_matching_writes(self):
        # This is a lazy-runtime identity and invalidation invariant, not a
        # native ordering claim about insertion into an active index.
        for position, physical in ((D(0), 0), (D(1), 1), (D('0.9'), 0), (D(2), 2)):
            with self.subTest(position=position):
                table = sample()
                table.indexes.add('Key')
                first, second = table.rows
                first.set_member('Key', 'a')
                self.assertEqual(found(table, Key='a'), [second, first])
                warmed = table._search.cache[(0,)]
                inserted = table.insert(position)
                self.assertIs(table.rows[physical], inserted)
                self.assertEqual(found(table, Key='a'), [second, first])
                self.assertIsNot(table._search.cache[(0,)], warmed)
                self.assertEqual(found(table, Key=None), [inserted])
                inserted.set_member('Key', 'a')
                self.assertEqual(found(table, Key='a'), [second, first, inserted])
                self.assertIs(table.find('a', 'Key'), second)

    def test_indexed_copy_empty_column_string_is_an_explicit_unindexed_selection(self):
        table = sample()
        saved = table.indexes.add('Key')
        self.assertEqual(found(table, Key='a'), table.rows)
        warm = table._search.cache[(0,)]
        explicit = table.copy(None, '')
        self.assertEqual(list(table.indexes), [saved])
        self.assertIs(table._search.cache[(0,)], warm)
        self.assertEqual(names(explicit), [])
        self.assertEqual([list(row) for row in explicit], [list(row) for row in table])
        self.assertIsNot(explicit.rows[0], table.rows[0])
        self.assertEqual(names(table.copy()), [['Key']])
        self.assertEqual(names(table.copy(None, 'Key,Second,Amount')), [])
        table.indexes.clear()
        self.assertEqual([list(row) for row in table.copy(None, '')], [list(row) for row in table])

    def test_implicit_find_keeps_physical_order_when_explicit_index_diverges(self):
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
                warm = table._search.cache[(0,)]
                for columns in (None, ''):
                    self.assertIs(table.find('a', columns), first)
                self.assertIs(table._search.cache[(0,)], warm)
                self.assertEqual(table.rows, [first, second])
                self.assertEqual(found(table, Key='a'), [second, first])
                table.sort('Key')
                self.assertIs(table.find('a', 'Key'), first)
                self.assertIs(table.find('a'), first)
                self.assertIs(table.find('a', ''), first)
                self.assertIsNone(table.find('missing'))

    def test_unsupported_key_uses_scan_until_a_valid_lazy_rebuild(self):
        table = sample()
        table.rows[1].set_member('Key', D('NaN'))
        index = table.indexes.add('Key')
        self.assertEqual(table._search.cache, {})
        self.assertEqual(found(table, Key='a'), [table.rows[0]])
        unavailable = table._search.cache[(0,)]
        self.assertIsNone(unavailable.buckets)
        self.assertEqual(found(table, Key='missing'), [])
        self.assertIs(table._search.cache[(0,)], unavailable)
        self.assertEqual(names(table), [['Key']])
        self.assertTrue(table.rows[1].get_member('Key').is_nan())
        table.rows[1].set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), table.rows)
        self.assertIsNot(table._search.cache[(0,)], unavailable)
        self.assertIsNotNone(table._search.cache[(0,)].buckets)
        self.assertIs(next(iter(table.indexes)), index)

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
        with patch('yadinassi.collections.value_tables._index_token', wraps=_index_token) as tokenize:
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
            for column in ('Key', 'Second'):
                for value in values:
                    actual = found(table, **{column: value})
                    expected = [row for row in table.rows if equal(row.get_member(column), value)]
                    self.assertEqual(set(actual), set(expected))
                    self.assertEqual(len(actual), len(expected))
            pairs = [(row.get_member('Key'), row.get_member('Second')) for row in table.rows]
            pairs.append(('missing', 'missing'))
            # Keep False and Decimal(0) as distinct lookup predicates.
            predicates = {(type(key), key, type(second), second) for key, second in pairs}
            for _, key, _, second in predicates:
                actual = found(table, Key=key, Second=second)
                expected = [row for row in table.rows if equal(row.get_member('Key'), key)
                            and equal(row.get_member('Second'), second)]
                self.assertEqual(set(actual), set(expected))
                self.assertEqual(len(actual), len(expected))
        self.assertEqual(names(table), [['Key'], ['Second'], ['Key', 'Second'], ['Key', 'Key'], []])
        self.assertEqual(table._search.declarations, {(0,), (1,), (0, 1)})

    def test_only_current_rows_remain_referenced(self):
        import gc
        import weakref

        table = sample()
        table.indexes.add('Key')
        first, second = table.rows
        first.set_member('Key', 'b')
        first.set_member('Key', 'a')
        self.assertEqual(found(table, Key='a'), [second, first])
        entry = table._search.cache[(0,)]
        old, remaining = weakref.ref(first), weakref.ref(second)
        table.delete(first)
        del first
        gc.collect()
        self.assertIsNone(old())  # Even with the stale cache entry alive.
        self.assertEqual(found(table, Key='a'), [second])
        self.assertIsNot(table._search.cache[(0,)], entry)
        self.assertEqual(tuple(table._search.cache[(0,)].buckets.values()), ((0,),))
        table.clear()
        del second
        gc.collect()
        self.assertIsNone(remaining())
        self.assertEqual(found(table, Key='a'), [])


if __name__ == '__main__':
    unittest.main()
