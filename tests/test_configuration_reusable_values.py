import unittest
from decimal import Decimal
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLError
from configuration_runtime_fixture import module_files
SOURCE='''
Function Token(Key="default") Export Return String(New UUID); EndFunction
Function Pair(Key) Export Return Token(Key)=Token(Key); EndFunction
Function Qualified(Key) Export Return Tools.Token(Key)=Tools.Token(Key); EndFunction
Function Change(Key) Export Key=Key+1; Return String(New UUID); EndFunction
Function Mutable(Key) Export A=New Array; A.Add("base"); Return A; EndFunction
Function Failure(Key) Export Raise String(New UUID); EndFunction
Procedure Touch(Val Value) Export Value.Seen=Value.Seen+1; EndProcedure
'''
def application(mode='DuringSession',source=SOURCE,flags=None,main=''):
    app=ConfigurationApplication.from_files(module_files([('Tools',source,{'ReturnValuesReuse':mode,**(flags or {})})],application=main));app.start();return app
class ReusableIntegration(unittest.TestCase):
    def app(self,*args,**kwargs):
        app=application(*args,**kwargs);self.addCleanup(app.close,force=True);return app
    def test_session(self):
        a=self.app();self.assertEqual(a.execute('Tools.Token("x")'),a.execute('Tools.Token("x")'))
    def test_request_within(self):self.assertTrue(self.app('DuringRequest').execute('(Tools.Token("x")=Tools.Token("x"))'))
    def test_request_between(self):
        a=self.app('DuringRequest');self.assertNotEqual(a.execute('Tools.Token("x")'),a.execute('Tools.Token("x")'))
    def test_self_calls(self):
        a=self.app();self.assertFalse(a.execute('Tools.Pair("x")'));self.assertTrue(a.execute('Tools.Qualified("x")'))
    def test_refresh_session(self):self.assertFalse(self.app().execute('A=Tools.Token("x");RefreshReusableValues();(A=Tools.Token("x"))'))
    def test_refresh_request(self):self.assertFalse(self.app('DuringRequest').execute('A=Tools.Token("x");RefreshReusableValues();(A=Tools.Token("x"))'))
    def test_mutation(self):self.assertTrue(self.app().execute('A=0;X=Tools.Change(A);B=0;Y=Tools.Change(B);(X=Y And A=1 And B=0)'))
    def test_alias(self):self.assertEqual(self.app().execute('A=Tools.Mutable("x");A.Add("change");Tools.Mutable("x").Count()'),Decimal(2))
    def test_families(self):self.assertNotEqual(self.app().execute('Tools.Token("x")'),self.app().execute('Tools.Token("x")'))
    def test_procedure(self):self.assertEqual(self.app().execute('A=New Structure("Seen",0);Tools.Touch(A);Tools.Touch(A);A.Seen'),Decimal(2))
    def test_modes_closed(self):
        for flags in ({'Server':'true'},{'Global':'true'},{'ServerCall':'true'},{'ExternalConnection':'true'},{'Privileged':'true'},{'ClientOrdinaryApplication':'true'}):
            with self.subTest(flags=flags),self.assertRaises(ValueError):application(flags=flags)
    def test_async_closed(self):
        with self.assertRaises(ValueError):application(source='Async Function F() Export Return 1; EndFunction')
    def test_failures(self):self.assertFalse(self.app().execute('Try Tools.Failure("x");Except A=ErrorDescription();EndTry;Try Tools.Failure("x");Except B=ErrorDescription();EndTry;(A=B)'))
    def test_closed(self):
        a=self.app();a.close(force=True)
        with self.assertRaises(ValueError):a.reusable_values.refresh(a.interpreter)
    def test_standalone(self):
        vm=Interpreter(lambda _:None);self.addCleanup(vm.close)
        with self.assertRaises(BSLError):vm.execute('RefreshReusableValues();')
    def test_array_argument_closed(self):
        with self.assertRaises(BSLError):self.app().execute('Tools.Token(New Array)')
    def test_request_finally(self):
        a=self.app('DuringRequest')
        with self.assertRaises(BSLError):a.execute('Tools.Token("x");Raise "failure";')
        self.assertIsNone(a.interpreter._scheduler.active_context.request_cache)
    def test_refresh_not_function(self):
        with self.assertRaises(BSLError):self.app().execute('A=RefreshReusableValues()')
    def test_refresh_arity(self):
        with self.assertRaises(BSLError):self.app().execute('RefreshReusableValues(1)')
    def test_normal_exit(self):
        a=self.app(main='Procedure OnExit() Tools.Token("exit"); EndProcedure');self.assertTrue(a.close())
