"""Picker ownership unit contracts over real form state; storage ports are controlled."""
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import unittest

from test_form_references import scopes
from yadinassi.form_model import BSLFormAttribute
from yadinassi.form_tables import FormTableColumn,FormTableSchema
from yadinassi.form_replication import ReplicatedFormServer,ReplicatedFormSession
from yadinassi.catalog_backend import CatalogKey,CatalogValueRow,CatalogValuePage,BackendError
from yadinassi.configuration_reference_choice import ConfigurationReferenceChoice

SOURCE='''&AtServer
Procedure Create(Cancel, StandardProcessing)
 F=Items.Add("ProductField",Type("FormField")); F.DataPath="Product";
 T=Items.Add("LinesTable",Type("FormTable")); T.DataPath="Lines";
EndProcedure'''

class PickerTests(unittest.TestCase):
    def setUp(self):
        ss,cs,self.empty,self.ref=scopes();kind=ss.descriptor(1)
        self.server=ReplicatedFormServer(SOURCE,{},handlers=(),attributes=(BSLFormAttribute('Product',kind),),
            tables=(FormTableSchema('Lines',(FormTableColumn('Product',kind),)),),
            reference_scope=ss,bindings={'OnCreateAtServer':'Create'})
        self.server.session.form._tables['lines']._replace_rows(((1,(self.empty,)),),1)
        self.client=ReplicatedFormSession('',self.server.exchange,handlers=(),reference_scope=cs);self.client.open()
        self.db=uuid4();self.key=CatalogKey(self.db,self.ref.value_type.metadata_uuid,self.ref.reference_uuid)
        self.overflow=False;self.deleted=False;self.views_closed=0
        test=self
        class View:
            database_id=test.db
            def scan_catalog_values(self,*args):
                return CatalogValuePage((CatalogValueRow(test.key,('P1','Product')),),'a'*32 if test.overflow else None)
            def read_catalog(self,key):return None if test.deleted else SimpleNamespace(deletion_mark=False)
            def close(self):test.views_closed+=1
        manager=SimpleNamespace(_schema=SimpleNamespace(identity=self.key.catalog_id,name='Products',code_length=8,description_length=80),
            _view=View,_ref=lambda identity:self.ref)
        self.server.session._reference_managers={1:manager}
        self.owned=SimpleNamespace(object=object(),pending_commit=False,pending_refresh=False,verify_source=lambda:None)
        self.choice=ConfigurationReferenceChoice(SimpleNamespace(reference_slots=(('Product','',1),('Lines','Product',1))),self.server,self.owned)

    def execute(self,action):
        self.choice.pending=action;self.server.session._busy=True
        try:return self.choice.execute(self.server.session)
        finally:self.server.session._busy=False

    def begin(self,table=False):
        self.assertEqual(self.execute({'action':'begin','control':'LinesTable' if table else 'ProductField',
            'row':1 if table else None,'column':'Product' if table else None}),'opened')
        return self.choice.projection()

    def test_begin_scan_closed_and_opaque_projection(self):
        p=self.begin();self.assertEqual(self.views_closed,1);self.assertTrue(self.choice.active)
        self.assertNotIn(str(self.key.record_id),str(p));self.assertNotIn(str(self.db),str(p))
        self.assertEqual(set(p),{'ticket','control','row','column','title','code','rows','error','navigation'})
        p['rows'].clear();self.assertEqual(len(self.choice.projection()['rows']),1)

    def test_apply_header_then_clear_and_replay_rejected(self):
        p=self.begin();action={'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']}
        self.assertEqual(self.execute(action),'applied');self.assertFalse(self.choice.active)
        self.assertIs(self.server.session.form._data['product'],self.ref)
        self.assertEqual(self.choice.changed_control,{'control':'ProductField','row':None,'column':None})
        with self.assertRaises(ValueError):self.execute(action)
        self.assertIsNone(self.choice.changed_control)
        self.assertEqual(self.execute({'action':'clear','control':'ProductField','row':None,'column':None}),'cleared')
        self.assertTrue(self.server.session.form._data['product'].is_empty())

    def test_table_apply_uses_live_row_identity(self):
        p=self.begin(True)
        self.assertEqual(self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']}),'applied')
        self.assertIs(self.server.session.form._tables['lines']._by_id[1]._data['product'],self.ref)
        self.assertTrue(self.server.session.form._data['product'].is_empty())

    def test_cancel_keeps_value_and_emits_no_change(self):
        p=self.begin();self.assertEqual(self.execute({'action':'cancel','ticket':p['ticket']}),'cancelled')
        self.assertIsNone(self.choice.changed_control);self.assertTrue(self.server.session.form._data['product'].is_empty())

    def test_overflow_is_empty_explicit_not_truncated(self):
        with patch('yadinassi.reference_choice_pages.MAX_ROWS',0):p=self.begin()
        self.assertEqual(p['rows'],[]);self.assertEqual(p['error'],'snapshot_limit');self.assertIsNone(p['navigation'])
        self.overflow=False;self.execute({'action':'filter','ticket':p['ticket'],'code':'P1'})
        self.assertEqual(len(self.choice.projection()['rows']),1);self.assertIsNone(self.choice.projection()['error'])

    def test_filter_invalidates_old_choice_tokens(self):
        p=self.begin();self.execute({'action':'filter','ticket':p['ticket'],'code':'P1'})
        with self.assertRaises(ValueError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        self.assertTrue(self.choice.active)

    def test_deleted_target_rechecked_without_assignment(self):
        p=self.begin();self.deleted=True
        with self.assertRaises(BackendError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        self.assertTrue(self.server.session.form._data['product'].is_empty());self.assertTrue(self.choice.active)
        self.assertEqual(self.views_closed,2)

    def test_deleted_row_and_changed_owner_cannot_apply(self):
        p=self.begin(True);table=self.server.session.form._tables['lines'];table._replace_rows((),1)
        with self.assertRaises(ValueError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        self.execute({'action':'cancel','ticket':p['ticket']})
        p=self.begin();self.owned.object=object()
        with self.assertRaises(ValueError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})

    def test_hidden_disabled_readonly_and_pending_block_choice(self):
        item=self.server.session.form.items._values['productfield']
        for flag,value in [('visible',False),('enabled',False),('read_only',True)]:
            old=getattr(item,flag);setattr(item,flag,value)
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.begin()
            setattr(item,flag,old)
        for flag in ('pending_commit','pending_refresh'):
            setattr(self.owned,flag,True)
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.begin()
            setattr(self.owned,flag,False)

    def test_preflight_failure_preserves_value_ticket_and_row_handles(self):
        p=self.begin(True);table=self.server.session.form._tables['lines'];row=table._by_id[1]
        with patch('yadinassi.configuration_reference_choice.encode_line',side_effect=ValueError('budget')):
            with self.assertRaises(ValueError):self.execute({'action':'apply','ticket':p['ticket'],'choice':p['rows'][0]['choice']})
        self.assertIs(table._by_id[1],row);self.assertTrue(row._data['product'].is_empty())
        self.assertTrue(self.choice.active);self.assertIsNone(self.choice.changed_control)
