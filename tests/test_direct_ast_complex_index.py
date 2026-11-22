"""Complex dynamic actuals have one subtree and an indexing-expression error site."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen import experimental_direct_ast as direct
from yadinassi.syntax import ast as bsl
from yadinassi.syntax.parser import parse

class ComplexIndexTests(unittest.TestCase):
    def test_dynamic_byref_scalar_rejects_before_index_in_both_index_shapes(self):
        for operand in ('index', 'NextIndex()'):
            with self.subTest(operand=operand):
                vm=Interpreter(allow_extensions=True); events=[]
                self.addCleanup(vm.close)
                vm.register_function('Receiver',lambda:events.append('receiver') or Decimal(7))
                vm.register_function('NextIndex',lambda:events.append('index') or Decimal(0))
                vm.register_function('Capture',lambda arg:events.append('callee'),returns_value=False)
                vm.functions['capture'].reference_parameters=frozenset({0})
                vm.execute(f'index=0; Try Capture(Receiver()[{operand}]); Except Caught=True; EndTry;')
                self.assertIs(vm.variables['caught'],True)
                self.assertEqual(events,['receiver'])

    def test_index_finalizer_success_error_and_close(self):
        from yadinassi.types.values import BSLArray
        for byref in (False,True):
            for action in ('normal','native','error','close'):
                with self.subTest(byref=byref,action=action):
                    vm=Interpreter(allow_extensions=True);events=[]
                    self.addCleanup(vm.close)
                    vm.variables['a']=[None] if action=='native' else BSLArray(Decimal(1))

                    class Index:
                        def __del__(self):
                            events.append(('del',vm.variables.get('caught'),vm.variables.get('done')))

                    def index():
                        events.append('index')
                        if action=='close':vm.close()
                        return Decimal(0) if action in ('normal','native') else Index()

                    vm.register_function('Index',index)
                    vm.register_function('Capture',lambda arg:events.append(('capture',arg.get() if byref else arg)))
                    vm.functions['capture'].reference_parameters=frozenset({0}) if byref else frozenset()
                    source='Try Capture(A[Index()]);Except Caught=1;EndTry;Done=1;'
                    if action=='close' or (byref and action in ('normal','error')):
                        message='closed during execution' if action=='close' else 'unregistered host member'
                        with self.assertRaisesRegex(BoundaryViolation,message):
                            vm.execute(source,'complex.bsl')
                        self.assertNotIn('caught',vm.variables)
                        self.assertNotIn('done',vm.variables)
                        self.assertEqual(events,['index'] if action=='normal' else ['index',('del',None,None)])
                    else:
                        vm.execute(source,'complex.bsl')
                        self.assertEqual(vm.variables['done'],Decimal(1))
                        if action in ('normal','native'):
                            self.assertNotIn('caught',vm.variables)
                            self.assertEqual(events,['index',('capture',None)])
                        else:
                            self.assertEqual(vm.variables['caught'],Decimal(1))
                            self.assertEqual(events,['index',('del',Decimal(1),Decimal(1))])
    def test_nested_index_emitted_once(self):
        original=direct.Emitter.expr
        for depth in (4,8,16):
            source='Capture(A['+'A['*depth+'Index()'+']'*depth+']);'
            program=parse(source);calls=[]
            def counted(self,node,*args,**kwargs):
                if type(node) is bsl.Call and type(node.callee) is bsl.Name and node.callee.name=='Index':calls.append(id(node))
                return original(self,node,*args,**kwargs)
            vm=Interpreter(allow_extensions=True);vm.register_function('Capture',lambda x:None);vm.register_function('Index',lambda:0);vm.variables['a']=[Decimal(0)]
            with patch.object(direct.Emitter,'expr',counted):vm.prepare_program(program)
            self.assertEqual(len(calls),1);vm.close()
    def test_complex_operation_error_points_to_index_expression(self):
        for byref in (False,True):
            vm=Interpreter(allow_extensions=True);vm.variables['a']=[Decimal(1)]
            vm.register_function('Capture',lambda x:None)
            vm.register_function('Bad',lambda:Decimal(99))
            vm.functions['capture'].reference_parameters=frozenset({0}) if byref else frozenset()
            with self.assertRaises(Exception) as caught:vm.execute('Capture(\n A[Bad()]\n);','index-site.bsl')
            self.assertIn('index-site.bsl:2:',str(caught.exception));vm.close()
    def test_index_child_error_stays_at_child(self):
        for byref in (False,True):
            vm=Interpreter(allow_extensions=True);vm.variables['a']=[Decimal(1)];vm.register_function('Capture',lambda x:None)
            vm.functions['capture'].reference_parameters=frozenset({0}) if byref else frozenset()
            with self.assertRaises(Exception) as caught:vm.execute('Capture(A[1/0]);','child.bsl')
            self.assertIn('child.bsl:1:',str(caught.exception));vm.close()

if __name__=='__main__':unittest.main()
