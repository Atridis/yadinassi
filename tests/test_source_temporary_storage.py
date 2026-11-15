"""Source-owned closed temporary storage, not a native source-host parity claim."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
from test_source_server_call import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.runtime import Interpreter
from yadinassi import temporary_storage as storage

BODY='''Function Put(Val V, Val Owner=Undefined) Export If Owner=Undefined Then Owner=New UUID; EndIf; Return PutToTempStorage(V,Owner); EndFunction
Function Get(Val Address) Export Return GetFromTempStorage(Address); EndFunction
Procedure Delete(Val Address) Export DeleteFromTempStorage(Address); EndProcedure
Function Recognize(Val Address) Export Return IsTempStorageURL(Address); EndFunction'''

class SourceTemporaryTests(unittest.TestCase):
    def app(self, body=BODY, startup=''):
        app=SourceApplication(configuration(startup,body),output=lambda _:None)
        self.addCleanup(app.close)
        app.start()
        return app

    def execute(self, app, code):
        return app.interpreter.execute(code)

    def put(self, app, value='"first"', owner='Undefined'):
        return self.execute(app,f'ServerAPI.Put({value},{owner})')

    def get(self, app, address):
        return self.execute(app,f'ServerAPI.Get("{address}")')

    def test_roundtrip_replacement_delete(self):
        app=self.app();address=self.put(app)
        self.assertEqual(self.get(app,address),'first')
        self.assertEqual(self.put(app,'"second"','"'+address+'"'),address)
        self.assertEqual(self.get(app,address),'second')
        self.execute(app,f'ServerAPI.Delete("{address}")')
        self.assertIsNone(self.get(app,address))
        self.assertTrue(self.execute(app,f'ServerAPI.Recognize("{address}")'))
        self.execute(app,f'ServerAPI.Delete("{address}")')
        with self.assertRaises(BSLError):self.put(app,'1','"'+address+'"')

    def test_native_closed_profile_replay(self):
        root=Path(__file__).resolve().parents[1]
        raw=(root/'tests/fixtures/native_temporary_storage_43056863128.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'0f475f9e8184890bdfa7f0d3e676970035586f7948365b0a1067275ba91486e7')
        source=(root/'scripts/temporary_storage_behavior/observe.bsl').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'a5d1cdce77f24f6801a55328812fc442c3978e5daae13fdebef807b355f520e7')
        declarations=source.decode().split('For CaseNo = 1 To 16 Do')[0]
        declarations+='\nFunction Run(Val CaseNo) Export Stage="read"; Return ObserveCase(CaseNo,Stage); EndFunction'
        app=self.app(declarations);expected=json.loads(raw)
        for n in range(1,17):
            with self.subTest(case=n):
                code=f'ServerAPI.Run({n})'
                if n==11:
                    with self.assertRaises(BSLError):self.execute(app,code)
                elif n in (12,15):self.assertEqual(self.execute(app,code),'error')
                else:self.assertEqual(self.execute(app,code),expected[n-1])

    def test_cross_application_isolation(self):
        app,other=self.app(),self.app();address=self.put(app)
        self.assertIsNone(self.get(other,address))
        with self.assertRaises(BSLError):self.put(other,'1','"'+address+'"')
        self.assertEqual(self.get(app,address),'first')
        address=self.put(app,'New Array')
        self.execute(app,f'Copy=ServerAPI.Get("{address}"); Copy.Add("client");')
        self.assertEqual(self.execute(app,f'ServerAPI.Get("{address}").Count()'),0)
        with self.assertRaises(BSLError):
            self.execute(app,'SetSafeMode(True); ServerAPI.Get("'+address+'");')

    def test_close_releases_values(self):
        app=self.app();self.put(app);store=app.temporary_storage;app.close()
        self.assertEqual(store._entries,{});self.assertEqual(store._units,0)
        with self.assertRaises(ValueError):store.authorize(app.interpreter)

    def test_start_failure_cleans_store(self):
        app=SourceApplication(configuration('ServerAPI.Put("x"); Raise "stop";',BODY),output=lambda _:None)
        self.addCleanup(app.close)
        with self.assertRaises(BSLError):app.start()
        self.assertTrue(app.temporary_storage._closed)
        self.assertEqual(app.temporary_storage._entries,{})
        from test_configuration_source_runtime import source
        from test_source_server_call import module
        files=module('ServerAPI',BODY)
        files['CommonModules/ServerAPI.xml']=files['CommonModules/ServerAPI.xml'].replace(
            b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000002">')
        cancelled=SourceApplication(source(b'Procedure BeforeStart(Cancel) ServerAPI.Put("x"); Cancel=True; EndProcedure',files),output=lambda _:None)
        self.addCleanup(cancelled.close)
        self.assertFalse(cancelled.start())
        self.assertTrue(cancelled.temporary_storage._closed)
        self.assertEqual(cancelled.temporary_storage._entries,{})

    def test_client_denied_before_arguments(self):
        app=self.app();app.interpreter.execute('Function Touch() Raise "wrong-side-effect"; EndFunction')
        with self.assertRaisesRegex(BSLError,'active server'):
            self.execute(app,'PutToTempStorage(Touch(),New UUID)')

    def test_foreign_marker_denied_before_arguments(self):
        app=self.app();vm=Interpreter(lambda _:None);self.addCleanup(vm.close)
        vm.register_function('Put',storage.SourceTemporaryCall(app.temporary_storage,storage.put_marker))
        vm.execute('Function Touch() Raise "wrong-side-effect"; EndFunction')
        with self.assertRaisesRegex(BSLError,'another or closed'):
            vm.execute('Put(Touch(),New UUID)')

    def test_arity_before_arguments(self):
        app=self.app(BODY+'\nFunction Probe() Export Return GetFromTempStorage(Touch(),Touch()); EndFunction\nFunction Touch() Raise "wrong-side-effect"; EndFunction')
        with self.assertRaisesRegex(BSLError,'arity'):self.execute(app,'ServerAPI.Probe()')

    def test_atomic_admission_and_quotas(self):
        app=self.app();address=self.put(app);before=(app.temporary_storage._units,app.temporary_storage._nodes)
        for name,limit in [('MAX_ENTRIES',1),('MAX_RETAINED_UNITS',before[0]),('MAX_SNAPSHOT_NODES',before[1])]:
            with self.subTest(name=name),mock.patch.object(storage,name,limit):
                with self.assertRaises(BSLError):self.put(app)
                self.assertEqual(self.get(app,address),'first')
        with mock.patch.object(storage,'capture',side_effect=ValueError('unsupported')):
            with self.assertRaises(BSLError):self.put(app,'1','"'+address+'"')
        self.assertEqual(self.get(app,address),'first')
        self.assertEqual((app.temporary_storage._units,app.temporary_storage._nodes),before)

    def test_unknown_owner_and_invalid_address_closed(self):
        app=self.app()
        for owner in ['42','""']:
            with self.subTest(owner=owner),self.assertRaises(BSLError):self.put(app,owner=owner)
        for address in ['42','"bad"']:
            with self.assertRaises(BSLError):self.execute(app,f'ServerAPI.Get({address})')
        self.assertEqual(app.temporary_storage._entries,{})

    def test_in_memory_safe_mode_and_russian_aliases(self):
        body='''Function Probe() Export
SetSafeMode(True);
A=ПоместитьВоВременноеХранилище("ok",New UUID);
V=ПолучитьИзВременногоХранилища(A);
УдалитьИзВременногоХранилища(A);
Return V+String(ЭтоАдресВременногоХранилища(A)); EndFunction'''
        self.assertTrue(self.execute(self.app(body),'ServerAPI.Probe()').startswith('ok'))

    def test_standalone_still_closed(self):
        vm=Interpreter(lambda _:None);self.addCleanup(vm.close)
        with self.assertRaises(BSLError):vm.execute('PutToTempStorage(1,New UUID)')
