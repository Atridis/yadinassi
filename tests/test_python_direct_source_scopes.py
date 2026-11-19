"""Opt-in source-host routine frames, independent of legacy VM dispatch."""
from contextlib import contextmanager
import unittest

from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_collections import UnsupportedNakedSyntax
from yadinassi.types.values import HostFunction


class ScopeContext(BoundaryContext):
    def __init__(self):
        super().__init__()
        self.frames=[]
        self.events=[]
        self._services['depth']=HostFunction('Depth',lambda:len(self.frames))

    @contextmanager
    def routine_scope(self):
        token=object();self.frames.append(token)
        self.events.append(('enter',len(self.frames)))
        try:
            yield
        finally:
            self.events.append(('leave',len(self.frames)))
            popped=self.frames.pop()
            if popped is not token:raise AssertionError("source frame stack changed")


class SourceRoutineScopeTests(unittest.TestCase):
    def compile(self,source,**kwargs):
        return compile_owned(parse(source),source_text=source,source_name='scopes.bsl',**kwargs)

    def test_callable_external_requires_trusted_source_scope_opt_in(self):
        with self.assertRaisesRegex(ValueError,'owning binding profile'):
            self.compile('A=Depth();',callable_externals=('depth',))
        with self.assertRaisesRegex(TypeError,'tuples of names'):
            self.compile('A=Depth();',source_scopes=True,callable_externals='depth')
        with self.assertRaisesRegex(UnsupportedNakedSyntax,'not callable'):
            self.compile('A=Depth();',external_names=('depth',),source_scopes=True)
        plan=self.compile('A=Depth();',external_names=('depth',),
            source_scopes=True,callable_externals=('depth',))
        state={};plan.run(state,context=ScopeContext())
        self.assertEqual(state['a'],0)

    def test_same_module_nested_calls_and_early_return_have_distinct_frames(self):
        plan=self.compile('''Function Inner() Return Depth(); EndFunction
Function Outer() Return Inner()+Depth(); EndFunction
A=Outer();B=Depth();''',source_scopes=True)
        context=ScopeContext();state={};plan.run(state,context=context)
        self.assertEqual(state,{'a':3,'b':0})
        self.assertEqual(context.events,[('enter',1),('enter',2),('leave',2),('leave',1)])
        self.assertEqual(context.frames,[])

    def test_caught_and_uncaught_errors_unwind_routine_frames(self):
        plan=self.compile('''Procedure Inner() Raise "failure"; EndProcedure
Procedure Outer() Inner(); EndProcedure
Try Outer();Except C=Depth();EndTry;''',source_scopes=True)
        context=ScopeContext();state={};plan.run(state,context=context)
        self.assertEqual(state['c'],0);self.assertEqual(context.frames,[])
        plan=self.compile('Procedure P() Raise "failure"; EndProcedure P();',source_scopes=True)
        with self.assertRaisesRegex(Exception,'failure'):plan.run({},context=context)
        self.assertEqual(context.frames,[])

    def test_boundary_checks_surround_scope_even_without_authority_repair(self):
        plan=self.compile('Procedure P() Revoke(); EndProcedure P();',source_scopes=True)
        context=ScopeContext();context._services['revoke']=HostFunction('Revoke',context.revoke)
        with self.assertRaises(BoundaryViolation):plan.run({},context=context)
        self.assertEqual(context.frames,[])
        self.assertIn('with _context.routine_scope():',plan.generated_source)

    def test_default_has_no_frame_hook_or_added_per_routine_guard(self):
        source='Function F() Return 1; EndFunction A=F();'
        baseline=self.compile(source)
        explicit=self.compile(source,source_scopes=False)
        self.assertEqual(baseline.generated_source,explicit.generated_source)
        self.assertNotIn('routine_scope',baseline.generated_source)
        baseline.run({},context=BoundaryContext())

    def test_missing_plain_and_boxed_locals_are_catchable(self):
        for box in (False,True):
            with self.subTest(box=box):
                tail='P(Missing);' if box else ''
                source=('Procedure P(X) EndProcedure '
                    'Function F() Try R=Missing;Except Return True;EndTry;'+tail+'EndFunction A=F();')
                context=ScopeContext();state={}
                self.compile(source,source_scopes=True).run(state,context=context)
                self.assertTrue(state['a']);self.assertEqual(context.frames,[])

    def test_missing_static_byref_fails_before_callee_effects(self):
        source=('Procedure P(X) Effect();EndProcedure '
            'Function F() Try P(Missing);Except Return True;EndTry;EndFunction A=F();')
        effects=[];context=ScopeContext()
        context._services['effect']=HostFunction('Effect',lambda:effects.append('called'))
        state={};self.compile(source,source_scopes=True).run(state,context=context)
        self.assertTrue(state['a']);self.assertEqual(effects,[]);self.assertEqual(context.frames,[])

    def test_opt_in_requires_exact_boolean_and_trusted_services(self):
        with self.assertRaises(TypeError):self.compile('',source_scopes=1)
        with self.assertRaises(ValueError):self.compile('',scalar_routines=True)

    def test_exported_closure_frame_is_entered_on_each_invocation(self):
        plan=self.compile('Function F() Return Depth(); EndFunction',
            exports=True,source_scopes=True)
        context=ScopeContext();context.enter()
        exports=plan.function({},plan.constants,[],context)
        self.assertEqual(context.events,[])
        self.assertEqual(exports['f'](),1);self.assertEqual(exports['f'](),1)
        self.assertEqual(context.events,[('enter',1),('leave',1),('enter',1),('leave',1)])
        self.assertEqual(context.frames,[])


