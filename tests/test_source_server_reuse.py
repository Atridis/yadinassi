"""Closed local source ServerCall scalar reuse; no split-server claim."""
import json
import unittest
from unittest.mock import patch
from test_source_server_call import configuration
from test_server_module_reuse_native_replay import application_files, NATIVE
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

TOKEN='Function Token(Val Key) Export Return String(New UUID); EndFunction'

class SourceServerReuseTests(unittest.TestCase):
    def app(self, body=TOKEN, **flags):
        source=configuration('',body,reuse=flags.pop('reuse','DuringSession'),**flags)
        app=SourceApplication(source,output=lambda _:None)
        self.addCleanup(app.close);app.start();return app

    def execute(self,app,code):return app.interpreter.execute(code)

    def test_session_cache_refresh_and_application_separation(self):
        a,b=self.app(),self.app();first=self.execute(a,'ServerAPI.Token("x")')
        self.assertEqual(first,self.execute(a,'ServerAPI.Token("x")'))
        self.assertNotEqual(first,self.execute(b,'ServerAPI.Token("x")'))
        self.execute(a,'RefreshReusableValues()')
        self.assertNotEqual(first,self.execute(a,'ServerAPI.Token("x")'))

    def test_request_boundary_and_failure_cleanup(self):
        app=self.app(reuse='DuringRequest')
        self.assertTrue(self.execute(app,'(ServerAPI.Token("x")=ServerAPI.Token("x"))'))
        first=self.execute(app,'ServerAPI.Token("x")')
        self.assertNotEqual(first,self.execute(app,'ServerAPI.Token("x")'))
        with self.assertRaises(BSLError):self.execute(app,'ServerAPI.Token("x"); Raise "stop"')
        self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)

    def test_native_event_sequence(self):
        files=application_files()
        app=SourceApplication(import_source(files),output=lambda _:None)
        self.addCleanup(app.close);app.start()
        expected=json.loads(NATIVE.read_bytes())['observations']
        first=self.execute(app,'Results=New Array;For I=1 To 15 Do Results.Add(Observe(I));EndDo;Results')
        self.assertEqual(first.items,expected[:15])
        last=self.execute(app,'Bit(ClientToken=CachedServerCall.Token("lifetime"))+":"+Bit(SessionToken=ServerInspector.SessionToken("lifetime"))+":"+Bit(RequestToken=ServerInspector.RequestToken("lifetime"))')
        self.assertEqual(last,expected[15])

    def test_bad_module_shapes_lazy_refusal(self):
        for body in [TOKEN.replace('Val Key','Key'),TOKEN.replace('Val Key','Val Key="x"'),
                     'Procedure Token(Val Key) Export EndProcedure','Async '+TOKEN]:
            with self.subTest(body=body),self.assertRaises(BSLError):
                self.execute(self.app(body),'ServerAPI.Token("x")')

        for helper in ['Function Hidden(Key) Return Key; EndFunction',
                       'Function Hidden(Val Key=1) Return Key; EndFunction',
                       'Procedure Hidden(Val Key) EndProcedure']:
            with self.subTest(helper=helper),self.assertRaises(BSLError):
                self.execute(self.app(TOKEN+'\n'+helper),'ServerAPI.Token("x")')

    def test_metadata_boundaries(self):
        for flags in [{'client':True},{'global_module':True},{'privileged':True}]:
            with self.subTest(flags=flags),self.assertRaises(BSLError):
                self.execute(self.app(**flags),'ServerAPI.Token("x")')

        for property_name in ['ClientOrdinaryApplication','ExternalConnection']:
            admitted=configuration('',TOKEN,reuse='DuringSession')
            files={item.path:item.content for item in admitted.files}
            path='CommonModules/ServerAPI.xml'
            files[path]=files[path].replace(b'</Properties>', ('<'+property_name+'>true</'+property_name+'></Properties>').encode())
            app=SourceApplication(import_source(files),output=lambda _:None)
            self.addCleanup(app.close);app.start()
            with self.subTest(property_name=property_name),self.assertRaises(BSLError):
                self.execute(app,'ServerAPI.Token("x")')

    def test_non_scalar_input_and_output_refused(self):
        app=self.app()
        for value in ['New Array','New Structure("K",1)','New UUID']:
            with self.subTest(value=value),self.assertRaises(BSLError):
                self.execute(app,f'ServerAPI.Token({value})')
        with self.assertRaises(BSLError):
            self.execute(self.app(TOKEN.replace('String(New UUID)','New Array')),'ServerAPI.Token("x")')

    def test_same_side_scalar_guard(self):
        body=TOKEN+'\nFunction Inner(Val Key) Export Return Token(New Array); EndFunction'
        with self.assertRaises(BSLError):self.execute(self.app(body),'ServerAPI.Inner("x")')

    def test_warm_cache_cannot_bypass_transaction_transfer_guard(self):
        app=self.app();self.execute(app,'ServerAPI.Token("warm")')
        with patch('yadinassi.database_transactions.forbid_transfer',side_effect=ValueError('denied')) as guard:
            with self.assertRaises(BSLError):self.execute(app,'ServerAPI.Token("warm")')
            guard.assert_called_once()

    def test_warm_cache_cannot_bypass_safe_mode(self):
        app=self.app();self.execute(app,'ServerAPI.Token("warm")')
        with self.assertRaises(BSLError):self.execute(app,'SetSafeMode(True);ServerAPI.Token("warm")')

    def test_foreign_and_closed_owner(self):
        a,b=self.app(),self.app()
        with self.assertRaises(ValueError):a.reusable_values.cache(b.interpreter,'DuringSession')
        a.close()
        with self.assertRaises(ValueError):a.reusable_values.cache(a.interpreter,'DuringSession')

    def test_arity_before_argument_effect(self):
        app=self.app()
        self.execute(app,'Function Touch() Raise "wrong-side-effect";EndFunction')
        with self.assertRaises(BSLError) as caught:self.execute(app,'ServerAPI.Token(Touch(),Touch())')
        self.assertNotIn('wrong-side-effect',str(caught.exception))

    def test_private_reusable_helper_not_exported(self):
        app=self.app(TOKEN.replace(' Export',''))
        with self.assertRaises(BSLError):self.execute(app,'ServerAPI.Token("x")')
