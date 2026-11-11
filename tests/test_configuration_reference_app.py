"""Real owned process reference selection; UI never supplies a record UUID."""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from test_configuration_reference_profile import sources
from yadinassi.catalogs import BSLCatalogs
from yadinassi.database_context import SQLiteDBContext
from yadinassi.metadata import BSLCatalogMetadataCollection, BSLMetadata
from yadinassi.documents import BSLDocuments
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.configuration_app import ConfigurationProcess, ConfigurationController, PROTOCOL, load_application


class ReferenceApplicationTests(unittest.TestCase):
    def setUp(self):
        self.setup_application(sources())

    def setup_application(self, files):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)/'source';self.root.mkdir();self.files=files
        for path,raw in self.files.items():
            target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        self.path=Path(temporary.name)/'db.sqlite'
        SQLiteCatalogBackend.create_reference_application(self.path,self.files).close()
        with closing(SQLiteDBContext(self.path)) as context:
            catalogs=BSLCatalogs(BSLCatalogMetadataCollection(context),context)
            category=catalogs.get_index('Categories').create_item();category.set_member('Code','C1');category.set_member('Description','Category One');category.write()
            product=catalogs.get_index('Products').create_item();product.set_member('Code','P1');product.set_member('Description','Product One');product.write()
            self.category_id=category.get_member('Ref').reference_uuid
            self.product_id=product.get_member('Ref').reference_uuid
        self.process=ConfigurationProcess(self.root,self.path,reference_application=True);self.addCleanup(self.process.close)
        self.app=ConfigurationController(load_application(self.root,reference_application=True),self.process.exchange,reference_application=True)
        self.addCleanup(self.app.close);self.rpc('hello',protocol=PROTOCOL)

    def rpc(self,method,**params):
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
        self.assertIsNone(result['error'],result)
        return result

    def open(self,name):
        return self.rpc('open',entry=self.app.names[name.casefold()],request=name)['session']

    def event(self,sid,event,**params):
        result=self.rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
            'event':event,'revision':self.app.sessions[sid][0].session.revision,**params}})
        self.assertIsNone(result['form']['result']['error']);return result

    def reference(self,sid,action):
        return self.rpc('reference',session=sid,revision=self.app.sessions[sid][0].session.revision,action=action)

    def choose(self,sid,control,row=None,column=None):
        result=self.reference(sid,{'action':'begin','control':control,'row':row,'column':column})
        choice=result['state']['choice'];self.assertTrue(choice['rows'])
        self.assertNotIn(str(self.product_id),str(choice));self.assertNotIn(str(self.category_id),str(choice))
        return self.reference(sid,{'action':'apply','ticket':choice['ticket'],'choice':choice['rows'][0]['choice']})

    def test_startup_and_reference_card_opens(self):
        sid=self.open('Catalog.Products.Form.Card');form=self.app.sessions[sid][0]._snapshot()
        value=next(item['value'] for item in form['items'] if item['name']=='CategoryInput')
        self.assertEqual(value['type'],'FormCatalogRef');self.assertIsNone(value['key']);self.assertEqual(value['text'],'')

    def test_catalog_choose_save_and_typed_storage(self):
        sid=self.open('Catalog.Products.Form.Card')
        self.event(sid,'change',control='CodeInput',value={'type':'String','value':'P2'})
        self.event(sid,'change',control='DescriptionInput',value={'type':'String','value':'Product Two'})
        result=self.choose(sid,'CategoryInput');self.assertIsNone(result['state']['choice'])
        self.event(sid,'command',control='SaveButton')
        with closing(SQLiteDBContext(self.path)) as context:
            manager=BSLCatalogs(BSLCatalogMetadataCollection(context),context).get_index('Products')
            view=manager._view()
            try:
                cards=view.select_catalog(manager._schema.identity)
            finally:view.close()
            card=next(c for c in cards if c.code=='P2')
            obj=manager._get_object(manager._ref(card.key.record_id))
            self.assertEqual(obj.get_member('Category').reference_uuid,self.category_id)

    def test_cancel_preserves_and_clear_assigns_typed_empty(self):
        sid=self.open('Catalog.Products.Form.Card');self.choose(sid,'CategoryInput')
        initial=next(i['value'] for i in self.app.sessions[sid][0]._snapshot()['items'] if i['name']=='CategoryInput')
        p=self.reference(sid,{'action':'begin','control':'CategoryInput','row':None,'column':None})['state']['choice']
        self.reference(sid,{'action':'cancel','ticket':p['ticket']})
        current=next(i['value'] for i in self.app.sessions[sid][0]._snapshot()['items'] if i['name']=='CategoryInput')
        self.assertEqual(initial,current)
        self.reference(sid,{'action':'clear','control':'CategoryInput','row':None,'column':None})
        current=next(i['value'] for i in self.app.sessions[sid][0]._snapshot()['items'] if i['name']=='CategoryInput')
        self.assertIsNone(current['key'])

    def test_active_picker_allows_retained_snapshot(self):
        sid=self.open('Catalog.Products.Form.Card')
        self.reference(sid,{'action':'begin','control':'CategoryInput','row':None,'column':None})
        for method,params in [('form.snapshot',{}),('form.hello',{'protocol':'yadinassi-form-ui/1'})]:
            result=self.rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':method,'params':params})
            self.assertIsNotNone(result['state']['choice'])

    def test_document_header_and_line_choice(self):
        sid=self.open('Document.Orders.Form.Card');self.choose(sid,'CategoryInput')
        self.event(sid,'command',control='NewLineButton')
        table=next(i for i in self.app.sessions[sid][0]._snapshot()['items'] if i['kind']=='table')
        self.choose(sid,table['name'],table['rows'][0]['id'],'Product')
        self.event(sid,'command',control='WriteButton')
        with closing(SQLiteDBContext(self.path)) as context:
            metadata=BSLMetadata(context);catalogs=BSLCatalogs(metadata._catalogs,context)
            manager=BSLDocuments(metadata._documents,context,catalogs).get_index('Orders')
            view=manager._view()
            try:
                from yadinassi.document_backend import DocumentSelection
                card=view.select_documents(manager._schema.identity,DocumentSelection())[0]
                stored=view.read_document(card.key)
            finally:view.close()
            self.assertEqual(stored.values[-1].record_id,self.category_id)
            self.assertEqual(stored.tabular_sections[0].rows[0].values[0].record_id,self.product_id)

    def test_reference_table_callback_uses_changed_row_once(self):
        sid=self.open('Document.Orders.Form.Card')
        for _ in range(2): self.event(sid,'command',control='NewLineButton')
        session=self.app.sessions[sid][0].session
        item=session.form.items._values['linestable']
        first,second=(row['id'] for row in next(i for i in self.app.sessions[sid][0]._snapshot()['items'] if i['kind']=='table')['rows'])
        self.event(sid,'select',control='LinesTable',row=first)
        invoked=[];original=session._invoke
        def invoke(handler,side,args):
            if args==[item]:
                invoked.append(item.current_row)
                item.get_member('CurrentData').set_member('Label','Changed row')
            return original(handler,side,args)
        session._invoke=invoke
        self.choose(sid,'LinesTable',second,'Product')
        self.assertEqual(invoked,[second])
        self.assertEqual(item._table()._lookup_id(first)._data['label'],'New line')
        self.assertEqual(item._table()._lookup_id(second)._data['label'],'Changed row')
        self.event(sid,'select',control='LinesTable',row=first)
        self.reference(sid,{'action':'clear','control':'LinesTable','row':second,'column':'Product'})
        self.assertEqual(invoked,[second,second])
        self.assertEqual(item.current_row,second)

    def test_callback_error_preserves_reference_but_discards_queued_opens(self):
        sid=self.open('Catalog.Products.Form.Card');session=self.app.sessions[sid][0].session
        def failed(handler,side,args):
            self.app._application_open_form('Catalog.Categories.Form.Card')
            raise ValueError('callback failed after known apply')
        session._invoke=failed
        choice=self.reference(sid,{'action':'begin','control':'CategoryInput','row':None,'column':None})['state']['choice']
        before=set(self.app.sessions)
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.reference','params':{
            'session':sid,'revision':session.revision,
            'action':{'action':'apply','ticket':choice['ticket'],'choice':choice['rows'][0]['choice']}}})['result']
        self.assertEqual(result['error'],'reference_refused')
        self.assertFalse(result['state']['uncertain']);self.assertIsNone(result['state']['choice'])
        self.assertFalse(self.app.pending);self.assertEqual(set(self.app.sessions),before)
        value=next(i['value'] for i in result['form']['result']['state']['items'] if i['name']=='CategoryInput')
        self.assertEqual(value['text'],'Category One');self.assertIsNotNone(value['key'])

    def test_reference_callback_commonmodule_messages_are_event_local(self):
        self.app.close();self.process.close()
        files=sources()
        key='Catalogs/Products/Forms/Card/Ext/Form/Module.bsl'
        files[key]=files[key].replace(b'Procedure Changed(Element)',b'Procedure Changed(Element)\n Tools.Report();')
        files['CommonModules/Tools/Ext/Module.bsl']+=b'\nProcedure Report() Export Message("Reference changed"); EndProcedure'
        self.setup_application(files)
        sid=self.open('Catalog.Products.Form.Card');initial=list(self.app.application_messages)
        result=self.choose(sid,'CategoryInput')
        self.assertEqual(result['form']['result']['state']['messages'],['Reference changed'])
        result=self.reference(sid,{'action':'clear','control':'CategoryInput','row':None,'column':None})
        self.assertEqual(result['form']['result']['state']['messages'],['Reference changed'])
        self.assertEqual(self.app.application_messages,initial)

    def test_reference_callback_write_refreshes_list_even_after_later_error(self):
        self.app.close();self.process.close();files=sources()
        key='Catalogs/Products/Forms/Card/Ext/Form/Module.bsl'
        callback=b'''Procedure Changed(Element)
 If Element.Name = "CategoryInput" Then
  SelectedCategory = Object.Category;
  Object.Description = "Saved from reference callback";
  If SelectedCategory.IsEmpty() Then Object.Description = "Cleared and saved"; EndIf;
  SaveAtServer();
  If SelectedCategory.IsEmpty() Then Raise "after saved"; EndIf;
 EndIf;'''
        files[key]=files[key].replace(b'Procedure Changed(Element)',callback)
        self.setup_application(files)
        entry=self.app.names['catalog.products.form.card'];self.rpc('catalog',entry=entry)
        sid=self.open('Catalog.Products.Form.Card');self.event(sid,'change',control='CodeInput',value={'type':'String','value':'P2'})
        result=self.choose(sid,'CategoryInput')
        row=next(r for r in result['state']['catalog']['rows'] if r['code']=='P2')
        self.assertEqual(row['description'],'Saved from reference callback')
        session=self.app.sessions[sid][0].session
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.reference','params':{
            'session':sid,'revision':session.revision,
            'action':{'action':'clear','control':'CategoryInput','row':None,'column':None}}})['result']
        self.assertEqual(result['error'],'reference_refused');self.assertFalse(result['state']['uncertain'])
        row=next(r for r in result['state']['catalog']['rows'] if r['code']=='P2')
        self.assertEqual(row['description'],'Cleared and saved')
