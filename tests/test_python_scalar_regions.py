import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine

class ScalarRegionTests(unittest.TestCase):
    def run_pair(self,body):
        source='Function F(Val n) RegionBoundary();s=0;i=0;'+body+' Return s;EndFunction result=F(20);'
        results=[]
        for mode in ('interpreter','compiled-strict'):
            vm=Interpreter(execution_backend=mode)
            vm.register_function('RegionBoundary',lambda:None)
            vm.execute(source);results.append(vm.variables['result'])
        self.assertEqual(*results)
        self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
        return vm
    def test_for_slots(self):
        self.run_pair('For i=1 To n Do s=s+i*3-7;EndDo;')
    def test_nested_outlined_slots_reload(self):
        self.run_pair('For i=1 To n Do If i>1 Then If i>2 Then s=s+i;EndIf;EndIf;EndDo;')
    def test_nested_outlined_continue_reload(self):
        self.run_pair('For i=1 To n Do If i>1 Then If i>2 Then i=i+1;s=s+i;Continue;EndIf;EndIf;EndDo;')
    def test_while_slots(self):
        self.run_pair('While i<n Do i=i+1;s=s+i;EndDo;')
    def test_counter_write_continue_break(self):
        self.run_pair('For i=1 To n Do i=i+1;If i=4 Then Continue;EndIf;If i>12 Then Break;EndIf;s=s+i;EndDo;')
    def test_reference_fallback(self):
        vm=Interpreter(execution_backend='compiled-strict')
        vm.execute('Procedure F(s) For i=1 To 3 Do s=s+i;EndDo;EndProcedure s=0;F(s);')
        self.assertEqual(vm.variables['s'],6)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
    def test_callback_fallback(self):
        vm=Interpreter(execution_backend='compiled-strict');seen=[]
        vm.register_function('Observe',lambda:seen.append(vm.locals['s']))
        vm.execute('Procedure F() s=0;For i=1 To 3 Do s=s+i;Observe();EndDo;EndProcedure F();')
        self.assertEqual(seen,[1,3,6]);self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
    def test_partial_error_flush(self):
        vm=Interpreter(execution_backend='compiled-strict')
        vm.execute('Function F() s=0;i=0;Try For i=1 To 3 Do s=s+1;s=s/(2-i);EndDo;Except Return s;EndTry;EndFunction result=F();')
        self.assertEqual(vm.variables['result'],2)
        self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
    def test_instrumented_hook_fallback(self):
        seen=[]
        original=Interpreter.compiled_before
        def before(vm,node):seen.append(node);return original(vm,node)
        with patch.object(Interpreter,'compiled_before',before):
            vm=Interpreter(execution_backend='compiled-strict')
            vm.execute('Function F() s=0;For i=1 To 3 Do s=s+i;EndDo;Return s;EndFunction result=F();')
        self.assertEqual(vm.variables['result'],6);self.assertTrue(seen)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)

    def test_engine_guard_instrumentation_fallback(self):
        from yadinassi.compiled_backend import Engine
        original=Engine.verify_node
        def verify(engine,node):return original(engine,node)
        with patch.object(Engine,'verify_node',verify):
            vm=Interpreter(execution_backend='compiled-strict')
            vm.execute('Function F() s=0;For i=1 To 3 Do s=s+i;EndDo;Return s;EndFunction result=F();')
        self.assertEqual(vm.variables['result'],6)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
    def test_undefined_counter_bound_does_not_become_none(self):
        source='Function F() s=0;For i=i To 3 Do s=s+1;EndDo;Return s;EndFunction result=F();'
        errors=[]
        for mode in ('interpreter','compiled-strict'):
            vm=Interpreter(execution_backend=mode)
            try:vm.execute(source)
            except Exception as error:errors.append(str(error))
        self.assertEqual(len(errors),2);self.assertEqual(*errors)

    def test_scope_not_pinned_after_region(self):
        import weakref,gc
        class Payload:pass
        vm=Interpreter(execution_backend='compiled-strict');references=[];seen=[]
        def make():
            value=Payload();references.append(weakref.ref(value));vm.locals={'payload':value,'s':Decimal(0)}
        def clear():
            vm.locals={};gc.collect();seen.append(references[-1]() is None)
        vm.register_function('Make',make);vm.register_function('Clear',clear)
        vm.execute('Procedure F() Make();For i=1 To 3 Do s=s+i;EndDo;Clear();EndProcedure F();')
        self.assertEqual(seen,[True])
        self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
    def test_expression_leaf_instrumentation_fallback(self):
        from yadinassi.python_translation_expressions import ExpressionExecution
        original=ExpressionExecution.leaf
        def leaf(execution,node,**kwargs):return original(execution,node,**kwargs)
        with patch.object(ExpressionExecution,'leaf',leaf):
            vm=Interpreter(execution_backend='compiled-strict')
            vm.execute('Function F() s=0;For i=1 To 3 Do s=s+i;EndDo;Return s;EndFunction result=F();')
        self.assertEqual(vm.variables['result'],6)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls',0),0)
