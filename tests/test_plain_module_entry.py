"""Public direct-module behavior retained from retired lower_module tests."""
from decimal import Decimal
import unittest
from yadinassi import Interpreter, BSLError


class DirectModuleEntryTests(unittest.TestCase):
    def run_module(self,source,expected,*,result=None,inputs=None,error=False):
        for prepared in (False,True):
            with self.subTest(prepared=prepared):
                vm=Interpreter();self.addCleanup(vm.close);vm.variables.update(inputs or {})
                def execute():
                    if prepared:return vm.execute_prepared(vm.prepare(source))
                    return vm.execute(source)
                if error:
                    with self.assertRaises(BSLError):execute()
                else:self.assertEqual(execute(),result)
                for name,value in expected.items():self.assertEqual(vm.variables[name],value)
                self.assertIsNone(vm.locals)

    def test_arithmetic_expression_result(self):
        self.run_module('x=2;y=x*3+1;y;',{'x':2,'y':7},result=Decimal(7))

    def test_partial_write_rhs_error(self):
        self.run_module('x=1;y=8;y=1/0;',{'x':1,'y':8},error=True)

    def test_loop_partial_write_error(self):
        self.run_module('s=0;For i=1 To 4 Do s=s+i;x=1/(3-i);EndDo;',{'s':6,'i':3,'x':1},error=True)

    def test_bounds_once_fractional_counter_and_mutation(self):
        self.run_module('n=4;s=0;For i=0.5 To n Do s=s+i;n=0;EndDo;s;',{'s':8,'n':0},result=Decimal(8))
        self.run_module('s=0;For i=1 To 7 Do s=s+i;i=i+1;EndDo;s;',{'s':16,'i':9},result=Decimal(16))

    def test_nested_continue_break(self):
        self.run_module('s=0;For i=1 To 5 Do If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;For j=1 To 2 Do s=s+i;EndDo;EndDo;s;',{'s':8,'i':4},result=Decimal(8))

    def test_while_and_statement_result(self):
        self.run_module('x=0;While x<4 Do x=x+1;EndDo;',{'x':4})
        self.run_module('x=1;If x=1 Then 99;Else 100;EndIf;',{'x':1})

    def test_short_circuit_and_conditional(self):
        self.run_module('x=False And 1/0>1;y=True Or 1/0>1;x;',{'x':False,'y':True},result=False)
        self.run_module('x=?(True,3,1/0);x;',{'x':3},result=Decimal(3))

    def test_var_keeps_existing_or_initializes(self):
        self.run_module('Var x;x;',{'x':9},inputs={'x':Decimal(9)},result=Decimal(9))
        self.run_module('Var x;x;',{'x':None})

    def test_try_body_handler_and_declaration(self):
        for source,value in [('x=1;Try x=2;Except x=3;EndTry;x;',2),('x=1;Try x=2;y=1/0;Except x=x+4;EndTry;x;',6),('Function F() Return 1;EndFunction x=1;x;',1)]:
            with self.subTest(source=source):self.run_module(source,{'x':value},result=Decimal(value))

    def test_repl_and_prepared_use_live_globals(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('x=1;');vm.execute('x=x+2;');self.assertEqual(vm.variables['x'],3)
        prepared=vm.prepare('x=x+1;x;')
        self.assertEqual(vm.execute_prepared(prepared),4)
        vm.variables['x']=Decimal(20)
        self.assertEqual(vm.execute_prepared(prepared),21)

    def test_host_observes_committed_prefix_once(self):
        observed=[];vm=Interpreter();self.addCleanup(vm.close)
        def host():observed.append(vm.variables['x']);return Decimal(2)
        vm.register_function('Host',host);vm.execute('x=1;y=Host();')
        self.assertEqual(observed,[Decimal(1)]);self.assertEqual(vm.variables['y'],2)


if __name__=='__main__':unittest.main()
