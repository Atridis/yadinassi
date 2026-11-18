"""Complex dynamic actuals have one subtree and an indexing-expression error site."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast as direct
from yadinassi.syntax import ast as bsl
from yadinassi.syntax.parser import parse
from direct_ast_text_oracle import compile_module as oracle

class ComplexIndexTests(unittest.TestCase):
    def compare(self,source,setup):
        results=[]
        for compiler in (oracle,direct.compile_module,direct.compile_module_whole_source):
            vm=Interpreter();events=[];setup(vm,events)
            with patch.object(python_direct,'_compile',compiler):
                try:vm.execute(source,'complex.bsl');error=None
                except BaseException as exc:error=(type(exc).__name__,getattr(exc,'message',str(exc).split(': ',1)[-1]))
            results.append((events,error,vm.variables.get('done')));vm.close()
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0],results[2])
    def test_index_finalizer_success_error_and_close(self):
        from yadinassi.values import BSLArray
        for byref in (False,True):
            for action in ('normal','error','close'):
                def setup(vm,events):
                    vm.variables['a']=BSLArray(Decimal(1))
                    class Index:
                        def __del__(self):events.append(('del',vm.variables.get('caught'),vm.variables.get('done')))
                    def index():
                        events.append('index')
                        if action=='close':vm.close()
                        return Decimal(0) if action=='normal' else Index()
                    vm.register_function('Index',index)
                    vm.register_function('Capture',lambda arg:events.append(('capture',arg.get() if byref else arg)))
                    vm.functions['capture'].reference_parameters=frozenset({0}) if byref else frozenset()
                with self.subTest(byref=byref,action=action):
                    self.compare('Try Capture(A[Index()]);Except Caught=1;EndTry;Done=1;',setup)
    def test_nested_index_emitted_once(self):
        original=direct.Emitter.expr
        for depth in (4,8,16):
            source='Capture(A['+'A['*depth+'Index()'+']'*depth+']);'
            program=parse(source);calls=[]
            def counted(self,node,*args,**kwargs):
                if type(node) is bsl.Call and type(node.callee) is bsl.Name and node.callee.name=='Index':calls.append(id(node))
                return original(self,node,*args,**kwargs)
            vm=Interpreter();vm.register_function('Capture',lambda x:None);vm.register_function('Index',lambda:0);vm.variables['a']=[Decimal(0)]
            with patch.object(direct.Emitter,'expr',counted):vm.prepare_program(program)
            self.assertEqual(len(calls),1);vm.close()
    def test_complex_operation_error_points_to_index_expression(self):
        for byref in (False,True):
            vm=Interpreter();vm.variables['a']=[Decimal(1)]
            vm.register_function('Capture',lambda x:None)
            vm.register_function('Bad',lambda:Decimal(99))
            vm.functions['capture'].reference_parameters=frozenset({0}) if byref else frozenset()
            with self.assertRaises(Exception) as caught:vm.execute('Capture(\n A[Bad()]\n);','index-site.bsl')
            self.assertIn('index-site.bsl:2:',str(caught.exception));vm.close()
    def test_index_child_error_stays_at_child(self):
        for byref in (False,True):
            vm=Interpreter();vm.variables['a']=[Decimal(1)];vm.register_function('Capture',lambda x:None)
            vm.functions['capture'].reference_parameters=frozenset({0}) if byref else frozenset()
            with self.assertRaises(Exception) as caught:vm.execute('Capture(A[1/0]);','child.bsl')
            self.assertIn('child.bsl:1:',str(caught.exception));vm.close()

if __name__=='__main__':unittest.main()
