"""ValueTree is a finite detached protocol, never generic Python/DB authority."""
from contextlib import ExitStack
import copy
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.collections import value_trees as trees
from yadinassi.types.values import BSLObject
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectValueTreeTests(unittest.TestCase):
    def vm(self, *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions);self.addCleanup(vm.close);return vm
    def setup_tree(self,vm):
        vm.execute('T=New ValueTree;C=T.Columns.Add("Name");R=T.Rows.Add();R.Name="one";')
        return vm.variables['t'],vm.variables['r']

    def test_source_ast_prepared_no_vm_dispatch(self):
        source='T=New ValueTree;T.Columns.Add("Name");R=T.Rows.Add();R.Name="one";S=R.Name;'
        for route in ('source','ast','prepared'):
            vm=self.vm()
            with self.subTest(route=route),ExitStack() as stack:
                for name in ('block','call_routine','semantic_new'):
                    stack.enter_context(patch.object(Interpreter,name,side_effect=AssertionError('VM')))
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['s'],'one');self.assertIs(type(vm.variables['t']),trees.BSLValueTree)

    def test_find_uses_current_rows_and_depth_first_identity(self):
        vm=self.vm();tree,first=self.setup_tree(vm)
        second=tree.rows.add();second.cells[tree.columns.items[0]]='hit'
        child=first.rows.add();child.cells[tree.columns.items[0]]='hit'
        self.assertIs(vm.execute('T.Rows.Find("hit","name")'),second)
        prepared=vm.prepare('T.Rows.Найти("hit"," Name, Name ",True)')
        self.assertIs(vm.execute_prepared(prepared),child)
        self.assertIs(vm.execute('R.Rows.Find("hit")'),child)
        child.cells[tree.columns.items[0]]='gone'
        self.assertIs(vm.execute_prepared(prepared),second)
        self.assertIsNone(vm.execute('R.Rows.Find("hit","Name",True)'))

    def test_find_checks_only_the_rows_it_reaches(self):
        vm=self.vm();tree,first=self.setup_tree(vm)
        last=tree.rows.add();last.cells={}
        # Search stops at the first hit, without validating unrelated rows.
        self.assertIs(vm.execute('T.Rows.Find("one","Name",True)'),first)
        with self.assertRaises(BoundaryViolation):
            vm.execute('T.Rows.Find("absent","Name",True)')
        # A non-recursive search never visits the first row's children.
        last.cells={tree.columns.items[0]:'hit'}
        first.rows.items.append(None)
        self.assertIs(vm.execute('T.Rows.Find("hit","Name")'),last)
        with self.assertRaises(BoundaryViolation):
            vm.execute('T.Rows.Find("hit","Name",True)')

    def test_find_rechecks_live_row_membership_after_arguments(self):
        vm=self.vm(allow_extensions=True);tree,row=self.setup_tree(vm)
        vm.register_function('RemoveMembership',lambda:tree._all_rows.pop(row) or 'one')
        with self.assertRaises(BoundaryViolation):
            vm.execute('T.Rows.Find(RemoveMembership(),"Name")')
        self.assertIs(tree.rows.items[0],row)

    def test_find_rechecks_activation_after_arguments(self):
        vm=self.vm(allow_extensions=True);self.setup_tree(vm)
        vm.register_function('Close',lambda:vm.close() or 'one')
        with self.assertRaises(BoundaryViolation):
            vm.execute('T.Rows.Find(Close(),"Name")')

    def test_read_projections_share_rows_and_only_visit_requested_depth(self):
        from decimal import Decimal
        vm=self.vm();tree,first=self.setup_tree(vm)
        total=tree.columns.add('Amount')
        name=tree.columns.items[0]
        first.cells[total]=Decimal(3)
        second=tree.rows.add()
        second.cells.update({name:'one',total:Decimal(5)})
        child=first.rows.add()
        child.cells.update({name:'one',total:Decimal(11)})
        selected=vm.execute('T.Rows.НайтиСтроки(New Structure("Name","one"),True)')
        self.assertEqual(len(selected.items),3)
        for actual,expected in zip(selected.items,(first,child,second)):
            self.assertIs(actual,expected)
        self.assertEqual(vm.execute('T.Rows.Итог("Amount",True)'),Decimal(19))

        # Appending to the tree changes future searches, not the result array.
        extra=tree.rows.add()
        extra.cells[total]=Decimal(7)
        self.assertEqual(len(selected.items),3)
        self.assertEqual(vm.execute('T.Rows.ВыгрузитьКолонку("Amount")').items,
                         [Decimal(3),Decimal(5),Decimal(7)])
        child.cells={}
        self.assertEqual(vm.execute('T.Rows.Total("Amount")'),Decimal(15))
        local=vm.execute('T.Rows.FindRows(New Structure("Name","one"))')
        self.assertIs(local.items[0],first)
        self.assertIs(local.items[1],second)
        for source in ('T.Rows.Total("Amount",True)',
                       'T.Rows.FindRows(New Structure("Name","one"),True)',
                       'R.Rows.UnloadColumn("Amount")'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):
                vm.execute(source)
        # Empty filters still produce an empty snapshot, with no row visited.
        self.assertEqual(vm.execute('R.Rows.FindRows(New Structure)').items,[])

    def test_read_projections_recheck_direct_arguments_and_cell_membership(self):
        vm=self.vm(allow_extensions=True);tree,row=self.setup_tree(vm)
        foreign_col=trees.BSLValueTree().columns.add('Name')
        vm.register_function('ChangeCells',lambda: setattr(row,'cells',{foreign_col:'one'}) or 'Name')
        for method in ('Total','UnloadColumn'):
            row.cells={tree.columns.items[0]:'one'}
            with self.subTest(method=method),self.assertRaises(BoundaryViolation):
                vm.execute(f'T.Rows.{method}(ChangeCells())')
        self.assertIs(tree.rows.items[0],row)

    def test_prepared_positional_metadata_reads_do_not_walk_row_graph(self):
        import sys
        vm=self.vm();tree,row=self.setup_tree(vm)
        column=tree.columns.items[0]
        unrelated=tree.rows.add();unrelated.cells={}
        tree.rows.items.reverse()
        program=vm.prepare('C=T.Columns.Найти("name");'
                           'CP=T.Columns.IndexOf(C);RP=T.Rows.Индекс(R);')
        checks=[]
        graph=trees.BSLValueTree._clear_graph.__code__;previous=sys.getprofile()
        def profile(frame,event,argument):
            if event=='call' and frame.f_code is graph:checks.append(1)
        sys.setprofile(profile)
        try:vm.execute_prepared(program)
        finally:sys.setprofile(previous)
        self.assertEqual(checks,[])
        self.assertIs(vm.variables['c'],column)
        self.assertEqual((vm.variables['cp'],vm.variables['rp']),(0,1))
        self.assertIsNone(vm.execute('T.Columns.Find("missing")'))
        other=trees.BSLValueTree();vm.variables['other']=other.rows.add()
        self.assertEqual(vm.execute('T.Rows.IndexOf(Other)'),-1)
        tree._all_rows.pop(row)
        with self.assertRaises(BoundaryViolation): vm.execute('T.Rows.IndexOf(R)')
        column._deleted=True
        with self.assertRaises(BoundaryViolation):vm.execute('T.Columns.Find("name")')

    def test_retained_deleted_child_reads_keep_catchable_model_error(self):
        vm=self.vm();self.setup_tree(vm)
        vm.execute('Retained=R.Rows;T.Rows.Delete(R);')
        for expression in ('Find("one","Name")','FindRows(New Structure("Name","one"))',
                           'Total("Name")','UnloadColumn("Name")','IndexOf(R)'):
            with self.subTest(expression=expression):
                vm.execute(f'Try Result=Retained.{expression};'
                           'Except Result="caught";EndTry;')
                self.assertEqual(vm.variables['result'],'caught')

    def test_forged_subclass_and_coherently_reparented_row_denied(self):
        vm=self.vm();tree,row=self.setup_tree(vm)
        other=trees.BSLValueTree();other.columns.add('Name')
        row.tree=other;row.collection=other.rows;row.parent=None;row.rows.tree=other
        other.rows.items.append(row);other._all_rows={row:None};row.cells={other.columns.items[0]:'one'}
        tree.rows.items.clear();tree._all_rows.clear()
        with self.assertRaises(BoundaryViolation):vm.execute('R.Name')
        forged=object.__new__(trees.BSLValueTree);forged.__dict__.update(other.__dict__)
        vm.variables['bad']=forged
        with self.assertRaises(BoundaryViolation):vm.execute('Bad.Rows')
        class Child(trees.BSLValueTree):pass
        vm.variables['bad']=Child()
        with self.assertRaises(BoundaryViolation):vm.execute('Bad.Rows')

    def test_row_index_reference_uses_live_column_position_or_name(self):
        vm=self.vm()
        vm.execute('Var T,Calls; T=New ValueTree; T.Columns.Add("Name"); Calls=0; '
                   'R=T.Rows.Add(); R.Name="one"; '
                   'Function NextIndex() Calls=Calls+1; Return 0; EndFunction '
                   'Function InsertColumn() T.Columns.Insert(0,"New"); Return "position"; EndFunction '
                   'Procedure Put(Target,Val NewValue) Target=NewValue; EndProcedure '
                   'Put(R[NextIndex()],InsertColumn()); Snapshot=R.New; R["nAmE"]="direct"; '
                   'Put(R["nAmE"],"name");')
        self.assertEqual(vm.execute('Calls'),1)
        self.assertEqual(vm.execute('Snapshot'),'position')
        self.assertEqual(vm.execute('R.Get(0)'),'position')
        self.assertEqual(vm.execute('R.Name'),'name')
        self.assertEqual(vm.execute('R.Get(1)'),'name')

    def test_bad_row_index_precedes_callee_and_deleted_row_cannot_be_written(self):
        vm=self.vm()
        vm.execute('Var T,R,Entered; T=New ValueTree; T.Columns.Add("Name"); '
                   'R=T.Rows.Add(); R[0]="start"; Entered=0;')
        definitions=('Var T,R,Entered; '
                     'Procedure Put(Target,Val Ignored) Entered=Entered+1; Target="changed"; EndProcedure '
                     'Function DeleteRow() T.Rows.Delete(R); Return 0; EndFunction ')
        for index in ('4','"missing"'):
            with self.subTest(index=index),self.assertRaises(BSLError):
                vm.execute(definitions+f'Put(R[{index}],0);')
        self.assertEqual(vm.execute('Entered'),0)
        self.assertEqual(vm.execute('R.Name'),'start')
        with self.assertRaisesRegex(BSLError,'отсоединенным'):
            vm.execute(definitions+'Put(R[0],DeleteRow());')
        self.assertEqual(vm.execute('Entered'),1)
        self.assertEqual(vm.execute('T.Rows.Count()'),0)

    def test_foreign_row_argument_and_deleted_row_semantics(self):
        vm=self.vm();tree,row=self.setup_tree(vm)
        other=trees.BSLValueTree();foreign=other.rows.add();vm.variables['foreign']=foreign
        with self.assertRaises(BSLError):vm.execute('T.Rows.Delete(Foreign)')
        self.assertEqual(vm.execute('T.Rows.Count()'),1)
        vm.execute('T.Rows.Delete(R)')
        with self.assertRaises(BSLError):vm.execute('R.Name')

    def test_late_argument_mutation_rechecks_before_method(self):
        vm=self.vm(allow_extensions=True);tree,row=self.setup_tree(vm);events=[]
        def mutate():
            tree.rows.add=lambda:events.append('hostile');return 0
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Insert(Mutate())')
        self.assertEqual(events,[]);self.assertEqual(len(tree.rows.items),1)

    def test_class_and_base_descriptors_denied_before_getter(self):
        vm=self.vm();self.setup_tree(vm);events=[]
        def getter(value):events.append('getter');return None
        for cls,name in ((trees.BSLValueTree,'columns'),(BSLObject,'__getattribute__')):
            with self.subTest(cls=cls),patch.object(cls,name,property(getter),create=True):
                with self.assertRaises(BoundaryViolation):vm.execute('T.Columns')
                self.assertEqual(events,[])

    def test_constructor_hooks_checked_before_and_after_arguments(self):
        vm=self.vm(allow_extensions=True);events=[]
        with patch.object(trees.BSLValueTree,'__init__',lambda *args:events.append('constructor')):
            with self.assertRaises(BoundaryViolation):vm.execute('New ValueTree')
        self.assertEqual(events,[])
        original=trees.BSLValueTree.__init__
        def mutate():trees.BSLValueTree.__init__=lambda *args:events.append('constructor');return 1
        vm.register_function('Mutate',mutate)
        try:
            with self.assertRaises(BoundaryViolation):vm.execute('New ValueTree(Mutate())')
        finally:trees.BSLValueTree.__init__=original
        self.assertEqual(events,[])

    def test_owner_revocation_prevents_method_after_arguments(self):
        vm=self.vm(allow_extensions=True);tree,row=self.setup_tree(vm)
        vm.register_function('Close',lambda:vm.close() or 0)
        with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Insert(Close())')
        self.assertEqual(len(tree.rows.items),1)

    def test_copy_checks_complete_registry_before_allocating_result(self):
        import sys
        vm=self.vm();tree,first=self.setup_tree(vm)
        copy=vm.prepare('T.Copy()')
        self.assertIsNot(vm.execute_prepared(copy).rows.items[0],first)
        orphan=tree.rows.add()
        self.assertIs(tree.rows.items.pop(),orphan)
        allocated=[]
        constructor=trees.BSLValueTree.__init__.__code__
        previous=sys.getprofile()
        def profile(frame,event,argument):
            if event=='call' and frame.f_code is constructor:
                allocated.append(1)
        sys.setprofile(profile)
        try:
            with self.assertRaises((BoundaryViolation,BSLError)):
                vm.execute_prepared(copy)
        finally:
            sys.setprofile(previous)
        self.assertEqual(allocated,[])
        self.assertIs(tree.rows.items[0],first)

    def test_class_copy_bookkeeping_does_not_invalidate_live_tree(self):
        vm=self.vm();tree,row=self.setup_tree(vm)
        for value in (tree,tree.rows,row,tree.columns,tree.columns.items[0]):copy.copy(value)
        self.assertEqual(vm.execute('R.Name'),'one')
        clone=vm.execute('T.Copy()');vm.variables['clone']=clone
        self.assertEqual(vm.execute('Clone.Rows.Get(0).Name'),'one')
        with patch.object(trees.BSLValueTree,'__slotnames__',['hostile']):
            with self.assertRaises(BoundaryViolation):vm.execute('T.Rows')


    def test_eval_and_imported_owning_boundary(self):
        vm=self.vm();vm.execute('T=Eval("New ValueTree");');self.assertIs(type(vm.variables['t']),trees.BSLValueTree)
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'Side.bsl').write_text('Function Make() Export Return New ValueTree;EndFunction',encoding='utf-8')
            vm.execute('// #Import Side.bsl\nT=Side.Make();T.Columns.Add("Name");',str(root/'Main.bsl'))
            self.assertEqual(vm.execute('T.Columns.Count()'),1)

    def test_native_filter_and_load_adapters_are_shallow_and_specific(self):
        vm=self.vm();self.setup_tree(vm)
        vm.execute('A=New Array;A.Add("new");T.Rows.LoadColumn(A,"Name");Matches=T.Rows.FindRows(New Structure("Name","new"));')
        self.assertEqual(vm.execute('Matches.Count()'),1)
        self.assertIs(vm.execute('Matches[0]'),vm.variables['r'])
        self.assertEqual(vm.execute('R.Name'),'new')

    def test_retained_method_expires_after_activation(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=self.vm();tree,row=self.setup_tree(vm)
        context=make_boundary(vm);context.enter()
        try:method=context.resolve_member(tree.rows,'Count');self.assertEqual(method(),1)
        finally:context.leave()
        with self.assertRaises(BoundaryViolation):method()
        context.enter()
        try:
            with self.assertRaises(BoundaryViolation):method()
        finally:context.leave()

    def test_local_count_and_append_do_not_scan_unrelated_rows(self):
        # Poisoning the full-graph helper would be caught by the class seal;
        # count actual entry via profiling without weakening that guard.
        import sys
        vm=self.vm();tree,row=self.setup_tree(vm);calls=[]
        code=trees.BSLValueTree._clear_graph.__code__;old=sys.getprofile()
        def profile(frame,event,arg):
            if event=='call' and frame.f_code is code:calls.append(1)
        sys.setprofile(profile)
        try:vm.execute('For I=1 To 20 Do T.Rows.Add();N=T.Rows.Count();EndDo;')
        finally:sys.setprofile(old)
        self.assertEqual(calls,[]);self.assertEqual(vm.variables['n'],21)

    def test_column_add_preflights_registry_before_mutation(self):
        vm=self.vm();tree,row=self.setup_tree(vm);events=[]
        class Foreign:
            @property
            def cells(self):events.append('cells');return {}
        tree._all_rows={Foreign():None}
        with self.assertRaises((BoundaryViolation,BSLError)):vm.execute('T.Columns.Add("Other")')
        self.assertEqual(events,[]);self.assertEqual(len(tree.columns.items),1)

    def test_cell_collision_is_rejected_without_equality_hook(self):
        vm=self.vm();tree,row=self.setup_tree(vm);column=tree.columns.items[0];events=[]
        class Foreign:
            def __hash__(self):return hash(column)
            def __eq__(self,other):events.append('eq');return False
        row.cells={Foreign():'bad'}
        for source in ('R.Name','R.Name="new";','R.Get(0)','R[0]="new";'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):vm.execute(source)
        self.assertEqual(events,[])

    def test_corrupt_schema_and_depth_cannot_dispatch_callbacks(self):
        vm=self.vm();tree,row=self.setup_tree(vm);column=tree.columns.items[0];events=[]
        class Foreign:
            def adjust_value(self,*args):events.append('adjust');return None
            def __add__(self,other):events.append('add');return 0
        saved=column.value_type;column.value_type=Foreign()
        with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Add()')
        column.value_type=saved;row.depth=Foreign()
        with self.assertRaises(BoundaryViolation):vm.execute('R.Rows.Add()')
        row.depth=0;column.default=Foreign()
        with self.assertRaises((BoundaryViolation,BSLError)):vm.execute('T.Rows.Add()')
        self.assertEqual(events,[]);self.assertEqual(len(tree.rows.items),1)

    def test_uuid_defaults_require_exact_zero_in_the_owning_typed_column(self):
        from yadinassi.types.unique_identifiers import BSLUUID

        vm = self.vm()
        vm.execute('T=New ValueTree;T.Columns.Add("U",New TypeDescription("UUID"));'
                   'T.Columns.Add("Other");R=T.Rows.Add();')
        tree, row = (vm.variables[name] for name in ('t', 'r'))
        uuid_column, other_column = tree.columns.items
        zero = uuid_column.default
        self.assertIs(type(zero), BSLUUID)
        self.assertEqual(zero.text, '00000000-0000-0000-0000-000000000000')
        self.assertEqual(row.get_member('U'), zero)

        class OpaqueText(str):
            def __eq__(self, other):
                raise AssertionError('UUID text compared through a host hook')

        malformed = BSLUUID(zero.text)
        object.__setattr__(malformed, 'text', OpaqueText(zero.text))
        extended = BSLUUID(zero.text)
        object.__setattr__(extended, 'get_member', lambda *_: self.fail('injected UUID hook'))
        for column, default in (
                (uuid_column, object.__new__(BSLUUID)), (uuid_column, malformed),
                (uuid_column, extended),
                (uuid_column, BSLUUID('11111111-2222-4333-8444-555555555555')),
                (other_column, zero)):
            with self.subTest(column=column.name, default=type(default)):
                old = column.default
                column.default = default
                try:
                    with self.assertRaisesRegex(BSLError, 'Неверное значение по умолчанию'):
                        vm.execute('T.Rows.Add()')
                finally:
                    column.default = old
                self.assertEqual(len(tree.rows.items), 1)
                self.assertIs(tree.rows.items[0], row)

    def test_schema_class_and_instance_hooks_are_sealed(self):
        vm=self.vm();tree,row=self.setup_tree(vm);events=[]
        description=tree.columns.items[0].value_type
        with patch.object(type(description),'adjust_value',lambda *args:events.append('adjust')):
            with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Add()')
        object.__setattr__(description,'adjust_value',lambda *args:events.append('instance'))
        with self.assertRaises(BoundaryViolation):vm.execute('R.Name="new";')
        self.assertEqual(events,[])

    def test_full_tree_audit_observes_live_enum_state_not_dictionary_order(self):
        from yadinassi.types.values import BSLType

        vm = self.vm()
        tree, _ = self.setup_tree(vm)
        expected = tree.columns.items[0].value_type
        # ValueType takes the full checked getter, even in ordinary mode.
        plan = vm.prepare('C.ValueType')
        self.assertIs(vm.execute_prepared(plan), expected)
        current = vars(BSLType.STRING)
        saved = tuple(current.items())
        recreated = tuple((key.encode().decode(), value) for key, value in saved)
        self.assertTrue(any(key is not other for (key, _), (other, _) in zip(saved, recreated)))

        def replace(entries):
            current.clear()
            current.update(entries)

        try:
            replace(recreated)
            self.assertIs(vm.execute_prepared(plan), expected)
            replace(reversed(saved))
            self.assertIs(vm.execute_prepared(plan), expected)
            replace((*saved[:-1], (object(), saved[-1][1])))
            with self.assertRaisesRegex(BoundaryViolation, 'enum member fields changed'):
                vm.execute_prepared(plan)
            # Both identity and alternative-order lanes must read live values.
            for entries in (saved, tuple(reversed(saved))):
                replace(entries)
                current[entries[0][0]] = object()
                with self.assertRaisesRegex(BoundaryViolation, 'enum member state changed'):
                    vm.execute_prepared(plan)
        finally:
            replace(saved)
        self.assertIs(vm.execute_prepared(plan), expected)

    def test_retained_write_reference_and_iterator_do_not_revive(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=self.vm();tree,row=self.setup_tree(vm);context=make_boundary(vm);context.enter()
        try:
            write=context.resolve_set_member(row,'Name')
            reference=context.reference_member(row,'Name')
            iterator=context.resolve_member(tree.rows,'__iter__')()
        finally:context.leave()
        context.enter()
        try:
            with self.assertRaises(BoundaryViolation):write('bad')
            with self.assertRaises(BoundaryViolation):reference.get()
            with self.assertRaises(BoundaryViolation):next(iterator)
        finally:context.leave()
        self.assertEqual(row.cells[tree.columns.items[0]],'one')

    def test_get_and_iteration_reject_non_receiver_collection_items(self):
        vm=self.vm();tree,row=self.setup_tree(vm);foreign=object()
        tree.rows.items[0]=foreign
        for source in ('T.Rows.Get(0)','T.Rows[0]','For Each R In T.Rows Do EndDo;'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):vm.execute(source)
        tree.rows.items[0]=row;tree.columns.items[0]=foreign
        for source in ('T.Columns.Get(0)','For Each C In T.Columns Do EndDo;'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):vm.execute(source)

    def test_iteration_admits_abi_once_per_resume_and_rechecks_next_resume(self):
        import sys
        from yadinassi.execution.direct.python_direct import make_boundary
        from yadinassi.execution.direct import python_direct_value_tree as bridge

        # The explicit Python-extension path retains its full model audit.
        vm=self.vm(allow_extensions=True);tree,first=self.setup_tree(vm)
        second=tree.rows.add()
        context=make_boundary(vm);context.enter()
        try:
            iterator=context.resolve_member(tree.rows,'__iter__')()
            checks=[]
            code=bridge.hooks.__code__
            saved=sys.getprofile()
            def profile(frame,event,_argument):
                if event=='call' and frame.f_code is code:checks.append(1)
            sys.setprofile(profile)
            try:
                self.assertIs(next(iterator),first)
                self.assertIs(next(iterator),second)
                with self.assertRaises(StopIteration):next(iterator)
            finally:sys.setprofile(saved)
            self.assertEqual(len(checks),2)

            iterator=context.resolve_member(tree.rows,'__iter__')()
            self.assertIs(next(iterator),first)
            with patch.object(trees.BSLValueTreeRow,'level',lambda self:0):
                with self.assertRaises(BoundaryViolation):next(iterator)
        finally:context.leave()

    def test_iteration_still_rejects_canonical_child_from_other_tree(self):
        vm=self.vm();tree,_=self.setup_tree(vm)
        other=trees.BSLValueTree()
        other.columns.add('Name')
        tree.rows.items[0]=other.rows.add()
        with self.assertRaises(BoundaryViolation):
            vm.execute('For Each R In T.Rows Do EndDo;')

    def test_registry_rejects_hostile_keys_without_hash_eq_or_repr(self):
        vm=self.vm();tree,row=self.setup_tree(vm);events=[]
        class Foreign:
            def __hash__(self):events.append('hash');return 0
            def __eq__(self,other):events.append('eq');return True
            def __repr__(self):events.append('repr');return 'foreign'
        foreign=Foreign();registry=tree._all_rows
        for action in (lambda:registry.__setitem__(foreign,None),lambda:registry.pop(foreign),
                       lambda:registry.__getitem__(foreign),lambda:registry.__contains__(foreign)):
            with self.assertRaises(ValueError):action()
        with self.assertRaises(ValueError):registry[row]=1
        self.assertEqual(events,[]);self.assertEqual(dict(registry),{row:None})
        self.assertFalse(hasattr(registry,'__dict__'));self.assertFalse(hasattr(registry,'_data'))

    def test_registry_root_swap_and_raw_dictionary_are_not_admitted(self):
        vm=self.vm();tree,row=self.setup_tree(vm);other=trees.BSLValueTree()
        saved=tree._all_rows
        for replacement in ({row:None},other._all_rows):
            tree._all_rows=replacement
            with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Add()')
        tree._all_rows=saved
        self.assertEqual(vm.execute('T.Rows.Count()'),1)

    def test_registry_gc_dead_entry_and_retained_orphan(self):
        import gc,weakref
        tree=trees.BSLValueTree();row=tree.rows.add();registry=tree._all_rows
        tree_ref,row_ref=weakref.ref(tree),weakref.ref(row)
        del row,tree;gc.collect()
        self.assertIsNone(tree_ref());self.assertIsNone(row_ref())
        with self.assertRaises(ValueError):len(registry)
        registry_ref=weakref.ref(registry);identity=id(registry)
        del registry;gc.collect()
        self.assertIsNone(registry_ref());self.assertNotIn(identity,trees._ROW_REGISTRY_STATE)
        tree=trees.BSLValueTree();row=tree.rows.add();row_ref=weakref.ref(row)
        tree.rows.items.clear();del row;gc.collect()
        self.assertIsNone(row_ref())
        with self.assertRaises(ValueError):len(tree._all_rows)
        with self.assertRaises(ValueError):tree.rows.add()

    def test_registry_copy_order_and_delete_clear(self):
        tree=trees.BSLValueTree();a=tree.rows.add();b=a.rows.add();c=tree.rows.add()
        self.assertEqual(list(tree._all_rows),[a,b,c]);self.assertEqual(list(tree._all_rows.items()),[(a,None),(b,None),(c,None)])
        clone=tree.copy();self.assertEqual(len(clone._all_rows),3)
        self.assertTrue(all(row.tree is clone for row in clone._all_rows))
        tree.rows.delete(a);self.assertEqual(list(tree._all_rows),[c])
        tree.rows.clear();self.assertEqual(tree._all_rows,{})

    def test_dependency_callbacks_are_denied_before_native_effects(self):
        from yadinassi.types.values import BSLArray,BSLType
        from yadinassi.temporal.dates import BSLDate
        from yadinassi.types.type_qualifiers import BSLAllowedSign
        vm=self.vm();vm.execute('T=New ValueTree;T.Columns.Add("D",New TypeDescription("Date"));S=New Structure;T.Rows.Add();')
        events=[]
        for cls,name,source in ((BSLArray,'__init__','T.Rows.FindRows(S)'),
                                (BSLDate,'__init__','T.Rows.Add()'),
                                (BSLType,'__hash__','T.Rows.Add()'),
                                (BSLAllowedSign,'__eq__','T.Rows.Add()')):
            with self.subTest(cls=cls),patch.object(cls,name,lambda *a:events.append('callback'),create=True):
                with self.assertRaises(BoundaryViolation):vm.execute(source)
                self.assertEqual(events,[])
        self.assertEqual(vm.execute('T.Rows.Count()'),1)

    def test_registry_class_hook_denied_before_dispatch(self):
        vm=self.vm();tree,row=self.setup_tree(vm);events=[]
        with patch.object(type(tree._all_rows),'__len__',lambda self:events.append('len') or 0):
            with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Add()')
        self.assertEqual(events,[])

    def test_registry_removed_rows_do_not_mark_live_registry_corrupt(self):
        import gc,weakref
        tree=trees.BSLValueTree();row=tree.rows.add();row_ref=weakref.ref(row)
        tree.rows.delete(row);del row;gc.collect()
        self.assertIsNone(row_ref());self.assertEqual(len(tree._all_rows),0)
        tree.rows.add();self.assertEqual(len(tree._all_rows),1)

    def test_registry_local_add_has_constant_storage_check_count(self):
        import sys
        vm=self.vm();self.setup_tree(vm)
        state_code=trees._registry_state.__code__;iter_code=trees._RowRegistry.__iter__.__code__
        totals=[];old=sys.getprofile()
        for size in (10,20):
            count=[0,0]
            def profile(frame,event,arg):
                if event=='call':
                    if frame.f_code is state_code:count[0]+=1
                    elif frame.f_code is iter_code:count[1]+=1
            sys.setprofile(profile)
            try:vm.execute('For I=1 To '+str(size)+' Do T.Rows.Add();N=T.Rows.Count();EndDo;')
            finally:sys.setprofile(old)
            totals.append(count)
        self.assertEqual(totals[0][1],0);self.assertEqual(totals[1][1],0)
        self.assertGreater(totals[0][0],0);self.assertEqual(totals[1][0],2*totals[0][0])

    def test_scalar_copy_bookkeeping_does_not_poison_tree_dispatch(self):
        from yadinassi.temporal.dates import BSLDate
        from yadinassi.types.unique_identifiers import BSLUUID
        vm=self.vm();self.setup_tree(vm)
        for scalar in (BSLDate(0),BSLUUID('00000000-0000-0000-0000-000000000000')):
            copy.copy(scalar);copy.deepcopy(scalar)
        self.assertEqual(vm.execute('T.Rows.Count()'),1)

    def test_definition_time_dependencies_are_not_blessed_by_lazy_import(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            import sys
            from unittest.mock import patch
            from yadinassi import Interpreter
            from yadinassi.collections.value_trees import BSLValueTree
            from yadinassi.types.type_descriptions import BSLTypeDescription
            from yadinassi.temporal.dates import BSLDate
            from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
            tree=BSLValueTree();tree.columns.add('D',BSLTypeDescription('Date'))
            vm=Interpreter();vm.variables['t']=tree;events=[]
            if 'yadinassi.execution.direct.python_direct_value_tree' in sys.modules:raise AssertionError('helper imported early')
            with patch.object(BSLDate,'__init__',lambda *args:events.append('callback')):
                try:vm.execute('T.Rows.Add()')
                except BoundaryViolation:pass
                else:raise AssertionError('patched date admitted')
            if events:raise AssertionError(events)
            vm.close()
        ''')
        command=[sys.executable]+(['-O'] if not __debug__ else [])+['-c',script]
        result=subprocess.run(command,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_enum_member_state_and_foreign_field_keys_are_sealed(self):
        from yadinassi.types.values import BSLType
        from yadinassi.types.type_qualifiers import BSLAllowedSign,BSLAllowedLength,BSLDateFractions
        vm=self.vm();vm.execute('T=New ValueTree;T.Columns.Add("S",New TypeDescription("String"));')
        events=[]
        class Evil:
            def __hash__(self):events.append('hash');return hash('_name_')
            def __eq__(self,other):events.append('eq');return False
        for member in (BSLType.STRING,BSLAllowedSign.ANY,BSLAllowedLength.FIXED,BSLDateFractions.DATE_TIME):
            for field in ('_name_','_value_'):
                with self.subTest(member=type(member),field=field),patch.object(member,field,Evil()):
                    with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Add()')
                    self.assertEqual(events,[])
            saved=dict(vars(member));bad=Evil()
            try:
                vars(member).pop('_name_');vars(member)[bad]='bad';events.clear()
                with self.assertRaises(BoundaryViolation):vm.execute('T.Rows.Add()')
                self.assertEqual(events,[])
            finally:vars(member).clear();vars(member).update(saved)
        self.assertEqual(vm.execute('T.Rows.Count()'),0)

    def test_enum_member_state_is_captured_before_lazy_bridge(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            import sys
            from unittest.mock import patch
            from yadinassi import Interpreter
            from yadinassi.collections.value_trees import BSLValueTree
            from yadinassi.types.type_descriptions import BSLTypeDescription
            from yadinassi.types.values import BSLType
            from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
            tree=BSLValueTree();tree.columns.add('S',BSLTypeDescription('String'))
            vm=Interpreter();vm.variables['t']=tree;events=[]
            if 'yadinassi.execution.direct.python_direct_value_tree' in sys.modules:raise AssertionError('helper imported early')
            class Evil:
                def __hash__(self):events.append('hash');return 0
            with patch.object(BSLType.STRING,'_name_',Evil()):
                try:vm.execute('T.Rows.Add()')
                except BoundaryViolation:pass
                else:raise AssertionError('patched member admitted')
            if events:raise AssertionError(events)
            vm.close()
        ''')
        command=[sys.executable]+(['-O'] if not __debug__ else [])+['-c',script]
        result=subprocess.run(command,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
