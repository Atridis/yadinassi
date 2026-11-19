"""Closed dynamic numbers are native internally and Decimal at public edges."""
import ast
import sys
from decimal import Decimal as D, localcontext
import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse

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

    def test_integer_intermediates_are_unbounded(self):
        vm,_,_=self.run_source('S=99999999999999999999999999999999999999; S=S+2;')
        self.assertEqual(vm.variables['s'],D('100000000000000000000000000000000000001'))

    def test_fraction_mixed_and_division_stay_decimal(self):
        cases=(('S=0.1; For i=1 To 10 Do S=S+i; EndDo;',D('55.1')),
               ('S=1; S=S/8;',D('.125')),
               ('S=1.25; S=S*2;',D('2.50')))
        for text,expected in cases:
            vm,_,_=self.run_source(text)
            self.assertEqual(vm.variables['s'],expected);self.assertIs(type(vm.variables['s']),D)

    def test_division_zero_partial_state(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaisesRegex(Exception,'Деление на ноль'):
            vm.execute('S=5; X=1/0; After=1;')
        self.assertEqual(vm.variables,{'s':D(5)})

    def test_host_boundary_observes_decimal(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
        vm.register_function('Observe',lambda x:seen.append(type(x)))
        vm.execute('S=0; For i=1 To 10 Do S=S+i; EndDo; Observe(S);')
        self.assertEqual(seen,[D])

    def test_scale_and_signed_zero_stay_decimal(self):
        for tail,expected in (('S=1.0; S;',D('1.0')), ('S=-0; S;',D('-0'))):
            source='S=0; For i=1 To 2 Do S=S+i; EndDo; '+tail
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

    def test_native_integer_context_divergence_is_explicit(self):
        from decimal import ROUND_FLOOR
        with localcontext() as ctx:
            ctx.rounding=ROUND_FLOOR;ctx.Emax=1
            _,plan,result=self.run_source('S=0; For i=1 To 10 Do S=S+i*i; EndDo; S;')
            self.assertEqual(result,D(385))
            self.assertNotIn('_integer_context_ok',plan._plan.generated_source)
        _,_,result=self.run_source('S=-1*0; S;')
        self.assertEqual(result.as_tuple(),D(0).as_tuple())

    def test_remainder_has_dividend_sign_and_decimal_errors(self):
        for source,expected in (('S=-7%3; S;',D(-1)),('S=7%-3; S;',D(1)),('S=-6%3; S;',D('-0')),('S=-7.5%3; S;',D('-1.5'))):
            _,_,result=self.run_source(source)
            self.assertEqual(result.as_tuple(),expected.as_tuple())
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(Exception):vm.execute('S=3; X=5%0; After=1;')
        self.assertEqual(vm.variables,{'s':D(3)})

    def test_boolean_and_fractional_counter(self):
        _,_,result=self.run_source('S=True; S;')
        self.assertIs(result,True)
        vm,_,result=self.run_source('S=0; For i=0.5 To 2.5 Do S=S+i; EndDo; S;')
        self.assertEqual(result,D('4.5'));self.assertEqual(vm.variables['i'],D('3.5'))

    def test_no_two_body_cost_for_one_off_or_nonarithmetic_loop(self):
        for source in ('S=1;', 'S=10*20+3; S;', 'For i=1 To 100 Do S=i; EndDo;'):
            vm,plan,_=self.run_source(source)
            self.assertNotIn('_integer_context_ok',plan._plan.generated_source)

    def test_table_raw_numbers_publish_through_public_access(self):
        from yadinassi.collections.plain_table_storage import RowStorage
        source='T=New ValueTable; T.Columns.Add("N"); For i=0 To 3 Do R=T.Add(); R.N=i*2; EndDo; S=0; For i=0 To 3 Do If T[i].N>=0 Then S=S+T[i]["N"]; EndIf; EndDo; S;'
        for mode in ('default','prepared'):
            vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
            plan=vm.prepare(source)
            self.assertIn('_raw_table_value',plan._plan.generated_source)
            result=vm.execute_prepared(plan) if mode=='prepared' else vm.execute_program(parse(source))
            self.assertEqual(result,D(12));self.assertIs(type(result),D)
            table=vm.variables['t']
            self.assertIs(type(RowStorage.get_value(table.get(1),'N')),int)
            self.assertIs(type(table.get(1).get_member('N')),D)
            seen=[];vm.register_function('Observe',lambda value:seen.append(type(value)))
            vm.execute('Observe(T[1].N); Kind=TypeOf(T[1].N);')
            self.assertEqual(seen,[D])
            from yadinassi.types.values import BSLType
            self.assertIs(vm.variables['kind'],BSLType.NUMBER)

    def test_array_remains_decimal_and_single_body(self):
        vm,plan,_=self.run_source('A=New Array; For i=1 To 2 Do A.Add(i); EndDo;')
        self.assertTrue(all(type(value) is D for value in vm.variables['a']))
        _,plan,_=self.run_source('S=0; For i=1 To 2 Do S=S+i; EndDo; S;')
        self.assertEqual(sum(isinstance(node,ast.For) for node in ast.walk(ast.parse(plan._plan.generated_source))),1)

    def test_numeric_map_keeps_integer_storage_and_public_number_contract(self):
        vm,plan,result = self.run_source(
            'M=New Map; For I=0 To 300 Do M.Insert(I,I); EndDo; '
            'S=0; For I=0 To 300 Do S=S+M.Get(I); EndDo; S;')
        self.assertEqual(result,D(45150))
        self.assertIs(type(result),D)
        self.assertTrue(all(type(key) is int and type(value) is int
                            for key,value in dict.items(vm.variables['m'])))
        loops = [node for node in ast.walk(ast.parse(plan._plan.generated_source))
                 if isinstance(node,ast.For)]
        self.assertEqual(len(loops),2)
        self.assertTrue(all('_Decimal' not in ast.unparse(loop) for loop in loops))
        from yadinassi.types.values import BSLType
        self.assertIs(vm.execute('TypeOf(M.Get(300))'),BSLType.NUMBER)
        self.assertIs(type(vm.execute('M[300]')),D)
        self.assertIs(type(vm.execute('For Each Entry In M Do K=Entry.Key; Break; EndDo; K;')),D)

    def test_numeric_map_fractional_keys_and_values_remain_decimal(self):
        vm,_,result = self.run_source('M=New Map; M.Insert(1.25,2.50); M.Get(1.25);')
        key,value = next(iter(dict.items(vm.variables['m'])))
        self.assertEqual(key.as_tuple(),D('1.25').as_tuple())
        self.assertEqual(value.as_tuple(),D('2.50').as_tuple())
        self.assertEqual(result.as_tuple(),D('2.50').as_tuple())
