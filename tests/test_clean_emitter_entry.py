import ast
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported


class CleanEmitterEntryTests(unittest.TestCase):
    def test_native_text_of_counted_loop_has_no_state_lookups_or_copy(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='R=0; For I=1 To 32768 Do R=R+I*3; EndDo;'
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        loop=[node for node in ast.walk(tree) if isinstance(node,(ast.While,ast.For))]
        self.assertEqual(len(loop),1)
        self.assertFalse(any(isinstance(node,(ast.Call,ast.Subscript)) for node in ast.walk(loop[0])))
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables,{'i':Decimal(32769),'r':Decimal(1610661888)})
        self.assertIs(type(vm.variables['r']),Decimal)

    def test_real_entry_has_one_generator_and_never_retries_unsupported_syntax(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaisesRegex(PythonDirectUnsupported,'clean emitter'):
            vm.execute('Before=1; Execute("Before=2;");')
        self.assertNotIn('before',vm.variables)

    def test_builtins_do_not_become_bsl_variables(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaises(NameError):
            vm.execute('UndefinedHostName = len;')
        self.assertNotIn('__builtins__',vm.variables)

    def test_array_index_is_the_only_adaptation_in_the_neighboring_loop(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='A=New Array; A.Add(4); Failed=False; Try A[-1]; Except Failed=True; EndTry; R=1+2;'
        vm.execute(source)
        self.assertTrue(vm.variables['failed'])
        self.assertEqual(vm.variables['r'],Decimal(3))


    def test_positional_hole_uses_python_default_and_full_call_stays_positional(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='''Function F(Val A=10, Val B=20, Val C=30)
            Return A+B+C;
        EndFunction
        R=F(1,,3); S=F(1,2,3);
        '''
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        invocation=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
                    and isinstance(node.func,ast.Name) and node.func.id.startswith('_T')]
        self.assertEqual([(len(node.args), [kw.arg for kw in node.keywords])
                          for node in invocation],[(1,['c']),(3,[])])
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['s']),(Decimal(24),Decimal(6)))

    def test_host_positional_hole_does_not_change_procedure_tail(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        for compile_first in (False,True):
            source='W=New JSONWriter; W.SetString(); WriteJSON(W,True,); W.Close()'
            result=vm.execute_prepared(vm.prepare(source)) if compile_first else vm.execute(source)
            self.assertEqual(result,'true')
        vm.execute('W=New JSONWriter; W.SetString();')

    def test_dynamic_constructor_accepts_native_int_dimensions(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Args=New Array; Args.Add(3); R=New("Array",Args); S=New Array(3);')
        self.assertEqual(vm.variables['r'],[None,None,None])
        self.assertEqual(vm.variables['s'],vm.variables['r'])

    def test_raise_options_keep_bsl_diagnostic(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Try Raise ("test",, "E12"); Except E=ErrorInfo(); R=E.Code; EndTry;')
        self.assertEqual(vm.variables['r'],'E12')