class MemberScopeContext(ScopeContext):
    def __init__(self,receiver,*,is_function=True):
        super().__init__();self.receiver=receiver;self.calls=[];self.is_function=is_function
        self._services['effect']=HostFunction('Effect',lambda:self.calls.append('effect') or 1)
    def resolve_source_member(self,receiver,name,*,require_value,argument_count,allow_references):
        self.calls.append(('bind',name,require_value,argument_count,allow_references))
        if receiver is not self.receiver:raise BoundaryViolation('foreign receiver')
        if argument_count!=1:raise TypeError('arity')
        def bump(ref):ref.set(ref.get()+1)
        return self.resolve_callable(HostFunction(name,bump,returns_value=self.is_function,reference_parameters=(0,)),
            require_value=require_value,allow_references=allow_references)
    def resolve_member(self,*args):raise AssertionError('legacy member route')


class SourceQualifiedCallTests(unittest.TestCase):
    def compile(self,source,**kwargs):
        return compile_owned(parse(source),source_text=source,source_name='scopes.bsl',**kwargs)

    def test_qualified_reference_for_ordinary_and_native_named_method(self):
        for method in ('Bump','Add'):
            with self.subTest(method=method):
                obj=object();context=MemberScopeContext(obj);state={'host':obj}
                plan=self.compile('X=1;Host.'+method+'(X);',source_scopes=True)
                plan.run(state,context=context)
                self.assertEqual(state['x'],2)
                self.assertEqual(context.calls,[('bind',method,False,1,True)])

    def test_arity_and_procedure_value_rejected_before_argument_effect(self):
        for source in ('Host.Bump(Effect(),Effect());','X=Host.Bump(Effect());'):
            with self.subTest(source=source):
                obj=object();context=MemberScopeContext(obj,is_function=False)
                plan=self.compile(source,source_scopes=True)
                with self.assertRaises(Exception):plan.run({'host':obj},context=context)
                self.assertNotIn('effect',context.calls)

    def test_native_collection_methods_do_not_resolve_source_members(self):
        obj=object();context=MemberScopeContext(obj)
        plan=self.compile('A=New Array;A.Add(7);N=A.Count();',source_scopes=True)
        state={};plan.run(state,context=context)
        self.assertEqual(state['a'],[7]);self.assertEqual(state['n'],1)
        self.assertEqual(context.calls,[])

    def test_default_host_lowering_has_no_source_member_hook(self):
        source='Host.Bump(1);Host.Add(1);'
        baseline=self.compile(source);explicit=self.compile(source,source_scopes=False)
        self.assertEqual(baseline.generated_source,explicit.generated_source)
        self.assertNotIn('resolve_source_member',baseline.generated_source)


if __name__=='__main__':unittest.main()
