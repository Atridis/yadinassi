"""Owned source-host startup without legacy AST execution or weakened grants."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch

from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication, _SourceInterpreter
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLError


def common_module(code,*,global_module=False):
    properties=(b'<Name>Helpers</Name><ClientManagedApplication>true</ClientManagedApplication>'
                + (b'<Global>true</Global>' if global_module else b''))
    return {'CommonModules/Helpers.xml':
        b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000002"><Properties>'
        +properties+b'</Properties></CommonModule></MetaDataObject>',
        'CommonModules/Helpers/Ext/Module.bsl':code}


class DirectSourceTests(unittest.TestCase):
    def app(self,code=b'',extra=None):
        output=[]
        app=SourceApplication(source(code,extra),output=output.append)
        self.addCleanup(app.close)
        return app,output

    @contextmanager
    def no_vm(self):
        with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy call')), \
             patch.object(_SourceInterpreter,'call',side_effect=AssertionError('legacy source dispatch')):
            yield

    def test_root_and_session_startup_without_vm_dispatch(self):
        app,out=self.app(b'Procedure OnStart() Message("app"); EndProcedure',
            {'Ext/SessionModule.bsl':b'Procedure SessionParametersSetting(Names) Message("session"); EndProcedure'})
        with self.no_vm():self.assertTrue(app.start())
        self.assertEqual(out,['session','app']);self.assertEqual(app.state,'running')

    def test_cancel_slot_and_no_start_after_cancellation(self):
        app,out=self.app(b'Procedure BeforeStart(Cancel) Cancel=True; EndProcedure\n'
                         b'Procedure OnStart() Message("bad"); EndProcedure')
        with self.no_vm():self.assertFalse(app.start())
        self.assertEqual(out,[]);self.assertEqual(app.state,'cancelled')

    def test_common_and_global_exports_have_owned_same_side_execution(self):
        for global_module in (False,True):
            with self.subTest(global_module=global_module):
                call='Answer(7)' if global_module else 'Helpers.Answer(7)'
                app,out=self.app(('Procedure OnStart() Message('+call+'); EndProcedure').encode(),
                    common_module(b'Function Answer(Val X) Export Return X+1; EndFunction',global_module=global_module))
                with self.no_vm():self.assertTrue(app.start())
                self.assertEqual(out,['8'])

    def test_safe_mode_nested_frames_and_failure_do_not_remove_parent(self):
        app,out=self.app(b'''Procedure Inner() SetSafeMode(True); Raise "error"; EndProcedure
Procedure Outer() SetSafeMode(True);Try Inner();Except EndTry;Message(SafeMode());EndProcedure
Procedure OnStart() Outer();Message(SafeMode());EndProcedure''')
        with self.no_vm():self.assertTrue(app.start())
        self.assertEqual(out,['\u0414\u0430','\u041d\u0435\u0442'])

    def test_host_close_cannot_be_caught_and_prevents_later_effects(self):
        app,out=self.app(b'Procedure OnStart() Try Close();Except Message("caught");EndTry;Message("later");EndProcedure')
        app.interpreter.register_function('Close',app.close)
        with self.no_vm(),self.assertRaises(BoundaryViolation):app.start()
        self.assertEqual(out,[]);self.assertEqual(app.state,'failed')

    def test_subclass_context_not_admitted(self):
        app,_=self.app();app.start()
        class ForgedSource(_SourceInterpreter):pass
        vm=ForgedSource(app,family_owner=app.interpreter)
        self.addCleanup(vm.close)
        with self.assertRaises(BoundaryViolation):vm.execute('Saved=1;')
        self.assertNotIn('saved',vm.variables)

    def test_replaced_native_constructor_refused_before_effects(self):
        app,_=self.app();app.start();vm=app.interpreter
        vm.register_type('Array',lambda:[])
        with self.assertRaises((ValueError,BoundaryViolation)):
            vm.execute('Saved=1;A=New Array;')
        self.assertNotIn('saved',vm.variables)

    def test_bound_common_module_revalidated_after_argument_effect(self):
        app,out=self.app(b'Procedure OnStart() Message(Helpers.Answer(Touch()));EndProcedure',
            common_module(b'Function Answer(Val X) Export Return X; EndFunction'))
        def touch():
            app._instances.clear()
            return 7
        app.interpreter.register_function('Touch',touch)
        with self.assertRaises((ValueError,BoundaryViolation)):app.start()
        self.assertEqual(out,[])

    def test_retained_host_reference_cannot_read_or_write_after_activation(self):
        from yadinassi.values import HostFunction
        app,_=self.app();app.start();vm=app.interpreter;retained=[]
        vm.functions['keep']=HostFunction('Keep',lambda ref:retained.append(ref),reference_parameters=(0,))
        vm.execute('X=1;Keep(X);')
        self.assertEqual(len(retained),1)
        with self.assertRaises(BoundaryViolation):retained[0].get()
        with self.assertRaises(BoundaryViolation):retained[0].set(9)
        vm.register_function('Stale',lambda:retained[0].set(9))
        with self.assertRaises(BoundaryViolation):vm.execute('Stale();')
        self.assertEqual(vm.variables['x'],1)

    def test_host_execute_reentry_is_rejected_before_inner_or_later_effects(self):
        app,_=self.app();app.start();vm=app.interpreter
        vm.register_function('Reenter',lambda:vm.execute('Injected=1;'))
        with self.assertRaises(BoundaryViolation):
            vm.execute('Saved=1;Try Reenter();Except Caught=True;EndTry;Saved=9;')
        self.assertEqual(vm.variables['saved'],1)
        self.assertNotIn('injected',vm.variables);self.assertNotIn('caught',vm.variables)

    def test_template_arity_and_foreign_owner_rejected_before_arguments(self):
        app,_=self.app();app.start();other,_=self.app();other.start()
        vm=app.interpreter;effects=[]
        vm.register_function('Effect',lambda:effects.append('effect') or 'name')
        with self.assertRaises(Exception):vm.execute('GetCommonTemplate(Effect(),Effect());')
        self.assertEqual(effects,[])
        vm.functions['getcommontemplate']=other.interpreter.functions['getcommontemplate']
        with self.assertRaises(BoundaryViolation):vm.execute('GetCommonTemplate(Effect());')
        self.assertEqual(effects,[])

    def test_prepared_signature_change_rejected_before_arguments(self):
        app,out=self.app();app.start();vm=app.interpreter;effects=[]
        vm.execute('Procedure P(Val X) Message("callee");EndProcedure')
        vm.routines['p'].parameters[0].by_value=False
        vm.register_function('Effect',lambda:effects.append('effect') or 1)
        with self.assertRaises(BoundaryViolation):vm.execute('P(Effect());')
        self.assertEqual(effects,[]);self.assertEqual(out,[])

    def test_prepared_constructor_change_rejected_before_arguments(self):
        app,out=self.app();app.start();vm=app.interpreter;effects=[]
        vm.execute('Procedure P(Val X) A=New Array;Message("callee");EndProcedure')
        vm.register_type('Array',lambda:[])
        vm.register_function('Effect',lambda:effects.append('effect') or 1)
        with self.assertRaises((BSLError,ValueError,BoundaryViolation)):vm.execute('P(Effect());')
        self.assertEqual(effects,[]);self.assertEqual(out,[])

    def test_prepared_signature_revalidated_after_arguments(self):
        app,out=self.app();app.start();vm=app.interpreter;effects=[]
        vm.execute('Procedure P(Val X) Message("callee");EndProcedure')
        def change():
            effects.append('change');vm.routines['p'].parameters[0].by_value=False
            return 1
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('P(Change());')
        self.assertEqual(effects,['change']);self.assertEqual(out,[])

    def test_qualified_procedure_value_and_arity_fail_before_arguments(self):
        for declaration,call in (
                (b'Procedure Put(Val X) Export Message("callee");EndProcedure','A=Helpers.Put(Effect());'),
                (b'Function Put(Val X) Export Return X;EndFunction','Helpers.Put(Effect(),Effect());')):
            with self.subTest(call=call):
                app,out=self.app(extra=common_module(declaration));app.start();effects=[]
                app.interpreter.register_function('Effect',lambda:effects.append('effect') or 1)
                with self.assertRaises(Exception):app.interpreter.execute(call)
                self.assertEqual(effects,[]);self.assertEqual(out,[])

    def test_qualified_common_module_byref_and_default_update_actual_storage(self):
        app,_=self.app(extra=common_module(
            b'Procedure Change(X,Val Y=2) Export X=X+Y;EndProcedure'))
        app.start()
        with self.no_vm():app.interpreter.execute('X=3;Helpers.Change(X);')
        self.assertEqual(app.interpreter.variables['x'],5)

    def test_exact_type_rejection_does_not_access_hostile_application_property(self):
        from yadinassi.python_direct_source import check_owner
        class ForgedSource(_SourceInterpreter):
            @property
            def application(self):raise AssertionError('hostile application property')
        with self.assertRaises(BoundaryViolation):check_owner(object.__new__(ForgedSource))

    def test_source_execute_remains_explicitly_unsupported(self):
        app,_=self.app();app.start()
        with self.assertRaisesRegex(ValueError,'Execute'):
            app.interpreter.execute('Saved=1;Execute("Saved=2;");')
        self.assertNotIn('saved',app.interpreter.variables)


if __name__=='__main__':unittest.main()
