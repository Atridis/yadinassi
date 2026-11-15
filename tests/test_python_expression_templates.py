import unittest
from yadinassi.python_translation_expressions import prepare_expressions, UnsupportedExpression
from yadinassi.syntax.parser import parse
from yadinassi.runtime import Interpreter

class TemplateTests(unittest.TestCase):
    def test_literal_name_templates_share_code_not_values(self):
        nodes=[parse('x='+str(i)+';')[0].value for i in range(100)]
        plan=prepare_expressions(nodes)
        self.assertLess(len(plan.source.encode()),200)
        self.assertEqual(len({id(f.__code__) for _,f in plan.functions.values()}),1)
        self.assertEqual([f.__defaults__[0].value for _,f in plan.functions.values()],list(range(100)))
    def test_shared_templates_still_charge_source_and_registry(self):
        node=parse('x=1;')[0].value
        with self.assertRaises(UnsupportedExpression):prepare_expressions([node],max_source_bytes=1)
        with self.assertRaises(UnsupportedExpression):prepare_expressions([node],max_function_bytes=1)
        with self.assertRaises(UnsupportedExpression):prepare_expressions([node],max_nodes=0)
    def test_retained_routine_defaults_and_groups(self):
        vm=Interpreter()
        vm.execute('Function F(Val x=7) Return (x+1);EndFunction')
        for i in range(3):vm.execute('unrelated=99;')
        vm.execute('a=F();b=F(4);')
        self.assertEqual((vm.variables['a'],vm.variables['b']),(8,5))
        self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
    def test_sync_leaf_boundaries_match_generator_registry(self):
        from unittest.mock import patch
        from yadinassi import translated_access
        from yadinassi.runtime import Interpreter
        for source in ('x=12;', 'x=missing;'):
            node=parse(source)[0].value
            plan=prepare_expressions([node])
            observations=[]
            for sync in (False,True):
                vm=Interpreter(execution_backend='interpreter');events=[]
                before,after,convert=vm.compiled_before,vm.compiled_after,vm.compiled_exception
                def b(n):events.append('before');return before(n)
                def a(n,v):events.append('after');return after(n,v)
                def e(n,error):events.append('error');return convert(n,error)
                execution=plan.bind(vm,guard=lambda n:events.append('guard'),access=translated_access)
                with patch.object(vm,'compiled_before',b),patch.object(vm,'compiled_after',a),patch.object(vm,'compiled_exception',e):
                    try:
                        if sync: value=execution.leaf(node)
                        else:
                            iterator=execution.evaluate(node)
                            try:next(iterator)
                            except StopIteration as stopped:value=stopped.value
                        outcome=('value',value)
                    except Exception as error:outcome=(type(error).__name__,str(error))
                observations.append((events,outcome))
            self.assertEqual(observations[0],observations[1])
    def test_compact_local_names_never_rewrite_literal_contents(self):
        vm=Interpreter();vm.execute('result="vm result _s _nodes";vm=result;')
        self.assertEqual(vm.variables['vm'],'vm result _s _nodes')

    def test_sync_leaf_after_failure_does_not_pin_value_in_traceback(self):
        import gc, weakref
        from types import SimpleNamespace
        from yadinassi import translated_access
        class Payload:pass
        node=parse('x=a;')[0].value
        box=[Payload()];reference=weakref.ref(box[0])
        def after(node,value):
            del value
            raise ValueError('after')
        vm=SimpleNamespace(compiled_before=lambda node:None,
            semantic_name=lambda node:box.pop(),compiled_after=after,
            compiled_exception=lambda node,error:error)
        execution=prepare_expressions([node]).bind(vm,guard=lambda node:None,access=translated_access)
        held=None
        try:execution.leaf(node)
        except ValueError as error:held=error
        self.assertIsNotNone(held)
        gc.collect();self.assertIsNone(reference())
