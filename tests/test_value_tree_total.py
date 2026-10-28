"""Local Total safety/extensions; native semantic evidence is in native32 tests."""
from decimal import Decimal as D, localcontext, Inexact, Rounded, InvalidOperation, ROUND_FLOOR
import unittest
from unittest import mock
from yadinassi import Interpreter, BSLError
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRowCollection as Rows
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.values import NULL


def fixture(values=(), types=None):
    tree=BSLValueTree();column=tree.columns.add('N',None if types is None else BSLTypeDescription(types))
    for value in values:
        tree.rows.add().set_member('N',value)
    return tree,column


def snapshot(tree):
    return (id(tree.columns),tuple(id(c) for c in tree.columns.items),
            tuple((id(r),id(r.collection),id(r.rows),id(r.parent),r.depth,
                   tuple((id(c),id(v)) for c,v in r.cells.items()),tuple(id(child) for child in r.rows.items))
                  for r in tree._all_rows),tuple(id(r) for r in tree.rows.items))


class TreeTotalTests(unittest.TestCase):
    def test_local_recursive_and_child_scope_preserve_every_view(self):
        tree,column=fixture((D(2),D(3)))
        a=tree.rows.items[0];d=a.rows.add();d.set_member('N',D(5));e=a.rows.add();e.set_member('N',D(11))
        f=d.rows.add();f.set_member('N',D(7));before=snapshot(tree)
        for recursive,root,child in ((False,5,16),(True,28,23),(D(1),28,23),('True',28,23)):
            self.assertEqual(tree.rows.total('N',recursive),D(root));self.assertEqual(a.rows.total(column,recursive),D(child))
        self.assertEqual(tree.rows.total('n'),D(5));self.assertEqual(snapshot(tree),before)

    def test_only_measured_descriptor_families_and_conversion_policies(self):
        for types,values,expected in ((None,[D(2),'3',True,None,NULL],D(2)),
                ('Number',[D('1.25'),D('2.5')],D('3.75')),('String',['2','3'],D(5)),
                ('String',['2','x'],D(2)),('Boolean',[True,False,True],D(2)),
                ('Number,String',[D(2),'3'],D(2)),('String,Boolean',['2',True],None)):
            tree,_=fixture(values,types);before=snapshot(tree)
            self.assertEqual(tree.rows.total('N'),expected);self.assertEqual(snapshot(tree),before)
        for types in ('Date','Null','Number,Boolean','Number,String,Boolean'):
            tree,_=fixture(types=types)
            with self.assertRaises((ValueError,TypeError)):tree.rows.total('N')

    def test_selector_method_local_fraction_truncation_not_move(self):
        tree,column=fixture((D(2),D(3)))
        for selector in ('N','n',D(0),D('.5'),D('-.5'),column):
            self.assertEqual(tree.rows.total(selector),D(5))
        foreign,fc=fixture();deleted=tree.columns.add('Deleted');tree.columns.delete(deleted)
        before=snapshot(tree)
        for selector in (True,False,None,NULL,'','missing',D(-1),D(1),fc,deleted):
            with self.subTest(selector=type(selector)), self.assertRaises((ValueError,TypeError,IndexError)):
                tree.rows.total(selector)
            self.assertEqual(snapshot(tree),before)
        with self.assertRaises(IndexError):tree.rows.move(D('-.5'),D(0))

    def test_empty_receiver_still_validates_column_and_flag(self):
        for types in (None,'Number'):
            tree,_=fixture(types=types)
            self.assertEqual(tree.rows.total('N'),D(0))
            for selector in ('missing','',None,True):
                with self.assertRaises((ValueError,TypeError)):tree.rows.total(selector)
            for flag in (None,NULL,D(0),D(2),D('.5'),'False','true',object()):
                with self.assertRaises((ValueError,TypeError)):tree.rows.total('N',flag)

    def test_exact_arithmetic_is_independent_of_all_ambient_context_settings(self):
        large=D('10000000000000000000000000000')
        for values,expected in (([large,D(1)],D('10000000000000000000000000001')),
                                ([large,D(1),large.copy_negate()],D(1)),([D('.1'),D('.2')],D('.3'))):
            tree,_=fixture(values);before=snapshot(tree)
            with localcontext() as context:
                context.prec=2;context.Emax=2;context.Emin=-2;context.rounding=ROUND_FLOOR;context.clamp=1
                for signal in context.traps:context.traps[signal]=True
                context.flags[Inexact]=True;context.flags[Rounded]=True
                old_flags=dict(context.flags);old_traps=dict(context.traps)
                self.assertEqual(tree.rows.total('N'),expected)
                self.assertEqual(dict(context.flags),old_flags);self.assertEqual(dict(context.traps),old_traps)
                self.assertEqual((context.prec,context.Emax,context.Emin,context.rounding,context.clamp),(2,2,-2,ROUND_FLOOR,1))
            self.assertEqual(snapshot(tree),before)

    def test_invalid_string_zero_does_not_leak_decimal_flags(self):
        tree,_=fixture(['2','x'],'String')
        with localcontext() as context:
            context.clear_flags();context.traps[InvalidOperation]=False
            self.assertEqual(tree.rows.total('N'),D(2));self.assertFalse(any(context.flags.values()))

    def test_nonfinite_huge_coefficient_exponents_and_work_are_bounded(self):
        for value in (D('NaN'),D('sNaN'),D('Infinity'),D('9'*4097),D('1e4097'),D('1e-4097')):
            tree,_=fixture();tree.rows.add().cells[tree.columns.items[0]]=value;before=snapshot(tree)
            with self.assertRaises(ValueError):tree.rows.total('N')
            self.assertEqual(snapshot(tree),before)
        tree,_=fixture(['9'*4097],'String')
        with self.assertRaises(ValueError):tree.rows.total('N')
        tree,_=fixture([D('1e4096'),D('1e-4096')])
        with mock.patch('yadinassi.value_trees._MAX_TOTAL_PRECISION',10),self.assertRaises(ValueError):tree.rows.total('N')
        tree,_=fixture([D(1),D(2),D(3)])
        for name,bound in (('_MAX_ROWS',2),('_MAX_CELLS',2),('_MAX_SEARCH_WORK',2)):
            with mock.patch('yadinassi.value_trees.'+name,bound),self.assertRaises(ValueError):tree.rows.total('N')

    def test_opaque_untyped_values_are_ignored_without_host_hooks(self):
        class Poison:
            def __str__(self):raise AssertionError('str hook')
            def __eq__(self,other):raise AssertionError('eq hook')
            def __int__(self):raise AssertionError('int hook')
        tree,column=fixture([D(2)]);tree.rows.add().cells[column]=Poison()
        self.assertEqual(tree.rows.total('N'),D(2))  # local opaque-value safety, not native coverage
        for value in (Poison(),):
            with self.assertRaises(TypeError):tree.rows.total(value)
            with self.assertRaises(TypeError):tree.rows.total('N',value)

    def test_corrupt_graphs_foreign_rows_duplicates_depth_and_deleted_receiver_reject(self):
        for change in ('duplicate','foreign','cycle','depth','cells','child-parent','child-items'):
            tree,column=fixture([D(1)]);row=tree.rows.items[0];child=row.rows.add();child.set_member('N',D(2))
            if change=='duplicate':tree.rows.items.append(row)
            elif change=='foreign':tree.rows.items.append(fixture([D(3)])[0].rows.items[0])
            elif change=='cycle':child.rows.items.append(row)
            elif change=='depth':child.depth=0
            elif change=='cells':child.cells={}
            elif change=='child-parent':child.rows.parent=row
            elif change=='child-items':child.rows.items=()
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError)):tree.rows.total('N',True)
        tree,column=fixture([D(1)]);row=tree.rows.items[0];tree.rows.delete(row)
        with self.assertRaises(ValueError):row.rows.total('N')

    def test_function_aliases_and_arity(self):
        value=Interpreter();value.execute('T=New ValueTree;T.Columns.Add("N");R=T.Rows.Add();R.N=2;X=T.Rows.иТоГ("n");Y=T.Rows.tOtAl("N",False);')
        self.assertEqual((value.variables['x'],value.variables['y']),(D(2),D(2)))
        before=snapshot(value.variables['t'])
        for call in ('X=T.Rows.Total();','X=T.Rows.Total("N",False,False);','X=T.Total("N");'):
            with self.assertRaises(BSLError):value.execute(call)
            self.assertEqual(snapshot(value.variables['t']),before)

    def test_empty_foreign_or_fabricated_receiver_rejects_without_traversal(self):
        tree,_=fixture([D(1)]);foreign,_=fixture([D(2)])
        row=tree.rows.items[0];row.rows.parent=foreign.rows.items[0]
        with self.assertRaises(ValueError):row.rows.total('N')
        detached=Rows(tree)
        with self.assertRaises(ValueError):detached.total('N')
