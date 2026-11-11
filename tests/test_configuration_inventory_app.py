"""Stock source-granted browser controller, real replicas and stored-source entry."""
from contextlib import closing
from pathlib import Path
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.configuration_inventory_application import import_inventory_application, PROFILE, validated_core
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import BackendError
from yadinassi.document_backend import DocumentSelection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, ConfigurationProcess, load_application, PROTOCOL
from yadinassi.ui.protocol import encode_line, decode_line, encode_value
from yadinassi.ui.database_launch import binding, verify_binding, main as launch_main
from inventory_application_fixture import source, EXAMPLE


class InventoryApplicationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'stock.sqlite'
        self.config=import_inventory_application(source(),inventory_runtime=PROFILE)
        with closing(SQLiteDBContext.create_inventory_application(self.path,self.config)) as context:
            with closing(Interpreter(database_context=context,output=lambda value:None)) as vm:
                vm.execute('P=Catalogs.Products.CreateItem();P.Code="P1";P.Description="Product";P.Write();'
                    'W=Catalogs.Warehouses.CreateItem();W.Code="W1";W.Description="Warehouse";W.Write();')
        forms=load_application(EXAMPLE,inventory_application=True)
        self.broker=ConfigurationBroker(forms,self.path,inventory_application=True)
        self.addCleanup(self.broker.close)
        def exchange(raw):
            request=decode_line(raw)
            result=self.broker.exchange({k:request[k] for k in ('operation','session','payload')})
            return encode_line({'id':request['id'],'session':request['session'],'result':result,'error':None})
        self.app=ConfigurationController(forms,exchange,inventory_application=True)
        self.addCleanup(self.app.close)
        self.rpc('hello',protocol=PROTOCOL)

    def rpc(self,method,**params):
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
        self.assertIsNone(result['error'],result)
        return result

    def open(self,name,request=None,record=None):
        entry=self.app.names[name.casefold()]
        result=self.rpc('open' if record is None else 'openRecord',entry=entry,request=request or name,
            **({} if record is None else {'record':record}))
        self.assertIsNotNone(result['session'],result)
        return result['session']

    def event(self,sid,event='command',**params):
        if event in ('change','cell'):params['value']=encode_value(params['value'])
        result=self.rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
            'event':event,'revision':self.app.sessions[sid][0].session.revision,**params}})
        self.assertIsNone(result['form']['result']['error'],result)
        return result

    def choose(self,sid,control,row=None,column=None):
        def choice(action):return self.rpc('reference',session=sid,
            revision=self.app.sessions[sid][0].session.revision,action=action)
        result=choice({'action':'begin','control':control,'row':row,'column':column})['state']['choice']
        self.assertTrue(result['rows'])
        return choice({'action':'apply','ticket':result['ticket'],'choice':result['rows'][0]['choice']})

    def prepare(self,name='Receipt',quantity=Decimal(10)):
        sid=self.open('Document.'+name+'.Form.Card')
        self.event(sid,'change',control='NumberInput',value=name+'-1')
        self.choose(sid,'WarehouseInput')
        self.event(sid,control='AddLineButton')
        table=next(i for i in self.app.sessions[sid][0]._snapshot()['items'] if i['kind']=='table')
        row=table['rows'][0]['id'];self.choose(sid,'LinesTable',row,'Product')
        self.event(sid,'cell',control='LinesTable',row=row,column='Quantity',value=quantity)
        self.event(sid,'cell',control='LinesTable',row=row,column='Amount',value=Decimal(100))
        return sid

    def cards(self,name='Receipt'):
        with closing(SQLiteCatalogBackend(self.path)) as backend:
            schema=next(s for s in self.config.documents if s.name==name)
            with closing(backend.begin_document_read()) as view:
                return tuple(view.read_document(c.key) for c in view.select_documents(schema.identity,DocumentSelection()))

    def test_entries_distinguish_catalogs_and_posting_documents(self):
        self.assertIsNone(self.broker.application);self.assertIsNone(self.app.application)
        for definition in self.broker.definitions.values():
            if definition.catalog_schema is not None:
                self.assertFalse(definition.posting_application)
                self.assertNotIn('Posted',dict(definition.object_fields))
                self.assertFalse(any(b.name=='YadinassiPostingSync' for b in definition.program.server_bindings))
        self.assertEqual([x['kind'] for x in self.app._state()['entries']].count('catalog-object'),2)
        self.assertEqual([x['kind'] for x in self.app._state()['entries']].count('posting-document'),2)

    def test_real_catalog_form_save_refreshes_list(self):
        entry=self.app.names['catalog.products.form.card'];self.rpc('catalog',entry=entry)
        sid=self.open('Catalog.Products.Form.Card')
        self.event(sid,'change',control='CodeInput',value='P2')
        self.event(sid,'change',control='DescriptionInput',value='New product')
        self.event(sid,control='SaveButton')
        self.assertEqual(len(self.app.catalog['rows']),2)
        self.event(sid,'close');self.assertNotIn(sid,self.app.sessions)

    def test_document_reference_choose_and_write(self):
        sid=self.prepare();self.event(sid,control='WriteButton')
        self.assertEqual(self.app.posting_states[sid]['state'],'saved',self.app.posting_states[sid])
        card=self.cards()[0];self.assertFalse(card.posted)
        self.assertEqual(card.tabular_sections[0].rows[0].values[1],Decimal(10))
        self.assertEqual(self.app.posting_states[sid]['state'],'saved')

    def test_post_then_undo_reuses_typed_document_image(self):
        sid=self.prepare();self.event(sid,control='PostButton');self.assertTrue(self.cards()[0].posted)
        self.event(sid,control='UndoPostingButton');self.assertFalse(self.cards()[0].posted)

    def test_posted_image_closes_without_losing_persistence(self):
        sid=self.prepare();self.event(sid,control='PostButton');self.event(sid,'close')
        self.assertNotIn(sid,self.app.sessions);self.assertTrue(self.cards()[0].posted)

    def test_issue_refusal_does_not_claim_posted(self):
        sid=self.prepare('Issue',Decimal(100));self.event(sid,control='PostButton')
        self.assertEqual(self.cards('Issue'),())
        self.assertEqual(self.app.posting_states[sid]['state'],'rejected')

    def test_active_picker_cannot_dispatch_post(self):
        sid=self.open('Document.Receipt.Form.Card')
        self.rpc('reference',session=sid,revision=self.app.sessions[sid][0].session.revision,
            action={'action':'begin','control':'WarehouseInput','row':None,'column':None})
        with self.assertRaises(ValueError):self.event(sid,control='PostButton')
        self.assertEqual(self.cards(),())

    def test_catalog_session_cannot_call_posting_endpoint(self):
        sid=self.open('Catalog.Products.Form.Card')
        with self.assertRaises(ValueError):self.broker.exchange({'operation':'posting','session':sid,
            'payload':{'action':'execute','command':'Post','receipt':None,'form':{}}})
        self.assertEqual(self.cards(),())

    def test_new_document_creation_is_clean(self):
        sid=self.open('Document.Receipt.Form.Card');self.event(sid,'close')
        self.assertNotIn(sid,self.app.sessions)

    def test_dirty_document_close_refused_by_authoritative_image(self):
        sid=self.prepare()
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.form','params':{
            'session':sid,'request':{'jsonrpc':'2.0','id':1,'method':'form.event','params':{
                'event':'close','revision':self.app.sessions[sid][0].session.revision}}}})['result']
        self.assertEqual(result['error'],'save_recovery_required');self.assertIn(sid,self.app.sessions)

    def test_stored_source_launch_snapshot_is_exact_inventory_grant(self):
        with closing(SQLiteCatalogBackend(self.path,read_only=True)) as backend:
            snapshot=backend.launch_snapshot()
            self.assertEqual(snapshot.route,'inventory');self.assertEqual(snapshot.profile,PROFILE)
            self.assertEqual({f.path:f.content for f in snapshot.files},source())
            self.assertEqual(verify_binding(backend,binding(snapshot),source(),route='inventory'),snapshot)

    def test_unified_launcher_uses_stored_source_without_external_directory(self):
        def run(argv):
            self.assertIn('--inventory-application',argv);self.assertIn('--launch-binding',argv)
            root=Path(argv[0]);self.assertTrue(root.is_dir())
            self.assertEqual({p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()},source())
            return 0
        with patch('yadinassi.ui.configuration_app.main',side_effect=run) as launched:
            self.assertEqual(launch_main(['--f',str(self.path)]),0);launched.assert_called_once()

    def test_core15_database_still_has_no_ui_authority(self):
        other=self.path.with_name('core.sqlite')
        with closing(SQLiteCatalogBackend.create_inventory(other,validated_core(self.config))) as backend:
            with self.assertRaises(BackendError):backend.launch_snapshot()

    def test_explicit_profiles_cannot_combine(self):
        with self.assertRaises(ValueError):load_application(EXAMPLE,inventory_application=True,posting_application=True)

    def test_real_child_process_uses_inventory_profile(self):
        with closing(ConfigurationProcess(EXAMPLE,self.path,inventory_application=True)) as process:
            forms=load_application(EXAMPLE,inventory_application=True)
            with closing(ConfigurationController(forms,process.exchange,inventory_application=True)) as app:
                result=app.exchange({'jsonrpc':'2.0','id':1,'method':'application.hello','params':{'protocol':PROTOCOL}})['result']
                self.assertIsNone(result['error']);self.assertEqual(len(result['state']['entries']),4)


    def seed_saved_lines(self, count):
        with closing(SQLiteDBContext(self.path)) as context:
            with closing(Interpreter(database_context=context, output=lambda value:None)) as vm:
                vm.execute('D=Documents.Receipt.CreateDocument();D.Number="CAP";'
                    'D.Date=Date(2026,1,1);D.Warehouse=Catalogs.Warehouses.FindByCode("W1");'
                    'For I=1 To '+str(count)+' Do L=D.Lines.Add();'
                    'L.Product=Catalogs.Products.FindByCode("P1");L.Quantity=1;L.Amount=10;EndDo;D.Write();')
        entry=self.app.names['document.receipt.form.card']
        listing=self.rpc('catalog',entry=entry)['state']['catalog']
        return entry,listing['rows'][0]['key']

    def open_saved_result(self, entry, record, request='capacity-probe'):
        return self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.openRecord',
            'params':{'entry':entry,'record':record,'request':request}})['result']

    def test_oversized_saved_document_refuses_before_form_or_root_and_keeps_sibling(self):
        sid=self.open('Catalog.Warehouses.Form.Card')
        self.event(sid,'change',control='DescriptionInput',value='Authoritative sibling draft')
        revision=self.app.sessions[sid][0].session.revision
        entry,record=self.seed_saved_lines(52)
        before=self.path.read_bytes();allocated=self.broker.allocated
        from yadinassi.configuration_forms import FormDefinition
        create=FormDefinition.create_server
        with patch('yadinassi.inventory_application_sessions.InventoryRootOperations') as root, patch(
                'yadinassi.configuration_forms.FormDefinition.create_server',autospec=True,side_effect=create) as server:
            for request in ('capacity-probe','capacity-probe','another-capacity-probe'):
                result=self.open_saved_result(entry,record,request)
                self.assertEqual(result['error'],'form_capacity');self.assertIsNone(result['session'])
                self.assertFalse(result['state']['uncertain'])
            root.assert_not_called()
            self.assertTrue(all(call.kwargs.get('_validate_only') is True for call in server.call_args_list))
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.broker.allocated,allocated)
        self.assertEqual(self.app.sessions[sid][0].session.revision,revision)
        self.assertEqual(self.app.active,sid)
        self.assertEqual(len(self.cards()[0].tabular_sections[0].rows),52)
        projection=self.rpc('report',report='StockBalance',at='2026-11-12T00:00:00',start=None,end=None)
        self.assertEqual(projection['state']['report']['rows'],[])
        self.assertEqual(self.path.read_bytes(),before)
        self.open('Document.Issue.Form.Card',request='small-form-after-refusal')

    def test_saved_document_at_row_limit_opens_complete_same_revision(self):
        entry,record=self.seed_saved_lines(32);card=self.cards()[0]
        result=self.open_saved_result(entry,record)
        self.assertIsNone(result['error']);sid=result['session']
        self.assertEqual(self.broker.objects[sid].object._revision,card.revision)
        table=next(i for i in self.app.sessions[sid][0]._snapshot()['items'] if i['kind']=='table')
        self.assertEqual(len(table['rows']),32)
        self.event(sid,'close');self.assertFalse(self.app.uncertain)

    def test_open_preflight_preserves_unknown_failure_as_uncertain(self):
        from yadinassi.ui.local_app import LocalTransportError
        entry,record=self.seed_saved_lines(1)
        with patch('yadinassi.configuration_document._read_form_document',side_effect=ValueError('unknown failure')):
            with self.assertRaises(LocalTransportError):self.open_saved_result(entry,record)
        self.assertTrue(self.app.uncertain)

    def test_oversized_open_checks_new_context_exact_source_before_capacity(self):
        from yadinassi.ui.local_app import LocalTransportError
        entry,record=self.seed_saved_lines(52)
        original=self.broker._open_context
        def other_source():
            context=original()
            actual=context.backend.export_configuration
            context.backend.export_configuration=lambda:dict(actual(), **{'extra.bsl':b'// mismatched source'})
            return context
        with patch.object(self.broker,'_open_context',side_effect=other_source), patch(
                'yadinassi.configuration_document._read_form_document') as read:
            with self.assertRaises(LocalTransportError):self.open_saved_result(entry,record)
            read.assert_not_called()
        self.assertTrue(self.app.uncertain)

    def test_preflight_reuses_pinned_card_instead_of_rereading_after_admission(self):
        from yadinassi.configuration_document import _read_form_document
        entry,record=self.seed_saved_lines(1);card=self.cards()[0]
        def captured(context,definition,key):
            opened=_read_form_document(context,definition,key)
            # Any later read_document on this owner would substitute a different
            # snapshot. Metadata/source read leases remain permitted.
            begin=context.backend.begin_document_read
            def no_record_read():
                view=begin()
                view.read_document=lambda key:(_ for _ in ()).throw(AssertionError('unexpected record reread'))
                return view
            context.backend.begin_document_read=no_record_read
            return opened
        with patch('yadinassi.configuration_document._read_form_document',side_effect=captured):
            result=self.open_saved_result(entry,record)
        self.assertIsNone(result['error'])
        self.assertEqual(self.broker.objects[result['session']].object._revision,card.revision)

    def test_concurrent_growth_keeps_open_snapshot_and_rejects_stale_write(self):
        from yadinassi.configuration_document import _read_form_document
        from yadinassi.unique_identifiers import BSLUUID
        entry,record=self.seed_saved_lines(1)
        def grow_after_read(context,definition,key):
            opened=_read_form_document(context,definition,key)
            with closing(SQLiteDBContext(self.path)) as other:
                with closing(Interpreter(database_context=other,output=lambda value:None)) as vm:
                    vm.variables['savedkey']=BSLUUID(str(key.record_id))
                    vm.execute('D=Documents.Receipt.GetRef(SavedKey).GetObject();'
                        'L=D.Lines.Add();L.Product=Catalogs.Products.FindByCode("P1");'
                        'L.Quantity=2;L.Amount=20;D.Write();')
            return opened
        with patch('yadinassi.configuration_document._read_form_document',side_effect=grow_after_read):
            result=self.open_saved_result(entry,record)
        self.assertIsNone(result['error']);sid=result['session']
        self.assertEqual(len(self.broker.objects[sid].image().sections[0][1]),1)
        self.assertEqual(len(self.cards()[0].tabular_sections[0].rows),2)
        self.event(sid,control='WriteButton')
        self.assertEqual(self.app.posting_states[sid]['state'],'rejected')
        self.assertEqual(len(self.cards()[0].tabular_sections[0].rows),2)

    def test_oversized_open_checks_exact_profile_not_only_same_source(self):
        from yadinassi.ui.local_app import LocalTransportError
        entry,record=self.seed_saved_lines(52)
        original=self.broker._open_context
        def wrong_profile():
            context=original();context.backend.accumulation_configuration=validated_core(self.config)
            return context
        with patch.object(self.broker,'_open_context',side_effect=wrong_profile), patch(
                'yadinassi.configuration_document._read_form_document') as read:
            with self.assertRaises(LocalTransportError):self.open_saved_result(entry,record)
            read.assert_not_called()
        self.assertTrue(self.app.uncertain)

    def test_failed_cleanup_never_returns_safe_capacity(self):
        from yadinassi.ui.local_app import LocalTransportError
        entry,record=self.seed_saved_lines(52)
        original=self.broker._open_context
        def broken_close():
            context=original();close=context.close
            def fail():
                close();raise RuntimeError('cleanup failed')
            context.close=fail
            return context
        with patch.object(self.broker,'_open_context',side_effect=broken_close):
            with self.assertRaises(LocalTransportError):self.open_saved_result(entry,record)
        self.assertTrue(self.app.uncertain);self.assertEqual(self.broker.allocated,0)
