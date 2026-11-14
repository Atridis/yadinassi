"""Differential allocation cleanup; semantics and hooks, not speed assertions."""
from decimal import Decimal
from types import MethodType
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi.values import require_number


class LegacyFor(Interpreter):
    def visit_For(self, node):
        start=require_number((yield from self._visit(node.start)))
        end=require_number((yield from self._visit(node.end)))
        name=node.name.casefold()
        self.set_variable(name,start)
        while require_number(self.visit_Name(ast.Name(node.token,name))) <= end:
            if not (yield from self.iteration(node.body)): break
            self.set_variable(name,require_number(self.visit_Name(ast.Name(node.token,name)))+Decimal(1))


class Trace:
    def __init__(self,*args,**kwargs):
        self.trace=[]; self.descriptors=[]
        super().__init__(*args,**kwargs)
    def visit_Name(self,node):
        self.trace.append(('name',node.name))
        self.descriptors.append(node)
        result=super().visit_Name(node)
        # Deliberately mutate the supplied Name after reading. For internal
        # counter reads the previous contract supplied a fresh node each time.
        if node.name=='i':node.name='changed'
        return result
    def set_variable(self,name,value):
        self.trace.append(('set',name,str(value)))
        return super().set_variable(name,value)
    def iteration(self,body):
        self.trace.append(('iteration',len(body)))
        return (yield from super().iteration(body))
    def block(self,body):
        self.trace.append(('block',len(body)))
        return (yield from super().block(body))


class TraceNew(Trace,Interpreter):pass
class TraceOld(Trace,LegacyFor):pass


