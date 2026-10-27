"""Generic search model and explicit local limits, not extra native witnesses."""
from decimal import Decimal as D, localcontext, InvalidOperation
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi import value_trees as trees
from yadinassi.values import NULL
from test_value_tree_findrows import setup


class FindGenericModel(unittest.TestCase):
    def setUp(self):
        self.tree, self.nodes = setup()
        self.a, self.b, self.b1, self.a1, self.a2, self.a11 = self.nodes

    def test_first_row_depth_first_not_insertion_or_breadth_first(self):
        for row in (self.a, self.b, self.a1): row.set_member('Key','no')
        self.assertIs(self.tree.rows.find('yes','Key',True),self.a11)
        self.assertIsNone(self.tree.rows.find('yes','Key'))
        self.assertIsNone(self.tree.rows.find('yes','Key',False))
        self.assertIs(self.a.rows.find('yes','Key'),self.a2)
        self.assertIs(self.a.rows.find('yes','Key',True),self.a11)
        self.assertIsNone(self.a11.rows.find('yes','Key',True))
        first=self.tree.rows.insert(D(0));first.set_member('Key','yes')
        self.assertIs(self.tree.rows.find('yes','Key',True),first)

    def test_measured_scalar_flags_recurse_and_unmeasured_forms_fail_closed(self):
        for row in (self.a, self.b, self.a1): row.set_member('Key','no')
        for flag in (D(1), 'True'):
            self.assertIs(self.tree.rows.find('yes','Key',flag), self.a11)
        for flag in (D(0), D(2), D('0.5'), D('NaN'), D('sNaN'),
                     D('Infinity'), '', 'true', 'False', ' True ', None, NULL):
            with self.assertRaises((TypeError, ValueError)):
                self.tree.rows.find('yes','Key',flag)

    def test_row_major_any_selected_column_and_complete_schema_validation(self):
        self.a.set_member('Key','no');self.a.set_member('Other','yes')
        for columns in ('Key,Other','Other,Key',' key , OTHER ','Key,,Other','Key,Key,Other'):
            self.assertIs(self.tree.rows.find('yes',columns,True),self.a)
        self.assertIs(self.tree.rows.find('yes','Key',True),self.a1)
        for receiver in (self.tree.rows,self.a11.rows):
            for columns in ('Missing','Key,Missing','Missing,Key'):
                with self.assertRaises(ValueError):receiver.find('yes',columns,True)

    def test_omitted_empty_undefined_columns_all_and_empty_schema(self):
        self.assertIs(self.tree.rows.find(D(7)),self.a)
        for columns in ('',None):self.assertIs(self.tree.rows.find(D(7),columns,True),self.a)
        empty=trees.BSLValueTree()
        self.assertIsNone(empty.rows.find('yes'))
        empty.columns.add('Key')
        self.assertIsNone(empty.rows.find('yes','Key',True))

    def test_query_scalars_type_sensitive_and_text_exact(self):
        values=(D('7.25'),True,'7.25','Mixed ',None,NULL)
        for row,value in zip(self.nodes,values):row.set_member('Key',value)
        for row,value in zip(self.nodes,values):
            self.assertIs(self.tree.rows.find(value,'Key',True),row)
        for value in ('mixed ','Mixed',D(1),False):
            self.assertIsNone(self.tree.rows.find(value,'Key',True))

    def test_reference_is_original_live_row_both_directions(self):
        self.a1.set_member('Key','unique')
        result=self.tree.rows.find('unique','Key',True)
        self.assertIs(result,self.a1)
        result.set_member('Other',D(42))
        self.assertEqual(self.a1.get_member('Other'),D(42))
        self.a1.set_member('Other',D(43))
        self.assertEqual(result.get_member('Other'),D(43))
        self.assertIs(result.owner(),self.tree)
        self.assertIs(result.parent,self.a)

    def test_aliases_arity_receivers_and_invalid_columns(self):
        output=[];vm=Interpreter(output.append)
        vm.execute('T=New ValueTree; T.Columns.Add("Key"); R=T.Rows.Add(); R.Key="hit"; Message(T.Rows.Find("hit","Key") = R); Message(T.Строки.Найти("hit","Key") = R);')
        self.assertEqual(output,['Да','Да'])
        for expr in ('T.Rows.Find()', 'T.Rows.Find("hit","Key",True,1)', 'T.Find("hit")', 'R.Find("hit")'):
            with self.assertRaises(BSLError):vm.execute(expr)
        for columns in (D(1),True,[],{},NULL):
            with self.assertRaises(TypeError):self.tree.rows.find('yes',columns)


