"""Same-side reuse never caches authority or falls back to VM dispatch."""
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch
import unittest
import subprocess
import sys
from pathlib import Path
import test_source_session_parameters as session_tests
from test_configuration_source_runtime import source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class SourceReuseTests(unittest.TestCase):
    def setUp(self):
        stack=ExitStack();self.addCleanup(stack.close)

    def app(self,body='Message(Helpers.Value());',function='Function Value() Export Return 42; EndFunction',mode='DuringSession', *, allow_extensions=False):
        config=session_tests.SourceSessionTests().cached_source(mode,body)
        files={f.path:f.content for f in config.files}
        files['CommonModules/Helpers/Ext/Module.bsl']=function.encode()
        out=[];app=SourceApplication(source(extra=files),output=out.append, allow_extensions=allow_extensions)
        self.addCleanup(app.close);app.start();return app,out

    def execute(self,app,text):
        owner=app._session_owner;owner._context_stack.append('server')
        try:return owner.execute(text)
        finally:owner._context_stack.pop()

    def test_existing_session_request_refresh_and_isolation(self):
        original=session_tests.SourceSessionTests()
        self.addCleanup(original.doCleanups)
        for name in ('test_same_side_cached_fixed_map_is_reused','test_session_reuse_survives_next_request',
                     'test_request_reuse_expires_at_next_request','test_refresh_invalidates_source_cache',
                     'test_caches_do_not_leak_between_source_applications'):
            with self.subTest(name=name):getattr(original,name)()

    def test_private_helper_is_not_cached(self):
        app,out=self.app('Message(Helpers.Value());Message(Helpers.Value());',
            'Function Helper() Message("private");Return 1;EndFunction\n'
            'Function Value() Export Return Helper()+Helper();EndFunction')
        self.assertEqual(out,['private','private','2','2'])

    def test_refresh_during_computation_does_not_publish_old_reservation(self):
        app,out=self.app('Message(Helpers.Value());Message(Helpers.Value());',
            'Function Value() Export Message("compute");RefreshReusableValues();Return 42;EndFunction')
        self.assertEqual(out,['compute','42','compute','42'])
        self.assertEqual(len(app.reusable_values._session._entries),0)

    def test_failure_never_publishes(self):
        app,out=self.app('Try Helpers.Value();Except EndTry;Try Helpers.Value();Except EndTry;',
            'Function Value() Export Message("compute");Raise "fail";EndFunction')
        self.assertEqual(out,['compute','compute'])
        self.assertEqual(len(app.reusable_values._session._entries),0)

    def test_warm_hit_revalidates_entry_and_hooks_before_arguments(self):
        for mutation in ('entry','entry_hook','cache','owner','policy'):
            with self.subTest(mutation=mutation):
                app,out=self.app('Message(Helpers.Value(1));', 'Function Value(Val X) Export Return X;EndFunction', allow_extensions=True)
                effects=[];app._session_owner.register_function('Touch',lambda:effects.append(1) or 1)
                if mutation=='entry':app._reuse_routines.clear()
                elif mutation=='entry_hook':
                    class Trap:
                        def __getitem__(self,index):effects.append('hook');return True
                    key=next(iter(app._reuse_routines));app._reuse_routines[key]=Trap()
                elif mutation=='cache':app.reusable_values._session.lookup=lambda key:effects.append('hook')
                elif mutation=='owner':app.reusable_values.authorize=lambda caller:effects.append('hook')
                else:app.files['CommonModules/Helpers.xml']=app.files['CommonModules/Helpers.xml'].replace(b'DuringSession',b'DuringRequest')
                with self.assertRaises(BoundaryViolation):self.execute(app,'Helpers.Value(Touch());')
                self.assertEqual(effects,[])

    def test_argument_effect_cannot_retarget_cache(self):
        app,out=self.app('Message(Helpers.Value(1));','Function Value(Val X) Export Return X;EndFunction', allow_extensions=True)
        from yadinassi.application.reusable_values import ReusableValueCache
        app._session_owner.register_function('Swap',lambda:setattr(app.reusable_values,'_session',ReusableValueCache()) or 1)
        with self.assertRaises(BoundaryViolation):self.execute(app,'Helpers.Value(Swap());')
        self.assertEqual(out,['1'])

    def test_typed_scalar_keys_and_expiry(self):
        app,out=self.app('Message(Helpers.Value(1));Message(Helpers.Value(1.0));Message(Helpers.Value("1"));',
            'Function Value(Val X) Export Message("compute");Return X;EndFunction')
        self.assertEqual(out,['compute','1','1','compute','1'])
        cache=app.reusable_values._session
        for key,(value,units,created,touched) in list(cache._entries.items()):
            cache._entries[key]=(value,units,created-2000,touched-2000)
        self.execute(app,'Helpers.Value(1);')
        self.assertEqual(out[-1],'compute')

    def test_defaults_and_byref_rejected_before_effects(self):
        for signature in ('Val X=1','X'):
            app,out=self.app(' ',f'Function Value({signature}) Export Return X;EndFunction', allow_extensions=True)
            effects=[];app._session_owner.register_function('Touch',lambda:effects.append(1) or 1)
            with self.assertRaises(BoundaryViolation):self.execute(app,'Helpers.Value(Touch());')
            self.assertEqual(effects,[])

    def test_invalid_retained_result_discarded_before_hit_returns(self):
        app,out=self.app()
        cache=app.reusable_values._session
        key=next(iter(cache._entries));value,units,created,touched=cache._entries[key]
        cache._entries[key]=(object(),units,created,touched)
        with self.assertRaises(Exception):self.execute(app,'Helpers.Value();')
        self.assertNotIn(key,cache._entries)

    def test_cache_entry_and_factory_hooks_never_run(self):
        app,out=self.app();effects=[];cache=app.reusable_values._session
        key=next(iter(cache._entries))
        class Trap:
            def __getitem__(self,index):effects.append(index);return 0
        old=cache._entries[key];cache._entries[key]=Trap()
        with self.assertRaises(BoundaryViolation):self.execute(app,'Helpers.Value();')
        self.assertEqual(effects,[]);cache._entries[key]=old
        # Patching inherited __new__ changes CPython's type allocation slot even
        # after mock removes the attribute. Keep the adversarial check, but do
        # not poison constructors used by later tests in the same process.
        script="""import sys,unittest
sys.path.insert(0,'tests')
from test_python_direct_source_reuse import SourceReuseTests
result=unittest.TextTestRunner().run(SourceReuseTests('_factory_new_hook_probe'))
raise SystemExit(not result.wasSuccessful())
"""
        options=['-B']+(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else [])
        child=subprocess.run([sys.executable,*options,'-c',script],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stdout+child.stderr)
        from yadinassi.application.reusable_values import ReusableValueCache
        ReusableValueCache(clock=lambda:0)  # Parent constructor remains usable.

    def _factory_new_hook_probe(self):
        app,out=self.app();effects=[]
        from yadinassi.application.reusable_values import ReusableValueCache
        with patch.object(ReusableValueCache,'__new__',side_effect=lambda *a:effects.append('factory')):
            with self.assertRaises(BoundaryViolation):self.execute(app,'Helpers.Value();')
        self.assertEqual(effects,[])


