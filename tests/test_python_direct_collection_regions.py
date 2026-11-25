"""Observable table/list behavior through the only direct generator."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.collections.value_tables import BSLValueTable, BSLValueTableRow
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem
from yadinassi.collections.plain_value_list import PlainValueList, PlainValueListItem


def snapshot(vm):
    # Across VMs, compare observable aliases rather than the identities of
    # freshly allocated rows/items themselves. Keep all names of a live owner.
    by_identity = {}
    for name, v in sorted(vm.variables.items()):
        by_identity.setdefault(id(v), []).append(name)

    def aliases(v):
        return tuple(by_identity.get(id(v), ())) if v is not None else ()

    def item_fields(item):
        return (*tuple(item), item.get_id())

    def value(v):
        if type(v) is BSLValueTable:
            return ('table', tuple(c.name for c in v.columns.items), tuple(tuple(r.cells[c] for c in v.columns.items) for r in v.rows))
        if type(v) is BSLValueList:
            return ('list',tuple(((i.value,i.presentation,i.check,None,i.get_id()),aliases(i)) for i in v.items),aliases(v))
        if type(v) is PlainValueList:
            return ('list',tuple((item_fields(item), aliases(item)) for item in v),aliases(v))
        if type(v) is BSLValueTableRow:
            return ('row',next((k for k,x in vm.variables.items() if x is v.table),None),v.table.rows.index(v))
        if type(v) is BSLValueListItem:
            return ('item',(v.value,v.presentation,v.check,None,v.get_id()),aliases(v._owner_ref()),aliases(v))
        if type(v) is PlainValueListItem:
            return ('item',item_fields(v),aliases(v._membership.owner()),aliases(v))
        return v
    return {k:value(v) for k,v in vm.variables.items()}


class CollectionRegionsTests(unittest.TestCase):
    def paired(self, source, *, install=None):
        outputs=[]
        for prepared in (False,True):
            vm=Interpreter(allow_extensions=install is not None);self.addCleanup(vm.close)
            if install:install(vm)
            error=None
            try:
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
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
        self.assertEqual(tuple((fields[0], fields[4]) for fields,_ in values['t'][1]),
                         tuple((i,i) for i in range(1,9)))

    def test_snapshot_distinguishes_equal_items_from_different_owners(self):
        snapshots = []
        for name in ('A','B'):
            vm=Interpreter();self.addCleanup(vm.close)
            vm.execute('A=New ValueList; B=New ValueList; A.Add(7); B.Add(7); Item='+name+'.Get(0);')
            snapshots.append(snapshot(vm))
        self.assertNotEqual(*snapshots)

    def test_multiple_columns_and_fresh_collections(self):
        values,error=self.paired('T=New ValueTable;T.Columns.Add("A");T.Columns.Add("B");L=New ValueList;For I=1 To 5 Do Row=T.Add();Row.A=I;Row.B=I*2;L.Add(Row.B);EndDo;')
        self.assertIsNone(error)
        self.assertEqual(values['t'][2],tuple((i,i*2) for i in range(1,6)))
        self.assertEqual(tuple(fields[0] for fields,_ in values['l'][1]),(2,4,6,8,10))

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
        values,error=self.paired('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;R=T.Get(-0.1).Value;')
        self.assertIsNone(error);self.assertEqual(values['r'],0)

    def test_unknown_call_ends_region_and_can_mutate(self):
        def install(vm):
            vm.register_function('Change',lambda:vm.variables['t'].clear())
        values,error=self.paired('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;Change();R=T.Get(0).Value;',install=install)
        self.assertEqual(values['t'][1],())
        self.assertNotIn('r',values)
        self.assertEqual(error[0],'BSLRuntimeError')

    def test_callback_inside_loop_disables_whole_loop(self):
        calls=[]
        def install(vm):
            calls.append([])
            seen=calls[-1]
            vm.register_function('Callback',lambda:seen.append('called') or Decimal(2))
        values,error=self.paired('T=New ValueList;For I=0 To 2 Do T.Add(Callback());EndDo;',install=install)
        self.assertIsNone(error)
        self.assertEqual(tuple(fields[0] for fields,_ in values['t'][1]),(2,2,2))
        self.assertEqual(calls,[['called']*3,['called']*3])

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
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            source=(source)
            def hook(x):
                vm.close();return original(x)
            error=None
            with patch.object(td,'_reference_description_kind',hook):
                try:
                    if prepared:vm.execute_prepared(vm.prepare(source))
                    else:vm.execute(source)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs)
        self.assertNotIn('i',outputs[-1][0])

    def test_routine_table_build_keeps_mutations_and_result(self):
        source=(
            'Function Build() T=New ValueTable;T.Columns.Add("N");'
            'For I=0 To 4 Do Row=T.Add();Row.N=I;EndDo;R=0;'
            'For I=0 To 4 Do R=R+T.Get(I).N;EndDo;Return R;EndFunction;'
            'Result=Build();'
        )
        values,error=self.paired(source)
        self.assertIsNone(error)
        self.assertEqual(values['result'],Decimal(10))

    def test_modulo_failure_preserves_partial_graph_in_fast_loop(self):
        values,error=self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 5 Do Row=T.Add();Row.N=1%(3-I);EndDo;')
        self.assertIsNotNone(error);self.assertEqual(values['i'],3);self.assertEqual(len(values['t'][2]),4)
        self.assertIsNone(values['t'][2][-1][0])

    def test_nested_loops_and_non_benchmark_names(self):
        values,error=self.paired('Data=New ValueTable;Data.Columns.Add("Price");Items=New ValueList;For A=1 To 3 Do For B=1 To 4 Do Entry=Data.Add();Entry.Price=A*B;Items.Add(Entry.Price);EndDo;EndDo;')
        self.assertIsNone(error)
        expected=tuple(a*b for a in range(1,4) for b in range(1,5))
        self.assertEqual(values['data'][2],tuple((v,) for v in expected))
        self.assertEqual(tuple(fields[0] for fields,_ in values['items'][1]),expected)

    def test_old_global_len_injection_selects_normal_boundary(self):
        from yadinassi.collections import value_tables as table
        outputs=[]
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            source=('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;')
            def injected(value):vm.close();return len(value)
            error=None
            with patch.object(table,'len',injected,create=True):
                try:
                    if prepared:vm.execute_prepared(vm.prepare(source))
                    else:vm.execute(source)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs)

    def test_weakref_callback_uses_normal_boundary_not_raw_leaf(self):
        import weakref
        original=weakref.ref;outputs=[]
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            source=('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
            def injected(value,*args):
                if type(value) is BSLValueList:vm.close()
                return original(value,*args)
            error=None
            with patch.object(weakref,'ref',injected):
                try:
                    if prepared:vm.execute_prepared(vm.prepare(source))
                    else:vm.execute(source)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[1][0]['t'][1]),1)

    def test_mutated_registration_never_becomes_raw_receiver(self):
        def install(vm):
            from yadinassi.types.values import HostFunction
            vm.types['valuelist']=HostFunction('ValueList',lambda:object())
        values,error=self.paired('T=New ValueList;For I=0 To 3 Do T.Add(I);EndDo;',install=install)
        self.assertIsNotNone(error);self.assertNotIn('t',values)

    def test_instance_shadow_self_restoring_hook_uses_normal_dispatch(self):
        from yadinassi.types import type_descriptions as td
        original=td._reference_description_kind;outputs=[]
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            source=('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;')
            def hook(description):
                td._reference_description_kind=original
                table=vm.variables['t'];add=table.add
                def changed():vm.close();return add()
                table.add=changed
                return original(description)
            error=None
            with patch.object(td,'_reference_description_kind',hook):
                try:
                    if prepared:vm.execute_prepared(vm.prepare(source))
                    else:vm.execute(source)
                except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][2]),1)

    def test_changed_function_defaults_preserve_canonical_behavior(self):
        old=BSLValueList.add.__defaults__
        try:
            BSLValueList.add.__defaults__=(None,'custom',True)
            values,error=self.paired('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
            self.assertIsNone(error);self.assertEqual(values['t'][1][0][0][1:3],('custom',True))
        finally:BSLValueList.add.__defaults__=old

    def test_zero_outer_nested_same_counter_and_missing_fields(self):
        self.paired('T=New ValueList;For I=2 To 1 Do For I=0 To 2 Do T.Add(I);EndDo;EndDo;')
        self.paired('T=New ValueList;For I=0 To 2 Do For I=0 To 2 Do T.Add(I);EndDo;EndDo;')
        self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.Absent=1%I;EndDo;')
        self.paired('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();R=Row.Absent;EndDo;')

    def test_numeric_digit_budget_in_real_fast_loop(self):
        values,error=self.paired('T=New ValueList;X='+('9'*4097)+';For I=0 To 2 Do T.Add(X);EndDo;')
        self.assertIsNotNone(error);self.assertEqual(len(values['t'][1]),0)

    def test_prior_host_local_finalizer_cannot_invalidate_loop_proof(self):
        outputs=[]
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            class Previous:
                def __del__(self):
                    table=vm.variables['t'];add=table.add
                    def changed():vm.close();return add()
                    table.add=changed
            vm.variables['row']=Previous()
            source=('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;')
            error=None
            try:
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
            except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][2]),2)

    def test_host_finalizer_between_loops_cannot_leave_stale_fast_flag(self):
        outputs=[]
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            class Previous:
                def __del__(self):
                    table=vm.variables['t'];add=table.add
                    def changed():vm.close();return add()
                    table.add=changed
            vm.variables['r']=Previous()
            source=('T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;R=0;Row=T.Add();')
            error=None
            try:
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
            except BaseException as e:error=(type(e).__name__,str(e))
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][2]),4)

    def test_old_canonical_item_external_weakref_callback_declines(self):
        import weakref
        outputs=[]
        for prepared in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            old=BSLValueList();item=old.add(Decimal(0));del old
            vm.variables['item']=item
            def callback(reference):
                collection=vm.variables['t'];add=collection.add
                def changed(*args):vm.close();return add(*args)
                collection.add=changed
            watch=weakref.ref(item,callback);del item
            source=('T=New ValueList;For I=0 To 2 Do Item=T.Add(I);EndDo;')
            error=None
            try:
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
            except BaseException as e:error=(type(e).__name__,str(e))
            self.assertIsNone(watch())
            outputs.append((snapshot(vm),error))
        self.assertEqual(*outputs);self.assertEqual(len(outputs[-1][0]['t'][1]),2)

if __name__=='__main__':unittest.main()
