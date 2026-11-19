"""Eager canonical collection islands, paired against ordinary direct routing."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_collection_regions import analyze
from yadinassi.collections.value_tables import BSLValueTable, BSLValueTableRow
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem


def snapshot(vm):
    def value(v):
        if type(v) is BSLValueTable:
            return ('table', tuple(c.name for c in v.columns.items), tuple(tuple(r.cells[c] for c in v.columns.items) for r in v.rows))
        if type(v) is BSLValueList:
            return ('list',tuple((i.value,i.presentation,i.check,i.get_id()) for i in v.items),v._next_id,v._revision,tuple(v._by_id))
        if type(v) is BSLValueTableRow:
            return ('row',next((k for k,x in vm.variables.items() if x is v.table),None),v.table.rows.index(v))
        if type(v) is BSLValueListItem:
            return ('item',v.value,v.get_id())
        return v
    return {k:value(v) for k,v in vm.variables.items()}


class CollectionRegionsTests(unittest.TestCase):
    def paired(self, source, *, install=None):
        outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            if install:install(vm)
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},frozenset())):
                plan=vm.prepare(source)
            error=None
            try:vm.execute_prepared(plan)
            except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs)
        return outputs[-1]

    def test_table_full_graph_and_suffix_observers(self):
        values,error=self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 8 Do Row=T.Add();Row.N=I;EndDo;R=0;For I=0 To 8 Do R=R+T.Get(I).N;EndDo;Same=(Row=T.Get(8));Owner=(Row.Owner()=T);')
        self.assertIsNone(error);self.assertEqual(values['r'],36);self.assertTrue(values['same']);self.assertTrue(values['owner'])

    def test_list_full_graph_ids_and_suffix_mutation(self):
        values,error=self.paired('T=New ValueList;For I=0 To 8 Do Item=T.Add(I);EndDo;R=0;For I=0 To 8 Do R=R+T.Get(I).Value;EndDo;T.Delete(0);Same=(Item=T.Get(7));')
        self.assertIsNone(error);self.assertTrue(values['same']);self.assertEqual(values['r'],36)

    def test_multiple_columns_and_fresh_collections(self):
        self.paired('T=New ValueTable;T.Columns.Add("A");T.Columns.Add("B");L=New ValueList;For I=1 To 5 Do Row=T.Add();Row.A=I;Row.B=I*2;L.Add(Row.B);EndDo;')

    def test_partial_arithmetic_failure_retains_added_default_row(self):
        values,error=self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 5 Do Row=T.Add();Row.N=1/(3-I);EndDo;')
        self.assertIsNotNone(error);self.assertEqual(values['i'],3);self.assertEqual(len(values['t'][2]),4);self.assertIsNone(values['t'][2][-1][0])

    def test_partial_list_failure_does_not_add(self):
        values,error=self.paired('T=New ValueList;For I=0 To 5 Do T.Add(1/(3-I));EndDo;')
        self.assertIsNotNone(error);self.assertEqual(len(values['t'][1]),3)

    def test_invalid_field_evaluation_order(self):
        self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 3 Do Row=T.Add();Row.Unknown=1/(1-I);EndDo;')

    def test_zero_iteration_does_not_rebind_existing_row(self):
        self.paired('T=New ValueTable;T.Columns.Add("N");For I=1 To 0 Do Row=T.Add();Row.N=I;EndDo;')

    def test_fractional_negative_get_and_case_aliases(self):
        self.paired('Т=Новый ТаблицаЗначений;Т.Колонки.Добавить("Число");Для Инд=0 По 4 Цикл Стр=Т.Добавить();Стр.число=Инд;КонецЦикла;R=Т.Получить(1.9).ЧИСЛО;')
        self.paired('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;R=T.Get(-0.1).Value;')

    def test_unknown_call_ends_region_and_can_mutate(self):
        def install(vm):
            vm.register_function('Change',lambda:vm.variables['t'].clear())
        self.paired('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;Change();R=T.Get(0).Value;',install=install)

    def test_callback_inside_loop_disables_whole_loop(self):
        def install(vm):vm.register_function('Callback',lambda:Decimal(2))
        self.paired('T=New ValueList;For I=0 To 2 Do T.Add(Callback());EndDo;',install=install)

    def test_runtime_abi_change_selects_ordinary_direct(self):
        source='T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;'
        vm=Interpreter();self.addCleanup(vm.close);plan=vm.prepare(source)
        original=BSLValueList.add;calls=[]
        def changed(owner,*args):calls.append(args);return original(owner,*args)
        with patch.object(BSLValueList,'add',changed):
            vm.execute_prepared(plan)
        self.assertEqual(len(calls),3)

    def test_preparation_during_patch_does_not_capture_replacement(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with patch.object(BSLValueList,'add',side_effect=AssertionError('stale patched method')):
            plan=vm.prepare('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
        vm.execute_prepared(plan);self.assertEqual(len(vm.variables['t'].items),3)

    def test_descriptor_dependency_callback_stops_at_same_source_boundary(self):
        from yadinassi.types import type_descriptions as td
        original=td._reference_description_kind
        outputs=[]
        source='T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;'
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},frozenset())):
                plan=vm.prepare(source)
            def hook(x):
                vm.close();return original(x)
            error=None
            with patch.object(td,'_reference_description_kind',hook):
                try:vm.execute_prepared(plan)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs)
        self.assertNotIn('i',outputs[-1][0])

    def test_fast_gate_is_reached_and_enabled(self):
        from yadinassi.execution.direct import python_direct_collection_regions as region
        seen=[];original=region.admitted
        def gate(*args):
            result=original(*args);seen.append(result);return result
        vm=Interpreter();self.addCleanup(vm.close)
        with patch.object(region,'admitted',gate):
            vm.execute('T=New ValueTable;T.Columns.Add("N");For I=0 To 4 Do Row=T.Add();Row.N=I;EndDo;R=0;For I=0 To 4 Do R=R+T.Get(I).N;EndDo;')
        self.assertEqual(seen,[True,True])

    def test_modulo_failure_preserves_partial_graph_in_fast_loop(self):
        values,error=self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 5 Do Row=T.Add();Row.N=1%(3-I);EndDo;')
        self.assertIsNotNone(error);self.assertEqual(values['i'],3);self.assertEqual(len(values['t'][2]),4)
        self.assertIsNone(values['t'][2][-1][0])

    def test_nested_loops_and_non_benchmark_names(self):
        self.paired('Data=New ValueTable;Data.Columns.Add("Price");Items=New ValueList;For A=1 To 3 Do For B=1 To 4 Do Entry=Data.Add();Entry.Price=A*B;Items.Add(Entry.Price);EndDo;EndDo;')

    def test_old_global_len_injection_selects_normal_boundary(self):
        from yadinassi.collections import value_tables as table
        outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},{})):
                plan=vm.prepare('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;')
            def injected(value):vm.close();return len(value)
            error=None
            with patch.object(table,'len',injected,create=True):
                try:vm.execute_prepared(plan)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs)

    def test_weakref_callback_uses_normal_boundary_not_raw_leaf(self):
        import weakref
        original=weakref.ref;outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},{})):
                plan=vm.prepare('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
            def injected(value,*args):
                if type(value) is BSLValueList:vm.close()
                return original(value,*args)
            error=None
            with patch.object(weakref,'ref',injected):
                try:vm.execute_prepared(plan)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[1][0]['t'][1]),1)

    def test_budget_limit_override_keeps_partial_state(self):
        from yadinassi.collections import value_lists as lists,value_tables as tables
        with patch.object(lists,'_MAX_ITEMS',3):
            values,error=self.paired('T=New ValueList;For I=0 To 5 Do T.Add(I);EndDo;')
            self.assertIsNotNone(error);self.assertEqual(len(values['t'][1]),3)
        with patch.object(tables,'_MAX_ROWS',3):
            values,error=self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 5 Do Row=T.Add();Row.N=I;EndDo;')
            self.assertIsNotNone(error);self.assertEqual(len(values['t'][2]),3)

    def test_mutated_registration_never_becomes_raw_receiver(self):
        def install(vm):
            from yadinassi.types.values import HostFunction
            vm.types['valuelist']=HostFunction('ValueList',lambda:object())
        values,error=self.paired('T=New ValueList;For I=0 To 3 Do T.Add(I);EndDo;',install=install)
        self.assertIsNotNone(error);self.assertNotIn('t',values)

    def test_instance_shadow_self_restoring_hook_uses_normal_dispatch(self):
        from yadinassi.types import type_descriptions as td
        original=td._reference_description_kind;outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},{})):
                plan=vm.prepare('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;')
            def hook(description):
                td._reference_description_kind=original
                table=vm.variables['t'];add=table.add
                def changed():vm.close();return add()
                table.add=changed
                return original(description)
            error=None
            with patch.object(td,'_reference_description_kind',hook):
                try:vm.execute_prepared(plan)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][2]),1)

    def test_detached_aliases_decline_guard(self):
        from yadinassi.execution.direct.python_direct_collection_regions import admitted
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=Interpreter();self.addCleanup(vm.close);context=make_boundary(vm);context.start()
        table=BSLValueTable();table.columns.add('N');row=table.add();table.delete(row)
        self.assertFalse(admitted(context,{'t':table,'row':row},{'t':'table','row':'row'}))
        values=BSLValueList();item=values.add(Decimal(1));values.delete(Decimal(0))
        self.assertFalse(admitted(context,{'t':values,'item':item},{'t':'list','item':'item'}))

    def test_graph_guard_rejects_hostile_keys_without_equality(self):
        from yadinassi.execution.direct.python_direct_collection_regions import admitted
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=Interpreter();self.addCleanup(vm.close);context=make_boundary(vm);context.start()
        table=BSLValueTable()
        class Key:
            def __hash__(self):return hash('rows')
            def __eq__(self,other):raise AssertionError('host equality')
        # Replace the dict rather than insert alongside colliding string key.
        fields=dict(vars(table));fields.pop('rows');fields[Key()]=[]
        table.__dict__=fields
        self.assertFalse(admitted(context,{'t':table},{'t':'table'}))

    def test_changed_function_defaults_preserve_canonical_behavior(self):
        old=BSLValueList.add.__defaults__
        try:
            BSLValueList.add.__defaults__=(None,'custom',True)
            values,error=self.paired('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
            self.assertIsNone(error);self.assertEqual(values['t'][1][0][1:3],('custom',True))
        finally:BSLValueList.add.__defaults__=old

    def test_each_leaf_has_entry_and_exit_liveness_even_baseexception(self):
        from yadinassi.execution.direct.python_direct_collection_regions import helpers
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        operations=helpers();table=BSLValueTable();table.columns.add('N')
        class Context:
            def __init__(self,fail):self.calls=0;self.fail=fail
            def _check(self):
                self.calls+=1
                if self.calls==self.fail:raise BoundaryViolation('revoked')
        with self.assertRaises(BoundaryViolation):operations['table_add'](Context(1),table)
        self.assertEqual(len(table.rows),0)
        with self.assertRaises(BoundaryViolation):operations['table_add'](Context(2),table)
        self.assertEqual(len(table.rows),1)
        context=Context(99)
        with self.assertRaises(IndexError):operations['table_get'](context,table,Decimal(9))
        self.assertEqual(context.calls,2)

    def test_zero_outer_nested_same_counter_and_missing_fields(self):
        self.paired('T=New ValueList;For I=2 To 1 Do For I=0 To 2 Do T.Add(I);EndDo;EndDo;')
        self.paired('T=New ValueList;For I=0 To 2 Do For I=0 To 2 Do T.Add(I);EndDo;EndDo;')
        self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.Absent=1%I;EndDo;')
        self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();R=Row.Absent;EndDo;')

    def test_numeric_digit_budget_in_real_fast_loop(self):
        values,error=self.paired('T=New ValueList;X='+('9'*4097)+';For I=0 To 2 Do T.Add(X);EndDo;')
        self.assertIsNotNone(error);self.assertEqual(len(values['t'][1]),0)

    def test_leaf_resource_limits_checked_before_allocation(self):
        from yadinassi.execution.direct.python_direct_collection_regions import helpers
        class Context:
            def _check(self):pass
        functions=helpers();table=BSLValueTable();table.rows=[None]*100000
        with self.assertRaisesRegex(ValueError,'предел ресурсов'):
            functions['table_add'](Context(),table)
        self.assertEqual(len(table.rows),100000)
        values=BSLValueList();values._next_id=2**32
        with self.assertRaisesRegex(ValueError,'предел идентификаторов'):
            functions['list_add'](Context(),values,Decimal(1))
        self.assertEqual(values.items,[])

    def test_prior_host_local_finalizer_cannot_invalidate_loop_proof(self):
        outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            class Previous:
                def __del__(self):
                    table=vm.variables['t'];add=table.add
                    def changed():vm.close();return add()
                    table.add=changed
            vm.variables['row']=Previous()
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},{})):
                plan=vm.prepare('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;')
            error=None
            try:vm.execute_prepared(plan)
            except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][2]),2)

    def test_host_finalizer_between_loops_cannot_leave_stale_fast_flag(self):
        outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            class Previous:
                def __del__(self):
                    table=vm.variables['t'];add=table.add
                    def changed():vm.close();return add()
                    table.add=changed
            vm.variables['r']=Previous()
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},{})):
                plan=vm.prepare('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;R=0;Row=T.Add();')
            error=None
            try:vm.execute_prepared(plan)
            except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][2]),4)

    def test_old_canonical_item_external_weakref_callback_declines(self):
        import weakref
        outputs=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            old=BSLValueList();item=old.add(Decimal(0));del old
            vm.variables['item']=item
            def callback(reference):
                collection=vm.variables['t'];add=collection.add
                def changed(*args):vm.close();return add(*args)
                collection.add=changed
            watch=weakref.ref(item,callback);del item
            with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else lambda *a,**k:(0,{},{})):
                plan=vm.prepare('T=New ValueList;For I=0 To 2 Do Item=T.Add(I);EndDo;')
            error=None
            try:vm.execute_prepared(plan)
            except BaseException as e:error=(type(e).__name__,str(e))
            self.assertIsNone(watch())
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][1]),2)

    def test_old_graph_qualifier_payload_and_oversized_rows_decline(self):
        from yadinassi.execution.direct.python_direct_collection_regions import admitted
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=Interpreter();self.addCleanup(vm.close);context=make_boundary(vm);context.start()
        table=BSLValueTable();column=table.columns.add('N')
        class Host:
            def __getattribute__(self,name):raise AssertionError('host descriptor payload')
        object.__setattr__(column.value_type,'number_qualifiers',Host())
        self.assertFalse(admitted(context,{'t':table},{'t':'table'}))
        table=BSLValueTable();table.rows=[None]*100001
        self.assertFalse(admitted(context,{'t':table},{'t':'table'}))

    def test_no_legacy_execution(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy')):
            vm.execute('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
        self.assertEqual(len(vm.variables['t'].items),3)

if __name__=='__main__':unittest.main()
