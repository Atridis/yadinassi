"""Closed integer arithmetic is native internally and Decimal at public edges."""
import ast
import sys
from decimal import Decimal as D, localcontext
import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct_integer_lane import analyze

class IntegerLaneTests(unittest.TestCase):
    def run_source(self, text):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare(text)
        result=vm.execute_prepared(plan)
        return vm,plan,result

    def test_closed_sum_native_loop_and_decimal_publication(self):
        vm,plan,result=self.run_source('S=0; For i=1 To 100 Do S=S+i*i; EndDo; S;')
        self.assertEqual(result,D(338350));self.assertIs(type(result),D)
        self.assertEqual(vm.variables,{'s':D(338350),'i':D(101)})
        self.assertTrue(all(type(v) is D for v in vm.variables.values()))
        tree=ast.parse(plan._plan.generated_source)
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For))
        self.assertNotIn('_Decimal',ast.unparse(loop))
        self.assertNotIn('_constants',ast.unparse(loop))

    def test_unary_and_subtraction_and_repeat(self):
        vm,plan,result=self.run_source('S=100; For i=1 To 3 Do S=S-i*2; EndDo; R=-S+5; R;')
        self.assertEqual(result,D(-83))
        self.assertEqual(vm.execute_prepared(plan),D(-83))

    def test_bound_overflow_declines(self):
        for text in ('S=99999999999999999999999999999999999999; S=S+1;',
                     'S=1; For i=1 To 100 Do S=S*2; EndDo;',
                     'S=0; For i=1 To 99999999999999999999999999999999999999 Do S=S+i; EndDo;'):
            self.assertFalse(analyze(parse(text)))
        vm,_,_=self.run_source('S=99999999999999999999999999999999999999; S=S+2;')
        with localcontext() as ctx:
            ctx.prec=38;expected=D('99999999999999999999999999999999999999')+2
        self.assertEqual(vm.variables['s'],expected)

    def test_fraction_mixed_and_division_stay_decimal(self):
        cases=(('S=0.1; For i=1 To 10 Do S=S+i; EndDo;',D('55.1')),
               ('S=1; S=S/8;',D('.125')),
               ('S=1.25; S=S*2;',D('2.50')))
        for text,expected in cases:
            self.assertFalse(analyze(parse(text)))
            vm,_,_=self.run_source(text)
            self.assertEqual(vm.variables['s'],expected);self.assertIs(type(vm.variables['s']),D)

    def test_division_zero_partial_state(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaisesRegex(Exception,'Деление на ноль'):
            vm.execute('S=5; X=1/0; After=1;')
        self.assertEqual(vm.variables,{'s':D(5)})

    def test_dynamic_and_control_cases_decline(self):
        for text in ('S=Input+1;', 'S=0; Host(S);', 'S=New Array;',
                     'S=0; For i=2 To 1 Do S=S+i; EndDo;',
                     'S=0; For i=1 To 2 Do i=3; EndDo;',
                     'S=0; T=0; For i=1 To 3 Do S=S+T; T=T+1; EndDo;',
                     'S=0; While S<2 Do S=S+1; EndDo;',
                     'S=True; S=S+1;', 'S=1.00;', 'S=-1*0;'):
            self.assertFalse(analyze(parse(text)),text)

    def test_host_boundary_observes_decimal(self):
        vm=Interpreter();self.addCleanup(vm.close);seen=[]
        vm.register_function('Observe',lambda x:seen.append(type(x)))
        vm.execute('S=0; For i=1 To 10 Do S=S+i; EndDo; Observe(S);')
        self.assertEqual(seen,[D])

    def test_scale_and_signed_zero_stay_decimal(self):
        for tail,expected in (('S=1.0; S;',D('1.0')), ('S=-0; S;',D('-0')), ('S=-1*0; S;',D('-0'))):
            source='S=0; For i=1 To 2 Do S=S+i; EndDo; '+tail
            self.assertFalse(analyze(parse(source)))
            vm,_,result=self.run_source(source)
            self.assertEqual(result.as_tuple(),expected.as_tuple())
            self.assertEqual(vm.variables['s'].as_tuple(),expected.as_tuple())

    def test_interrupted_loop_publishes_decimal_partial_state(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.variables['preserved']=D(42)
        plan=vm.prepare('S=0; For i=1 To 10 Do S=S+i; EndDo;')
        code=plan._plan.function.__code__
        def trace(frame,event,arg):
            if frame.f_code is code and event=='line':
                if any(type(value) is int and value==3 for value in frame.f_locals.values()):
                    raise RuntimeError('interrupt integer loop')
            return trace
        previous=sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaisesRegex(Exception,'interrupt integer loop'):
                vm.execute_prepared(plan)
        finally:sys.settrace(previous)
        self.assertEqual(vm.variables['preserved'],D(42))
        self.assertTrue(all(type(value) is D for value in vm.variables.values()))

    def test_cancellation_keeps_decimal_rounding_and_negative_zero(self):
        from decimal import ROUND_FLOOR
        for tail in ('S=1-1; S;', 'S=-1+1; S;'):
            source='S=0; For i=1 To 2 Do S=S+i; EndDo; '+tail
            self.assertFalse(analyze(parse(source)))
            with localcontext() as ctx:
                ctx.rounding=ROUND_FLOOR
                vm,_,result=self.run_source(source)
            self.assertEqual(result.as_tuple(),D('-0').as_tuple())

    def test_prepared_context_change_retains_decimal_errors_and_results(self):
        from unittest.mock import patch
        from decimal import Overflow, Subnormal
        source='S=100; For i=1 To 10 Do S=S+i*i; EndDo; S;'
        vm=Interpreter();self.addCleanup(vm.close)
        fast=vm.prepare(source)
        with patch('yadinassi.execution.direct.python_direct_integer_lane.analyze',return_value=False):
            other=Interpreter();self.addCleanup(other.close)
            ordinary=other.prepare(source)
        for settings in ({'Emax':1}, {'Emin':0}, {'clamp':1}):
            results=[]
            for owner,plan in ((vm,fast),(other,ordinary)):
                with localcontext() as ctx:
                    for name,value in settings.items():setattr(ctx,name,value)
                    ctx.traps[Overflow]=True;ctx.traps[Subnormal]=True
                    try:result=owner.execute_prepared(plan);results.append(('value',result.as_tuple()))
                    except Exception as error:results.append(('error',type(error),str(error)))
            self.assertEqual(results[0],results[1],settings)
        self.assertEqual(vm.execute_prepared(fast),D(485))

    def test_no_two_body_cost_for_one_off_or_nonarithmetic_loop(self):
        for source in ('S=1;', 'S=10*20+3; S;', 'For i=1 To 100 Do S=i; EndDo;'):
            self.assertFalse(analyze(parse(source)))
            vm,plan,_=self.run_source(source)
            self.assertNotIn('_integer_context_ok',plan._plan.generated_source)
