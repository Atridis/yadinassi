"""Live behavior migrated from retired compiled-engine tests.

No legacy oracle or fallback. Unsupported live behavior must fail normally.
Engine flags, registry layouts, tier counters and old node-visitor ABI are retired.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.errors import BSLRuntimeError

class StrictCodegenTests(unittest.TestCase):
    def run_strict(self, source, source_name='<direct-migrated-test>', vm=None):
        output=[]
        if vm is None: vm=Interpreter(execution_backend='python-direct',output=output.append)
        vm.execute(source,source_name)
        self.assertEqual(vm.execution_backend,'python-direct')
        return vm,output

    def test_scalar_control_and_mutable_counter(self):
        vm, _ = self.run_strict('''
            r=0; For i=1 To 10 Do
                i=i+1;
                If i=4 Then Continue; EndIf;
                If i=8 Then Break; EndIf;
                r=r+i*3-7;
            EndDo;
            While r<10 Do r=r+1; EndDo;
        ''')
        self.assertEqual(vm.variables['r'], Decimal(10))
        self.assertEqual(vm.variables['i'], Decimal(8))

    def test_lazy_logic_and_conditional(self):
        vm, _ = self.run_strict('a=False And Missing();b=True Or Missing();r=?(a,Missing(),7);')
        self.assertFalse(vm.variables['a']);self.assertTrue(vm.variables['b'])
        self.assertEqual(vm.variables['r'], Decimal(7))

    def test_sync_calls_aliases_defaults_return_and_cleanup(self):
        vm, _ = self.run_strict('''
            Function F(x, y, Val z=3)
                x=x+1;y=y+2; Return x+y+z;
            EndFunction
            n=1;r=F(n,n);
        ''')
        self.assertEqual(vm.variables['n'], Decimal(4))
        self.assertEqual(vm.variables['r'], Decimal(11))
        self.assertIsNone(vm.locals)

    def test_foreach_constructors_members_and_indexes(self):
        vm, _ = self.run_strict('''
            a=New Array;a.Add(2);a.Add(3);a[0]=4;
            r=0;For Each x In a Do r=r+x;EndDo;
            t=Type("Array");b=New (t);b.Add(r);
        ''')
        self.assertEqual(vm.variables['r'], Decimal(7))
        self.assertEqual(list(vm.variables['b']), [Decimal(7)])

    def test_try_raise_and_goto_lexical_unwind(self):
        vm, output = self.run_strict('''
            n=0;
            ~Again:
            n=n+1;
            Try
                If n<3 Then Goto ~Again; EndIf;
                Raise "x";
            Except
                Message(ErrorDescription());
            EndTry;
            r=n;
        ''')
        self.assertEqual(vm.variables['r'], Decimal(3))
        self.assertTrue(any('x' in value for value in output))
        self.assertEqual(vm._handled_errors, [])

    def test_async_suspension_and_fifo(self):
        vm, output = self.run_strict('''
            Async Function F(Val n)
                Message(n);r=Await n;Message(r+10);Return r;
            EndFunction
            p=F(1);q=F(2);
        ''')
        self.assertEqual(output, ['1','2','11','12'])
        self.assertEqual(vm.variables['p'].result, Decimal(1))
        self.assertEqual(vm.variables['q'].result, Decimal(2))
        self.assertIsNone(vm.locals)

    def test_dynamic_execute_and_eval(self):
        vm, _ = self.run_strict('r=0;Execute "For i=1 To 3 Do r=r+i;EndDo;";v=Eval("r*2");')
        self.assertEqual(vm.variables['r'], Decimal(6))
        self.assertEqual(vm.variables['v'], Decimal(12))

    def test_import_enters_strict_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'helper.bsl').write_text('Function F() Export Return 7;EndFunction', encoding='utf-8')
            vm, _ = self.run_strict('// #Import helper.bsl\nr=helper.F();',str(root/'main.bsl'))
            self.assertEqual(vm.variables['r'],Decimal(7))
            child=vm.imports['helper'].interpreter
            self.assertEqual(child.execution_backend,'python-direct')