class ForAllocationContractTests(unittest.TestCase):
    def run_vm(self,cls,code,setup=None):
        output=[];vm=cls(output.append);self.addCleanup(vm.close)
        if setup:setup(vm)
        error=None
        try:vm.execute(code,'for-contract.bsl');vm.ensure_complete()
        except BSLError as e:error=(type(e).__name__,str(e))
        return vm,output,error

    def equivalent(self,code,setup=None):
        old,out1,error1=self.run_vm(LegacyFor,code,setup)
        new,out2,error2=self.run_vm(Interpreter,code,setup)
        self.assertEqual(out1,out2);self.assertEqual(error1,error2)
        for key,value in old.variables.items():
            if type(value) in (Decimal,str,bool,type(None)):
                self.assertEqual(new.variables.get(key),value,key)
        return new,out2,error2

    def test_fractional_counter_postloop(self):
        _,out,error=self.equivalent('For i=0.5 To 2.5 Do Message(i); EndDo; Message(i);')
        self.assertIsNone(error);self.assertEqual(out,['0,5','1,5','2,5','3,5'])

    def test_descending_empty_and_bounds_once_order(self):
        _,out,error=self.equivalent('Function Bound(Val n) Message(n); Return n; EndFunction For i=Bound(3) To Bound(1) Do Message("bad"); EndDo; Message(i);')
        self.assertIsNone(error);self.assertEqual(out,['3','1','3'])

    def test_mutable_counter_and_reference_parameter(self):
        _,out,error=self.equivalent('Procedure Run(i) For i=1 To 5 Do Message(i); i=i+1; EndDo; EndProcedure X=0; Run(X); Message(X);')
        self.assertIsNone(error);self.assertEqual(out,['1','3','5','7'])

    def test_routine_shadowing_module_counter(self):
        _,out,error=self.equivalent('i=99; Function Run() For i=1 To 2 Do EndDo; Return i; EndFunction Message(Run()); Message(i);')
        self.assertIsNone(error);self.assertEqual(out,['3','99'])

    def test_break_continue_goto_nested_and_errors(self):
        programs=[
            'For i=1 To 5 Do If i=2 Then Continue; EndIf; Message(i); If i=3 Then Break; EndIf; EndDo; Message(i);',
            'For i=1 To 2 Do For j=1 To 2 Do Message(i+j); Goto ~Done; EndDo; EndDo; ~Done: Message(i);',
            'For i=1 To 2 Do i="wrong"; EndDo;',
            'For i=1 To 2 Do X=1/0; EndDo;',
            'For i=1 To "bad" Do EndDo;',
            'For i=1 To 2 Do Try Raise "caught"; Except Message(i); EndTry; EndDo;']
        for code in programs:
            with self.subTest(code=code):self.equivalent(code)

    def test_decimal_context_38_digit_arithmetic(self):
        _,out,error=self.equivalent('R=9999999999999999999999999999999999999; For i=0.1 To 3 Do R=R+i/3; EndDo; Message(R);')
        self.assertIsNone(error);self.assertTrue(out)

    def test_async_bounds_and_body(self):
        _,out,error=self.equivalent('Async Function Bound(Val n) Return Await n; EndFunction Async Function Run() For i=Await Bound(1) To Await Bound(3) Do Message(Await i); EndDo; Message(i); Return i; EndFunction P=Run();')
        self.assertIsNone(error);self.assertEqual(out,['1','2','3','4'])

    def test_subclass_hooks_receive_fresh_descriptors(self):
        code='For i=1 To 3 Do EndDo;'
        old,_,e1=self.run_vm(TraceOld,code);new,_,e2=self.run_vm(TraceNew,code)
        self.assertIsNone(e1);self.assertIsNone(e2)
        self.assertEqual(old.trace,new.trace)
        self.assertEqual(len({id(n) for n in new.descriptors}),len(new.descriptors))

    def test_instance_hook_can_appear_and_disappear_inside_body(self):
        def setup(vm):
            def hooked(self,node):
                result=Interpreter.visit_Name(self,node)
                if node.name=='i':node.name='changed'
                return result
            def install():vm.visit_Name=MethodType(hooked,vm)
            def remove():del vm.visit_Name
            vm.register_function('Install',install);vm.register_function('Remove',remove)
        _,out,error=self.equivalent('For i=1 To 3 Do Install(); Remove(); EndDo; Message(i);',setup)
        self.assertIsNone(error);self.assertEqual(out,['4'])

    def test_active_instance_hook_preserves_counter_descriptor(self):
        def setup(vm):
            def hooked(self,node):
                result=Interpreter.visit_Name(self,node)
                if node.name=='i':node.name='changed'
                return result
            vm.register_function('Install',lambda:setattr(vm,'visit_Name',MethodType(hooked,vm)))
        _,_,error=self.equivalent('For i=1 To 3 Do Install(); EndDo;',setup)
        self.assertIsNone(error)

    def test_class_hook_installed_inside_loop_gets_fresh_descriptors(self):
        original=Interpreter.visit_Name
        for cls in (LegacyFor,Interpreter):
            nodes=[]
            def hooked(vm,node):
                result=original(vm,node)
                if node.name=='i':
                    nodes.append(node);node.name='changed'
                return result
            with patch.object(Interpreter,'visit_Name',original):
                def setup(vm):
                    vm.register_function('Install',lambda:setattr(Interpreter,'visit_Name',hooked))
                vm,_,error=self.run_vm(cls,'For i=1 To 3 Do Install(); EndDo;',setup)
                self.assertIsNone(error);self.assertEqual(vm.variables['i'],Decimal(4))
                self.assertEqual(len(nodes),6)
                self.assertEqual(len({id(n) for n in nodes}),6)

    def test_mutable_body_before_execution_is_not_frozen(self):
        program=parse('For i=1 To 3 Do EndDo;')
        program[0].body[:]=parse('x=7;')
        vm=Interpreter();self.addCleanup(vm.close);vm.execute_program(program)
        self.assertEqual(vm.variables['x'],Decimal(7));self.assertEqual(vm.variables['i'],Decimal(4))

    def test_empty_loop_visit_accounting_unchanged_not_per_iteration(self):
        class Count(Interpreter):
            def _visit(self,node):
                self.count+=1
                return (yield from super()._visit(node))
        vm=Count();self.addCleanup(vm.close);vm.count=0
        vm.execute('For i=1 To 50 Do EndDo;')
        self.assertEqual(vm.count,3) # For + two bounds, not 50 iteration charges.

if __name__=='__main__':unittest.main()
