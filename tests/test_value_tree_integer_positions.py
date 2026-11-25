import unittest
from decimal import Decimal as D
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections.value_trees import (
    BSLValueTree, BSLValueTreeColumnCollection, BSLValueTreeRowCollection, _position)


class ValueTreeIntegerPositionsTests(unittest.TestCase):
    def test_position_preserves_strict_contract(self):
        self.assertIs(type(_position(1, 2)), int)
        self.assertEqual(_position(D(1), 2), 1)
        for value in (True, False, D('1.1'), D('NaN'), D('Infinity')):
            with self.assertRaises(TypeError): _position(value, 3)
        for value in (-1, 3, D(-1), D(3)):
            with self.assertRaises(IndexError): _position(value, 3)
        self.assertEqual(_position(3, 3, True), 3)

    def test_internal_append_supplies_native_position(self):
        tree = BSLValueTree()
        # Inspect argument only: no monkeypatch of numeric or authority helpers.
        with patch.object(BSLValueTreeColumnCollection, 'insert', autospec=True) as insert:
            tree.columns.add('N')
            self.assertIs(type(insert.call_args.args[1]), int)
        with patch.object(BSLValueTreeRowCollection, 'insert', autospec=True) as insert:
            tree.rows.add()
            self.assertIs(type(insert.call_args.args[1]), int)

    def test_actual_tree_indices_and_public_numbers(self):
        tree = BSLValueTree(); column = tree.columns.add('N')
        first = tree.rows.add(); second = tree.rows.insert(0)
        first.set(0, D(7))
        self.assertIs(tree.rows.get(1), first)
        self.assertIs(tree.columns.get(0), column)
        self.assertIs(type(first.get(0)), D)
        self.assertIs(type(tree.rows.count()), D)
        self.assertIs(type(tree.rows.index_of(first)), D)
        self.assertIs(type(tree.columns.index_of(column)), D)
        self.assertIs(type(second.level()), D)
        for collection in (tree.rows, tree.columns):
            with self.assertRaises(TypeError): collection.get(True)
            with self.assertRaises(TypeError): collection.get(D('0.5'))

    def test_native_bsl_integers_reach_tree_number_operations(self):
        setup = """
        T = New ValueTree;
        T.Columns.Add("N");
        A = T.Rows.Add();
        A.N = 1;
        B = T.Rows.Add();
        B.N = True;
        C = A.Rows.Add();
        C.N = 4.5 - 3.5;
        """
        cases = (
            ('R = T.Rows.Итог(0, 1);', D(2)),
            ('R = T.Rows.Total("N");', D(1)),
            ('R = T.Rows.UnloadColumn(0).Count();', D(2)),
            ('V = New Array; V.Add(9); T.Rows.ЗагрузитьКолонку(V, 0); R = A.N;', D(9)),
            ('R = T.Rows.Find(4.5 - 3.5, "N").N;', D(1)),
            ('R = T.Rows.Find(1, "N", 1).N;', D(1)),
            ('R = T.Rows.FindRows(New Structure("N", 1), 1).Count();', D(2)),
            ('R = T.Rows.FindRows(New Structure("N", True), 1).Count();', D(1)),
        )
        for prepared in (False, True):
            for code, expected in cases:
                with self.subTest(prepared=prepared, code=code):
                    vm = Interpreter()
                    source = setup + code
                    if prepared:
                        vm.execute_prepared(vm.prepare(source))
                    else:
                        vm.execute(source)
                    self.assertEqual(vm.variables['r'], expected)
