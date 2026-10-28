"""Move local safety tests; unmeasured conversions/limits are not native claims."""
from decimal import Decimal as D, localcontext, InvalidOperation, Rounded, Inexact
import unittest
from unittest import mock
from yadinassi import Interpreter, BSLError
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRowCollection as Rows
from yadinassi.values import NULL


def fixture():
    tree=BSLValueTree();tree.columns.add('Id')
    rows=[tree.rows.add() for _ in range(3)]
    children=[rows[0].rows.add(),rows[0].rows.add()]
    return tree,rows,children


class MoveTests(unittest.TestCase):
    def test_reorder_preserves_views_registry_subtree_and_cells(self):
        tree,rows,children=fixture(); grandchild=children[0].rows.add()
        views=(tree.rows,tree.rows.items,rows[0].rows,rows[0].rows.items)
        columns=tree.columns; cells=tuple(row.cells for row in rows+children+[grandchild])
        registry=tuple(tree._all_rows)
        tree.rows.move(rows[0],D(2))
        self.assertEqual(tree.rows.items,[rows[1],rows[2],rows[0]])
        self.assertIs(tree.rows,views[0]);self.assertIs(tree.rows.items,views[1])
        self.assertIs(rows[0].rows,views[2]);self.assertIs(rows[0].rows.items,views[3])
        self.assertEqual(rows[0].rows.items,children);self.assertIs(grandchild.parent,children[0])
        self.assertEqual(tuple(tree._all_rows),registry);self.assertIs(tree.columns,columns)
        for row,old in zip(rows+children+[grandchild],cells): self.assertIs(row.cells,old)

    def test_fraction_index_and_offset_are_deliberately_different(self):
        tree,rows,_=fixture()
        with self.assertRaises(IndexError):tree.rows.move(D('-.5'),D(1))
        self.assertEqual(tree.rows.items,rows)
        tree.rows.move(D('.5'),D('1.9'));self.assertEqual(tree.rows.items,[rows[1],rows[0],rows[2]])
        tree.rows.move(rows[0],D('-1.9'));self.assertEqual(tree.rows.items,rows)
        for value in ('-.5','.5','0'):
            tree.rows.move(rows[1],D(value));self.assertEqual(tree.rows.items,rows)

    def test_bounds_reject_without_wrap_clamp_or_partial_mutation(self):
        for selector,offset in ((D(0),D(-1)),(D(2),D(1)),(D(1),D(10)),(D(1),D(-10)),(D(3),D(-1))):
            tree,rows,_=fixture()
            with self.assertRaises(IndexError):tree.rows.move(selector,offset)
            self.assertEqual(tree.rows.items,rows)

    def test_empty_singleton_and_local_zero_offset_policy(self):
        tree=BSLValueTree()
        for offset in (D(0),D(1)):
            with self.assertRaises(IndexError):tree.rows.move(D(0),offset)
        row=tree.rows.add();tree.rows.move(D(0),D(0));self.assertEqual(tree.rows.items,[row])
        with self.assertRaises(IndexError):tree.rows.move(D(0),D(1))
        self.assertEqual(tree.rows.items,[row])

    def test_child_receiver_only_and_foreign_sibling_safety(self):
        tree,rows,children=fixture();foreign=BSLValueTree().rows.add();sibling=rows[1].rows.add()
        rows[0].rows.move(children[0],D(1))
        self.assertEqual(tree.rows.items,rows);self.assertEqual(rows[0].rows.items,children[::-1])
        for invalid in (rows[1],foreign,sibling):
            with self.assertRaises(ValueError):rows[0].rows.move(invalid,D(0))
            self.assertEqual(rows[0].rows.items,children[::-1])

    def test_deleted_row_and_deleted_receiver_are_local_safety(self):
        tree,rows,children=fixture();tree.rows.delete(rows[1])
        before=list(tree.rows.items)
        with self.assertRaises(ValueError):tree.rows.move(rows[1],D(0))
        self.assertEqual(tree.rows.items,before)
        tree.rows.delete(rows[0])
        with self.assertRaises(ValueError):rows[0].rows.move(children[0],D(0))

    def test_measured_true_and_string_one_and_local_number_extensions(self):
        for selector in (True,'1'):
            for offset in (True,'1'):
                tree,rows,_=fixture();tree.rows.move(selector,offset)
                self.assertEqual(tree.rows.items,[rows[0],rows[2],rows[1]])
        # Existing Number converter extensions; these are not extra native observations.
        tree,rows,_=fixture();tree.rows.move(False,'2');self.assertEqual(tree.rows.items,[rows[1],rows[2],rows[0]])
        tree.rows.move('2',False);self.assertEqual(tree.rows.items,[rows[1],rows[2],rows[0]])

    def test_reject_undefined_null_bad_text_and_host_hooks_without_mutation(self):
        class Poison:
            def __int__(self):raise AssertionError('conversion hook')
            def __str__(self):raise AssertionError('string hook')
            def __eq__(self,other):raise AssertionError('equality hook')
        for invalid in (None,NULL,'bad','',Poison(),1):
            for as_offset in (False,True):
                tree,rows,_=fixture()
                with self.assertRaises((TypeError,ValueError)):
                    tree.rows.move(rows[1] if as_offset else invalid,invalid if as_offset else D(1))
                self.assertEqual(tree.rows.items,rows)

    def test_nonfinite_huge_values_and_coefficients_are_bounded_before_int(self):
        for value in (D('NaN'),D('sNaN'),D('Infinity'),D('-Infinity'),D('1e999999'),D('1.'+'0'*4096),'9'*4097):
            for as_offset in (False,True):
                tree,rows,_=fixture()
                with self.assertRaises((TypeError,ValueError,IndexError)):
                    tree.rows.move(rows[1] if as_offset else value,value if as_offset else D(1))
                self.assertEqual(tree.rows.items,rows)

    def test_invalid_text_does_not_leak_decimal_flags(self):
        tree,rows,_=fixture()
        with localcontext() as context:
            context.clear_flags();context.traps[InvalidOperation]=False
            with self.assertRaises(ValueError):tree.rows.move(rows[1],'bad')
            self.assertFalse(any(context.flags.values()))
            context.prec=1;context.traps[Rounded]=True;context.traps[Inexact]=True
            tree.rows.move(D('1.9'),D('-.5'))
            self.assertFalse(any(context.flags.values()))

    def test_local_row_budget_and_corrupt_membership_guard_before_mutation(self):
        tree,rows,_=fixture()
        with mock.patch('yadinassi.value_trees._MAX_ROWS',2),self.assertRaises(ValueError):tree.rows.move(rows[0],D(1))
        self.assertEqual(tree.rows.items,rows)
        orphan=tree.rows.add();tree.rows.items.pop()
        with self.assertRaises(ValueError):tree.rows.move(orphan,D(0))
        self.assertEqual(tree.rows.items,rows)

    def test_aliases_procedure_only_and_arity_before_mutation(self):
        vm=Interpreter();vm.execute('T=New ValueTree;A=T.Rows.Add();B=T.Rows.Add();C=T.Rows.Add();')
        rows=vm.variables['t'].rows;initial=list(rows.items)
        for call in ('X=T.Rows.Move(0,1);','T.Rows.Move();','T.Rows.Move(0);','T.Rows.Move(0,1,2);','T.Move(0,1);'):
            with self.assertRaises(BSLError):vm.execute(call)
            self.assertEqual(rows.items,initial)
        vm.execute('T.Rows.СдВиНуТь(0,1); T.Rows.mOvE(1,-1);')
        self.assertEqual(rows.items,initial)
