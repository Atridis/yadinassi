"""Source-owned closed temporary storage, not a native source-host parity claim."""
import unittest
from unittest import mock
from test_source_server_call import configuration
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLError
from yadinassi.runtime import Interpreter
from yadinassi.application import temporary_storage as storage

BODY='''Function Put(Val V, Val Owner=Undefined) Export If Owner=Undefined Then Owner=New UUID; EndIf; Return PutToTempStorage(V,Owner); EndFunction
Function Get(Val Address) Export Return GetFromTempStorage(Address); EndFunction
Procedure Delete(Val Address) Export DeleteFromTempStorage(Address); EndProcedure
Function Recognize(Val Address) Export Return IsTempStorageURL(Address); EndFunction'''

class SourceTemporaryTests(unittest.TestCase):
    def app(self, body=BODY, startup='', *, allow_extensions=False):
        app=SourceApplication(configuration(startup,body),output=lambda _:None, allow_extensions=allow_extensions)
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

    # The pinned full native replay lives in test_application_temporary_storage.
    # This suite tests the source bridge's distinct policy and boundary paths.
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

    def test_client_get_and_put_on_one_store_in_both_directions(self):
        app=self.app()
        client=self.execute(app,'ПоместитьВоВременноеХранилище("client",New UUID)')
        self.assertEqual(self.get(app,client),'client')
        server=self.put(app,'"server"')
        self.assertEqual(self.execute(app,f'ПолучитьИзВременногоХранилища("{server}")'),'server')
        self.execute(app,f'ServerAPI.Delete("{client}");')
        self.assertIsNone(self.execute(app,f'GetFromTempStorage("{client}")'))

    def test_client_crossing_copies_nested_mutable_values(self):
        extra="""Function Make() Export
V=New Array;V.Add("server"); Box=New Structure("Items",V);
A=PutToTempStorage(Box,New UUID); V.Add("alias"); Return A; EndFunction
Function NestedCount(Val Address) Export Return GetFromTempStorage(Address).Items.Count(); EndFunction"""
        app=self.app(BODY+'\n'+extra)
        address=self.execute(app,'''V=New Array; V.Add("client"); B=New Structure("Items",V);
A=PutToTempStorage(B,New UUID); V.Add("not sent"); A''')
        self.assertEqual(self.execute(app,f'ServerAPI.NestedCount("{address}")'),1)
        server=self.execute(app,'ServerAPI.Make()')
        self.execute(app,f'Copy=GetFromTempStorage("{server}"); Copy.Items.Add("not shared");')
        self.assertEqual(self.execute(app,f'GetFromTempStorage("{server}").Items.Count()'),2)
        self.assertEqual(self.execute(app,f'ServerAPI.NestedCount("{server}")'),2)

    def test_client_uuid_only_and_wrong_arity_denies_before_actuals(self):
        app=self.app();self.execute(app,'Function Touch() Raise "wrong-side-effect"; EndFunction')
        for wrong in ('PutToTempStorage(Touch())','GetFromTempStorage(Touch(),Touch())'):
            with self.subTest(wrong=wrong),self.assertRaisesRegex(BSLError,'arity'):
                self.execute(app,wrong)
        address=self.put(app)
        for owner in ('Undefined','42','""','"'+address+'"'):
            with self.subTest(owner=owner),self.assertRaisesRegex(BSLError,'explicit UUID'):
                self.execute(app,f'PutToTempStorage("not stored",{owner})')
        self.assertEqual(self.get(app,address),'first')
        self.assertEqual(len(app.temporary_storage._entries),1)

    def test_client_safe_mode_denied_before_argument_effects(self):
        app=self.app()
        self.execute(app,'''Function Touch() Raise "wrong-side-effect"; EndFunction
Procedure Restricted() SetSafeMode(True); PutToTempStorage(Touch(),New UUID); EndProcedure''')
        with self.assertRaisesRegex(BSLError,'source safe mode does not support cross-context'):
            self.execute(app,'Restricted();')
        self.assertFalse(app.temporary_storage._entries)

    def test_client_get_adds_no_own_scan_of_entries(self):
        import sys
        app=self.app()
        address=self.execute(app,'PutToTempStorage("hit",New UUID)')
        missing=self.put(app)
        self.execute(app,f'ServerAPI.Delete("{missing}");')
        entries=app.temporary_storage._entries
        scans=[]
        def profile(frame,event,arg):
            if event=='c_call' and getattr(arg,'__self__',None) is entries and arg.__name__=='items':
                scans.append(frame.f_code.co_name)
        previous=sys.getprofile()
        sys.setprofile(profile)
        try:
            self.assertIsNone(self.execute(app,f'GetFromTempStorage("{missing}")'))
            self.assertEqual(scans,[])
            self.assertEqual(self.execute(app,f'GetFromTempStorage("{address}")'),'hit')
        finally:
            sys.setprofile(previous)
        self.assertEqual(scans,['_measure'])

    def test_client_get_does_not_reach_a_different_or_closed_session(self):
        first,other=self.app(),self.app()
        address=self.execute(first,'PutToTempStorage("private",New UUID)')
        self.assertIsNone(self.execute(other,f'GetFromTempStorage("{address}")'))
        first.close()
        with self.assertRaises((BSLError,ValueError)):
            self.execute(first,f'GetFromTempStorage("{address}")')
        self.assertFalse(first.temporary_storage._entries)

    def test_foreign_marker_denied_before_arguments(self):
        app=self.app();vm=Interpreter(lambda _:None, allow_extensions=True);self.addCleanup(vm.close)
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
