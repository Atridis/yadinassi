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
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
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
        vm.execute(source)
        self.assertIs(type(vm.variables['r']), Decimal)
        self.assertEqual(vm.variables['r'], 4)
        vm.execute_prepared(program)
        self.assertEqual(vm.variables['r'], 4)
        vm.execute('T.Rows.Add();P.Rows.Add();T.Columns.Add("Y");')
        vm.execute_prepared(program)
        self.assertEqual(vm.variables['r'], 8)

    def test_prepared_tree_positional_fields_use_only_current_owners(self):
        vm = self.vm()
        vm.execute('T=New ValueTree;T.Columns.Add("X");T.Columns.Add("Y");'
                   'P=T.Rows.Add();P.X=1;Nested=P.Rows.Add();Nested.X=2;'
                   'Unrelated=T.Rows.Add();')
        tree=vm.variables['t']; row=vm.variables['p']; child=vm.variables['nested']
        # No search or default checks on an unobserved row/column.
        vm.variables['unrelated'].cells={}
        original=tree.columns.items[1].value_type
        tree.columns.items[1].value_type=None
        plan=vm.prepare('A=T.Rows.Get(0).X; B=T.Строки[0].Строки.Получить(0).X;'
                        'C=T.Колонки[0].Имя; D=T.Columns.Get(0).Name;')
        with patch.object(direct_tree,'hooks',side_effect=AssertionError('full model audit')):
            vm.execute_prepared(plan)
        self.assertEqual(tuple(vm.variables[k] for k in 'abcd'),(1,2,'X','X'))
        tree.columns.items[1].value_type=original
        self.assertIs(vm.execute('T.Rows.Get(0);'),row)
        self.assertIs(vm.execute('P.Rows[0];'),child)
        old=row.rows.items[0];row.rows.items[0]=row
        with self.assertRaises(BoundaryViolation):vm.execute('P.Rows[0];')
        row.rows.items[0]=old
        tree._all_rows.pop(child)
        with self.assertRaises(BoundaryViolation):vm.execute('P.Rows.Get(0);')

    def test_tree_position_binds_before_effects_and_rechecks_after_arguments(self):
        vm=self.vm()
        vm.execute('Var R,Other,Calls;T=New ValueTree;T.Columns.Add("X");T.Rows.Add().X=1;'
                   'U=New ValueTree;U.Columns.Add("X");U.Rows.Add().X=2;'
                   'R=T.Rows;Other=U.Rows;Calls=0;'
                   'Function Choose() Calls=Calls+1;R=Other;Return 0;EndFunction;'
                   'A=R.Get(Choose()).X;B=R[0].X;')
        self.assertEqual(tuple(vm.variables[k] for k in ('a','b','calls')),(1,2,1))
        tree=vm.variables['t']; context=make_boundary(vm); context.enter()
        try:
            selected=context.resolve_member(tree.rows,'Get')
            self.assertIs(selected(0),tree.rows.items[0])
            tree._all_rows.pop(tree.rows.items[0])
            with self.assertRaises(BoundaryViolation):selected(0)
        finally:context.leave()
        context.enter()
        try:
            with self.assertRaises(BoundaryViolation):selected(0)
        finally:context.leave()

    def test_unsupported_magic_spelling_does_not_enter_direct_positional_dispatch(self):
        vm=self.vm()
        vm.execute('Var Calls;Calls=0;T=New ValueTree;T.Columns.Add("X");T.Rows.Add().X=1;'
                   'Function IndexArg() Calls=Calls+1;Return 0;EndFunction;'
                   'A=False;B=False;'
                   'Try V=T.Rows.__GETITEM__(IndexArg());Except A=True;EndTry;'
                   'Try V=T.Columns.__GETITEM__(IndexArg());Except B=True;EndTry;')
        self.assertIs(vm.variables['a'],True);self.assertIs(vm.variables['b'],True)
        self.assertEqual(vm.variables['calls'],0)

    def test_tree_position_wrong_index_and_extensions_preserve_effects(self):
        vm=self.vm()
        vm.execute('T=New ValueTree;P=T.Rows.Add();R=P.Rows;T.Rows.Delete(P);')
        for expression in ('T.Rows[2]','T.Rows.Get(0.5)','R.Get(0)'):
            with self.subTest(expression=expression):
                vm.execute(f'Caught=False;Try V={expression};Except Caught=True;EndTry;')
                self.assertIs(vm.variables['caught'],True)
        hosted=self.vm(allow_extensions=True)
        hosted.execute('T=New ValueTree;T.Columns.Add("X");T.Rows.Add().X=1;')
        tree=hosted.variables['t']; original=value_trees.BSLValueTreeRowCollection.get; events=[]
        def mutate():
            value_trees.BSLValueTreeRowCollection.get=lambda *_: events.append('mutant')
            return 0
        hosted.register_function('Mutate',mutate)
        try:
            with self.assertRaises(BoundaryViolation):hosted.execute('T.Rows.Get(Mutate()).X;')
        finally:value_trees.BSLValueTreeRowCollection.get=original
        self.assertEqual(events,[]);self.assertEqual(len(tree.rows.items),1)

    def test_tree_position_preserves_retained_column_clear_and_delete_forwarding(self):
        vm=self.vm(native_target=LINUX_8_3_27_1508)
        vm.execute('Var T,Col;T=New ValueTree;Col=T.Columns.Add("X");Parent=T.Rows.Add();'
                   'Retained=Parent.Rows;Retained.Add();'
                   'Function Choose() T.Columns.Clear();T.Rows.Add();Return 0;EndFunction;'
                   'Selected=Retained.Get(Choose());')
        self.assertIs(vm.variables['selected'],vm.variables['t'].rows.items[0])
        self.assertEqual(vm.execute('Col.Name;'),'')
        vm.execute('U=New ValueTree;U.Columns.Add("X");P=U.Rows.Add();Old=P.Rows;Old.Add();'
                   'U.Columns.Delete(U.Columns.Get(0));U.Rows.Add();'
                   'Caught=False;Try V=Old.Get(0);Except Caught=True;EndTry;')
        self.assertIs(vm.variables['caught'],True)

    def test_prepared_tree_iteration_uses_current_row_and_column_admission(self):
        vm=self.vm()
        vm.execute('T=New ValueTree;T.Columns.Add("X");T.Columns.Add("Y");'
                   'P=T.Rows.Add();P.X=1;P.Rows.Add().X=2;P.Rows.Add().X=3;')
        plan=vm.prepare('Sum=0; Text=""; For Each R In P.Rows Do Sum=Sum+R.X;EndDo;'
                        'For Each C In T.Columns Do Text=Text+C.Name;EndDo;')
        with patch.object(direct_tree,'hooks',side_effect=AssertionError('full model audit')):
            vm.execute_prepared(plan)
        self.assertEqual((vm.variables['sum'],vm.variables['text']),(5,'XY'))

    def test_tree_row_cell_iteration_keeps_existing_payload_snapshot(self):
        vm=self.vm()
        vm.execute('T=New ValueTree;T.Columns.Add("X");T.Columns.Add("Y");R=T.Rows.Add();R.X=1;R.Y=2;')
        with patch.object(direct_tree,'_structural_iter',side_effect=AssertionError('not a collection cursor')):
            vm.execute('S="";For Each Cell In R Do S=S+String(Cell);R.Y=9;EndDo;')
        self.assertEqual(vm.variables['s'],'12')
        self.assertEqual(vm.execute('R.Y;'),9)

    def test_tree_live_cursor_keeps_append_delete_move_and_clear_semantics(self):
        for mutation, expected in (
            ('T.Rows.Add().X=4;', '1234'), ('T.Rows.Delete(R);', '13'),
            ('T.Rows.Move(R,1);', '113'), ('T.Rows.Clear();', '1'),
            ('T.Columns.Clear();', '1'),
        ):
            with self.subTest(mutation=mutation):
                vm=self.vm(native_target=LINUX_8_3_27_1508)
                vm.execute('T=New ValueTree;T.Columns.Add("X");'
                           'For I=1 To 3 Do T.Rows.Add().X=I;EndDo;'
                           'S="";First=True;For Each R In T.Rows Do S=S+String(R.X);'
                           'If First Then First=False;'+mutation+'EndIf;EndDo;')
                self.assertEqual(vm.variables['s'],expected)
        vm=self.vm(native_target=LINUX_8_3_27_1508)
        vm.execute('T=New ValueTree;T.Columns.Add("X");P=T.Rows.Add();Child=P.Rows;Child.Add().X=4;'
                   'S="";For Each R In Child Do S=S+String(R.X);T.Columns.Clear();T.Rows.Add();EndDo;'
                   'Caught=False;Try For Each R In Child Do S="item";EndDo;Except Caught=True;EndTry;')
        self.assertEqual(vm.variables['s'],'4');self.assertIs(vm.variables['caught'],True)

    def test_tree_iteration_rechecks_real_output_effect_before_next_row(self):
        seen=[]
        def output(message):
            seen.append(message)
            if len(seen)==1:
                tree,other=(vm.variables[name] for name in ('t','u'))
                tree.rows.items[1]=other.rows.items[0]
        vm=self.vm(output=output)
        vm.execute('T=New ValueTree;T.Columns.Add("X");T.Rows.Add().X=1;T.Rows.Add().X=2;'
                   'U=New ValueTree;U.Columns.Add("X");U.Rows.Add().X=9;')
        with self.assertRaises(BoundaryViolation):
            vm.execute('For Each R In T.Rows Do Message(R.X);EndDo;')
        self.assertEqual(seen,['1'])

    def test_tree_iterator_checks_reached_hooks_and_keeps_sticky_exhaustion(self):
        vm=self.vm()
        vm.execute('T=New ValueTree;T.Rows.Add();T.Rows.Add();U=New ValueTree;')
        tree,empty=(vm.variables[name] for name in ('t','u'))
        context=make_boundary(vm);context.enter()
        try:
            retained=context.resolve_member(tree.rows,'__iter__')()
            exhausted=context.resolve_member(empty.rows,'__iter__')()
            with self.assertRaises(StopIteration):next(exhausted)
            empty.rows.add()
            self.assertIs(next(retained),tree.rows.items[0])
            events=[]
            with patch.object(value_trees.BSLValueTreeRowCollection,'__iter__',lambda self:events.append('hook')):
                with self.assertRaises(BoundaryViolation):next(retained)
            self.assertEqual(events,[])
            retained=context.resolve_member(tree.rows,'__iter__')()
        finally:context.leave()
        context.enter()
        try:
            with self.assertRaises(StopIteration):next(exhausted)
            with self.assertRaises(BoundaryViolation):next(retained)
        finally:context.leave()

    def test_evaluated_projections_keep_live_structural_reads_in_both_contexts(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        source = ('R=T.Rows.Count()+Rows.Count()+Holder.Rows.Count()+Holder.Columns.Count()'
                  '+Holder.Indexes.Count()+Table.Count();')
        for database in (False, True):
            with self.subTest(database=database):
                if database:
                    fixture=OrderedTopMainDemoTests()
                    fixture.setUp()
                    self.addCleanup(fixture.doCleanups)
                    vm=fixture.vm
                else:
                    vm=self.vm()
                vm.execute('T=New ValueTree;T.Columns.Add("N");T.Rows.Add();'
                           'Table=New ValueTable;Table.Columns.Add("N");Table.Add();'
                           'Table.Indexes.Add("N");'
                           'Holder=New Structure("Rows,Columns,Indexes",T.Rows,T.Columns,Table.Indexes);'
                           'Rows=Holder.Rows;')
                plan=vm.prepare(source)
                if database:trace,traced=fixture.actual_trace()
                else:
                    from contextlib import nullcontext
                    trace,traced=[],nullcontext()
                with traced:
                    vm.execute(source)
                    self.assertEqual(vm.variables['r'],6)
                    vm.execute_prepared(plan)
                self.assertEqual(trace,[])
                vm.execute('Rows.Add();Holder.Rows=Rows;')
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'],9)

    def test_fallback_member_is_evaluated_once_and_extensions_keep_dispatch(self):
        local=self.vm()
        local.execute('Var Calls,Holder;Calls=0;T=New ValueTree;T.Rows.Add();'
                      'Holder=New Structure("Rows",T.Rows);'
                      'Function Supply() Calls=Calls+1;Return Holder;EndFunction;'
                      'N=Supply().Rows.Count();')
        self.assertEqual((local.variables['calls'],local.variables['n']),(1,1))

        vm=self.vm(allow_extensions=True)
        vm.execute('T=New ValueTree;T.Rows.Add();Holder=New Structure("Rows",T.Rows);')
        seen=[]
        vm.register_function('Supply',lambda:seen.append('supply') or vm.variables['holder'])
        self.assertEqual(vm.execute('Supply().Rows.Count()'),Decimal(1))
        self.assertEqual(seen,['supply'])
        holder=vm.variables['holder']
        vm.register_function('CloseSupply',lambda:vm.close() or holder)
        with self.assertRaises(BoundaryViolation):
            vm.execute('CloseSupply().Rows.Count()')

    def test_imported_value_counts_preserve_import_resolution(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        vm=self.vm()
        with TemporaryDirectory() as directory:
            main=str(Path(directory)/'Main.bsl')
            (Path(directory)/'Side.bsl').write_text(
                'Var Holder Export;T=New ValueTree;T.Rows.Add();Holder=New Structure("Rows",T.Rows);',
                encoding='utf-8')
            vm.execute('// #Import Side.bsl\n',main)
            source='Local=Side.Holder;Local.Rows.Count()'
            program=vm.prepare(source,main)
            self.assertEqual(vm.execute_prepared(program),Decimal(1))
            self.assertEqual(vm.execute(source,main),Decimal(1))

    def test_actual_database_receiver_stays_on_its_existing_dispatch(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        fixture=OrderedTopMainDemoTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.vm.execute('D=Documents.Receipt.CreateDocument();')
        self.assertEqual(fixture.vm.execute('D.Lines.Count()'),Decimal(0))

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
            from yadinassi import Interpreter
            from yadinassi.collections.plain_value_table_runtime import BSLValueTable
            vm = Interpreter()
            vm.variables['t'] = BSLValueTable()
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
