"""Host enum picker contracts; no native event parity claim."""
from types import SimpleNamespace
import unittest
from test_form_enumerations import scopes
from test_configuration_reference_choice import SOURCE
from yadinassi.form_model import BSLFormAttribute
from yadinassi.form_tables import FormTableColumn,FormTableSchema
from yadinassi.form_replication import ReplicatedFormServer,ReplicatedFormSession
from yadinassi.configuration_reference_choice import ConfigurationReferenceChoice

class EnumPickerTests(unittest.TestCase):
    def setUp(self):
        ss,cs,self.manager,self.life=scopes();kind=ss.descriptor(1)
        self.server=ReplicatedFormServer(SOURCE,{},handlers=(),attributes=(BSLFormAttribute('Product',kind),),
            tables=(FormTableSchema('Lines',(FormTableColumn('Product',kind),)),),
            reference_scope=ss,bindings={'OnCreateAtServer':'Create'})
        self.server.session.form._tables['lines']._replace_rows(((1,(self.manager._empty,)),),1)
        self.client=ReplicatedFormSession('',self.server.exchange,handlers=(),reference_scope=cs);self.client.open()
        self.server.session._reference_managers={1:self.manager}
        self.owned=SimpleNamespace(object=object(),pending_commit=False,pending_refresh=False,verify_source=lambda:None)
        self.choice=ConfigurationReferenceChoice(SimpleNamespace(reference_slots=(('Product','',1),('Lines','Product',1))),self.server,self.owned)
    def execute(self,action):
        self.choice.pending=action;self.server.session._busy=True
        try:return self.choice.execute(self.server.session)
        finally:self.server.session._busy=False
    def begin(self,table=False):
        self.execute({'action':'begin','control':'LinesTable' if table else 'ProductField','row':1 if table else None,'column':'Product' if table else None})
        return self.choice.projection()
    def test_header_apply_clear_and_opaque_identity(self):
        p=self.begin();self.assertEqual(len(p['rows']),len(self.manager._values))
        self.assertNotIn(str(self.manager._value_type.metadata_uuid),str(p))
        action={'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']}
        self.assertEqual(self.execute(action),'applied');self.assertIs(self.server.session.form._data['product'],self.manager._values[0])
        with self.assertRaises(ValueError):self.execute(action)
        self.execute({'action':'clear','control':'ProductField','row':None,'column':None})
        self.assertIs(self.server.session.form._data['product'],self.manager._empty)
    def test_table_apply_and_filter_invalidates_token(self):
        p=self.begin(True);self.execute({'action':'filter','ticket':p['ticket'],'code':p['rows'][0]['code']})
        with self.assertRaises(ValueError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        p=self.choice.projection();self.assertEqual(len(p['rows']),1)
        self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        self.assertIs(self.server.session.form._tables['lines']._by_id[1]._data['product'],self.manager._values[0])
    def test_owner_change_rejects_and_cancel_keeps_empty(self):
        p=self.begin();self.owned.object=object()
        with self.assertRaises(ValueError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        self.execute({'action':'cancel','ticket':p['ticket']})
        self.assertIs(self.server.session.form._data['product'],self.manager._empty)
