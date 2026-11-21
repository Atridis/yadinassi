"""Exact main-demo startup, not general configured-runtime parity."""
import dis
from contextvars import ContextVar
import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.execution.invocation import InvocationServer
from yadinassi.configuration.configuration_main_demo import import_main_demo_configuration, PROFILE
from yadinassi.ui.main_demo import form_family
from yadinassi.execution.direct.python_direct_configuration import ConfigurationBoundary, invoke_routine, check_owner
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from test_main_demo_configuration import source

class DirectConfigurationTests(unittest.TestCase):
    def config(self):return import_main_demo_configuration(source(),profile=PROFILE)
    def family(self,side,**kw):
        app=form_family(self.config(),side=side,**kw)
        self.addCleanup(lambda:app.close(force=True))
        return app
    def test_exact_startup_and_one_packet_without_ast_dispatch(self):
        with patch.object(Interpreter,'execute_program',side_effect=AssertionError('AST module')) ,patch.object(Interpreter,'block',side_effect=AssertionError('AST block')),patch.object(Interpreter,'_visit',side_effect=AssertionError('AST node')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM call')):
            server=self.family('server');server.start()
            endpoint=InvocationServer.from_handlers(server.server_endpoints,message_scope=server.event_messages)
            packets=[];output=[]
            def exchange(raw):packets.append(raw);return endpoint.exchange(raw)
            client=self.family('client',output=output.append,server_exchange=exchange)
            self.assertTrue(client.start())
        self.assertEqual(output,['Основная демо: справочники, документы и регистр накопления.'])
        self.assertEqual(len(packets),1)
        with self.assertRaisesRegex(ValueError,'start only once'):client.start()
    def test_closed_application_and_family_reject_saved_calls(self):
        app=self.family('server');app.start()
        owner=app._modules['demoservice','server'].interpreter
        routine=owner.server_routines['applicationtitle']
        self.assertEqual(invoke_routine(app,owner,routine,[]),'Основная демо')
        app.interpreter.close()
        with self.assertRaises(BoundaryViolation):invoke_routine(app,owner,routine,[])
    def test_server_cannot_resolve_client_module(self):
        app=self.family('server');app.start();ctx=ConfigurationBoundary(app,app.interpreter);ctx.enter()
        with self.assertRaisesRegex(ValueError,'unavailable on the server'):ctx.external_get('demotools')
    def test_unregistered_receiver_never_reflects(self):
        app=self.family('server');app.start();ctx=ConfigurationBoundary(app,app.interpreter);ctx.enter()
        class Host:
            @property
            def secret(self):raise AssertionError('descriptor ran')
        with self.assertRaises(BoundaryViolation):ctx.resolve_member(Host(),'secret')
    def test_service_policy_before_effect_and_after_argument_binding(self):
        from yadinassi.types.values import HostFunction
        app=self.family('client',server_exchange=lambda _:self.fail('unexpected packet'))
        effects=[]
        app.interpreter.functions['openform']=HostFunction('OpenForm',lambda *args:effects.append(args))
        ctx=ConfigurationBoundary(app,app.interpreter);ctx.enter()
        with self.assertRaises(ValueError):ctx.resolve_service('OpenForm')
        app.state='starting';call=ctx.resolve_service('OpenForm');app.state='exiting'
        with self.assertRaises(ValueError):call('test')
        self.assertEqual(effects,[])
    def test_transaction_service_denied_and_scope_restored(self):
        app=self.family('server');app.start()
        owner=app._modules['demoservice','server'].interpreter
        routine=owner.server_routines['applicationtitle']
        original=owner._direct_configuration_plan.function
        def factory(state,constants,output,ctx):
            return {'applicationtitle':lambda:ctx.resolve_service('BeginTransaction')()}
        owner._direct_configuration_plan.function=factory
        with patch('yadinassi.db.database_transactions.begin') as begin:
            with self.assertRaises(Exception):invoke_routine(app,owner,routine,[])
            begin.assert_not_called()
        self.assertTrue(owner._transaction_activation_allowed)
        self.assertEqual(owner._context_stack,['server'])
        owner._direct_configuration_plan.function=original
    def test_restricted_context_rejected_before_generated_entry(self):
        from yadinassi.execution import safe_mode
        app=self.family('server');app.start()
        owner=app._modules['demoservice','server'].interpreter
        routine=owner.server_routines['applicationtitle']
        token=safe_mode._CURRENT.set(object())
        try:
            with patch.object(owner._direct_configuration_plan,'function',side_effect=AssertionError('entered')):
                with self.assertRaises(BoundaryViolation):invoke_routine(app,owner,routine,[])
        finally:safe_mode._CURRENT.reset(token)
    def test_server_shutdown_policy_rechecked_after_service(self):
        from yadinassi.types.values import HostFunction
        app=self.family('server');app.start()
        owner=app._modules['demoservice','server'].interpreter
        routine=owner.server_routines['applicationtitle']
        owner.functions['shutdown']=HostFunction('Shutdown',lambda:setattr(app,'state','exiting'))
        ctx=ConfigurationBoundary(app,owner,routine);ctx.enter()
        with self.assertRaisesRegex(ValueError,'shutdown'):ctx.resolve_service('Shutdown')()

    def test_owner_hot_path_has_no_import_bytecode(self):
        self.assertFalse(any(op.opname.startswith('IMPORT_') for op in dis.get_instructions(check_owner)))

    def test_owner_observes_live_restricted_context_attributes(self):
        from yadinassi.execution import safe_mode
        from yadinassi.db import source_transactions, database_transactions
        app=self.family('server');app.start()
        owner=app.interpreter
        check_owner(app,owner)
        for module,name in ((safe_mode,'_CURRENT'),(source_transactions,'_current'),(database_transactions,'_execution')):
            with self.subTest(module=module.__name__),patch.object(module,name,ContextVar('denied',default=object())):
                with self.assertRaisesRegex(BoundaryViolation,'restricted execution'):
                    check_owner(app,owner)
            check_owner(app,owner)
