"""Pure numeric lowering, without evaluator or host arithmetic dispatch."""
import unittest
from contextlib import ExitStack
from decimal import Decimal, localcontext
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_scalar_semantics import decimal_divide, decimal_sign

class DirectDecimalDivisionTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter(execution_backend='python-direct');self.addCleanup(vm.close);return vm

    def test_source_ast_prepared_eval_execute_routine(self):
        expected=Decimal('0.000000003725290298461914063')
        source='Result=1/268435456;'
        for route in ('source','ast','prepared','eval','execute','routine'):
            vm=self.vm()
            with self.subTest(route=route):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                elif route=='eval':vm.execute('Result=Eval("1/268435456");')
                elif route=='execute':vm.execute('Var Result;Execute("'+source+'");')
                else:vm.execute('Function F(A,B) Return A/B; EndFunction Result=F(1,268435456);')
                self.assertEqual(vm.variables['result'],expected)

    def test_no_vm_dispatch_and_operand_effect_order(self):
        vm=self.vm();events=[]
        vm.register_function('LeftValue',lambda: events.append('left') or Decimal(1))
        vm.register_function('RightValue',lambda: events.append('right') or Decimal(3))
        with ExitStack() as stack:
            for method in ('block','call_routine'):
                stack.enter_context(patch.object(Interpreter,method,side_effect=AssertionError('fallback')))
            stack.enter_context(patch('yadinassi.runtime.binary_values',side_effect=AssertionError('fallback')))
            self.assertEqual(vm.execute('LeftValue()/RightValue()'),Decimal('0.'+'3'*27))
        self.assertEqual(events,['left','right'])

    def test_no_host_or_decimal_subclass_hooks(self):
        events=[]
        class Hostile:
            def __truediv__(self,other):events.append('divide');raise AssertionError
            def __rtruediv__(self,other):events.append('rdivide');raise AssertionError
            def __neg__(self):events.append('neg');raise AssertionError
            def __pos__(self):events.append('pos');raise AssertionError
        class HostDecimal(Decimal):
            def is_finite(self):events.append('finite');raise AssertionError
        for bad in (Hostile(),HostDecimal(1),True,1,'1',None):
            for pair in ((bad,Decimal(1)),(Decimal(1),bad)):
                with self.assertRaises(TypeError):decimal_divide(*pair)
            for sign in ('+','-'):
                with self.assertRaises(TypeError):decimal_sign(bad,sign)
        self.assertEqual(events,[])

    def test_context_independent_sign_and_division(self):
        vm=self.vm();value=Decimal('1.'+'123456789'*40);vm.variables['a']=value
        with localcontext() as ctx:
            ctx.prec=1;ctx.Emin=-2;ctx.Emax=2
            for signal in ctx.traps:ctx.traps[signal]=True
            ctx.clear_flags();before=ctx.copy()
            self.assertEqual(vm.execute('-a/1'),value.copy_negate())
            self.assertIs(vm.execute('+a'),value)
            self.assertEqual(ctx.flags,before.flags)

    def test_resource_error_catchable_and_assignment_atomic(self):
        vm=self.vm();vm.variables['a']=Decimal('1e5000')
        vm.execute('Saved=17;Try Saved=A/1;Except Caught=True;EndTry;')
        self.assertIs(vm.variables['caught'],True);self.assertEqual(vm.variables['saved'],Decimal(17))
        for invalid in ('NaN','Infinity','-Infinity'):
            vm.variables['a']=Decimal(invalid)
            with self.assertRaisesRegex(BSLRuntimeError,'конечные'):vm.execute('A/1')

    def test_live_native_division_suffix_all_71_records(self):
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        fixture=json.loads((root/'tests/fixtures/division_half_ties_linux.json').read_text())
        output=[];vm=Interpreter(output.append,execution_backend='python-direct');self.addCleanup(vm.close)
        vm.execute((root/'integrational_tests/tests/numbers.bsl').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(output),421)
        self.assertEqual(output[350:],fixture['records'])
