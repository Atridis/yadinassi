from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from yadinassi.forms.direct_form_parameters import (structure_items,is_parameters,get_parameter,bind_parameter_method,bind_parameter_write)
from yadinassi.execution.codegen.direct_structure import new_structure,_DirectStructure
from yadinassi.configuration.configuration_forms import bind_parameters
from yadinassi.forms.form_results import freeze_result,result_value
from yadinassi.collections.structures import BSLStructure,BSLFixedStructure
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

class DirectFormParametersTests(unittest.TestCase):
    def session(self):
        return SimpleNamespace(state='created',_busy=False,form=SimpleNamespace(_check=lambda:None))

    def test_native_input_is_scalar_snapshot_not_alias(self):
        incoming=new_structure('DraftTitle,Amount','draft',Decimal(7));session=self.session()
        bind_parameters(session,incoming)
        self.assertIs(type(session._parameters),BSLFixedStructure)
        incoming['Amount']=Decimal(99)
        self.assertEqual(get_parameter(session,session._parameters,'amount'),7)
        with self.assertRaises(ValueError):bind_parameter_write(session,session._parameters,'Amount')(Decimal(8))
        self.assertEqual(get_parameter(session,session._parameters,'Amount'),7)
        with self.assertRaises(TypeError):bind_parameters(self.session(),new_structure('Nested',[]))

    def test_method_case_and_replacement_bound_authority(self):
        session=self.session();bind_parameters(session,{'Name':'value'})
        values=session._parameters
        self.assertTrue(bind_parameter_method(session,values,'Свойство')('name'))
        self.assertEqual(bind_parameter_method(session,values,'Count')(),1)
        with self.assertRaises(ValueError):get_parameter(session,values,'Property')
        bound=bind_parameter_method(session,values,'Property');bind_parameters(session,{'Name':'new'})
        with self.assertRaises(BoundaryViolation):bound('Name')
        with self.assertRaises(TypeError):bind_parameter_method(session,session._parameters,'Property')('Name',object())

    def test_no_ducktyping_or_hostile_type_equality(self):
        seen=[]
        class Meta(type):
            def __eq__(self,other):seen.append('eq');return True
        class Host(metaclass=Meta):
            def items(self):seen.append('items');return ()
        self.assertIsNone(structure_items(Host()));self.assertEqual(seen,[])
        with self.assertRaises(ValueError):bind_parameters(self.session(),Host())
        self.assertEqual(seen,[])

    def test_native_result_roundtrip_and_freeze_detaches(self):
        incoming=new_structure('DraftTitle,Amount,Comment','Draft',Decimal('2.5'),'x')
        raw=freeze_result(incoming);incoming['Amount']=Decimal(99)
        direct=result_value(raw)
        self.assertIs(type(direct),_DirectStructure)
        self.assertEqual(direct['Amount'],Decimal('2.5'))
        direct['Amount']=Decimal(100)
        self.assertEqual(result_value(raw)['Amount'],Decimal('2.5'))
        with self.assertRaises(Exception):freeze_result(new_structure('Nested',new_structure()))
        with self.assertRaises(Exception):freeze_result({'RawMap':1})
        for value in (None,True,Decimal(4),'text'):
            self.assertEqual(result_value(freeze_result(value)),value)

    def test_ui_parameter_boundary_accepts_native_only_structure(self):
        from yadinassi.ui.configuration_app import _parameters
        source=new_structure('Name,Number','Test',Decimal(3));result=_parameters(source)
        source['Name']='changed';self.assertEqual(result,{'Name':'Test','Number':3})
        with self.assertRaises(Exception):_parameters(new_structure('Nested',new_structure()))

    def test_actual_draftdetails_created_source_without_vm_dispatch(self):
        from yadinassi import Interpreter
        from yadinassi.ui.configuration_app import load_application
        from yadinassi.execution.direct.python_direct_forms import FormBoundary
        root=Path(__file__).resolve().parents[1]/'examples/demo'
        original_get=FormBoundary.get_member;original_method=FormBoundary.resolve_member
        def get(ctx,value,name):
            return get_parameter(ctx.session,value,name) if is_parameters(ctx.session,value) else original_get(ctx,value,name)
        def method(ctx,value,name):
            return bind_parameter_method(ctx.session,value,name) if is_parameters(ctx.session,value) else original_method(ctx,value,name)
        # Explicitly install the agreed narrow hooks in this isolated test;
        # the separate callback integration owns FormBoundary's production edits.
        with patch.object(FormBoundary,'get_member',get), patch.object(FormBoundary,'resolve_member',method):
            app=load_application(root,main_demo_application=True)
            server=app.forms['commonform.draftdetails'].create_server(parameters=new_structure('DraftTitle,Amount,Comment','Actual source',Decimal(7),'memo'))
            session=server.session;session._begin(session.revision)
            try:
                self.assertEqual(session._event('oncreateatserver',[False,True]),[False,True])
                self.assertEqual(session.form.get_member('DraftTitle'),'Actual source')
                self.assertEqual(session.form.get_member('Amount'),7)
                self.assertEqual(session.form.get_member('Comment'),'memo')
            finally:session._busy=False;session._gate.release()

if __name__=='__main__':unittest.main()
