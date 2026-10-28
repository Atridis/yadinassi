"""LoadColumn native slice plus explicitly local integrity/resource limits."""
from decimal import Decimal as D
import unittest
from unittest import mock
from yadinassi import Interpreter, BSLError
import yadinassi.value_trees as tree
from yadinassi.values import BSLArray, BSLFixedArray, NULL
from yadinassi.structures import BSLStructure
from yadinassi.type_descriptions import BSLTypeDescription


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


class LoadColumnTests(unittest.TestCase):
    def setUp(self):
        self.tree = tree.BSLValueTree()
        self.id = self.tree.columns.add('Id')
        self.value = self.tree.columns.add('Value')
        self.a = self.tree.rows.add()
        self.b = self.tree.rows.add()
        self.c = self.a.rows.add()
        for row, value in ((self.a, 1), (self.b, 2), (self.c, 3)):
            row.set_member('Id', D(value))

    def test_local_prefix_short_long_empty_and_no_descendants(self):
        self.tree.rows.load_column(array(D(6)), 'Id')
        self.assertEqual([r.get_member('Id') for r in (self.a,self.b,self.c)], [D(6),D(2),D(3)])
        self.tree.rows.load_column(array(D(7),D(5),object()), 'Id')
        self.assertEqual([r.get_member('Id') for r in (self.a,self.b,self.c)], [D(7),D(5),D(3)])
        self.tree.rows.load_column(array(), 'Id')
        self.a.rows.load_column(array(D(4),D(6)), 'Id')
        self.assertEqual(self.c.get_member('Id'), D(4))
        self.c.rows.load_column(array(D(7)), 'Id')

    def test_casefold_own_column_and_method_local_fractional_selectors(self):
        for selector in ('iD', self.id, D(0), D('0.5'), D('-0.5')):
            self.tree.rows.load_column(array(D(6)), selector)
            self.assertEqual(self.a.get_member('Id'), D(6))
        for selector in (D(1), D('1.5'), D('1.9')):
            self.tree.rows.load_column(array(D(7)), selector)
            self.assertEqual(self.a.get_member('Value'), D(7))
        with self.assertRaises(TypeError): self.tree.rows.get(D('0.5'))
        with self.assertRaises(TypeError): self.tree.columns.get(D('0.5'))

    def test_array_only_and_exact_arity(self):
        for source in (BSLFixedArray(array()), 'bad', D(7), None, NULL, True, BSLStructure()):
            with self.assertRaises(TypeError): self.tree.rows.load_column(source, 'Id')
        for args in ((), (array(),), (array(), 'Id', True)):
            with self.assertRaises(TypeError): self.tree.rows.load_column(*args)

    def test_invalid_selector_even_empty_source_and_receiver(self):
        foreign = tree.BSLValueTree().columns.add('Id')
        for rows in (self.tree.rows, self.c.rows):
            for source in (array(), array(D(7))):
                for selector in ('missing', None, NULL, True, D(-1), D(2), foreign):
                    with self.subTest(selector=repr(selector)), self.assertRaises((ValueError,TypeError,IndexError)):
                        rows.load_column(source, selector)
        with self.assertRaises(ValueError): tree.BSLValueTree().rows.load_column(array(), 'Id')

    def test_typed_number_conversion_and_ignored_excess(self):
        col = self.tree.columns.add('Number', BSLTypeDescription('Number'))
        for source, expected in ((array(D(7),'bad'), [D(7),D(0)]),
                                 (array('bad',D(7)), [D(0),D(7)]),
                                 (array(D(7),None), [D(7),D(0)]),
                                 (array(D(6),D(7),object()), [D(6),D(7)])):
            self.tree.rows.load_column(source, col)
            self.assertEqual([self.a.cells[col],self.b.cells[col]], expected)

    def test_untyped_structure_aliases_and_membership_independence(self):
        cell = BSLStructure('Mark','base'); source = array(cell,D(7))
        self.tree.rows.load_column(source, 'Value')
        self.assertIs(self.a.cells[self.value], cell)
        cell.set_member('Mark','source')
        self.assertEqual(self.a.cells[self.value].get_member('Mark'),'source')
        self.a.cells[self.value].set_member('Mark','result')
        self.assertEqual(source.items[0].get_member('Mark'),'result')
        source.items.clear()
        self.assertIs(self.a.cells[self.value],cell)
        self.assertEqual(len(self.tree.rows.items),2)

    def test_procedure_aliases_and_expression_rejected_before_mutation(self):
        for alias in ('LoadColumn','lOaDcOlUmN','ЗагрузитьКолонку'):
            method=self.tree.rows.get_method(alias)
            self.assertFalse(method.returns_value)
            vm=Interpreter(lambda _:None)
            vm.variables['t']=self.tree;vm.variables['a']=array(D(7))
            with self.assertRaises(BSLError): vm.execute(f'X = T.Rows.{alias}(A,"Id");')
            self.assertEqual(self.a.get_member('Id'),D(1))
            vm.execute(f'T.Rows.{alias}(A,"Id");')
            self.assertEqual(self.a.get_member('Id'),D(7))
            self.a.set_member('Id',D(1))
        with self.assertRaises(ValueError): self.tree.get_method('LoadColumn')

    def test_unknown_selector_or_source_never_invokes_hooks(self):
        class Hostile:
            def __str__(self): raise AssertionError('str')
            def __eq__(self, other): raise AssertionError('eq')
            def __int__(self): raise AssertionError('int')
            def __iter__(self): raise AssertionError('iter')
        class Text(str):
            def casefold(self): raise AssertionError('casefold')
        for selector in (Hostile(),Text('Id')):
            with self.assertRaises(TypeError): self.tree.rows.load_column(array(),selector)
        with self.assertRaises(TypeError): self.tree.rows.load_column(Hostile(),'Id')
        opaque=Hostile();self.tree.rows.load_column(array(opaque),'Id')
        self.assertIs(self.a.cells[self.id],opaque)

    def test_local_numeric_text_and_work_resource_limits(self):
        for selector in (D('NaN'),D('sNaN'),D('Infinity'),D('1e999999999'),D('9'*10001)):
            with self.assertRaises((TypeError,ValueError,IndexError)):
                self.tree.rows.load_column(array(),selector)
        for constant, limit, selector in (('_MAX_SEARCH_TEXT',2,'Value'),
                ('_MAX_SEARCH_WORK',3,'Id'),('_MAX_COLUMNS',1,self.id),('_MAX_ROWS',1,self.id)):
            with mock.patch.object(tree,constant,limit), self.assertRaises(ValueError):
                self.tree.rows.load_column(array(D(7)),selector)
        with mock.patch.object(tree,'_MAX_ROWS',2), self.assertRaises(ValueError):
            self.c.rows.load_column(array(1,2,3), 'Id')

    def test_local_converter_failure_retains_written_prefix_only(self):
        # Synthetic converter failure, NOT a native LoadColumn behavior claim.
        original = tree._adjust
        def adjust(description, value):
            if value is None:
                raise ValueError('synthetic converter failure')
            return original(description, value)
        with mock.patch.object(tree, '_adjust', adjust), self.assertRaises(ValueError):
            self.tree.rows.load_column(array(D(7), None), 'Id')
        self.assertEqual(self.a.get_member('Id'), D(7))
        self.assertEqual(self.b.get_member('Id'), D(2))
        self.assertEqual(self.c.get_member('Id'), D(3))

    def test_deleted_rows_columns_and_corrupted_storage(self):
        for obj, field, value in ((self.tree.rows,'items',tuple(self.tree.rows.items)),
                (self.tree.columns,'items',(self.id,)),(self.a,'cells',[]),
                (self.a,'collection',self.c.rows)):
            with mock.patch.object(obj,field,value),self.assertRaises(ValueError):
                self.tree.rows.load_column(array(D(7)),self.id)
        source=array(D(7));source.items=(D(7),)
        with self.assertRaises(ValueError): self.tree.rows.load_column(source,self.id)
        foreign=tree.BSLValueTree().columns.add('Id')
        with mock.patch.object(self.tree.columns,'items',[foreign]),self.assertRaises(ValueError):
            self.tree.rows.load_column(array(D(7)),self.id)
        self.tree.rows.delete(self.a)
        with self.assertRaises(ValueError): self.a.rows.load_column(array(),self.id)
        self.tree.columns.delete(self.id)
        with self.assertRaises(ValueError): self.tree.rows.load_column(array(),self.id)


if __name__ == '__main__': unittest.main()
