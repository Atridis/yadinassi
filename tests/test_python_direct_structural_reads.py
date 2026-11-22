"""Immediate structural reads keep ownership, not unrelated payload auditing."""
from decimal import Decimal
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.collections import value_trees
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508, target_context
from yadinassi.collections.plain_value_table_runtime import BSLValueTable
from yadinassi.execution.direct import python_direct_value_tree as direct_tree
from yadinassi.execution.direct.python_direct import make_boundary


class StructuralReadTests(unittest.TestCase):
    def vm(self, **options):
        vm = Interpreter(**options)
        self.addCleanup(vm.close)
        return vm

    def test_default_and_prepared_root_child_and_prebound_read_live_counts(self):
        vm = self.vm()
        vm.execute('T=New ValueTree;T.Columns.Add("X");P=T.Rows.Add();P.Rows.Add();Rows=T.Rows;')
        source = 'R=T.Строки.Количество()+Rows.Count()+T.Columns.Count()+P.Rows.Count();'
        program = vm.prepare_program(parse(source))
        hooks = []
        old_profile = sys.getprofile()
        def profile(frame, event, arg):
            if event == 'call' and frame.f_code is direct_tree.hooks.__code__:
                hooks.append(1)
        sys.setprofile(profile)
        try:
            vm.execute(source)
            self.assertIs(type(vm.variables['r']), Decimal)
            self.assertEqual(vm.variables['r'], 4)
            vm.execute_prepared(program)
        finally:
            sys.setprofile(old_profile)
        self.assertEqual(hooks, [])
        vm.execute('T.Rows.Add();P.Rows.Add();T.Columns.Add("Y");')
        vm.execute_prepared(program)
        self.assertEqual(vm.variables['r'], 8)

    def test_plain_table_root_columns_indexes_and_generic_native_count(self):
        vm = self.vm()
        vm.execute('T=New ValueTable;T.Columns.Add("X");T.Add();T.Indexes.Add("X");Cols=T.Columns;')
        program = vm.prepare_program(parse('R=T.Count()+T.Колонки.Количество()+T.Индексы.Count()+Cols.Count();'))
        vm.execute_prepared(program)
        self.assertIs(type(vm.variables['r']), Decimal)
        self.assertEqual(vm.variables['r'], 4)
        vm.execute('T.Add();T.Columns.Add("Y");T.Indexes.Clear();')
        vm.execute_prepared(program)
        self.assertEqual(vm.variables['r'], 6)
        self.assertEqual(vm.execute('A=New Array;A.Add(1);A.Count()'), 1)

    def test_deleted_child_counts_remain_catchable_and_base_evaluated_once(self):
        vm = self.vm()
        vm.execute('Var Calls; Var T;T=New ValueTree;P=T.Rows.Add();Child=P.Rows;Calls=0;'
                   'Function Base() Calls=Calls+1; Return T; EndFunction; N=Base().Rows.Count();')
        self.assertEqual(vm.variables['calls'], 1)
        self.assertEqual(vm.variables['n'], 1)
        vm.execute('T.Rows.Delete(P); A=False;B=False;'
                   'Try A=P.Rows.Count(); Except A=True; EndTry;'
                   'Try B=Child.Count(); Except B=True; EndTry;')
        self.assertIs(vm.variables['a'], True)
        self.assertIs(vm.variables['b'], True)

    def test_retained_rows_after_columns_clear_use_native_forwarding(self):
        with target_context(LINUX_8_3_27_1508):
            vm = self.vm(native_target=LINUX_8_3_27_1508)
            vm.execute('T=New ValueTree;T.Columns.Add("X");P=T.Rows.Add();Rows=P.Rows;')
            vm.execute('T.Columns.Clear();T.Rows.Add();')
            self.assertEqual(vm.execute('Rows.Count()'), 1)
            vm.execute('Caught=False;Try V=P.Rows.Count();Except Caught=True;EndTry;')
            self.assertIs(vm.variables['caught'], True)

    def test_supplied_table_override_uses_existing_member_dispatch(self):
        vm = self.vm()
        table = BSLValueTable()
        vm.variables['t'] = table
        self.assertEqual(vm.execute('T.Count()'), 0)
        with patch.object(BSLValueTable, 'count', lambda self: Decimal(42)):
            self.assertEqual(vm.execute('T.Count()'), 42)

    def test_supplied_table_code_change_before_first_compilation_is_not_blessed(self):
        script = textwrap.dedent("""
            from decimal import Decimal
            import sys
            from yadinassi import Interpreter
            from yadinassi.collections.plain_value_table_runtime import BSLValueTable
            vm = Interpreter()
            vm.variables['t'] = BSLValueTable()
            if 'yadinassi.execution.direct.python_direct_structural_reads' in sys.modules:
                raise AssertionError('structural bridge loaded before first compilation')
            BSLValueTable.count.__code__ = (lambda self: Decimal(42)).__code__
            result = vm.execute('T.Count()')
            if type(result) is not Decimal or result != 42:
                raise AssertionError(repr(result))
            vm.close()
        """)
        command = [sys.executable, *(['-O'] if not __debug__ else []), '-c', script]
        result = subprocess.run(command, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_foreign_projection_remains_unadmitted(self):
        vm = self.vm()
        vm.execute('T=New ValueTree;U=New ValueTree;')
        left, right = vm.variables['t'], vm.variables['u']
        original = left.rows
        left.rows = right.rows
        with self.assertRaises(BoundaryViolation):
            vm.execute('T.Rows.Count()')
        left.rows = original
        events = []
        original.count = lambda: events.append('count')
        try:
            with self.assertRaises(BoundaryViolation):
                vm.execute('T.Rows.Count()')
        finally:
            del original.count
        self.assertEqual(events, [])
        with patch.object(value_trees.BSLValueTreeRowCollection, 'items',
                          property(lambda self: events.append('items')), create=True):
            with self.assertRaises(BoundaryViolation):
                vm.execute('T.Rows.Count()')
        self.assertEqual(events, [])

    def test_explicit_extensions_and_deferred_methods_keep_existing_checks(self):
        vm = self.vm(allow_extensions=True)
        vm.execute('T=New ValueTree;T.Rows.Add();')
        program = vm.prepare_program(parse('T.Rows.Count()'))
        tree = vm.variables['t']
        with patch.object(value_trees.BSLValueTreeRowCollection, 'count', lambda self: Decimal(999)):
            with self.assertRaises(BoundaryViolation):
                vm.execute_prepared(program)
        context = make_boundary(vm)
        context.enter()
        try:
            bound = context.resolve_member(tree.rows, 'Count')
            self.assertEqual(bound(), 1)
        finally:
            context.leave()
        context.enter()
        try:
            with self.assertRaises(BoundaryViolation):
                bound()
        finally:
            context.leave()