class FindLocalPolicy(unittest.TestCase):
    def setUp(self):
        self.tree,self.nodes=setup()

    def test_hostile_values_names_and_flags_never_invoke_hooks(self):
        calls=[]
        class Hostile:
            def __eq__(self,other):calls.append('eq');raise AssertionError
            def __str__(self):calls.append('str');raise AssertionError
            def __bool__(self):calls.append('bool');raise AssertionError
            def __hash__(self):calls.append('hash');raise AssertionError
        class Text(str):
            def casefold(self):calls.append('casefold');raise AssertionError
            def strip(self):calls.append('strip');raise AssertionError
        hostile=Hostile()
        for query in (hostile,Text('yes'),[],{},D('NaN'),D('sNaN'),D('Infinity')):
            with self.assertRaises((TypeError,ValueError)):self.tree.rows.find(query,'Key',True)
        for columns in (hostile,Text('Key')):
            with self.assertRaises(TypeError):self.tree.rows.find('yes',columns,True)
        with self.assertRaises(TypeError):self.tree.rows.find('yes','Key',hostile)
        self.nodes[0].set_member('Key',hostile)
        with self.assertRaises(TypeError):self.tree.rows.find('no','Key',True)
        self.assertEqual(calls,[])

    def test_selected_cells_validated_before_short_circuit_without_mutation(self):
        bad=object();self.nodes[0].set_member('Other',bad)
        with self.assertRaises(TypeError):self.tree.rows.find('yes','Key,Other',True)
        self.assertIs(self.tree.rows.find('yes','Key',True),self.nodes[0])
        self.assertIs(self.nodes[0].get_member('Other'),bad)

    def test_search_text_number_and_work_limits_are_preflight_bounded(self):
        for value in ('x'*(trees._MAX_SEARCH_TEXT+1),D('9'*4097)):
            with self.assertRaises(ValueError):self.tree.rows.find(value,'Key',True)
        with self.assertRaises(ValueError):self.tree.rows.find('yes','x'*(trees._MAX_SEARCH_TEXT+1),True)
        with self.assertRaises(ValueError):self.tree.rows.find('yes','Key,'*trees._MAX_COLUMNS,True)
        with patch.object(trees,'_MAX_SEARCH_WORK',2):
            with self.assertRaises(ValueError):self.tree.rows.find('yes','Key',True)
        with patch.object(trees,'_MAX_ROWS',1):
            with self.assertRaises(ValueError):self.tree.rows.find('absent','Key',True)
        with patch.object(trees,'_MAX_CELLS',1):
            with self.assertRaises(ValueError):self.tree.rows.find('absent','Key,Other',True)

    def test_decimal_validation_preserves_ambient_flags(self):
        for initial in (False,True):
            with localcontext() as context:
                context.flags[InvalidOperation]=initial
                before=dict(context.flags)
                for query in (D('NaN'),D('sNaN'),D('Infinity'),D('9'*4097)):
                    with self.assertRaises(ValueError):self.tree.rows.find(query,'Key',True)
                self.assertEqual(dict(context.flags),before)
        for query in (D('1e999999'),D('1e-999999')):
            self.nodes[0].set_member('Key',query)
            self.assertIs(self.tree.rows.find(query,'Key',True),self.nodes[0])

    def test_deleted_and_corrupt_rows_fail_closed(self):
        child=self.nodes[0].rows
        self.tree.rows.delete(self.nodes[0])
        with self.assertRaises(ValueError):child.find('yes','Key',True)
        other=trees.BSLValueTree();foreign=other.rows.add()
        self.tree.rows.items.insert(0,foreign)
        with self.assertRaises(ValueError):self.tree.rows.find('yes','Key',True)

    def test_corrupt_container_hooks_are_not_called(self):
        calls=[]
        class Mapping(dict):
            def __getitem__(self,key):calls.append('getitem');raise AssertionError
        class Items(list):
            def __iter__(self):calls.append('iter');raise AssertionError
            def __len__(self):calls.append('len');raise AssertionError
        row=self.nodes[0]
        old=row.cells;row.cells=Mapping(old)
        with self.assertRaises(ValueError):self.tree.rows.find('yes','Key',True)
        row.cells=old
        old=self.tree.rows.items;self.tree.rows.items=Items(old)
        with self.assertRaises(ValueError):self.tree.rows.find('yes','Key',True)
        self.tree.rows.items=old
        old=self.tree.columns.items;self.tree.columns.items=Items(old)
        with self.assertRaises(ValueError):self.tree.rows.find('yes','Key',True)
        self.tree.columns.items=old
        row.rows.items=Items(row.rows.items)
        with self.assertRaises(ValueError):self.tree.rows.find('absent','Key',True)
        self.assertEqual(calls,[])

    def test_depth_guard_and_iterative_traversal(self):
        tree=trees.BSLValueTree();tree.columns.add('Key');row=tree.rows.add();row.set_member('Key','no')
        for _ in range(trees._MAX_DEPTH):
            row=row.rows.add();row.set_member('Key','no')
        row.set_member('Key','deep')
        self.assertIs(tree.rows.find('deep','Key',True),row)
        with patch.object(trees,'_MAX_DEPTH',2):
            with self.assertRaises(ValueError):tree.rows.find('deep','Key',True)


if __name__=='__main__':unittest.main()
