"""NoDB by-value scalar root commands; not general configuration parity."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.python_direct_configuration import ConfigurationBoundary
from yadinassi.runtime import Interpreter
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.errors import BSLRuntimeError
from configuration_runtime_fixture import CLIENT, SERVER, module_files


class DirectConfigurationCommandTests(unittest.TestCase):
    def app(self,modules=(CLIENT,),output=None):
        app=ConfigurationApplication.from_files(module_files(modules),output=output or (lambda x:None))
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_named_export_private_helper_casefold_and_persistent_scalar_state(self):
        source='Function Hidden(Val X) Return X+1;EndFunction Function Public(Val X) Export Return Hidden(X)*2;EndFunction'
        app=self.app([('Tools',source,{})])
        self.assertEqual(app.execute('tOoLs.pUbLiC(3)'),Decimal(8))
        self.assertIsNone(app.execute('X=Tools.Public(4);'))
        self.assertEqual(app.execute('X+Tools.Public(2)'),Decimal(16))
        with self.assertRaises(Exception):app.execute('Tools.Hidden(1);')

    def test_cross_module_repeated_nested_calls_and_no_legacy(self):
        output=[]
        app=self.app([CLIENT,('Other','Function Go(Val X) Export Return Tools.Double(X)+Tools.Double(X);EndFunction',{})],output.append)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in ('execute_program','block','_visit','call_routine'):
                stack.enter_context(patch.object(Interpreter,name,side_effect=AssertionError(name)))
            app.execute('Message(Other.Go(2));Message(Other.Go(3));')
        self.assertEqual(output,['8','12'])

    def test_byref_defaults_global_and_crossing_fail_at_reached_call(self):
        for source,flags in (
            ('Function F(X) Export Return X;EndFunction',{}),
            ('Function F(Val X=-1) Export Return X;EndFunction',{}),
            ('Function F(Val X) Export Return X;EndFunction',{'Global':'true'}),
            ('Function F(Val X) Export Return X;EndFunction',SERVER)):
            with self.subTest(source=source,flags=flags):
                output=[];app=self.app([('Tools',source,flags)],output.append)
                with self.assertRaises((BoundaryViolation,BSLRuntimeError)):app.execute('Message("before");Tools.F(1);')
                self.assertEqual(output,['before'])

    def test_scalar_arguments_results_and_command_shapes_fail_closed(self):
        for text in ('X=New Array();','Var X;','Execute "X=1";','Eval("1")','Tools=1;',
                     'Tools.Double(,);','X=Tools;','While True Do EndDo;'):
            app=self.app()
            with self.subTest(text=text),self.assertRaises((BoundaryViolation,Exception)):
                app.execute(text)
        app=self.app([('Tools','Function F() Export Return New Array();EndFunction',{})])
        with self.assertRaises(BoundaryViolation):app.execute('X=Tools.F();')
        self.assertNotIn('x',app.interpreter.variables)
        class Host:
            def __getattribute__(self,name):raise AssertionError(name)
        app=self.app();app.interpreter.variables['x']=Host()
        with self.assertRaises(BoundaryViolation):app.execute('Tools.Double(X);')

    def test_transitive_service_gate_denies_custom_host_and_eval(self):
        for call in ('Eval("1")','Custom()'):
            app=self.app([('Tools',f'Function F() Export Return {call};EndFunction',{})])
            effects=[];owner=app._modules['tools','client'].interpreter
            owner.register_function('Custom',lambda:effects.append(1))
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F();')
            self.assertEqual(effects,[])
        app=self.app();effects=[]
        app.interpreter.register_function('Message',lambda x:effects.append(x))
        with self.assertRaises(BoundaryViolation):app.execute('Message(1);')
        self.assertEqual(effects,[])

    def test_host_and_call_policies_remain_authoritative(self):
        output=[];app=self.app([('Tools','Function F(Val X) Export Message(X);Return X;EndFunction',{})],output.append)
        with patch.object(app,'check_call',wraps=app.check_call) as call,patch.object(app,'check_host_service',wraps=app.check_host_service) as host:
            self.assertEqual(app.execute('Tools.F(3)'),Decimal(3))
            self.assertTrue(call.called);self.assertGreaterEqual(host.call_count,2)
        self.assertEqual(output,['3'])
        with patch.object(app,'check_host_service',side_effect=ValueError('policy')):
            with self.assertRaises(Exception):app.execute('Tools.F(4);')
        self.assertEqual(output,['3'])

    def test_application_owner_binding_and_state_rechecked_after_callback(self):
        for mutation in ('state','owner','binding','code'):
            events=[];app=None
            def output(value):
                events.append(value)
                child=app._modules['tools','client'].interpreter
                if mutation=='state':app.state='exiting'
                elif mutation=='owner':child._family_generation+=1
                elif mutation=='binding':app._modules['tools','client']=object()
                else:child._direct_configuration_plan.function=lambda *a:events.append('bad')
            app=self.app([('Tools','Function F(Val X) Export Message(X);Return X;EndFunction',{})],output)
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F(1);Message("after");')
            self.assertEqual(events,['1'])

    def test_database_scheduler_restricted_and_nested_execution_stay_denied(self):
        from yadinassi import safe_mode
        app=self.app()
        with patch.object(Interpreter,'database_context',property(lambda self:object())):
            self.assertEqual(app.execute('Tools.Double(2)'),Decimal(4))
        token=safe_mode._CURRENT.set(object())
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.Double(2)')
        finally:safe_mode._CURRENT.reset(token)
        app.interpreter._scheduler._pending.add(object())
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.Double(2)')
        finally:app.interpreter._scheduler._pending.clear()
        events=[]
        def output(value):
            with self.assertRaises(BoundaryViolation):app.execute('Tools.Double(9)')
            events.append(value)
        app=self.app(output=output);app.execute('Message(Tools.Double(2));')
        self.assertEqual(events,['4'])
        self.assertEqual(app.execute('Tools.Double(3)'),Decimal(6))

    def test_reuse_and_async_initial_admission_unchanged(self):
        for source,flags in (
            ('Function F() Export Return 1;EndFunction',{'ReturnValuesReuse':'DuringSession'}),
            ('Async Function F() Export Return 1;EndFunction',{})):
            with self.assertRaises((ValueError,BoundaryViolation)):
                self.app([('Tools',source,flags)])

    def test_foreign_scalar_metaclass_and_routine_do_not_run_hooks(self):
        calls=[]
        class Meta(type):
            def __eq__(cls,other):calls.append('eq');raise AssertionError('metaclass')
        class Host(metaclass=Meta):
            def __getattribute__(self,name):calls.append(name);raise AssertionError(name)
        app=self.app();app.interpreter.variables['x']=Host()
        with self.assertRaises(BoundaryViolation):app.execute('Tools.Double(X);')
        app.interpreter.variables.clear()
        app._modules['tools','client'].interpreter.routines['injected']=Host()
        self.assertEqual(app.execute('Tools.Double(1)'),Decimal(2))
        self.assertEqual(calls,[])

    def test_explicit_transport_is_not_implicitly_admitted_by_commands(self):
        packets=[]
        app=ConfigurationApplication.from_files(module_files([('Remote','Function F(Val X) Export Return X;EndFunction',SERVER)]),
            side='client',server_exchange=lambda packet:packets.append(packet))
        self.addCleanup(lambda:app.close(force=True));app.start()
        with self.assertRaises(BSLRuntimeError):app.execute('Remote.F(1);')
        self.assertEqual(packets,[])

    def test_custom_namespace_mappings_are_rejected_without_hooks(self):
        calls=[]
        class Mapping(dict):
            def get(self,*args):calls.append('get');raise AssertionError('mapping')
        for field in ('functions','variables','routines'):
            app=self.app();owner=app._modules['tools','client'].interpreter
            setattr(owner,field,Mapping(getattr(owner,field)))
            with self.assertRaises(BoundaryViolation):app.execute('Tools.Double(1);')
        self.assertEqual(calls,[])

    def test_captured_host_callable_cannot_bypass_scope_service_gate(self):
        from yadinassi.python_direct_configuration import _COMMAND_SCOPE
        from yadinassi.python_direct_configuration_commands import _Scope
        from yadinassi.values import HostFunction
        app=self.app();effects=[]
        scope=_Scope(app);scope.enter()
        try:
            context=ConfigurationBoundary(app,app.interpreter);context.enter()
            with self.assertRaises(BoundaryViolation):
                context.resolve_callable(HostFunction('Foreign',lambda:effects.append(1)))
            self.assertEqual(effects,[])
            context.resolve_callable(app.interpreter.functions['message'])(Decimal(1))
        finally:scope.leave()

    def test_pre_lazy_message_class_override_is_not_canonical(self):
        import importlib
        from yadinassi import python_direct_configuration_commands as commands
        effects=[]
        with patch.object(Interpreter,'_message',lambda *args:effects.append(args)):
            importlib.reload(commands)
            app=self.app()
            with self.assertRaises(BoundaryViolation):app.execute('Message(1);')
        self.assertEqual(effects,[])

    def test_active_boundary_pins_origin_thread_and_exact_context(self):
        import contextvars
        import threading
        from yadinassi.python_direct_configuration_commands import _Scope
        output=[];app=self.app(output=output.append)
        scope=_Scope(app);scope.enter()
        try:
            context=ConfigurationBoundary(app,app.interpreter);context.enter()
            for foreign in (contextvars.Context(),contextvars.copy_context()):
                with self.assertRaises(BoundaryViolation):
                    foreign.run(lambda:context.resolve_service('Message')(Decimal(1)))
            errors=[]
            def worker():
                try:context.resolve_service('Message')(Decimal(2))
                except BaseException as error:errors.append(type(error))
            thread=threading.Thread(target=worker);thread.start();thread.join()
            self.assertEqual(errors,[BoundaryViolation]);self.assertEqual(output,[])
            context.resolve_service('Message')(Decimal(3))
            self.assertEqual(output,['3'])
        finally:scope.leave()
        with self.assertRaises(BoundaryViolation):context.resolve_service('Message')(Decimal(4))
        self.assertEqual(output,['3'])

    def test_captured_callable_revalidates_after_policy_mutates_implementation(self):
        from yadinassi.python_direct_configuration_commands import _Scope
        app=self.app();effects=[];scope=_Scope(app);scope.enter()
        try:
            context=ConfigurationBoundary(app,app.interpreter);context.enter()
            function=app.interpreter.functions['message']
            bound=context.resolve_callable(function)
            def policy(value,owner):value.function=lambda *a:effects.append(a)
            with patch.object(app,'check_host_service',side_effect=policy):
                with self.assertRaises(BoundaryViolation):bound(Decimal(1))
            self.assertEqual(effects,[])
        finally:scope.leave()

    def test_procedure_value_rejected_before_operand_effects(self):
        output=[]
        app=self.app([('Tools','Procedure P(Val X) Export Message(X);EndProcedure',{})],output.append)
        app.execute('Tools.P(3);')
        with self.assertRaisesRegex(Exception,'Процедура не возвращает значение'):
            app.execute('X=Tools.P(Message("bad"));')
        self.assertEqual(output,['3'])

    def test_scalar_command_scope_cannot_enter_existing_form_boundary(self):
        from yadinassi.form_runtime import FormSession
        from yadinassi.python_direct_forms import FormBoundary
        from yadinassi.python_direct_configuration_commands import _Scope
        session=FormSession('Procedure Event() EndProcedure')
        session._begin(session.revision)
        try:
            routine=session.interpreter.routines['event']
            context=FormBoundary(session,routine);context.enter()
            app=self.app();scope=_Scope(app);scope.enter()
            try:
                with self.assertRaises(BoundaryViolation):context.checkpoint()
                with self.assertRaises(BoundaryViolation):FormBoundary(session,routine)
                self.assertEqual(session._steps,0)
            finally:scope.leave()
            context.checkpoint();self.assertEqual(session._steps,1)
        finally:
            session._busy=False;session._gate.release()


class LazyConfigurationCommandTests(unittest.TestCase):
    app=DirectConfigurationCommandTests.app
    def test_unused_byref_and_server_modules_do_not_block_scalar(self):
        app=self.app([('Tools','Function Good(Val X) Export Return X+1;EndFunction Function Unused(X) Export Return X;EndFunction',{}),
                      ('Remote','Function ServerOnly(Val X) Export Return X;EndFunction',SERVER)])
        self.assertEqual(app.execute('1+2'),Decimal(3))
        self.assertEqual(app.execute('Tools.Good(3)'),Decimal(4))
        app.execute('If False Then Remote.ServerOnly(1);EndIf;')
        with self.assertRaises((BoundaryViolation,BSLRuntimeError)):app.execute('Tools.Unused(3)')

    def test_unused_database_routine_branch_does_not_run(self):
        app=self.app([('Tools','Function Database(Val X) Export BeginTransaction();Return X;EndFunction',{})])
        self.assertEqual(app.execute('1+2'),Decimal(3))
        app.execute('If False Then Tools.Database(1);EndIf;')
        with self.assertRaises((BoundaryViolation,BSLRuntimeError)):app.execute('Tools.Database(1)')

    def test_plain_command_does_not_read_module_definitions_or_metadata(self):
        app=self.app([CLIENT,('Remote','Function F() Export Return 1;EndFunction',SERVER)])
        from yadinassi import python_direct_configuration_metadata as metadata
        with patch.object(metadata,'validate_definition',side_effect=AssertionError('unused module inspected')):
            self.assertEqual(app.execute('1+2'),Decimal(3))

    def test_unsupported_call_denied_before_argument_effect(self):
        output=[]
        app=self.app([('Tools','Function Bad(X) Export Return X;EndFunction Function Effect() Export Message("argument");Return 1;EndFunction',{})],output.append)
        with self.assertRaises((BoundaryViolation,BSLRuntimeError)):app.execute('Tools.Bad(Tools.Effect())')
        self.assertEqual(output,[])
