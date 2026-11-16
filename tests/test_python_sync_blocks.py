import unittest
from decimal import Decimal,localcontext
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.python_translation_sync_routines import lower_block,Ineligible

class SyncBlockEmitterTests(unittest.TestCase):
    def prepare(self,source,start=0,stop=None):
        vm=Interpreter(execution_backend='compiled-strict')
        routine='Return' in source
        program=parse(('Function F() '+source+' EndFunction') if routine else source,'block-test.bsl')
        engine=vm._compiled();engine.prepare(program,module_entry=True)
        block=engine.execution_view(program[0]).body if routine else engine.execution_view(program)
        return vm,block,lower_block(block,start=start,stop=stop)
    def test_complete_module_scalar_region(self):
        vm,block,plan=self.prepare('s=0;For i=1 To n Do s=s+i;EndDo;result=s;')
        self.assertEqual(plan.parameters,('n',));scope={'n':Decimal(10)}
        self.assertEqual(plan.function(vm,scope),(False,None))
        self.assertEqual(scope['result'],55);self.assertEqual(scope['i'],11)
        self.assertIs(plan.containers[0],block)
    def test_real_range_excludes_opaque_siblings(self):
        vm,block,plan=self.prepare('before=Clock();s=0;For i=1 To n Do s=s+i;EndDo;after=Clock();',1,3)
        scope={'n':Decimal(3)};plan.function(vm,scope)
        self.assertEqual(scope['s'],6)
        self.assertFalse(any(node is block[0] or node is block[3] for node in plan.nodes))
        self.assertIs(plan.containers[0],block)
        with self.assertRaises(Ineligible):lower_block(block[1:3])
    def test_initial_values_and_redeclaration_preserved(self):
        vm,_,plan=self.prepare('Var s;s=s+1;')
        scope={'s':Decimal(7)};self.assertEqual(plan.parameters,())
        plan.function(vm,scope);self.assertEqual(scope['s'],8)
    def test_conditional_assignment_keeps_prior_scope(self):
        vm,_,plan=self.prepare('If flag Then s=9;EndIf;Var s;result=s;')
        scope={'flag':False,'s':Decimal(7)};plan.function(vm,scope)
        self.assertEqual(scope['result'],7)
    def test_return_distinct_from_fallthrough(self):
        vm,_,plan=self.prepare('For i=1 To n Do If i=2 Then Return;EndIf;EndDo;')
        self.assertEqual(plan.function(vm,{'n':Decimal(3)}),(True,None))
        self.assertEqual(plan.function(vm,{'n':Decimal(0)}),(False,None))
    def test_nested_return_value_and_published_loop_state(self):
        vm,_,plan=self.prepare('s=0;For i=1 To n Do s=s+i;If i=2 Then Return s;EndIf;EndDo;')
        scope={'n':Decimal(3)};self.assertEqual(plan.function(vm,scope),(True,Decimal(3)))
        self.assertEqual(scope['i'],2);self.assertEqual(scope['s'],3)
    def test_external_loop_control_ineligible(self):
        for source in ('Break;','Continue;'):
            vm,block,_=self.prepare('While True Do '+source+' EndDo;')
            with self.assertRaises(Ineligible):lower_block(block[0].body)
    def test_nested_loop_continue_and_break(self):
        vm,_,plan=self.prepare('s=0;For i=1 To n Do i=i+1;If i=4 Then Continue;EndIf;If i=8 Then Break;EndIf;s=s+i;EndDo;')
        scope={'n':Decimal(10)};plan.function(vm,scope)
        old=Interpreter(execution_backend='interpreter');old.variables['n']=Decimal(10)
        old.execute('s=0;For i=1 To n Do i=i+1;If i=4 Then Continue;EndIf;If i=8 Then Break;EndIf;s=s+i;EndDo;')
        self.assertEqual(scope,old.variables)
    def test_partial_error_scope_and_location(self):
        source='s=0;For i=1 To n Do s=s+1;s=s/(2-i);EndDo;'
        vm,_,plan=self.prepare(source);scope={'n':Decimal(3)};errors=[]
        try:plan.function(vm,scope)
        except Exception as error:errors.append(str(error))
        old=Interpreter(execution_backend='interpreter');old.variables['n']=Decimal(3)
        try:old.execute(source,'block-test.bsl')
        except Exception as error:errors.append(str(error))
        self.assertEqual(len(errors),2);self.assertEqual(*errors)
        self.assertEqual(scope,old.variables)
    def test_opaque_expression_ineligible(self):
        for source in ('s=Clock();','s=New Query;','s=Eval("1");'):
            with self.assertRaises(Ineligible):self.prepare(source)
    def test_inputs_only_before_definite_write(self):
        vm,_,plan=self.prepare('s=0;s=s+n;result=s;')
        self.assertEqual(plan.parameters,('n',))
    def test_owned_containers_and_budget(self):
        vm,block,plan=self.prepare('If flag Then For i=1 To n Do s=i;EndDo;EndIf;')
        self.assertGreaterEqual(len(plan.containers),3)
        with self.assertRaises(Ineligible):lower_block(block,max_bindings=1)
        with self.assertRaises(Ineligible):lower_block(block,max_source_bytes=1)
        with self.assertRaises(Ineligible):lower_block(block,start=1,stop=1)
