import gc
import unittest
import weakref
from decimal import Decimal
from types import SimpleNamespace
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.python_translation_expressions import prepare_expressions, UnsupportedExpression
from yadinassi import python_translation_expression_fusion as fusion
from yadinassi import translated_access
from tests.test_python_translation_expressions import finish


def compile_fused(node, *, discard=False):
    lines=['def fused(_s):','    vm = _s.vm','    if False: yield None']
    nodes=[];serial=[0]
    def bind(node): nodes.append(node);return f'_nodes[{len(nodes)-1}]'
    def temp(): serial[0]+=1;return '_v'+str(serial[0])
    def emit(depth,line):lines.append('    '*depth+line)
    emitter=fusion.ExpressionEmitter(bind,emit,temp)
    result=emitter.emit_expression(node,1)
    if discard:
        emitter.release(result,1);emit(1,'yield "released"');emit(1,'return None')
    else:emit(1,'return '+result)
    namespace={'_nodes':tuple(nodes),'_PE':fusion}
    source='\n'.join(lines)
    exec(compile(source,'<fused-test>','exec'),namespace)
    return namespace['fused'],source


class FusionTests(unittest.TestCase):
    def run_pair(self,source,setup=lambda vm:None):
        outcomes=[];traces=[]
        node=parse('r='+source+';')[0].value
        for fused in (False,True):
            trace=[]
            class VM(Interpreter):
                def compiled_before(self,node):trace.append(('before',type(node).__name__))
                def compiled_after(self,node,value):trace.append(('after',type(node).__name__));return value
                def compiled_exception(self,node,error):trace.append(('error',type(node).__name__));return super().compiled_exception(node,error)
            vm=VM();setup(vm)
            execution=prepare_expressions([node]).bind(vm,guard=lambda n:trace.append(('guard',type(n).__name__)),access=translated_access)
            vm._visit=lambda *a: (_ for _ in ()).throw(AssertionError('AST execution'))
            try:
                outcomes.append(('value',finish(compile_fused(node)[0](SimpleNamespace(vm=vm,expressions=execution))) if fused else finish(execution.evaluate(node))))
            except Exception as e:outcomes.append(('error',type(e),str(e)))
            traces.append(trace)
        from yadinassi.values import BSLArray
        outcomes=[(kind, tuple(value.items)) if kind=='value' and type(value) is BSLArray else (kind,value) for kind,value in outcomes] if all(len(item)==2 for item in outcomes) else outcomes
        self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(traces[0],traces[1])
        return outcomes[0]

    def test_families_and_hook_order(self):
        for source in ('1+2*3','(1+2)*3','-3','Not False','False And Boom()',
                       'True Or Boom()','?(False,Boom(),7)','True=1','"abc"+2',
                       'StrLen("abc")+StrLen("de")','1/0','New Array(3)'):
            with self.subTest(source=source):self.run_pair(source)

    def test_attributes_indexes_and_reference_calls(self):
        def setup(vm):vm.execute('a=New Array;a.Add(4);s=New Structure("n",3);')
        self.assertEqual(self.run_pair('a[0]+s.n',setup),('value',7))

    def test_pure_expression_never_enters_generator_registry(self):
        node=parse('r=?(1<2,(3+4)*5,9);')[0].value;vm=Interpreter()
        execution=prepare_expressions([node]).bind(vm,guard=lambda n:None,access=translated_access)
        execution.evaluate=lambda n: (_ for _ in ()).throw(AssertionError('registry entry'))
        function,source=compile_fused(node)
        self.assertEqual(finish(function(SimpleNamespace(vm=vm,expressions=execution))),35)
        self.assertNotIn('.evaluate(',source)

    def test_call_order_once(self):
        events=[]
        def setup(vm):vm.register_function('Tick',lambda n:events.append(n) or n)
        self.run_pair('Tick(1)+Tick(2)*Tick(3)',setup)
        self.assertEqual(events,[1,2,3,1,2,3])

    def test_await_preserves_yield_and_resume_guard(self):
        node=parse('Async Function F() Return Await (1+2);EndFunction')[0].body[0].value
        vm=Interpreter();guards=[]
        execution=prepare_expressions([node]).bind(vm,guard=guards.append,access=translated_access)
        task=compile_fused(node)[0](SimpleNamespace(vm=vm,expressions=execution))
        self.assertEqual(next(task).value,3)
        with self.assertRaises(StopIteration) as done:task.send(Decimal(7))
        self.assertEqual(done.exception.value,7);self.assertIs(guards[-1],node)

    def test_released_result_does_not_pin_host_object(self):
        class Resource:pass
        refs=[];vm=Interpreter()
        def create():
            value=Resource();refs.append(weakref.ref(value));return value
        vm.register_function('Resource',create)
        node=parse('r=Resource();')[0].value
        execution=prepare_expressions([node]).bind(vm,guard=lambda n:None,access=translated_access)
        task=compile_fused(node,discard=True)[0](SimpleNamespace(vm=vm,expressions=execution))
        self.assertEqual(next(task),'released');gc.collect()
        self.assertIsNone(refs[0]());task.close()

    def test_emit_budget_and_cycle(self):
        node=parse('r=(1);')[0].value;node.expression=node
        with self.assertRaises(UnsupportedExpression):compile_fused(node)
