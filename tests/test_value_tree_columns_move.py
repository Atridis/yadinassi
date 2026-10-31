"""Local safety policies, distinct from the 51 attributed native observations."""
from decimal import Decimal as D, Inexact, Rounded, localcontext
import unittest
from unittest.mock import patch
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context
from yadinassi.value_trees import BSLValueTree, BSLValueTreeColumnCollection as Columns
from yadinassi.values import NULL


class Poison:
    def __str__(self): raise AssertionError('str hook')
    def __bool__(self): raise AssertionError('bool hook')
    def __int__(self): raise AssertionError('int hook')
    def __eq__(self, other): raise AssertionError('eq hook')
    def __iter__(self): raise AssertionError('iter hook')
    def __hash__(self): raise AssertionError('hash hook')


class ColumnsMovePolicyTests(unittest.TestCase):
    def setUp(self):
        scope = target_context(LINUX_8_3_27_1508)
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)

    def fixture(self):
        tree = BSLValueTree()
        for name in ('Key', 'Secondary', 'Tag'):
            tree.columns.add(name)
        return tree

    def reject(self, columns, *args):
        before = tuple(map(id, columns.items)) if type(columns.items) is list else id(columns.items)
        with self.assertRaises((ValueError, TypeError, IndexError)):
            columns.move(*args)
        after = tuple(map(id, columns.items)) if type(columns.items) is list else id(columns.items)
        self.assertEqual(before, after)

    def test_general_live_and_deleted_destination_model(self):
        for position in range(3):
            for distance in range(-5, 6):
                tree = self.fixture(); original = list(tree.columns.items)
                destination = position + distance
                if 0 <= destination <= 3:
                    tree.columns.move(D(position), D(distance))
                    expected = list(original)
                    if destination < 3:
                        expected.insert(destination, expected.pop(position))
                    self.assertEqual(list(map(id, tree.columns.items)), list(map(id, expected)))
                else:
                    self.reject(tree.columns, D(position), D(distance))
        tree = self.fixture(); deleted = tree.columns.add('Removed'); tree.columns.delete(deleted)
        for distance in range(-3, 8):
            if 0 <= -1 + distance <= 3:
                before = tuple(map(id, tree.columns.items))
                tree.columns.move(deleted, D(distance))
                self.assertEqual(tuple(map(id, tree.columns.items)), before)
            else:
                self.reject(tree.columns, deleted, D(distance))

    def test_owner_liveness_and_exact_type_guards(self):
        for value in (Poison(), None, NULL, True, False, 1, [], {}):
            self.reject(self.fixture().columns, value, D(1))
            if type(value) is not bool:
                self.reject(self.fixture().columns, D(0), value)
        tree = self.fixture(); foreign = self.fixture().columns.items[0]
        self.reject(tree.columns, foreign, D(1))
        foreign.table.columns.delete(foreign)
        self.reject(tree.columns, foreign, D(1))
        missing = tree.columns.items.pop()
        self.reject(tree.columns, missing, D(0))
        class ForeignColumns(Columns): pass
        fake = ForeignColumns(tree)
        self.reject(fake, D(0), D(0))

    def test_hostile_schema_never_invokes_hooks(self):
        for mutate in (
            lambda t: setattr(t.columns, 'items', Poison()),
            lambda t: t.columns.items.append(Poison()),
            lambda t: t.columns.items.append(t.columns.items[0]),
            lambda t: setattr(t.columns.items[0], 'table', Poison()),
            lambda t: setattr(t.columns.items[0], '_deleted', Poison()),
            lambda t: setattr(t.columns.items[0], 'name', Poison()),
            lambda t: setattr(t.columns.items[1], 'name', 'KEY'),
            lambda t: setattr(t.columns, 'table', Poison()),
        ):
            tree = self.fixture(); mutate(tree)
            self.reject(tree.columns, D(0), D(1))

    def test_pure_permutation_does_not_scan_rows_or_cells(self):
        tree = self.fixture(); parent = tree.rows.add(); child = parent.rows.add()
        columns = list(tree.columns.items)
        for row in (parent, child):
            for column in columns:
                row.cells[column] = Poison()
        before = [(id(row), id(row.cells), tuple((id(k), id(v)) for k, v in row.cells.items()),
                   id(row.collection), id(row.parent), id(row.rows), row.depth) for row in (parent, child)]
        tree._all_rows = Poison()  # No traversal is needed to permute schema.
        tree.columns.move('secondary', D(1))
        after = [(id(row), id(row.cells), tuple((id(k), id(v)) for k, v in row.cells.items()),
                  id(row.collection), id(row.parent), id(row.rows), row.depth) for row in (parent, child)]
        self.assertEqual(before, after)
        self.assertEqual(list(map(id, tree.columns.items)), list(map(id, (columns[0], columns[2], columns[1]))))

    def test_numeric_text_and_work_budgets_before_conversion(self):
        for value in (D('NaN'), D('sNaN'), D('Infinity'), D('-Infinity'),
                      D('1e999999999'), D('-1e999999999'), D('1' * 5000)):
            self.reject(self.fixture().columns, value, D(0))
            self.reject(self.fixture().columns, D(0), value)
        for text in ('1' * 5000, 'bad', 'NaN', 'Infinity', '1e999999999'):
            self.reject(self.fixture().columns, D(0), text)
        tree = self.fixture()
        with patch('yadinassi.value_trees._MAX_COLUMNS', 2):
            self.reject(tree.columns, D(0), D(1))
        with patch('yadinassi.value_trees._MAX_SEARCH_WORK', 1):
            self.reject(self.fixture().columns, D(0), D(1))
        with patch('yadinassi.value_trees._MAX_SEARCH_TEXT', 2):
            self.reject(self.fixture().columns, D(0), D(1))

    def test_decimal_context_is_not_modified(self):
        tree = self.fixture()
        with localcontext() as context:
            context.prec = 1; context.traps[Inexact] = True; context.traps[Rounded] = True
            before = (context.prec, dict(context.flags), dict(context.traps))
            tree.columns.move(D('-0.5'), '1.9')
            self.assertEqual((context.prec, dict(context.flags), dict(context.traps)), before)
        self.assertEqual([c.name for c in tree.columns.items], ['Secondary', 'Key', 'Tag'])

    def test_target_scope_not_host_os_and_procedure_arity(self):
        tree = self.fixture()
        with target_context(WINDOWS_8_3_27_2342):
            self.reject(tree.columns, D(0), D(1))
        with patch('os.name', 'nt'):
            tree.columns.move(D(0), D(1))
        for name in ('Move', 'Сдвинуть'):
            self.assertFalse(tree.columns.get_method(name).returns_value)
        for arguments in ((), (D(0),), (D(0), D(0), D(0))):
            self.reject(tree.columns, *arguments)

    def test_unmeasured_clear_target_and_last_column_guards(self):
        tree = self.fixture(); tree.rows.add()
        with target_context(WINDOWS_8_3_27_2342), self.assertRaises(ValueError): tree.columns.clear()
        tree.columns.delete(tree.columns.items[-1]); tree.columns.delete(tree.columns.items[-1])
        tree.columns.delete(tree.columns.items[-1])
        self.assertEqual(tree.rows.count(), D(0))


if __name__ == '__main__':
    unittest.main()
