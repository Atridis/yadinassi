"""Product regressions migrated from the removed plain/translated engine matrix.

Expected values are independent constants, not another execution engine's output.
Both public direct execution entry points are exercised. Unsupported product
behavior remains an ordinary failing test, never an oracle equality or skip.
"""
from decimal import Decimal, localcontext, Inexact, Rounded
import unittest
from yadinassi import Interpreter, BSLError


class WholeRoutineBehaviorTests(unittest.TestCase):
    def execute(self, source, expected, *, effects=(), inputs=None, host=False):
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                observed=[]
                vm=Interpreter(output=lambda value:observed.append(('output',str(value))), allow_extensions=True)
                self.addCleanup(vm.close)
                vm.variables.update(inputs or {})
                if host:
                    def tick(value):
                        observed.append(('host',str(value)))
                        return value+Decimal(1)
                    vm.register_function('Tick',tick)
                self.assertEqual(vm.execution_backend,'python-direct')
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                for name,value in expected.items():
                    self.assertIn(name,vm.variables)
                    self.assertEqual(vm.variables[name],value)
                self.assertEqual(observed,list(effects))
                self.assertIsNone(vm.locals)
                self.assertEqual(vm.pending_promises,())

    def test_val_decimal_fractional_loop(self):
        self.execute('Function Sum(Val n) s=0;For i=0.5 To n Do s=s+i;EndDo;Return s;EndFunction r=Sum(3);',{'r':Decimal('4.5')})

    def test_byref_alias_and_val_copy(self):
        self.execute('Procedure Mutate(a,b,Val c) a=a+1;b=b+2;c=c+100;EndProcedure x=3;y=7;Mutate(x,x,y);r=x+y;',{'r':13,'x':6,'y':7})

    def test_defaults_omissions_and_nested_calls(self):
        self.execute('Function Add(Val a,Val b=4) Return a+b;EndFunction Function Outer(Val x) Return Add(Add(x),);EndFunction r=Outer(2);',{'r':10})

    def test_live_collection_alias_and_reference_writeback(self):
        self.execute('Procedure Change(x) x=x+3;EndProcedure Function Work(Val a) a.Add(4);Change(a[0]);Return a[0];EndFunction items=New Array();alias=items;r=Work(items);n=alias.Count();v=alias[0];',{'r':7,'n':1,'v':7})

    def test_loop_control_same_list_goto_short_circuit(self):
        self.execute('Function Work(Val n) s=0;For i=1 To n Do If i=2 Then Continue;EndIf;If i=5 Then Break;EndIf;s=s+i;EndDo;If False And Tick(99)>0 Then s=999;EndIf;Goto ~Done;s=888;~Done:Return s;EndFunction r=Work(10);',{'r':8},host=True)

    def test_dynamic_execute_eval_module_state(self):
        self.execute('Var total; Function Work(Val x) Execute "total=total+1;";Return Eval("x+total");EndFunction total=3;r=Work(4);after=total;',{'r':8,'after':4})

    def test_server_context_byref_copyback(self):
        self.execute('&AtServer\nFunction Work(x,Val y) x=x+y;Return x*2;EndFunction n=3;r=Work(n,4);',{'r':14,'n':7})

    def test_async_await_result_and_cleanup(self):
        # An explicit product gap must fail here, not disappear with old Engine.
        for prepared in (False,True):
            with self.subTest(prepared=prepared):
                vm=Interpreter();self.addCleanup(vm.close)
                source='Async Function Work(Val n) x=Await n;Return x+1;EndFunction p=Work(4);'
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual(vm.variables['p'].result,5)
                self.assertIsNone(vm.locals);self.assertEqual(vm.pending_promises,())

    def test_host_effect_once_before_result(self):
        self.execute('Function Work(Val x) y=Tick(x);Message(y);Return y+1;EndFunction r=Work(4);',{'r':6},host=True,effects=[('host','4'),('output','5')])

    def test_decimal_error_does_not_publish_result(self):
        for expression,input_value in [('x+1',Decimal('sNaN')),('x/0',Decimal(2))]:
            for prepared in (False,True):
                with self.subTest(expression=expression,prepared=prepared),localcontext() as context:
                    context.prec=7;context.clear_flags()
                    vm=Interpreter();self.addCleanup(vm.close);vm.variables['n']=input_value
                    source='Function F(Val x)\nReturn '+expression+';\nEndFunction\nr=F(n);'
                    with self.assertRaises(BSLError) as caught:
                        if prepared:vm.execute_prepared(vm.prepare(source))
                        else:vm.execute(source)
                    self.assertEqual(caught.exception.line,2)
                    self.assertNotIn('r',vm.variables);self.assertIsNone(vm.locals)

    def test_decimal_division_scale_and_host_context_isolation(self):
        # BSL division has its own 27-digit scale; ambient host precision and
        # sticky flags must not leak into or out of script execution.
        with localcontext() as context:
            context.prec=7;context.clear_flags()
            self.execute('Function F(Val n) Return n/7;EndFunction r=F(1);',{'r':Decimal('0.142857142857142857142857143')})
            self.assertFalse(context.flags[Inexact]);self.assertFalse(context.flags[Rounded])

    def test_wide_control_matrix(self):
        cases=[
            ('Function F(Val x) While x<4 Do x=x+1;EndDo;Return x;EndFunction r=F(1);',{'r':4},()),
            ('Function F(Val x) Try x=1/0;Except x=7;EndTry;Return x;EndFunction r=F(1);',{'r':7},()),
            ('Function F(Val x) If x>1 Then Return x*2;Else Return x+1;EndIf;EndFunction r=F(3);',{'r':6},()),
            ('Function F(Val a) s=0;For Each x In a Do s=s+x;EndDo;Return s;EndFunction a=New Array();a.Add(2);a.Add(3);r=F(a);',{'r':5},()),
            ('Procedure F(x) x=x+1;Return; x=99;EndProcedure n=4;F(n);r=n;',{'r':5,'n':5},()),
            ('Function F(Val x) Return Tick(x)+Tick(x+1);EndFunction r=F(2);',{'r':7},[('host','2'),('host','3')]),
            ('Function F(Val x) Return x;EndFunction r=F(Tick(2));',{'r':3},[('host','2')]),
        ]
        for source,expected,effects in cases:
            with self.subTest(source=source):self.execute(source,expected,host=True,effects=effects)

    def test_repeated_calls_live_module_state(self):
        self.execute('Var total;Function F(Val x) total=total+1;Return x+total;EndFunction total=0;a=F(3);b=F(5);r=a+b;',{'a':4,'b':7,'r':11,'total':2})

    def test_scalar_expressions(self):
        cases=[('x+"!"','"abc"','abc!'),('NOT x','False',True),('x=Undefined','Undefined',True),('?(x,10,20)','True',10),('x/2','9',Decimal('4.5')),('x%2','9',1),('(x+1)*2','5',12),('-x+ +x','5',0),('x<>4','5',True),('x<6','5',True),('x<=5','5',True),('x>4','5',True),('x>=5','5',True),('True=x','5',False),('False AND -True','5',False),('True OR -False','5',True),('(x=5) AND (x>0)','5',True)]
        for expression,arg,expected in cases:
            with self.subTest(expression=expression):self.execute('Function F(Val x) Var a;a='+expression+';Return a;EndFunction r=F('+arg+');',{'r':expected})

    def test_nested_tail_calls(self):
        self.execute('Function G(Val x) Return x+1;EndFunction Function F(Val x) x=x+2;Return G(x);EndFunction r=F(3);',{'r':6})

    def test_default_literal_actual_effect_once(self):
        self.execute('Function F(Val x=4) Return x+1;EndFunction r=F(Tick(2));d=F();',{'r':4,'d':5},host=True,effects=[('host','2')])

    def test_procedure_empty_implicit_early_return(self):
        for body in ('','x=x+1;','If x>0 Then Return;EndIf;x=x+1;'):
            with self.subTest(body=body):self.execute('Procedure P(Val x=1) '+body+' EndProcedure P();r=7;',{'r':7})

    def test_wrong_arity_before_actual_effects(self):
        output=[];vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        vm.register_function('Tick',lambda:output.append(1))
        with self.assertRaises(BSLError):vm.execute('Function G(Val x) Return x;EndFunction Function F(Val x) Return G(Tick(),Tick());EndFunction r=F(1);')
        self.assertEqual(output,[]);self.assertNotIn('r',vm.variables)

    def test_multiple_host_boundaries(self):
        self.execute('Function F(Val x) y=Tick(x);y=y+2;z=Tick(y);Return z*2;EndFunction r=F(1);',{'r':10},host=True,effects=[('host','1'),('host','4')])

    def test_prefix_before_host_not_replayed(self):
        self.execute('Function F(Val n) s=0;For i=1 To n Do s=s+i;EndDo;s=Tick(s);Return s+1;EndFunction r=F(5);',{'r':17},host=True,effects=[('host','15')])

    def test_explicit_routine_redefinition(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('Function Sum(Val n) Return n+1;EndFunction r=Sum(10);')
        self.assertEqual(vm.variables['r'],11)
        vm.execute('Function Sum(Val n) Return n+2;EndFunction r=Sum(10);')
        self.assertEqual(vm.variables['r'],12)

    def test_prepared_program_owns_snapshot(self):
        from yadinassi.syntax.parser import parse
        vm=Interpreter();self.addCleanup(vm.close)
        program=parse('Function Sum(Val n) Return n+1;EndFunction r=Sum(10);')
        prepared=vm.prepare_program(program)
        program[0].body[0].value.right.value=Decimal(999)
        vm.execute_prepared(prepared)
        self.assertEqual(vm.variables['r'],11)

    def test_unassigned_local_is_an_explicit_error(self):
        for body in ('While n<0 Do s=1;EndDo;Return s;', 'If n<0 Then s=1;EndIf;Return s;'):
            with self.subTest(body=body):
                vm=Interpreter();self.addCleanup(vm.close)
                # Direct locals currently expose Python's missing-local error;
                # do not turn this into a successful None or catch all errors.
                with self.assertRaises((BSLError,UnboundLocalError)):
                    vm.execute('Function F(Val n) '+body+' EndFunction r=F(5);')
                self.assertNotIn('r',vm.variables)

    def test_deep_arithmetic(self):
        expression='n'
        for _ in range(24):expression='('+expression+'+1)'
        self.execute('Function F(Val n) Return '+expression+';EndFunction r=F(10);',{'r':34})

    def test_declared_local_retains_prior_value(self):
        self.execute('Function F() x=3;Var x;Return x;EndFunction r=F();',{'r':3})

    def test_conditional_local_counter_shadows_module_variable(self):
        self.execute('Var i;Procedure F() For i=1 To 2 Do Var i;i=10;EndDo;EndProcedure F();',{'i':1})

    def test_conditional_backward_goto_does_not_replay_prefix(self):
        self.execute('Function F(Val n) n=n+2;~Again:n=n-1;If n>0 Then Goto ~Again;EndIf;Return n;EndFunction r=F(3);',{'r':0})

    def test_boolean_counter_mutation_reports_error(self):
        # A one-iteration bound avoids a runaway loop if bool is mistakenly
        # treated as native int: that regression is a normal assertion failure.
        for body in ('i=True;', 'i=True; Continue;'):
            for prepared in (False,True):
                with self.subTest(body=body,prepared=prepared):
                    messages=[]
                    vm=Interpreter(messages.append);self.addCleanup(vm.close)
                    source=('Function F() For i=1 To 1 Do Message("body");'+body+
                            'EndDo;Message("after");Return i;EndFunction r=F();')
                    with self.assertRaisesRegex(BSLError, 'Ожидается число'):
                        if prepared:vm.execute_prepared(vm.prepare(source))
                        else:vm.execute(source)
                    self.assertNotIn('r',vm.variables)
                    self.assertEqual(messages,['body'])
        # Break does not advance a counter, so its value can remain Boolean.
        self.execute('Function F() For i=1 To 1 Do i=True;Break;EndDo;Return i;EndFunction r=F();kind=TypeOf(r)=Type("Boolean");',{'r':True,'kind':True})

    def test_live_opaque_counter_releases_before_following_statement(self):
        for prepared in (False,True):
            with self.subTest(prepared=prepared):
                events=[]
                vm=Interpreter(events.append,allow_extensions=True);self.addCleanup(vm.close)
                class Counter:
                    def __add__(self, increment):
                        events.append(('add',increment))
                        return Decimal(2)
                    def __del__(self):
                        events.append('release')
                vm.register_function('Make',Counter)
                source=('Function F() For i=1 To 1 Do i=Make(); EndDo; '
                        'Message("after"); Return i; EndFunction R=F();')
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual(events,[('add',1),'release','after'])
                self.assertEqual(vm.variables['r'],Decimal(2))

    def test_loop_and_branch_results(self):
        for n,expected in [(-1,0),(0,0),(1,1),(10,55),(101,5151)]:
            self.execute('Function Sum(Val n) s=0;For i=1 To n Do s=s+i;EndDo;Return s;EndFunction r=Sum(n);',{'r':expected},inputs={'n':Decimal(n)})
        for n,expected in [(-1,1),(0,2),(4,3)]:
            self.execute('Function F(Val n) If n<0 Then s=1;ElsIf n=0 Then s=2;Else s=3;EndIf;Return s;EndFunction r=F(n);',{'r':expected},inputs={'n':Decimal(n)})

    def test_loop_control_and_bound_order(self):
        for body,expected in [
            ('s=0;For i=1 To n Do If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;s=s+i;EndDo;Return s;',4),
            ('For i=1 To n Do i=i+1;EndDo;Return i;',7),
            ('i=0;s=0;While i<n Do i=i+1;If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;s=s+i;EndDo;Return s;',4),
            ('s=0;For i=1 To n Do For j=1 To 3 Do If j=2 Then Continue;EndIf;s=s+1;EndDo;EndDo;Return s;',10),
            ('i=4;For i=1 To i Do n=n+1;EndDo;Return n;',9)]:
            with self.subTest(body=body):self.execute('Function F(Val n) '+body+' EndFunction r=F(5);',{'r':expected})


if __name__=='__main__':unittest.main()
