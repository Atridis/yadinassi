import unittest
from contextlib import contextmanager
from decimal import Decimal
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct_handlers import prepare_handlers
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext,BoundaryViolation
from yadinassi.types.errors import BSLRuntimeError

class DirectHandlerTests(unittest.TestCase):
    def prepare(self,source):return prepare_handlers(parse(source,'handlers.bsl'),source_text=source,source_name='handlers.bsl')

    def test_byref_val_sibling_call_and_persistent_globals_without_dispatch(self):
        source='Var total;Procedure Add(x) x=x+1;EndProcedure Procedure Event(cancel,Val copy) Add(cancel);copy=99;total=total+1;EndProcedure'
        p=self.prepare(source);state={'total':Decimal(0)}
        self.assertEqual(p.invoke('Event','client',[Decimal(3),Decimal(7)],state=state,context_factory=BoundaryContext),[4,7])
        self.assertEqual(p.invoke('Event','client',[Decimal(5),Decimal(8)],state=state,context_factory=BoundaryContext),[6,8])
        self.assertEqual(state['total'],2)

    def test_fresh_context_host_bindings_and_no_session_state_capture(self):
        p=self.prepare('Var value;Procedure Event() value=Read();EndProcedure');state={};contexts=[]
        def factory():
            ctx=BoundaryContext(services={'Read':lambda:len(contexts)});contexts.append(ctx);return ctx
        p.invoke('Event','client',[],state=state,context_factory=factory);self.assertEqual(state['value'],1)
        other={};p.invoke('Event','client',[],state=other,context_factory=factory)
        self.assertEqual((state['value'],other['value']),(1,2));self.assertIsNone(p._plans['client'].last_state)

    def test_bind_rejects_wrong_side_function_and_arity_before_factory(self):
        p=self.prepare('Procedure Event(x) EndProcedure Function F() Return 1;EndFunction')
        def forbidden():raise AssertionError('context created')
        for name,side,args in [('Event','server',[1]),('Event','client',[]),('F','client',[])]:
            with self.assertRaises(ValueError):p.invoke(name,side,args,state={},context_factory=forbidden)

    def test_owned_ast_snapshot(self):
        source='Procedure Event(x) x=7;EndProcedure';nodes=parse(source);p=prepare_handlers(nodes,source_text=source)
        nodes[0].body[0].value.value=Decimal(99)
        self.assertEqual(p.invoke('Event','client',[0],state={},context_factory=BoundaryContext),[7])

    def test_error_source_partial_effect_and_scope_cleanup(self):
        source='Var value;\nProcedure Event()\nvalue=1;\nx=1/0;\nEndProcedure'
        p=self.prepare(source);state={};events=[]
        @contextmanager
        def scope():
            events.append('enter')
            try:yield
            finally:events.append('leave')
        with self.assertRaises(BSLRuntimeError) as caught:p.invoke('Event','client',[],state=state,context_factory=BoundaryContext,execution_scope=scope)
        self.assertEqual(state['value'],1);self.assertEqual(caught.exception.line,4);self.assertEqual(events,['enter','leave'])

    def test_revocation_is_not_caught_as_bsl_runtime_error(self):
        p=self.prepare('Var value;Procedure Event() Revoke();value=1;EndProcedure');state={};ctx=BoundaryContext()
        ctx._services['revoke']=ctx.revoke
        with self.assertRaises(BoundaryViolation):p.invoke('Event','client',[],state=state,context_factory=lambda:ctx)
        self.assertIsNone(state['value'])

    def test_server_side_factory(self):
        source='Procedure Event(x) x=x+1;EndProcedure';nodes=parse(source);nodes[0].execution_context='server'
        p=prepare_handlers(nodes,source_text=source)
        self.assertEqual(p.invoke('Event','server',[Decimal(1)],state={},context_factory=BoundaryContext),[2])

    def test_module_effects_are_rejected(self):
        with self.assertRaises(ValueError):self.prepare('x=1;Procedure Event() EndProcedure')

    def test_side_local_module_declarations_preserve_existing_values(self):
        source='Var total;Procedure Event(x) x=total;EndProcedure'
        nodes=parse(source)
        for node in nodes:node.execution_context='server'
        p=prepare_handlers(nodes,source_text=source)
        self.assertEqual(p.invoke('Event','server',[0],state={'total':Decimal(9)},context_factory=BoundaryContext),[9])
        state={};self.assertEqual(p.invoke('Event','server',[0],state=state,context_factory=BoundaryContext),[None])
        self.assertEqual(state,{'total':None})

    def test_invalid_storage_rejected_before_context_or_handler(self):
        p=self.prepare('Procedure Event() Host();EndProcedure')
        with self.assertRaises(ValueError):
            p.invoke('Event','client',[],state={'NotFolded':1},context_factory=lambda:self.fail('context created'))

    def test_explicit_loop_header_budget_and_cleanup(self):
        source='Procedure Event() While True Do EndDo;EndProcedure'
        p=prepare_handlers(parse(source),source_text=source)
        ctx=BoundaryContext(loop_budget=2)
        with self.assertRaises(BoundaryViolation):p.invoke('Event','client',[],state={},context_factory=lambda:ctx)
        self.assertEqual(ctx.loop_backedges,2)

    def test_external_form_namespace_in_generated_handler(self):
        source='Procedure Event(cancel) Field=Field+1;cancel=Field;EndProcedure'
        p=prepare_handlers(parse(source),source_text=source,external_names=('Field',))
        fields={'field':Decimal(4)}
        class FormContext(BoundaryContext):
            def external_get(self,name):return fields[name]
            def external_set(self,name,value):fields[name]=value
        self.assertEqual(p.invoke('Event','client',[0],state={},context_factory=FormContext),[5])
        self.assertEqual(fields,{'field':5})
