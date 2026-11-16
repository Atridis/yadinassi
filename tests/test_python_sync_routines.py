import unittest
from decimal import Decimal,localcontext
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
from yadinassi.python_translation_sync_routines import lower,Ineligible

class SyncRoutineEmitterTests(unittest.TestCase):
    def prepared(self,body,parameters='Val n'):
        vm=Interpreter(execution_backend='compiled-strict')
        routine=parse('Function F('+parameters+')\n'+body+'\nEndFunction','sync-test.bsl')[0]
        engine=vm._compiled();engine.prepare([routine]);owned=engine.execution_view(routine)
        return vm,lower(owned)
    def pair(self,body,n=Decimal(10)):
        vm,plan=self.prepared(body);scope={'n':n}
        with localcontext() as context:
            context.prec=38
            try:actual=('value',plan.function(vm,scope))
            except Exception as error:actual=(type(error).__name__,str(error))
        old=Interpreter(execution_backend='interpreter');old.variables['n']=n
        try:
            old.execute('Function F(Val n)\n'+body+'\nEndFunction\nr=F(n);','sync-test.bsl')
            expected=('value',old.variables['r'])
        except Exception as error:expected=(type(error).__name__,str(error))
        self.assertEqual(actual,expected)
        return scope,plan
    def test_for_locals_decimal(self):
        scope,plan=self.pair('s=0;For i=1 To n Do s=s+i;EndDo;Return s;')
        self.assertEqual(scope['s'],55);self.assertEqual(scope['i'],11)
        self.assertNotIn('yield',plan.source);self.assertNotIn('guard',plan.source)
        self.assertNotIn('set_variable',plan.source);self.assertNotIn('semantic_name',plan.source)
    def test_for_continue_counter_assignment_and_break(self):
        self.pair('s=0;For i=1 To n Do i=i+1;If i=4 Then Continue;EndIf;If i>8 Then Break;EndIf;s=s+i;EndDo;Return s;')
    def test_nested_loops(self):
        self.pair('s=0;For i=1 To n Do j=0;While j<5 Do j=j+1;If j=2 Then Continue;EndIf;If j=4 Then Break;EndIf;s=s+i*j;EndDo;EndDo;Return s;')
    def test_short_circuit_and_conditional(self):
        self.pair('s=False AND 1/0=0;Return ?(s,1/0,n+2);')
    def test_var_branch_then_declaration(self):
        self.pair('If n>1 Then s=5;EndIf;Var s;Return s;',Decimal(0))
        self.pair('If n>1 Then s=5;EndIf;Var s;Return s;',Decimal(5))
    def test_var_preserves_existing_nonparameter_binding(self):
        vm,plan=self.prepared('Var s;Return s;',parameters='')
        scope={'s':Decimal(5)}
        self.assertEqual(plan.function(vm,scope),Decimal(5))
        self.assertEqual(scope,{'s':Decimal(5)})
    def test_division_error_location_and_partial_scope(self):
        scope,_=self.pair('s=0;For i=1 To n Do s=s+1;s=s/(2-i);EndDo;Return s;')
        self.assertEqual(scope['s'],2);self.assertEqual(scope['i'],2)
    def test_decimal_invalid_operation_location(self):
        self.pair('Return n+1;',Decimal('sNaN'))
    def test_counter_type_error_location(self):
        self.pair('For i=1 To n Do i="bad";EndDo;Return i;')
    def test_null_return(self):
        self.pair('Return;')
    def test_definite_assignment_rejected(self):
        for body in ('If n>0 Then x=1;EndIf;Return x;',
                     'For i=1 To n Do x=1;EndDo;Return x;',
                     'Return unknown;'):
            with self.assertRaises(Ineligible):self.prepared(body)
    def test_opaque_byref_rejected(self):
        for body,parameters in [('Return n;','n'),('Return Abs(n);','Val n'),
                                ('Try Return n;Except Return 0;EndTry;','Val n')]:
            with self.assertRaises(Ineligible):self.prepared(body,parameters)
    def test_budget_and_owned_required(self):
        vm,plan=self.prepared('Return n+1;')
        with self.assertRaises(Ineligible):lower(plan.nodes[0],max_source_bytes=1)
        with self.assertRaises(Ineligible):lower(parse('Function F(Val n) Return n;EndFunction')[0])
    def test_authority_inventory_includes_leaves_and_targets(self):
        _,plan=self.prepared('s=n+1;Return s;')
        from yadinassi.owned_syntax import syntax_kind
        kinds={syntax_kind(node) for node in plan.nodes}
        self.assertTrue({ast.Routine,ast.Parameter,ast.Assign,ast.Name,ast.Literal,ast.Return,ast.Binary}<=kinds)
    def test_publish_before_exception_conversion(self):
        vm,plan=self.prepared('s=1;s=1/0;Return s;');scope={'n':Decimal(1)};observed=[]
        original=vm.compiled_exception
        def convert(node,error):
            observed.append(dict(scope));return original(node,error)
        vm.compiled_exception=convert
        with self.assertRaises(Exception):plan.function(vm,scope)
        self.assertEqual(observed[0]['s'],1)
