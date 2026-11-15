import unittest
from decimal import Decimal
from yadinassi import Interpreter

from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class ControlTests(unittest.TestCase):
    def compare(self, body, n=5, plain=True):
        source='Function F(Val n) '+body+' EndFunction result=F(n);'
        outcomes=[]
        for enabled in (False,True):
            vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
            vm.variables['n']=Decimal(n)
            try:
                vm.execute(source);outcome=('ok',vm.variables['result'])
            except Exception as error:outcome=(type(error).__name__,str(error))
            outcomes.append(outcome)
            self.assertIsNone(vm.locals)
            self.assertEqual(vm._compiled().active_frames,0)
            self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
            if enabled and plain and outcome[0]=='ok':
                self.assertGreater(vm.compiled_backend_stats.get('plain_routine_calls',0),0)
        self.assertEqual(*outcomes)
        return outcomes[0]
    def test_expressions(self):
        for expr in ['(n+1)*2','-n+ +n','NOT n','n=5','n<>4','n<6','n<=5','n>4','n>=5','True=n','False AND -True','True OR -False','(n=5) AND (n>0)','True+1']:
            with self.subTest(expr=expr):self.compare('Return '+expr+';')
    def test_if(self):
        body='s=0;If n<0 Then s=1; ElsIf n=0 Then s=2; Else s=3;EndIf;Return s;'
        for n in [-1,0,4]:self.compare(body,n)
        self.compare('If n>0 Then s=1;Else s=2;EndIf;Return s;')
    def test_for_continue_break(self):
        self.compare('s=0;For i=1 To n Do If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;s=s+i;EndDo;Return s;')
        self.compare('For i=1 To n Do i=i+1;EndDo;Return i;')
    def test_while_continue_break(self):
        self.compare('i=0;s=0;While i<n Do i=i+1;If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;s=s+i;EndDo;Return s;')
    def test_nested_loops(self):
        self.compare('s=0;For i=1 To n Do For j=1 To 3 Do If j=2 Then Continue;EndIf;s=s+1;EndDo;EndDo;Return s;',plain=False)
    def test_zero_loop_definite_assignment(self):
        self.compare('While n<0 Do s=1;EndDo;Return s;',plain=False)
        self.compare('If n<0 Then s=1;EndIf;Return s;',plain=False)
    def test_non_numeric_counter_error(self):
        self.compare('For i=1 To n Do i=True;EndDo;Return i;')
    def test_counter_start_end_order(self):
        self.compare('i=4;For i=1 To i Do n=n+1;EndDo;Return n;')

    def test_terminal_call_spills_and_preserves_suspension(self):
        from yadinassi.syntax.parser import parse
        from yadinassi.plain_routines import lower
        routine=parse('Function F(Val n) If n>0 Then s=7;EndIf;Return G(n);EndFunction')[0]
        plan=lower(routine)
        self.assertTrue(plan.generator)
        class VM:
            def __init__(self,n):
                self.locals={'n':n};self.stats={}
            def _compiled(self):return self
            def _visit(self,node):
                yield 'suspended'
                return Decimal(11)
            def compiled_exception(self,node,error):return error
        for n in (Decimal(1),Decimal(0)):
            vm=VM(n);identity=vm.locals;operation=plan.function(vm,n)
            self.assertEqual(next(operation),'suspended');self.assertIs(vm.locals,identity)
            self.assertEqual('s' in vm.locals,n>0)
            with self.assertRaises(StopIteration) as done:next(operation)
            self.assertEqual(done.exception.value,11)
    def test_nonterminal_calls_are_explicit_mixed_plans(self):
        from yadinassi.syntax.parser import parse
        from yadinassi.plain_routines import lower,Ineligible
        for source in ['Function F(Val n) s=G(n);Return s;EndFunction',
                       'Function F(Val n) If n>0 Then Return G(n);EndIf;Return n;EndFunction']:
            plan=lower(parse(source)[0]);self.assertTrue(plan.generator);self.assertTrue(plan.prefix_only)

if __name__=='__main__':unittest.main()
