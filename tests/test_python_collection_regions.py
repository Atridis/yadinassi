"""Fresh direct-collection graphs preserve public translated BSL contracts."""
import gc
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.errors import BSLRuntimeError
from yadinassi.syntax import ast
from yadinassi.owned_syntax import syntax_kind
from yadinassi.python_translation_scalar_regions import ClosedLease

class PythonCollectionRegionTests(unittest.TestCase):
    def run_pair(self, source, observe):
        outcomes=[]
        for instrumented in (True,False):
            vm=Interpreter(execution_backend='compiled-strict')
            if instrumented:vm.compiled_before=lambda node:None
            vm.execute(source,'collections-regions.bsl');outcomes.append(observe(vm))
            self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
            if not instrumented:
                self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls',0)+vm.compiled_backend_stats.get('python_sync_routine_calls',0),0)
        self.assertEqual(outcomes[0],outcomes[1]);return outcomes[1]

    def test_scalar_only_region_does_not_pay_collection_admission(self):
        from yadinassi import python_translation_collections as collections
        vm=Interpreter(execution_backend='compiled-strict')
        with patch.object(collections,'trusted',side_effect=AssertionError('collection audit on scalar plan')):
            vm.execute('s=0;For i=1 To 10 Do s=s+i;EndDo;result=s;')
        self.assertEqual(vm.variables['result'],55)
        self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)

    def test_array_aliases_are_canonical_and_mutations_shared(self):
        actual=self.run_pair('a=New Array;b=a;For i=1 To 4 Do a.Add(i);EndDo;b[1]=9;result=a[1]+a.Count();',lambda vm:(vm.variables['a'] is vm.variables['b'],list(vm.variables['a'].items),vm.variables['result']))
        self.assertEqual(actual,(True,[1,9,3,4],13))

    def test_map_boolean_and_number_keys_do_not_collapse(self):
        actual=self.run_pair('m=New Map;m.Insert(True,11);m.Insert(1,22);m.Insert(False,33);m.Insert(0,44);result=m.Get(True)*1000+m.Get(1)*100+m.Get(False)*10+m.Get(0);',lambda vm:(vm.variables['result'],len(vm.variables['m']._items)))
        self.assertEqual(actual,(13574,4))

    def test_structure_casefold_spelling_and_method_property_names(self):
        actual=self.run_pair('s=New Structure("Name,Count",1,7);s.NAME=2;s.Insert("nAmE",3);result=s.name+s.Count+s.Count();',lambda vm:(vm.variables['result'],tuple(vm.variables['s']._items.values())))
        self.assertEqual(actual,(12,(('nAmE',3),('Count',7))))

    def test_array_foreach_observes_append_like_builtin_iterator(self):
        actual=self.run_pair('a=New Array;a.Add(1);a.Add(2);s=0;For Each x In a Do s=s+x;If x=1 Then a.Add(3);EndIf;EndDo;result=s;',lambda vm:(vm.variables['result'],list(vm.variables['a'].items)))
        self.assertEqual(actual,(6,[1,2,3]))

    def test_map_and_structure_composition_mutation_errors_match(self):
        for constructor in ('New Map','New Structure'):
            outcomes=[]
            for instrumented in (True,False):
                vm=Interpreter(execution_backend='compiled-strict')
                if instrumented:vm.compiled_before=lambda node:None
                source=f'm={constructor};m.Insert("a",1);m.Insert("b",2);s=0;For Each pair In m Do s=s+pair.Value;m.Insert("c",3);EndDo;'
                with self.assertRaises(BSLRuntimeError) as caught:vm.execute(source,'mutation.bsl')
                outcomes.append((str(caught.exception),vm.variables['s'],len(vm.variables['m']._items)))
                self.assertEqual(vm._compiled()._active_frames,0)
            self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[1][1:],(1,3))

    def test_index_failures_publish_same_partial_fresh_graph(self):
        for index in ('-1','2','0.5','True'):
            outcomes=[]
            for instrumented in (True,False):
                vm=Interpreter(execution_backend='compiled-strict')
                if instrumented:vm.compiled_before=lambda node:None
                with self.assertRaises(BSLRuntimeError) as caught:
                    vm.execute(f'a=New Array;a.Add(1);a.Add(2);a[1]=3;a[{index}]=4;','bounds.bsl')
                outcomes.append((str(caught.exception),list(vm.variables['a'].items)))
                self.assertEqual(vm._compiled()._active_frames,0)
            self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[1][1],[1,3])

    def test_error_is_catchable_by_outer_bsl_try(self):
        actual=self.run_pair('caught=False;Try a=New Array;a.Add(1);a.Add(2);a[8]=3;Except caught=True;EndTry;result=caught;',lambda vm:(vm.variables['result'],list(vm.variables['a'].items)))
        self.assertEqual(actual,(True,[1,2]))

    def test_import_collision_and_receiver_write_still_reject(self):
        for name in ('reserved','ThisObject'):
            outcomes=[]
            for instrumented in (True,False):
                vm=Interpreter(execution_backend='compiled-strict');vm.imports['reserved']=object()
                if instrumented:vm.compiled_before=lambda node:None
                with self.assertRaises(BSLRuntimeError) as caught:
                    vm.execute(f'{name}=New Array;{name}.Add(1);{name}.Add(2);result=1;','names.bsl')
                outcomes.append(str(caught.exception));self.assertNotIn(name.casefold(),vm.variables)
            self.assertEqual(*outcomes)

    def test_hostile_external_value_uses_generic_route_without_protocol_probe(self):
        calls=[]
        class Meta(type):
            def __eq__(cls,other):calls.append('class-eq');raise AssertionError('class equality')
            def __hash__(cls):calls.append('class-hash');raise AssertionError('class hash')
        class Host(metaclass=Meta):
            def __eq__(self,other):calls.append('eq');raise AssertionError('equality')
            def __hash__(self):calls.append('hash');raise AssertionError('hash')
            def __bool__(self):calls.append('bool');raise AssertionError('truth')
            def __iter__(self):calls.append('iter');raise AssertionError('iteration')
        vm=Interpreter(execution_backend='compiled-strict');host=Host();vm.variables['x']=host
        vm.execute('a=New Array;a.Add(x);a.Add(x);result=a[0];')
        self.assertIs(vm.variables['result'],host);self.assertEqual(calls,[])
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)

    def test_source_budget_rejection_precedes_collection_effects(self):
        vm=Interpreter(execution_backend='compiled-strict');vm._compiled().MAX_INLINE_FUNCTION_BYTES=64
        with self.assertRaises(CompiledUnsupported):vm.execute('a=New Array;a.Add(1);a.Add(2);a.Add(3);')
        self.assertNotIn('a',vm.variables)

    def test_postentry_revocation_does_not_publish_fresh_graph(self):
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled();original=ClosedLease.backedge;revoked=[];enabled=gc.isenabled()
        def revoke_after_entry(lease):
            original(lease)
            if not revoked:
                node=next(n for n in lease.plan.nodes if syntax_kind(n) is ast.New)
                del engine._nodes[id(node)];revoked.append(True)
        with patch.object(ClosedLease,'backedge',revoke_after_entry):
            with self.assertRaises(CompiledUnsupported):vm.execute('a=New Array;For i=1 To 3 Do a.Add(i);EndDo;result=a;')
        self.assertEqual(revoked,[True]);self.assertNotIn('a',vm.variables);self.assertNotIn('result',vm.variables)
        self.assertEqual(engine._active_frames,0);self.assertEqual(gc.isenabled(),enabled)

    def test_fresh_acyclic_nested_graph_and_identity_keys_stay_fast(self):
        actual=self.run_pair('a=New Array;child=New Array;a.Add(child);m=New Map;m.Insert(a,7);b=New Array;m.Insert(b,9);result=m.Get(a);',lambda vm:(vm.variables['a'].items[0] is vm.variables['child'],vm.variables['result'],len(vm.variables['m']._items)))
        self.assertEqual(actual,(True,7,2))

    def test_array_method_value_extraction_stays_general_without_replay(self):
        outcomes=[]
        for instrumented in (True,False):
            vm=Interpreter(execution_backend='compiled-strict')
            if instrumented:vm.compiled_before=lambda node:None
            vm.execute('a=New Array;method=a.Count;a.Add(1);a.Add(2);result=method();')
            outcomes.append((vm.variables['result'],list(vm.variables['a'].items)))
        self.assertEqual(outcomes,[(2,[1,2]),(2,[1,2])])

    def test_branch_receiver_member_extraction_preserves_method_or_property(self):
        from yadinassi.values import HostFunction
        for branch in ('True','False'):
            outcomes=[]
            for instrumented in (True,False):
                vm=Interpreter(execution_backend='compiled-strict')
                if instrumented:vm.compiled_before=lambda node:None
                vm.execute(f'r=New Structure("Count",7);If {branch} Then r=New Array;EndIf;result=r.Count;')
                value=vm.variables['result']
                outcomes.append(('method',value()) if type(value) is HostFunction else ('property',value))
            self.assertEqual(outcomes[0],outcomes[1])
            self.assertEqual(outcomes[1],('method',0) if branch=='True' else ('property',7))

    def test_invalid_receiver_method_and_argument_error_order(self):
        for source in (
            'a=New Array;x=1;y=x.foo;result=0;',
            'a=New Array;a.foo=1;result=0;s=0;',
            'a=New Array;a.foo=1/0;result=0;s=0;',
            'a=New Map;a.Add(1/0);result=0;s=0;',
            'a=New Array;a.Add(1,1/0);result=0;s=0;',
            'a=New Array;s=0;For Each x In 1 Do s=s+1;EndDo;',
        ):
            outcomes=[]
            for instrumented in (True,False):
                vm=Interpreter(execution_backend='compiled-strict')
                if instrumented:vm.compiled_before=lambda node:None
                with self.assertRaises(BSLRuntimeError) as caught:vm.execute(source,'invalid-collection.bsl')
                outcomes.append((str(caught.exception),'a' in vm.variables))
            with self.subTest(source=source):self.assertEqual(outcomes[0],outcomes[1])

    def test_registered_constructor_override_is_respected_once(self):
        from yadinassi.values import BSLArray
        outcomes=[]
        for instrumented in (True,False):
            vm=Interpreter(execution_backend='compiled-strict');calls=[]
            def replacement():
                calls.append(1);value=BSLArray();value.add(9);return value
            vm.register_type('Array',replacement)
            if instrumented:vm.compiled_before=lambda node:None
            vm.execute('a=New Array;a.Add(1);a.Add(2);result=a.Count();')
            outcomes.append((calls,vm.variables['result'],list(vm.variables['a'].items)))
            self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
        self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[1],([1],3,[9,1,2]))

    def test_class_override_before_first_compilation_is_not_trusted_as_original(self):
        import subprocess
        import sys
        from pathlib import Path
        script='''import sys
sys.path.insert(0,sys.argv[1])
from yadinassi import Interpreter
from yadinassi.values import BSLArray
calls=[]
original=BSLArray.add
def custom(self,value=None):
    calls.append(value)
    return original(self,value+10)
BSLArray.add=custom
vm=Interpreter(execution_backend='compiled-strict')
vm.execute('a=New Array;a.Add(1);a.Add(2);result=a[0]+a[1];')
assert vm.variables['result']==23,vm.variables['result']
assert calls==[1,2],calls
assert vm.compiled_backend_stats.get('python_sync_segment_calls',0)==0
'''
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-I','-c',script,str(root)],cwd=root,
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_key_helper_override_before_first_compilation_declines_closed_code(self):
        import subprocess
        import sys
        from pathlib import Path
        script='''import sys
sys.path.insert(0,sys.argv[1])
from yadinassi import Interpreter
from yadinassi import maps
calls=[]
original=maps._key
def custom(value):
    calls.append(value)
    return original(value)
maps._key=custom
vm=Interpreter(execution_backend='compiled-strict')
vm.execute('m=New Map;m.Insert("a",1);m.Insert("b",2);result=m.Get("a")+m.Get("b");')
assert vm.variables['result']==3
assert calls==['a','b','a','b'],calls
assert vm.compiled_backend_stats.get('python_sync_segment_calls',0)==0
'''
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-I','-c',script,str(root)],cwd=root,
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_constructor_registry_override_before_first_compilation(self):
        import subprocess
        import sys
        from pathlib import Path
        script='''import sys
sys.path.insert(0,sys.argv[1])
from yadinassi import Interpreter
from yadinassi.values import BSLArray
calls=[]
def replacement():
    calls.append(1)
    result=BSLArray();result.add(9);return result
vm=Interpreter(execution_backend='compiled-strict')
vm.register_type('Array',replacement)
vm.execute('a=New Array;a.Add(1);a.Add(2);result=a.Count();')
assert vm.variables['result']==3
assert calls==[1],calls
assert vm.compiled_backend_stats.get('python_sync_segment_calls',0)==0
'''
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-I','-c',script,str(root)],cwd=root,
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_loop_member_receiver_changes_type_on_later_iteration(self):
        from yadinassi.values import HostFunction
        outcomes=[]
        for instrumented in (True,False):
            vm=Interpreter(execution_backend='compiled-strict')
            if instrumented:vm.compiled_before=lambda node:None
            vm.execute('r=New Structure("Count",7);a=New Array;For i=1 To 2 Do a.Add(r.Count);r=New Array;EndDo;result=a;')
            items=vm.variables['result'].items
            self.assertIs(type(items[1]),HostFunction)
            outcomes.append((items[0],items[1]()))
        self.assertEqual(outcomes,[(7,0),(7,0)])

    def test_postentry_helper_replacement_cannot_leak_unpublished_graph(self):
        from yadinassi import maps
        vm=Interpreter(execution_backend='compiled-strict');leaked=[];installed=[]
        original_key=maps._key;original_edge=ClosedLease.backedge
        def replacement(value):
            leaked.append(value)
            return original_key(value)
        def replace_after_entry(lease):
            original_edge(lease)
            if not installed:
                installed.append(True);maps._key=replacement
        try:
            with patch.object(ClosedLease,'backedge',replace_after_entry):
                with self.assertRaises(CompiledUnsupported):
                    vm.execute('a=New Array;m=New Map;For i=1 To 3 Do m.Insert(a,i);EndDo;result=1;')
        finally:maps._key=original_key
        self.assertEqual(installed,[True]);self.assertEqual(leaked,[])
        self.assertNotIn('a',vm.variables);self.assertNotIn('m',vm.variables)
        self.assertEqual(vm._compiled()._active_frames,0)

    def test_postentry_constructor_replacement_cannot_receive_fresh_objects(self):
        from yadinassi.values import BSLArray
        vm=Interpreter(execution_backend='compiled-strict');leaked=[];installed=[]
        original_init=BSLArray.__init__;original_edge=ClosedLease.backedge
        def replacement(value,*args):
            leaked.append(value)
            original_init(value,*args)
        def replace_after_entry(lease):
            original_edge(lease)
            if not installed:
                installed.append(True);BSLArray.__init__=replacement
        try:
            with patch.object(ClosedLease,'backedge',replace_after_entry):
                with self.assertRaises(CompiledUnsupported):
                    vm.execute('s=0;For i=1 To 3 Do a=New Array;a.Add(i);s=s+a[0];EndDo;result=s;')
        finally:BSLArray.__init__=original_init
        self.assertEqual(installed,[True]);self.assertEqual(leaked,[])
        self.assertNotIn('a',vm.variables);self.assertNotIn('result',vm.variables)
        self.assertEqual(vm._compiled()._active_frames,0)

    def test_potential_cycles_decline_before_execution_preserving_graphs(self):
        cases = (
            ('For i=1 To 50 Do a=New Array;a.Add(a);EndDo;',
             lambda v: v['a'].items[0] is v['a']),
            ('a=New Array;b=New Array;a.Add(b);b.Add(a);',
             lambda v: v['a'].items[0] is v['b'] and v['b'].items[0] is v['a']),
            ('a=New Array;b=a;b.Add(a);result=1;',
             lambda v: v['b'] is v['a'] and v['a'].items[0] is v['a']),
            ('a=New Array;b=a;a=New Array;a.Add(b);b.Add(a);',
             lambda v: v['a'].items[0] is v['b'] and v['b'].items[0] is v['a']),
            ('a=New Array;b=New Array;a.Add(b);c=a[0];c.Add(a);',
             lambda v: v['c'] is v['b'] and v['b'].items[0] is v['a']),
            ('a=New Array;b=New Array;a.Add(b);c=a.Get(0);c.Add(a);',
             lambda v: v['c'] is v['b'] and v['b'].items[0] is v['a']),
            ('a=New Array;b=New Array;a.Add(b);For Each c In a Do c.Add(a);EndDo;',
             lambda v: v['b'].items[0] is v['a']),
            ('a=New Structure("child",New Array);b=a.child;b.Add(a);result=1;',
             lambda v: v['b'].items[0] is v['a']),
            ('a=New Array;b=New Array;d=New Array;a.Add(b);c=a[0];c.Add(d);d.Add(b);',
             lambda v: v['b'].items[0] is v['d'] and v['d'].items[0] is v['b']),
            ('m=New Map;m[m]=1;x=0;result=1;',
             lambda v: next(iter(v['m']._items.values()))[0] is v['m']),
            ('a=New Array(1,1);b=a[0];b.Add(a);result=1;',
             lambda v: v['b'].items[1] is v['a']),
            ('m=New Map;a=New Array;m.Insert("a",a);b=m.Get("a");b.Add(m);',
             lambda v: v['b'] is v['a'] and v['a'].items[0] is v['m']),
        )
        for source, observe in cases:
            with self.subTest(source=source):
                for instrumented in (True,False):
                    vm=Interpreter(execution_backend='compiled-strict')
                    if instrumented:vm.compiled_before=lambda node:None
                    vm.execute(source)
                    self.assertTrue(observe(vm.variables))
                    self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
                    self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
                    self.assertEqual(vm._compiled()._active_frames,0)

    def test_acyclic_nested_get_and_foreach_payloads_stay_fast(self):
        actual=self.run_pair('a=New Array;b=New Array;b.Add(7);a.Add(b);c=a.Get(0);result=c[0];For Each child In a Do result=result+child[0];EndDo;',lambda vm:(vm.variables['result'],vm.variables['c'] is vm.variables['b']))
        self.assertEqual(actual,(14,True))
