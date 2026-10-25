"""Standalone local contract, not a substitute for a real 1C checkpoint."""
from decimal import Decimal as D
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.value_trees import BSLValueTree
from yadinassi.type_descriptions import BSLTypeDescription


class ValueTreeTests(unittest.TestCase):
    def setUp(self):
        self.tree = BSLValueTree()
        self.col = self.tree.columns.add('Name')
        self.root = self.tree.rows.add()
        self.child = self.root.rows.add()

    def test_shared_columns_and_case_insensitive_cells(self):
        col = self.tree.columns.insert(D(0), 'N', BSLTypeDescription('Number'))
        self.assertEqual(self.child.get(D(0)), D(0))
        self.child.set_index('n', D(12))
        col.set_member('Name', 'Amount')
        self.assertEqual(self.child.get_member('AMOUNT'), D(12))
        self.assertEqual(list(self.root), [D(0), None])
        self.tree.columns.delete(col)
        self.assertEqual(list(self.child), [None])

    def test_hierarchy_and_local_counts(self):
        self.assertIs(self.child.owner(), self.tree)
        self.assertEqual(self.child.level(), D(1))
        self.assertEqual(self.root.level(), D(0))
        self.assertIs(self.child.get_member('Parent'), self.root)
        self.assertIs(self.root.rows.get_member('Parent'), self.root)
        self.assertIsNone(self.tree.rows.get_member('Parent'))
        self.assertEqual(self.tree.rows.count(), D(1))
        self.assertEqual(self.tree.rows.index_of(self.child), D(-1))
        self.assertEqual(list(self.root.rows), [self.child])

    def test_insert_delete_and_clear_subtree(self):
        extra = self.tree.rows.insert(D(0))
        self.assertIs(self.tree.rows.get(D(1)), self.root)
        grandchild = self.child.rows.add()
        self.tree.rows.delete(self.root)
        self.assertEqual(list(self.tree._all_rows), [extra])
        for row in (self.root, self.child, grandchild):
            with self.assertRaises(ValueError):
                row.get(D(0))
            with self.assertRaises(ValueError):
                row.rows.add()
        self.tree.rows.clear()
        self.assertEqual(self.tree._all_rows, {})

    def test_wrong_collection_and_foreign_rows(self):
        other = BSLValueTree().rows.add()
        for row in (other, self.child):
            with self.assertRaises(ValueError):
                self.tree.rows.delete(row)
        self.assertEqual(self.tree.rows.count(), D(1))

    def test_strict_indices_fail_without_mutation(self):
        for value in (D(-1), D(2), D('0.5'), D('NaN'), True, '0'):
            with self.assertRaises((ValueError, TypeError, IndexError)):
                self.tree.rows.insert(value)
        self.assertEqual(self.tree.rows.count(), D(1))

    def test_global_budgets_and_transactionality(self):
        with patch('yadinassi.value_trees._MAX_ROWS', 2):
            with self.assertRaises(ValueError):
                self.child.rows.add()
        with patch('yadinassi.value_trees._MAX_CELLS', 3):
            with self.assertRaises(ValueError):
                self.tree.columns.add('Extra')
        self.assertEqual(len(self.tree.columns.items), 1)
        self.assertEqual(len(self.tree._all_rows), 2)

    def test_depth_budget_and_iterative_clear(self):
        row = self.child
        with patch('yadinassi.value_trees._MAX_DEPTH', 2):
            row = row.rows.add()
            with self.assertRaises(ValueError):
                row.rows.add()
        self.tree.rows.clear()
        self.assertFalse(self.tree._all_rows)

    def test_reserved_and_read_only_properties(self):
        for name in ('Rows', 'Parent', 'Строки', 'Родитель'):
            with self.assertRaises(ValueError):
                self.tree.columns.add(name)
            with self.assertRaises(ValueError):
                self.col.set_member('Name', name)
            with self.assertRaises(ValueError):
                self.child.set_member(name, None)
        with self.assertRaises(ValueError):
            self.col.set_member('ValueType', None)
        with self.assertRaises(ValueError):
            self.col.get_member('__dict__')


class ValueTreeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('t = New ValueTree(); c = t.Columns.Add("Name"); '
                        'r = t.Rows.Add(); child = r.Rows.Add();')

    def test_bilingual_types_and_construction(self):
        for expr, name in [('t','ValueTree'), ('c','ValueTreeColumn'),
                           ('t.Columns','ValueTreeColumnCollection'),
                           ('r','ValueTreeRow'), ('r.Rows','ValueTreeRowCollection')]:
            self.assertTrue(self.vm.execute(f'(TypeOf({expr}) = Type("{name}"))'))
        self.vm.execute('other = New("ДеревоЗначений");')
        self.assertEqual(self.vm.execute('other.Строки.Количество()'), D(0))
        for name in ('ValueTreeRow', 'ValueTreeColumn', 'ValueTreeRowCollection'):
            with self.assertRaises(BSLError):
                self.vm.execute(f'x = New {name}();')

    def test_iteration_and_references(self):
        self.vm.execute('Procedure Put(x) x = "changed"; EndProcedure '
                        'Put(child.Name); Put(r[0]); Put(c.Title); '
                        'n=0; For Each x In t.Rows Do n=n+1; EndDo; '
                        'For Each x In child Do n=n+1; EndDo;')
        self.assertEqual(self.vm.execute('child["NAME"]'), 'changed')
        self.assertEqual(self.vm.execute('r.Get(0)'), 'changed')
        self.assertEqual(self.vm.execute('c.Title'), 'changed')
        self.assertEqual(self.vm.execute('n'), D(2))

    def test_omitted_column_arguments(self):
        self.vm.execute('n=t.Columns.Add("N", , "Number", 12); '
                        'cols=t.Columns; z=cols.Insert(0,"Z", , "Z title");')
        self.assertEqual(self.vm.execute('n.Title'), 'Number')
        self.assertEqual(self.vm.execute('z.Width'), D(0))

    def test_host_access_and_unsupported_features_fail_closed(self):
        for expr in ('t._all_rows','r.cells','r.tree','c.table','t.Rows.items',
                     't.Copy()', 't.Rows.Find(1)', 't.ChooseRow()',
                     'ValueToStringInternal(t)', 'ValueToStringInternal(Type("ValueTree"))',
                     'XMLString(t)', 't[0]', 't.Rows[0]=r;'):
            with self.subTest(expr=expr), self.assertRaises(BSLError):
                self.vm.execute(expr)

    def test_all_tree_objects_and_type_records_have_explicit_codec_rejection(self):
        for value in ('t', 't.Rows', 'r', 't.Columns', 'c'):
            for expr in (value, 'TypeOf(' + value + ')'):
                with self.subTest(expr=expr), self.assertRaisesRegex(BSLError, 'сериализация ДеревоЗначений'):
                    self.vm.execute('ValueToStringInternal(' + expr + ')')
        self.vm.execute('a=New Array; a.Add(t);')
        with self.assertRaisesRegex(BSLError, 'сериализация ДеревоЗначений'):
            self.vm.execute('ValueToStringInternal(a)')

    def test_fixed_string_defaults_share_and_have_aggregate_budget(self):
        self.vm.execute('q=New StringQualifiers(100,AllowedLength.Fixed); '
                        'd=New TypeDescription("String",,q); '
                        'b=t.Columns.Add("Big",d); later=t.Rows.Add();')
        root = self.vm.execute('r.Big')
        self.assertIs(root, self.vm.execute('child.Big'))
        self.assertIs(root, self.vm.execute('later.Big'))
        with patch('yadinassi.value_trees._MAX_DEFAULT_TEXT', 150):
            with self.assertRaises(BSLError):
                self.vm.execute('t.Columns.Add("TooBig",d);')
        self.assertEqual(self.vm.execute('t.Columns.Count()'), D(2))
        self.assertEqual(self.vm.execute('r.Big'), ' ' * 100)

    def test_required_holes_reject_before_effects(self):
        self.vm.execute('Var hits; hits=0; Function Touch() hits=hits+1; Return 1; EndFunction')
        with self.assertRaises(BSLError):
            self.vm.execute('t.Columns.Insert(,Touch());')
        self.assertEqual(self.vm.execute('hits'), D(0))


if __name__ == '__main__':
    unittest.main()
