"""Authored bounded application-service contracts; native replay is separate."""
from decimal import Decimal
from unittest import mock
import unittest
from configuration_runtime_fixture import module_files,SERVER
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.errors import BSLRuntimeError
from yadinassi.runtime import Interpreter
from yadinassi import temporary_storage as storage

SOURCE='''Function Put(Val Value,Val Owner=Undefined) Export If Owner=Undefined Then Owner=New UUID; EndIf; Return PutToTempStorage(Value,Owner); EndFunction
Function Get(Val Address) Export Return GetFromTempStorage(Address); EndFunction
Procedure Delete(Val Address) Export DeleteFromTempStorage(Address); EndProcedure
Function IsAddress(Val Address) Export Return IsTempStorageURL(Address); EndFunction'''

class ApplicationTemporaryStorageTests(unittest.TestCase):
    def app(self,source=SOURCE,application=''):
        app=ConfigurationApplication.from_files(module_files((('Store',source,SERVER),),application=application),output=lambda value:None)
        self.addCleanup(lambda:app.close(force=True));app.start();return app
    def put(self,app,value='"first"'):
        return app.execute('Store.Put('+value+')')
    def get(self,app,address):
        return app.execute('Store.Get("'+address+'")')
    def test_scalar_roundtrip_and_recognize(self):
        app=self.app();address=self.put(app)
        self.assertEqual(self.get(app,address),'first');self.assertTrue(app.execute('Store.IsAddress("'+address+'")'))
        self.assertFalse(app.execute('Store.IsAddress("not-an-address")'))
    def test_same_context_put_and_get_preserve_collection_alias(self):
        extra='''Function Probe() Export
V=New Array;V.Add("before");Address=PutToTempStorage(V,New UUID);V[0]="after";
First=GetFromTempStorage(Address);First[0]="changed";Return GetFromTempStorage(Address)[0];EndFunction'''
        self.assertEqual(self.app(SOURCE+'\n'+extra).execute('Store.Probe()'),'changed')
    def test_replacement_keeps_address(self):
        app=self.app();address=self.put(app)
        self.assertEqual(app.execute('Store.Put("second","'+address+'")'),address)
        self.assertEqual(self.get(app,address),'second');self.assertEqual(len(app.temporary_storage._entries),1)
    def test_failed_replacement_keeps_value_and_accounting(self):
        app=self.app();address=self.put(app);before=(app.temporary_storage._units,app.temporary_storage._nodes)
        with mock.patch.object(storage,'capture',side_effect=ValueError('unsupported')):
            with self.assertRaises(BSLRuntimeError):app.execute('Store.Put("bad","'+address+'")')
        self.assertEqual(self.get(app,address),'first');self.assertEqual(before,(app.temporary_storage._units,app.temporary_storage._nodes))
    def test_entry_quota_and_replacement(self):
        app=self.app()
        with mock.patch.object(storage,'MAX_ENTRIES',1):
            address=self.put(app)
            with self.assertRaises(BSLRuntimeError):self.put(app)
            app.execute('Store.Put("new","'+address+'")')
        self.assertEqual(self.get(app,address),'new')
    def test_aggregate_byte_quota_atomic(self):
        app=self.app();address=self.put(app);before=app.temporary_storage._units
        with mock.patch.object(storage,'MAX_RETAINED_UNITS',before):
            with self.assertRaises(BSLRuntimeError):self.put(app)
        self.assertEqual(app.temporary_storage._units,before);self.assertEqual(self.get(app,address),'first')
    def test_aggregate_node_quota_atomic(self):
        app=self.app();address=self.put(app);before=app.temporary_storage._nodes
        with mock.patch.object(storage,'MAX_SNAPSHOT_NODES',before):
            with self.assertRaises(BSLRuntimeError):self.put(app)
        self.assertEqual(app.temporary_storage._nodes,before);self.assertEqual(self.get(app,address),'first')
    def test_delete_releases_retained_units(self):
        app=self.app();address=self.put(app);app.execute('Store.Delete("'+address+'")')
        self.assertIsNone(self.get(app,address));self.assertEqual(app.temporary_storage._units,0)
        app.execute('Store.Delete("'+address+'")');self.assertTrue(app.execute('Store.IsAddress("'+address+'")'))
    def test_another_application_cannot_read_or_replace(self):
        app=self.app();address=self.put(app);other=self.app();self.assertIsNone(self.get(other,address))
        with self.assertRaises(BSLRuntimeError):other.execute('Store.Put("foreign","'+address+'")')
        self.assertEqual(self.get(app,address),'first')
    def test_close_clears_storage_and_invalidates_handles(self):
        app=self.app();self.put(app);store=app.temporary_storage;app.close(force=True)
        self.assertFalse(store._entries);self.assertEqual(store._units,0)
        with self.assertRaises(ValueError):store.authorize(app.interpreter)
    def test_client_denial_precedes_argument_effects(self):
        app=self.app(application='Function SideEffect() Export Raise "should-not-run"; EndFunction')
        with self.assertRaisesRegex(BSLRuntimeError,'active server'):
            app.execute('PutToTempStorage(SideEffect(),New UUID)')
    def test_standalone_cannot_create_ambient_storage(self):
        interpreter=Interpreter(output=lambda value:None);self.addCleanup(interpreter.close)
        with self.assertRaisesRegex(BSLRuntimeError,'explicit application'):
            interpreter.execute('PutToTempStorage("v",New UUID)')
    def test_unknown_owner_fails_closed(self):
        app=self.app()
        with self.assertRaises(BSLRuntimeError):app.execute('Store.Put("v",42)')
        self.assertFalse(app.temporary_storage._entries)
    def test_invalid_address_not_coerced(self):
        app=self.app()
        for value in ['42','"invalid"']:
            with self.assertRaises(BSLRuntimeError):app.execute('Store.Get('+value+')')
    def test_application_failure_releases_startup_values(self):
        files=module_files((('Store',SOURCE,SERVER),),application='Procedure BeforeStart(Cancel) Store.Put("v"); Raise "failed"; EndProcedure')
        app=ConfigurationApplication.from_files(files,output=lambda value:None)
        with self.assertRaises(BSLRuntimeError):app.start()
        self.assertEqual(app.state,'failed');self.assertFalse(app.temporary_storage._entries);self.assertTrue(app.temporary_storage._closed)

    def test_native_closed_profile_replay_and_explicit_deferred_owner_forms(self):
        import hashlib,json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        raw=(root/'tests/fixtures/native_temporary_storage_43056863128.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'0f475f9e8184890bdfa7f0d3e676970035586f7948365b0a1067275ba91486e7')
        source=(root/'scripts/temporary_storage_behavior/observe.bsl').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'a5d1cdce77f24f6801a55328812fc442c3978e5daae13fdebef807b355f520e7')
        declarations=source.decode().split('For CaseNo = 1 To 16 Do')[0]
        declarations+='\nFunction Run(Val CaseNo) Export Stage="read"; Return ObserveCase(CaseNo,Stage); EndFunction'
        app=self.app(declarations);expected=json.loads(raw)
        for number in range(1,17):
            with self.subTest(case=number):
                expression='Store.Run('+str(number)+')'
                if number==11:
                    self.assertEqual(expected[number-1],'without-owner')
                    with self.assertRaises(BSLRuntimeError):app.execute(expression)
                elif number in (12,15):
                    self.assertEqual(expected[number-1],'stored' if number==12 else 'stored:empty-owner')
                    self.assertEqual(app.execute(expression),'error')
                else:self.assertEqual(app.execute(expression),expected[number-1])
