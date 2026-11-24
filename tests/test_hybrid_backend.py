"""Live behavior retained from the retired hybrid differential suite.

There is no interpreter/hybrid oracle or fallback. Arithmetic uses independent
expected values; effects and errors are asserted directly. Old compiler tier,
eligibility, depth-budget and instrumentation-fallback tests were implementation
only. The removed benchmark had no workflow/script/test consumers.
"""
import random
import subprocess
import sys
import unittest
from contextlib import closing
from decimal import Decimal, getcontext, localcontext

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse


class DirectBehaviorTests(unittest.TestCase):
    def vm(self, **kwargs):
        return Interpreter(execution_backend='python-direct', **kwargs)

    def test_generated_integer_arithmetic_has_independent_oracle(self):
        rng = random.Random(813)
        for _ in range(60):
            a,b,c = [rng.randrange(-100,100) for _ in range(3)]
            op = rng.choice(['+','-','*'])
            expected = a
            for i in range(-2,6):
                expected = {'+':lambda:expected+b, '-':lambda:expected-b,
                            '*':lambda:expected*b}[op]() + i*c
            vm = self.vm()
            vm.execute(f'r={a};For i=-2 To 5 Do r=(r {op} {b})+i*{c};EndDo;')
            self.assertEqual(vm.variables['r'], expected)

    def test_loop_results_and_effects(self):
        cases = [
            ('r=0;For i=1 To 100 Do r=r+i*3-7;EndDo;',14450,[]),
            ('r=0;For i=1 To 0 Do r=7;EndDo;',0,[]),
            ('For i=0.5 To 3.7 Do r=i;EndDo;',Decimal('3.5'),[]),
            ('For i=-3 To -1 Do r=-i;EndDo;',1,[]),
            ('r=0;For i=1 To 3 Do r=r+1;Message(r);EndDo;',3,['1','2','3']),
            ('r=0;For i=1 To 3 Do r=r+1;Break;EndDo;',1,[]),
            ('r=0;For i=1 To 3 Do Continue;r=r+1;EndDo;',0,[]),
            ('Function F() Message(7);Return 2;EndFunction For i=F() To F()+1 Do r=i;EndDo;',3,['7','7']),
        ]
        for source,expected,messages in cases:
            with self.subTest(source=source):
                output=[];vm=self.vm(output=output.append);vm.execute(source)
                self.assertEqual(vm.variables['r'],expected)
                self.assertEqual(output,messages)

    def test_reference_counter_behavior(self):
        vm=self.vm()
        vm.execute('Procedure F(x) For x=1 To 3 Do x=x+1;EndDo;EndProcedure r=0;F(r);')
        self.assertEqual(vm.variables['r'],5)

    def test_error_never_replays_and_preserves_location(self):
        vm=self.vm(allow_extensions=True);events=[]
        vm.register_function('Touch',lambda:events.append(1))
        with self.assertRaises(BSLRuntimeError) as caught:
            vm.execute('r=0;For i=1 To 2 Do Touch();r=r+1;\nz=1/0;EndDo;','once.bsl')
        self.assertEqual(events,[1]);self.assertEqual(vm.variables['r'],1)
        self.assertNotIn('z',vm.variables)
        self.assertIn('once.bsl:2:',str(caught.exception))

    def test_overflow_preserves_prior_write(self):
        vm=self.vm();vm.variables['big']=Decimal('1e999999')
        with self.assertRaises(BSLRuntimeError):
            vm.execute('r=0;For i=1 To 2 Do r=r+1;z=big*big;EndDo;')
        self.assertEqual(vm.variables['r'],1);self.assertNotIn('z',vm.variables)

    def test_nonfinite_counter_rejected(self):
        vm=self.vm();vm.variables['big']=Decimal('NaN')
        with self.assertRaises(BSLRuntimeError):vm.execute('For i=1 To big Do r=i;EndDo;')
        self.assertNotIn('r',vm.variables)

    def test_decimal_context_is_not_host_precision(self):
        # This checks isolation from Python's ambient precision, not native
        # 1C's rules for results wider than 38 digits. The old integer witness
        # has the same numeric value even if its stored coefficient is rounded
        # over a trailing zero. The fraction exercises actual Decimal math.
        cases = (
            ('12345678901234567890*12345678901234567890',
             Decimal('152415787532388367501905199875019052100')),
            ('12345678.1234*2.5', Decimal('30864195.3085')),
        )
        for expression, expected in cases:
            source=f'For i=1 To 1 Do r={expression};EndDo;'
            for prepared in (False, True):
                with self.subTest(expression=expression, prepared=prepared):
                    with localcontext() as context, closing(self.vm()) as vm:
                        context.prec=7
                        if prepared:
                            vm.execute_prepared(vm.prepare_program(parse(source)))
                        else:
                            vm.execute(source)
                        self.assertEqual(vm.variables['r'],expected)
                        self.assertIs(getcontext(),context)
                        self.assertEqual(context.prec,7)

    def test_new_ast_execution_observes_explicit_edit(self):
        nodes=parse('For i=1 To 2 Do r=1;EndDo;');vm=self.vm()
        vm.execute_program(nodes);nodes[0].body[0].value.value=Decimal(4)
        vm.execute_program(nodes);self.assertEqual(vm.variables['r'],4)

    def test_later_execution_observes_changed_state_type(self):
        vm=self.vm();vm.execute('r=0;For i=1 To 1 Do r=r+1;EndDo;')
        vm.variables['r']='s';vm.execute('For i=1 To 1 Do r=r+1;EndDo;')
        self.assertEqual(vm.variables['r'],'s1')

    def test_profile_and_trace_preserve_direct_results(self):
        for setter,getter in ((sys.settrace,sys.gettrace),(sys.setprofile,sys.getprofile)):
            previous=getter()
            try:
                setter(lambda *args:None)
                vm=self.vm();vm.execute('For i=1 To 2 Do r=i;EndDo;')
                self.assertEqual(vm.variables['r'],2)
                self.assertEqual(vm.execution_backend,'python-direct')
            finally:setter(previous)


class DirectCLITests(unittest.TestCase):
    def run_cli(self,*args):
        return subprocess.run([sys.executable,'-m','yadinassi',*args],capture_output=True,
                              encoding='utf-8',timeout=15)

    def test_explicit_direct_mode(self):
        result=self.run_cli('--execution-backend','python-direct','-c',
            'r=0;For i=1 To 10 Do r=r+i*3-7;EndDo;Message(r);')
        self.assertEqual((result.returncode,result.stdout.strip(),result.stderr),(0,'95',''))

    def test_retired_modes_are_rejected_before_body(self):
        for mode in ('interpreter','hybrid','compiled-strict'):
            with self.subTest(mode=mode):
                result=self.run_cli('--execution-backend',mode,'-c','Message("BAD");')
                self.assertEqual(result.returncode,2)
                self.assertNotIn('BAD',result.stdout)
