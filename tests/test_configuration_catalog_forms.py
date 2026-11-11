"""Declared XML object forms over a real profile-bound SQLite database."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.configuration_xml import import_catalog_forms_configuration
from yadinassi.form_program import compile_form_module
from yadinassi.invocation import _encode_scalar
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, PROTOCOL
from yadinassi.ui.protocol import decode_line, encode_line

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/configuration-catalog-forms'


def catalog_form_sources():
    return {p.relative_to(EXAMPLE).as_posix(): p.read_bytes() for p in EXAMPLE.rglob('*') if p.is_file()}


class ConfigurationCatalogFormIntegrationTests(unittest.TestCase):
    def setup_app(self, files=None):
        files = catalog_form_sources() if files is None else files
        imported = import_catalog_forms_configuration(files)
        configuration = load_configuration_forms(files, catalog_schemas=imported.catalogs)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'catalogs.sqlite'
        SQLiteCatalogBackend.create_catalog_forms(path, files).close()
        broker = ConfigurationBroker(configuration, path)
        self.addCleanup(broker.close)
        def exchange(raw):
            request = decode_line(raw)
            result = broker.exchange({key: request[key] for key in ('operation', 'session', 'payload')})
            return encode_line({'id': request['id'], 'session': request['session'], 'result': result, 'error': None})
        app = ConfigurationController(configuration, exchange)
        self.rpc(app, 'hello', protocol=PROTOCOL)
        return broker, app

    def rpc(self, app, method, **params):
        return app.exchange({'jsonrpc':'2.0', 'id':1, 'method':'application.'+method, 'params':params})['result']

    def entry(self, app, catalog='Products'):
        return app.names[('Catalog.'+catalog+'.Form.Card').casefold()]

    def create(self, app, catalog='Products'):
        return self.rpc(app, 'open', entry=self.entry(app,catalog), request=str(uuid4()))['session']

    def event(self, app, sid, event, control=None, value=None):
        session = app.sessions[sid][0].session
        params = {'event':event,'revision':session.revision}
        if event != 'close': params['control'] = control
        if event == 'change': params['value'] = _encode_scalar(value)
        return self.rpc(app,'form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':params})

    def change(self, app, sid, field, value):
        return self.event(app,sid,'change',field+'Input',value)

    def save(self, app, sid):
        return self.event(app,sid,'command','SaveButton')

    def fill(self, app, sid, code='P1', description='Product one'):
        self.change(app,sid,'Code',code)
        self.change(app,sid,'Description',description)

    def data(self, app, sid):
        return app.sessions[sid][0].session.form._data

    def test_two_declared_layouts_create_save_and_opaque_reopen(self):
        broker, app = self.setup_app()
        self.rpc(app,'catalog',entry=self.entry(app))
        sid = self.create(app)
        self.fill(app,sid,description='  Product one  ')
        self.change(app,sid,'Price',Decimal('25.50'))
        self.change(app,sid,'Active',True)
        result = self.save(app,sid)
        self.assertEqual(self.data(app,sid)['status'],'saved')
        self.assertFalse(self.data(app,sid)['dirty'])
        self.assertEqual(result['state']['catalog']['rows'][0]['description'],'Product one')
        key = result['state']['catalog']['rows'][0]['key']
        self.assertTrue(key.startswith('record-'))
        self.assertNotIn('41b52620',key)
        reopened = self.rpc(app,'openRecord',entry=self.entry(app),record=key,request='reopen')['session']
        self.assertEqual(broker.objects[reopened].values()['Price'],Decimal('25.50'))
        self.assertEqual(broker.objects[reopened].values()['Description'],'Product one')
        category = self.create(app,'Categories')
        self.fill(app,category,'C1','Category one'); self.save(app,category)
        self.assertEqual(self.data(app,category)['status'],'saved')
        self.assertNotEqual(app.sessions[category][0].session.form.title,app.sessions[sid][0].session.form.title)
        self.assertNotIn('Price',broker.objects[category].fields)

    def test_custom_bsl_commands_run_distinct_declared_behaviors(self):
        broker, app = self.setup_app()
        sid = self.create(app); self.fill(app,sid)
        self.change(app,sid,'Price',Decimal('100'))
        self.event(app,sid,'command','CustomButton'); self.save(app,sid)
        self.assertEqual(broker.objects[sid].values()['Price'],Decimal('90'))
        category=self.create(app,'Categories'); self.fill(app,category,'C1','  Category  ')
        self.event(app,category,'command','CustomButton'); self.save(app,category)
        self.assertEqual(broker.objects[category].values()['Description'],'Category')

    def test_form_refusal_is_not_object_write(self):
        broker, app = self.setup_app()
        sid=self.create(app); self.fill(app,sid,description='Form reject')
        self.save(app,sid)
        self.assertEqual(self.data(app,sid)['status'],'rejected')
        self.assertEqual(broker.objects[sid].error,'form_validation')
        self.assertTrue(broker.objects[sid].object.is_new())
        self.assertTrue(self.data(app,sid)['dirty'])
        self.assertEqual(self.rpc(app,'catalog',entry=self.entry(app))['state']['catalog']['rows'],[])

    def test_mandatory_object_module_refusal_survives_form_preparation(self):
        broker, app = self.setup_app()
        sid=self.create(app); self.fill(app,sid,description='Object reject')
        self.save(app,sid)
        self.assertEqual(broker.objects[sid].error,'object_validation')
        self.assertEqual(self.data(app,sid)['status'],'rejected')
        self.assertTrue(broker.objects[sid].object.is_new())

    def test_negative_price_refusal_can_be_corrected_without_reopening(self):
        broker, app = self.setup_app()
        sid=self.create(app); self.fill(app,sid)
        self.change(app,sid,'Price',Decimal('-1')); self.save(app,sid)
        self.assertEqual(broker.objects[sid].error,'form_validation')
        self.change(app,sid,'Price',Decimal('1')); self.save(app,sid)
        self.assertEqual(self.data(app,sid)['status'],'saved')

    def test_dirty_sibling_preserved_when_list_refreshes(self):
        broker, app = self.setup_app()
        self.rpc(app,'catalog',entry=self.entry(app))
        first=self.create(app); second=self.create(app)
        self.fill(app,first,'P1','First'); self.fill(app,second,'P2','Unsaved sibling')
        before=dict(self.data(app,second))
        result=self.save(app,first)
        self.assertEqual(self.data(app,second),before)
        self.assertTrue(broker.objects[second].object.is_new())
        self.assertEqual(len(result['state']['catalog']['rows']),1)
        self.assertEqual(result['state']['catalog']['rows'][0]['description'],'First')

    def test_rename_and_deletion_mark_refresh_list_behind_open_card(self):
        broker, app=self.setup_app(); self.rpc(app,'catalog',entry=self.entry(app))
        sid=self.create(app); self.fill(app,sid); first=self.save(app,sid)
        oldkey=first['state']['catalog']['rows'][0]['key']
        self.change(app,sid,'Description','Renamed'); self.change(app,sid,'DeletionMark',True)
        result=self.save(app,sid)
        self.assertIn(sid,app.sessions)
        row=result['state']['catalog']['rows'][0]
        self.assertEqual((row['key'],row['description'],row['deletionMark']),(oldkey,'Renamed',True))

    def test_dirty_close_refusal_and_saved_close(self):
        broker, app=self.setup_app(); sid=self.create(app)
        self.fill(app,sid); self.event(app,sid,'close')
        self.assertIn(sid,app.sessions)
        self.save(app,sid); self.event(app,sid,'close')
        self.assertNotIn(sid,app.sessions); self.assertNotIn(sid,broker.objects)

    def test_openform_from_client_opens_other_declared_object_form(self):
        broker, app=self.setup_app(); sid=self.create(app)
        result=self.event(app,sid,'command','CategoryButton')
        child=result['state']['active']
        self.assertNotEqual(child,sid)
        self.assertEqual(broker.objects[child].schema.name,'Categories')
        self.assertTrue(broker.objects[child].object.is_new())

    def test_crosscatalog_and_raw_record_keys_rejected(self):
        broker, app=self.setup_app(); self.rpc(app,'catalog',entry=self.entry(app))
        sid=self.create(app); self.fill(app,sid); result=self.save(app,sid)
        key=result['state']['catalog']['rows'][0]['key']
        self.rpc(app,'catalog',entry=self.entry(app,'Categories'))
        for entry, record in ((self.entry(app,'Categories'),key),(self.entry(app),str(uuid4()))):
            with self.subTest(record=record),self.assertRaises(ValueError):
                self.rpc(app,'openRecord',entry=entry,record=record,request='bad')

    def test_source_mismatch_rejected_before_any_form_lifecycle(self):
        broker, app=self.setup_app()
        files=catalog_form_sources()
        path='Catalogs/Products/Forms/Card/Ext/Form/Module.bsl'
        files[path]+=b'\n// different trusted source\n'
        imported=import_catalog_forms_configuration(files)
        other=ConfigurationBroker(load_configuration_forms(files,catalog_schemas=imported.catalogs),broker.database)
        self.addCleanup(other.close)
        other.exchange({'operation':'hello','session':'','payload':{'source':other.configuration.source_sha256}})
        result=other.exchange({'operation':'catalog','session':'','payload':{'entry':self.entry(app)}})
        self.assertEqual(result,{'error':'catalog_unavailable'})
        self.assertEqual(other.sessions,{})

    def test_object_projection_rejects_escape_shadow_and_nocontext(self):
        for source in ('&AtClient\nProcedure C()\nX=Object;\nEndProcedure',
                       '&AtClient\nProcedure C(Object)\nEndProcedure',
                       '&AtClient\nProcedure C()\nObject.Unknown=1;\nEndProcedure',
                       '&AtServerNoContext\nFunction F()\nReturn Object.Code;\nEndFunction'):
            with self.subTest(source=source),self.assertRaises(ValueError):
                compile_form_module(source,object_fields=('Code','Description','DeletionMark'))

    def test_object_xml_rejects_wrong_owner_and_unknown_path(self):
        key='Catalogs/Products/Forms/Card/Ext/Form.xml'
        for old,new in ((b'cfg:CatalogObject.Products',b'cfg:CatalogObject.Categories'),
                        (b'Object.Price',b'Object.Price.Length'),
                        (b'<MainAttribute>true</MainAttribute>',b'<MainAttribute>false</MainAttribute>'),
                        (b'<Type><v8:Type>cfg:CatalogObject.Products',b'<Type>text<v8:Type>cfg:CatalogObject.Products')):
            files=catalog_form_sources();files[key]=files[key].replace(old,new)
            with self.subTest(new=new),self.assertRaises(ValueError): import_catalog_forms_configuration(files)

    def test_catalog_dates_and_boolean_survive_real_save_reopen(self):
        from yadinassi.dates import BSLDate, TICKS_PER_SECOND
        broker,app=self.setup_app();self.rpc(app,'catalog',entry=self.entry(app))
        sid=self.create(app);self.fill(app,sid)
        date=BSLDate(86400*TICKS_PER_SECOND)
        self.change(app,sid,'AvailableDate',date);self.change(app,sid,'Active',True)
        result=self.save(app,sid)
        key=result['state']['catalog']['rows'][0]['key']
        other=self.rpc(app,'openRecord',entry=self.entry(app),record=key,request='date-reopen')['session']
        self.assertEqual(broker.objects[other].values()['AvailableDate'],date)
        self.assertIs(broker.objects[other].values()['Active'],True)

    def test_recovery_close_keeps_card_and_nested_snapshot_without_dispatch(self):
        broker, app = self.setup_app()
        self.rpc(app, 'catalog', entry=self.entry(app))
        sid = self.create(app)
        owned = broker.objects[sid]
        owned.pending_refresh = True
        session = app.sessions[sid][0].session
        before = session.revision
        reply = app.exchange({'jsonrpc':'2.0','id':73,'method':'application.form', 'params':{
            'session':sid,'request':{'jsonrpc':'2.0','id':19,'method':'form.event',
            'params':{'event':'close','revision':before}}}})
        self.assertEqual(reply['id'],73)
        result = reply['result']
        self.assertEqual(result['error'],'save_recovery_required')
        self.assertEqual(result['form']['id'],19)
        self.assertEqual(result['form']['result']['error'],'busy')
        self.assertEqual(session.revision,before)
        self.assertFalse(session.closed)
        self.assertFalse(app.uncertain)
        self.assertIn(sid,broker.objects)
        self.assertIsNotNone(result['state']['catalog'])
        owned.pending_refresh = False
        self.fill(app, sid)
        broker.record_keys = {(999, index): 'reserved-'+str(index) for index in range(4096)}
        self.save(app, sid)
        self.assertTrue(owned.pending_refresh)
        self.assertEqual(owned.save_state, 'committed')
        self.assertEqual(self.data(app, sid)['status'], 'committed')
        broker.record_keys.clear()
        self.save(app, sid)
        self.assertFalse(owned.pending_refresh)
        self.assertEqual(owned.save_state, 'saved')

    def test_normal_form_reply_preserves_distinct_outer_id(self):
        _, app = self.setup_app()
        sid = self.create(app)
        reply = app.exchange({'jsonrpc':'2.0','id':91,'method':'application.form', 'params':{
            'session':sid,'request':{'jsonrpc':'2.0','id':7,'method':'form.snapshot','params':{}}}})
        self.assertEqual(reply['id'],91)
        self.assertEqual(reply['result']['form']['id'],7)
