"""Bounded application storage contracts and the pinned native replay."""
from decimal import Decimal
from unittest import mock
import unittest
from configuration_runtime_fixture import module_files,SERVER
from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.runtime import Interpreter
from yadinassi.application import temporary_storage as storage

SOURCE='''Function Put(Val Value,Val Owner=Undefined) Export If Owner=Undefined Then Owner=New UUID; EndIf; Return PutToTempStorage(Value,Owner); EndFunction
Function Get(Val Address) Export Return GetFromTempStorage(Address); EndFunction
Procedure Delete(Val Address) Export DeleteFromTempStorage(Address); EndProcedure
Function IsAddress(Val Address) Export Return IsTempStorageURL(Address); EndFunction'''

class ApplicationTemporaryStorageTests(unittest.TestCase):
    def construct(self,files):
        files=dict(files)
        files.setdefault('Ext/ManagedApplicationModule.bsl',b'')
        app=SourceApplication(import_source(files),output=lambda value:None)
        self.addCleanup(app.close)
        return app

    def app(self,source=SOURCE,application=''):
        app=self.construct(module_files((('Store',source,SERVER),),application=application))
        app.start()
        return app
    def put(self,app,value='"first"'):
        return app.interpreter.execute('Store.Put('+value+')')
    def get(self,app,address):
        return app.interpreter.execute('Store.Get("'+address+'")')
    def test_scalar_roundtrip_and_recognize(self):
        app=self.app();address=self.put(app)
        self.assertEqual(self.get(app,address),'first');self.assertTrue(app.interpreter.execute('Store.IsAddress("'+address+'")'))
        self.assertFalse(app.interpreter.execute('Store.IsAddress("not-an-address")'))
    def test_same_context_put_and_get_preserve_collection_alias(self):
        extra='''Function Probe() Export
V=New Array;V.Add("before");Address=PutToTempStorage(V,New UUID);V[0]="after";
First=GetFromTempStorage(Address);First[0]="changed";Return GetFromTempStorage(Address)[0];EndFunction'''
        self.assertEqual(self.app(SOURCE+'\n'+extra).interpreter.execute('Store.Probe()'),'changed')
    def test_replacement_keeps_address(self):
        app=self.app();address=self.put(app)
        self.assertEqual(app.interpreter.execute('Store.Put("second","'+address+'")'),address)
        self.assertEqual(self.get(app,address),'second');self.assertEqual(len(app.temporary_storage._entries),1)
    def test_failed_replacement_keeps_value_and_accounting(self):
        app=self.app();address=self.put(app);before=(app.temporary_storage._units,app.temporary_storage._nodes)
        with mock.patch.object(storage,'capture',side_effect=ValueError('unsupported')):
            with self.assertRaises(BSLRuntimeError):app.interpreter.execute('Store.Put("bad","'+address+'")')
        self.assertEqual(self.get(app,address),'first');self.assertEqual(before,(app.temporary_storage._units,app.temporary_storage._nodes))
    def test_entry_quota_and_replacement(self):
        app=self.app()
        with mock.patch.object(storage,'MAX_ENTRIES',1):
            address=self.put(app)
            with self.assertRaises(BSLRuntimeError):self.put(app)
            app.interpreter.execute('Store.Put("new","'+address+'")')
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
        app=self.app();address=self.put(app);app.interpreter.execute('Store.Delete("'+address+'")')
        self.assertIsNone(self.get(app,address));self.assertEqual(app.temporary_storage._units,0)
        app.interpreter.execute('Store.Delete("'+address+'")');self.assertTrue(app.interpreter.execute('Store.IsAddress("'+address+'")'))
    def test_another_application_cannot_read_or_replace(self):
        app=self.app();address=self.put(app);other=self.app();self.assertIsNone(self.get(other,address))
        with self.assertRaises(BSLRuntimeError):other.interpreter.execute('Store.Put("foreign","'+address+'")')
        self.assertEqual(self.get(app,address),'first')
    def test_close_clears_storage_and_invalidates_handles(self):
        app=self.app();self.put(app);store=app.temporary_storage;app.close()
        self.assertFalse(store._entries);self.assertEqual(store._units,0)
        with self.assertRaises(ValueError):store.authorize(app.interpreter)
    def test_client_denial_precedes_argument_effects(self):
        app=self.app(application=('Var Effects; Function SideEffect() Export Effects=1; '
                                  'Raise "should-not-run"; EndFunction\nEffects=0;'))
        with self.assertRaisesRegex(BSLRuntimeError,'active server'):
            app.interpreter.execute('DeleteFromTempStorage(SideEffect())')
        self.assertEqual(app.interpreter.execute('Effects'),Decimal(0))
        self.assertFalse(app.temporary_storage._entries)
    def test_standalone_cannot_create_ambient_storage(self):
        interpreter=Interpreter(output=lambda value:None);self.addCleanup(interpreter.close)
        call = 'Saved=PutToTempStorage("v",New UUID);'
        source = 'temporary-storage.bsl'
        with self.assertRaises(BSLRuntimeError) as raised:
            interpreter.execute(f'Saved="old";\n{call}\nAfter=True;', source)
        error = raised.exception
        self.assertEqual((error.source, error.line, error.source_line), (source, 2, call))
        self.assertRegex(error.message.casefold(), r'temporary storage.*(?:requires|needs).*application')
        self.assertIsNone(interpreter._configuration_runtime)
        self.assertEqual(interpreter.variables, {'saved': 'old'})
        interpreter.execute('Recovered=Saved;')
        self.assertEqual(interpreter.variables['recovered'], 'old')
    def test_unknown_owner_fails_closed(self):
        app=self.app()
        with self.assertRaises(BSLRuntimeError):app.interpreter.execute('Store.Put("v",42)')
        self.assertFalse(app.temporary_storage._entries)
    def test_invalid_address_not_coerced(self):
        app=self.app()
        for value in ['42','"invalid"']:
            with self.assertRaises(BSLRuntimeError):app.interpreter.execute('Store.Get('+value+')')
    def test_application_failure_releases_startup_values(self):
        files=module_files((('Store',SOURCE,SERVER),),application='Procedure BeforeStart(Cancel) Store.Put("v"); Raise "failed"; EndProcedure')
        app=self.construct(files)
        with self.assertRaisesRegex(BSLRuntimeError,'failed'):app.start()
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
                    with self.assertRaises(BSLRuntimeError):app.interpreter.execute(expression)
                elif number in (12,15):
                    self.assertEqual(expected[number-1],'stored' if number==12 else 'stored:empty-owner')
                    self.assertEqual(app.interpreter.execute(expression),'error')
                else:self.assertEqual(app.interpreter.execute(expression),expected[number-1])
