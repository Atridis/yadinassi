"""Local bounded Delete policies; exact native semantics have separate fixtures."""
from decimal import Decimal as D
import unittest
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context
from yadinassi.value_trees import BSLValueTree


class Poison:
    __hash__ = object.__hash__
    def __eq__(self, other): raise AssertionError('equality hook')
    def __bool__(self): raise AssertionError('boolean hook')
    def __str__(self): raise AssertionError('string hook')
    def __iter__(self): raise AssertionError('iteration hook')
    def __int__(self): raise AssertionError('integer hook')


class DeletePolicyTests(unittest.TestCase):
    def setUp(self):
        scope = target_context(LINUX_8_3_27_1508); scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)

    def fixture(self):
        t = BSLValueTree(); c = t.columns.add('Key'); c.title = 'P'; c.width = D(9)
        r = t.rows.add(); child = r.rows.add(); other = t.rows.add()
        return t, c, (r, child, other)

    def test_nonlast_removes_only_selected_cells_and_resets_metadata(self):
        for selector in ('index', 'column', 'name'):
            with self.subTest(selector=selector):
                t, c, rows = self.fixture(); other = t.columns.add('Other')
                poison = Poison()
                for r in rows: r.cells[c] = r.cells[other] = poison
                t.columns.delete({'index': D(0), 'column': c, 'name': 'KEY'}[selector])
                self.assertEqual(t.rows.count(), D(2)); self.assertEqual(len(t._all_rows), 3)
                for r in rows:
                    self.assertFalse(r._deleted); self.assertEqual(list(r.cells), [other]); self.assertIs(r.cells[other], poison)
                self.assertEqual((c.get_member('Name'), c.get_member('Title'), c.get_member('Width')), ('', '', D(0)))
                with self.assertRaises(ValueError): c.get_member('ValueType')

    def test_last_deletion_root_forwarding_is_cause_bounded(self):
        t, c, rows = self.fixture(); held = rows[1].rows
        t.columns.delete(c)
        self.assertEqual(t.rows.count(), D(0)); self.assertEqual(t._all_rows, {})
        self.assertEqual(held.count(), D(0)); self.assertIs(held.get_member('Parent'), rows[1])
        for r in rows:
            for get in (r.owner, r.level, lambda r=r: r.get_member('Rows')):
                with self.assertRaises(ValueError): get()
        t.columns.add('Key'); new = held.add(); new.set_member('Key', D(6))
        self.assertIs(new.collection, t.rows); self.assertIsNone(new.parent)
        self.assertEqual(held.count(), D(1)); self.assertIs(held.get_member('Parent'), rows[1])
        for call in (lambda: held.get(D(0)), lambda: held.insert(D(0)), held.clear, lambda: iter(held)):
            with self.assertRaises(ValueError): call()
        self.assertEqual(t.rows.count(), D(1))

    def test_injected_native_delete_hook_cannot_bypass_validation(self):
        t, c, rows = self.fixture()
        t.columns._delete_linux = lambda *args: self.fail('injected callback')
        for call in (lambda: t.columns.delete(c), lambda: t.columns.get_method('Delete')(c)):
            with self.assertRaises(ValueError): call()
        self.assertFalse(c._deleted)

    def test_named_last_schema_only_preserves_legacy_metadata(self):
        t = BSLValueTree(); c = t.columns.add('Key'); c.title = 'P'; c.width = D(9)
        t.columns.delete('Key')
        self.assertEqual((c.name,c.title,c.width), ('Key','P',D(9)))
        with self.assertRaises(ValueError): c.get_member('Title')

    def test_named_last_remains_guarded(self):
        t, c, rows = self.fixture()
        with self.assertRaises(ValueError): t.columns.delete('Key')
        self.assertEqual(len(t._all_rows), 3); self.assertFalse(c._deleted)

    def test_ordinary_row_removal_does_not_enable_forwarding(self):
        for clear in (False, True):
            t, c, rows = self.fixture(); held = rows[0].rows
            if clear: t.rows.clear()
            else: t.rows.delete(rows[0])
            for call in (held.count, held.add, lambda: held.get_member('Parent')):
                with self.assertRaises(ValueError): call()

    def test_invalid_selector_is_atomic_and_does_not_call_hooks(self):
        for value in (None, True, Poison(), D('NaN'), D('Infinity'), D('1e999999'), D('-1'), D('0.5'), 'Absent'):
            with self.subTest(type=type(value)):
                t, c, rows = self.fixture()
                with self.assertRaises((ValueError, TypeError, IndexError)): t.columns.delete(value)
                self.assertEqual(len(t._all_rows), 3); self.assertIs(t.columns.items[0], c)
                self.assertFalse(c._deleted)

    def test_corrupt_graph_rejected_before_mutation(self):
        mutations = [lambda t,c,r: r[0].rows.items.append(r[0]),
                     lambda t,c,r: t._all_rows.pop(r[0]),
                     lambda t,c,r: setattr(r[0], 'cells', []),
                     lambda t,c,r: setattr(c, 'width', Poison()),
                     lambda t,c,r: setattr(c, 'name', Poison()),
                     lambda t,c,r: setattr(c, 'default', Poison())]
        for mutate in mutations:
            t, c, rows = self.fixture(); mutate(t, c, rows)
            with self.assertRaises((ValueError, TypeError)): t.columns.delete(c)
            self.assertFalse(c._deleted); self.assertIs(t.columns.items[0], c)
            self.assertFalse(rows[0]._deleted)

    def test_nonlinux_legacy_guard_and_deleted_metadata_preserved(self):
        with target_context(WINDOWS_8_3_27_2342):
            t, c, rows = self.fixture()
            with self.assertRaises(ValueError): t.columns.delete(c)
            other = t.columns.add('Other'); t.columns.delete(c)
            self.assertEqual((c.name,c.title,c.width), ('Key','P',D(9)))
            with self.assertRaises(ValueError): c.get_member('Title')
            self.assertEqual(len(t._all_rows),3)

    def test_procedure_policy_before_argument_evaluation(self):
        for method in ('Delete', 'Удалить'):
            vm = Interpreter(native_target=LINUX_8_3_27_1508)
            vm.execute('T=New ValueTree;T.Columns.Add("Key");T.Columns.Add("Other");')
            with self.assertRaises(BSLRuntimeError): vm.execute('R=T.Columns.'+method+'(T.Columns.Add("SideEffect"));')
            self.assertEqual(len(vm.variables['t'].columns.items),2)