class SourceClientReuseTests(unittest.TestCase):
    def app(self, body, **options):
        from configuration_runtime_fixture import module_files
        files=module_files([('Helpers',body,{'ReturnValuesReuse':'DuringSession'})])
        messages=[]
        app=SourceApplication(source(extra=files),output=messages.append,**options)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        return app,messages

    def test_client_omission_and_signed_defaults_only_key_missing_actuals(self):
        app,out=self.app('Function Value(Val X=-2,Val Y=4) Export '
                         'Message("compute"); Return X; EndFunction')
        vm=app.interpreter
        self.assertEqual(vm.execute('Helpers.Value()'),Decimal(-2))
        self.assertEqual(vm.execute('Helpers.Value(-2,4)'),Decimal(-2))
        self.assertEqual(vm.execute('Helpers.Value(,4)'),Decimal(-2))
        self.assertIsNone(vm.execute('Helpers.Value(Undefined,4)'))
        self.assertEqual(out,['compute','compute'])

    def test_client_byref_samples_once_on_hit_and_never_copies_out(self):
        from yadinassi.types.values import Reference
        from yadinassi.types.errors import BSLError
        app,out=self.app('Function Value(X) Export '
                         'Message("compute"); X=X+1; Return X; EndFunction')
        vm=app.interpreter
        values=[Decimal(3),Decimal(3)]
        effects=[]
        def get(i):
            effects.append(('read',i));return values[i]
        def put(i,value):
            effects.append(('write',i));values[i]=value
        for i,name in enumerate(('a','b')):
            vm.variables[name]=Reference(lambda i=i:get(i),lambda value,i=i:put(i,value))
        with self.assertRaises(BSLError):
            vm.execute('Helpers.Value(A,0)')
        self.assertEqual(effects,[])
        self.assertEqual(vm.execute('Helpers.Value(A)'),Decimal(4))
        self.assertEqual(vm.execute('Helpers.Value(B)'),Decimal(4))
        self.assertEqual(values,[Decimal(4),Decimal(3)])
        self.assertEqual(effects,[('read',0),('read',0),('write',0),('read',0),('read',1)])
        self.assertEqual(out,['compute'])

    def test_client_byref_readmit_policy_before_warm_lookup(self):
        from yadinassi.types.values import Reference
        app,out=self.app('Function Value(X) Export Message("compute"); Return X; EndFunction')
        vm=app.interpreter
        self.assertEqual(vm.execute('Helpers.Value(3)'),Decimal(3))
        cache=app.reusable_values._session
        saved=tuple(cache._entries.items())
        seen=[]
        def read():
            seen.append('read')
            path='CommonModules/Helpers.xml'
            app.files[path]=app.files[path].replace(b'DuringSession',b'DuringRequest')
            return Decimal(3)
        vm.variables['a']=Reference(read,lambda _:self.fail('cache hit must not write'))
        with self.assertRaises(BoundaryViolation):
            vm.execute('Helpers.Value(A)')
        self.assertEqual(seen,['read'])
        self.assertEqual(out,['compute'])
        self.assertEqual(tuple(cache._entries.items()),saved)

    def test_client_procedures_run_live_and_do_not_enter_cache(self):
        app,out=self.app('Procedure SetValue(X) Export Message(X); X=X+1; EndProcedure')
        app.interpreter.execute('A=0; Helpers.SetValue(A); Helpers.SetValue(A); Message(A);')
        self.assertEqual(out,['0','1','2'])
        self.assertFalse(app.reusable_values._session._entries)
