import unittest
from decimal import Decimal
from yadinassi.experimental_naked_collections import prepare,UnsupportedNakedSyntax
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
from yadinassi.python_direct import REPAIRS

class ProductContext(BoundaryContext):
    def __init__(self,values=None,services=None):
        super().__init__(services=services);self.values={} if values is None else values;self.events=[]
    def external_get(self,name):self.events.append(('get',name));return self.values[name]
    def external_set(self,name,value):
        self.events.append(('set',name,value))
        if name=='thisobject':raise ValueError('product readonly')
        self.values[name]=value

class ExternalNamespaceTests(unittest.TestCase):
    def run_source(self,source,ctx,external=('amount','thisobject'),state=None):
        p=prepare(source,repairs=REPAIRS,external_names=external,_trusted_entry=True)
        state={} if state is None else state;p.run(state,context=ctx);return state

    def test_schema_known_before_values_initialized(self):
        ctx=ProductContext();state=self.run_source('Amount=1;seen=Amount;Amount=Amount+2;',ctx)
        self.assertEqual(ctx.values['amount'],3);self.assertEqual(state,{'seen':1})

    def test_read_current_host_write_no_copy(self):
        ctx=ProductContext({'amount':Decimal(1)})
        ctx._services['mutate']=lambda:ctx.values.__setitem__('amount',Decimal(8))
        state=self.run_source('before=Amount;Mutate();after=Amount;',ctx)
        self.assertEqual(state,{'before':1,'after':8})

    def test_parameters_and_explicit_locals_shadow(self):
        ctx=ProductContext({'amount':Decimal(5)})
        state=self.run_source('Function P(Val Amount) Amount=Amount+1;Return Amount;EndFunction Function L() Var Amount;Amount=9;Return Amount;EndFunction pResult=P(2);lResult=L();external=Amount;',ctx)
        self.assertEqual(state,{'presult':3,'lresult':9,'external':5});self.assertEqual(ctx.values['amount'],5)

    def test_implicit_routine_external_assignment(self):
        ctx=ProductContext({'amount':Decimal(1)})
        state=self.run_source('Procedure Update() Amount=Amount+3;private=8;EndProcedure Update();',ctx)
        self.assertEqual(ctx.values['amount'],4);self.assertEqual(state,{})

    def test_readonly_product_setter_after_rhs(self):
        effects=[];ctx=ProductContext(services={'Rhs':lambda:effects.append(1) or 9})
        with self.assertRaisesRegex(Exception,'product readonly'):self.run_source('ThisObject=Rhs();',ctx)
        self.assertEqual(effects,[1]);self.assertEqual(ctx.events,[('set','thisobject',9)])

    def test_bare_external_byref_stays_rejected_before_callee(self):
        effects=[];ctx=ProductContext({'amount':Decimal(1)},services={'Seen':lambda:effects.append(1)})
        with self.assertRaisesRegex(Exception,'без Знач'):
            self.run_source('Procedure F(a) Seen();a=2;EndProcedure F(Amount);',ctx)
        self.assertEqual(effects,[]);self.assertEqual(ctx.values['amount'],1)

    def test_val_argument_reads_external_value(self):
        ctx=ProductContext({'amount':Decimal(1)})
        state=self.run_source('Function F(Val a) Return a+1;EndFunction r=F(Amount);',ctx)
        self.assertEqual(state['r'],2)

    def test_external_for_and_continue(self):
        ctx=ProductContext()
        state=self.run_source('s=0;For Amount=1 To 3 Do If Amount=2 Then Continue;EndIf;s=s+Amount;EndDo;',ctx)
        self.assertEqual(state,{'s':4});self.assertEqual(ctx.values['amount'],4)

    def test_external_foreach(self):
        ctx=ProductContext();state=self.run_source('a=New Array;a.Add(2);a.Add(7);For Each Amount In a Do last=Amount;EndDo;',ctx)
        self.assertEqual(ctx.values['amount'],7);self.assertEqual(state['last'],7);self.assertNotIn('amount',state)

    def test_default_context_has_no_implicit_authority(self):
        with self.assertRaises(BoundaryViolation):self.run_source('Amount=1;',BoundaryContext())

    def test_declaration_and_conditional_shadow_refused(self):
        for source in ('Var Amount;', 'Procedure F() If True Then Var Amount;EndIf;EndProcedure'):
            with self.assertRaises(UnsupportedNakedSyntax):prepare(source,repairs=REPAIRS,external_names=('amount',),_trusted_entry=True)

    def test_real_form_product_setter_adjusts_and_preserves_readonly(self):
        from yadinassi.form_runtime import FormSession
        from yadinassi.form_model import BSLFormAttribute
        from yadinassi.type_descriptions import BSLTypeDescription
        from yadinassi.type_qualifiers import BSLStringQualifiers
        from yadinassi.execution_policy import execution_backend_policy
        with execution_backend_policy('compiled-strict'):
            session=FormSession('',attributes=(BSLFormAttribute('Label',BSLTypeDescription('String',None,BSLStringQualifiers(Decimal(3)))),))
        class FormContext(BoundaryContext):
            def external_get(self,name):return session.form.get_member(name)
            def external_set(self,name,value):return session.form.set_member(name,value)
        session._busy=True
        try:
            state=self.run_source('Label="abcdef";observed=Label;',FormContext(),external=('label',))
            self.assertEqual(state['observed'],'abc');self.assertEqual(session.form._data['label'],'abc')
            session.form._host_readonly=frozenset({'label'})
            with self.assertRaisesRegex(Exception,'read-only'):self.run_source('Label="x";',FormContext(),external=('label',))
            self.assertEqual(session.form._data['label'],'abc')
        finally:session._busy=False

if __name__=='__main__':unittest.main()
