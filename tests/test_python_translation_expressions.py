import unittest
from unittest.mock import patch
from yadinassi.compiled_backend import Engine
from decimal import Decimal
from types import SimpleNamespace
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.python_translation_expressions import prepare_expressions, UnsupportedExpression


def finish(gen):
    try:
        value=next(gen)
    except StopIteration as done:
        return done.value
    raise AssertionError(('unexpected suspension',value))


class Expressions(unittest.TestCase):
    def expression(self, source, vm=None):
        vm=vm or Interpreter()
        node=parse('result='+source+';')[0].value
        plan=prepare_expressions([node])
        visited=[]
        execution=plan.bind(vm,guard=visited.append,access=SimpleNamespace())
        vm._visit=lambda *a: (_ for _ in ()).throw(AssertionError('AST execution'))
        return finish(execution.evaluate(node)), visited

    def test_arithmetic_and_boolean_decimal(self):
        for source, expected in [('2+3*4',14),('Истина=1',True),('1/4',Decimal('.25')),('7%3',1),('-(2+3)',-5),('"x"+2','x2')]:
            with self.subTest(source=source): self.assertEqual(self.expression(source)[0],expected)

    def test_short_circuit_and_conditional(self):
        for source, expected in [('Ложь И Boom()',False),('Истина Или Boom()',True),('?(Истина,7,Boom())',7)]:
            self.assertEqual(self.expression(source)[0],expected)

    def test_nested_builtin_calls(self):
        self.assertEqual(self.expression('СтрДлина(СокрЛП(" abc "))')[0],3)

    def test_host_order_and_once(self):
        vm=Interpreter(); events=[]
        vm.register_function('Tick',lambda x:events.append(x) or x)
        vm.register_function('Pair',lambda a,b:10*a+b)
        self.assertEqual(self.expression('Pair(Tick(1),Tick(2))',vm)[0],12)
        self.assertEqual(events,[1,2])

    def test_new_and_method(self):
        vm=Interpreter(); vm.variables['a']=self.expression('Новый Массив(3)',vm)[0]
        self.assertEqual(self.expression('a.Количество()',vm)[0],3)

    @patch.object(Engine, "DETAILED_INLINE_STATS", True)
    def test_routine_plain_actuals_no_visit(self):
        vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
        vm.execute('Function Add(Val a,Val b) Return a+b;EndFunction')
        before=vm.compiled_backend_stats.get('python_translated_node_kinds',{}).get('Return',0)
        self.assertEqual(self.expression('Add(СтрДлина("abc"),2)',vm)[0],5)
        stats=vm.compiled_backend_stats
        self.assertEqual(stats.get('python_translated_node_kinds',{}).get('Return',0)-before,1)
        self.assertEqual(stats.get('plain_adapter_blocks',0),0)
        self.assertEqual(stats.get('interpreter_fallbacks',0),0)

    def test_missing_prepared_node_and_budgets(self):
        node=parse('r=1;')[0].value
        with self.assertRaises(UnsupportedExpression): prepare_expressions([node],max_source_bytes=1)
        with self.assertRaises(UnsupportedExpression): prepare_expressions([node],max_nodes=0)
        execution=prepare_expressions([]).bind(Interpreter(),guard=lambda n:None,access=None)
        with self.assertRaises(UnsupportedExpression): finish(execution.evaluate(node))

    def test_live_guard_exception_prevents_effect(self):
        vm=Interpreter(); events=[]; vm.register_function('Tick',lambda:events.append(1))
        node=parse('r=Tick();')[0].value
        def deny(node): raise PermissionError('revoked')
        execution=prepare_expressions([node]).bind(vm,guard=deny,access=None)
        with self.assertRaises(PermissionError): finish(execution.evaluate(node))
        self.assertEqual(events,[])

    def test_eval_rejects_bad_arity_before_argument_effect(self):
        from yadinassi import BSLError
        vm=Interpreter();events=[]
        vm.register_function('Tick',lambda:events.append(1))
        with self.assertRaises(BSLError):self.expression('Eval(Tick(),Tick())',vm)
        self.assertEqual(events,[])

    def test_unsupported_only_when_reached(self):
        from yadinassi.syntax import ast
        node=parse('r=?(Истина,1,2);')[0].value
        node.when_false=ast.OmittedArgument(node.token)
        execution=prepare_expressions([node]).bind(Interpreter(),guard=lambda n:None,access=None)
        self.assertEqual(finish(execution.evaluate(node)),1)
        with self.assertRaises(UnsupportedExpression): finish(execution.evaluate(node.when_false))

    def test_call_preserves_suspension_and_revalidation(self):
        from yadinassi.values import InterpreterCall
        events=[]
        def authorize(vm): events.append('authorize')
        def dispatch(vm, values):
            events.append('before')
            response=yield 'suspended'
            events.append(response)
            return values[0]+response
        vm=Interpreter();vm.register_function('Suspend',InterpreterCall(1,1,authorize,dispatch))
        node=parse('r=Suspend(2);')[0].value
        execution=prepare_expressions([node]).bind(vm,guard=lambda n:None,access=None)
        vm._visit=lambda *a: (_ for _ in ()).throw(AssertionError('AST execution'))
        task=execution.evaluate(node)
        self.assertEqual(next(task),'suspended')
        with self.assertRaises(StopIteration) as done: task.send(Decimal(3))
        self.assertEqual(done.exception.value,5)
        self.assertEqual(events,['authorize','authorize','before',Decimal(3)])

    def test_host_reference_variable_and_index(self):
        from yadinassi.values import HostFunction, BSLArray
        vm=Interpreter();vm.variables['x']=Decimal(1);vm.variables['a']=BSLArray(Decimal(1))
        def set_value(reference): reference.set(Decimal(9)); return reference.get()
        vm.functions['setvalue']=HostFunction('SetValue',set_value,reference_parameters=frozenset({0}))
        self.assertEqual(self.expression('SetValue(x)',vm)[0],9)
        self.assertEqual(vm.variables['x'],9)
        self.assertEqual(self.expression('SetValue(a[0])',vm)[0],9)
        self.assertEqual(vm.variables['a'].get(Decimal(0)),9)

    def test_reference_constructor_effects_once(self):
        from yadinassi.values import HostFunction, BSLArray
        vm=Interpreter();events=[];array=BSLArray(Decimal(1))
        vm.register_function('Receiver',lambda:events.append('receiver') or array)
        vm.register_function('Index',lambda:events.append('index') or Decimal(0))
        vm.functions['setvalue']=HostFunction('SetValue',lambda ref:ref.set(Decimal(3)),reference_parameters=frozenset({0}))
        self.expression('SetValue(Receiver()[Index()])',vm)
        self.assertEqual(events,['receiver','index']); self.assertEqual(array.get(Decimal(0)),3)

    def test_source_form_invocation_keeps_scalar_snapshot_hook(self):
        from yadinassi.source_forms import _SourceFormInterpreter
        vm=Interpreter();vm._form_session=SimpleNamespace(form=SimpleNamespace(_static={'field':None}))
        node=parse('r=Field;')[0].value; events=[]
        class Evaluation:
            def evaluate(self,node):
                events.append('scalar_snapshot')
                if False: yield
                return Decimal(42)
            def argument(self,node): raise AssertionError('must not bind form attribute as dictionary reference')
        value=finish(_SourceFormInterpreter._invocation_argument(vm,node,_evaluation=Evaluation()))
        self.assertEqual(value,42);self.assertEqual(events,['scalar_snapshot'])
