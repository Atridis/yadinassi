"""Local process-family contracts, not native application-host evidence."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch, PropertyMock
from yadinassi.runtime import Interpreter
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.forms.form_runtime import FormSession
from yadinassi.execution.invocation import InvocationServer, InvocationPort, InvocationError
from yadinassi.types.values import HostFunction
from configuration_runtime_fixture import module_files, CLIENT, SERVER


class ApplicationFamilyTests(unittest.TestCase):
    def test_child_release_does_not_reset_owner(self):
        root = Interpreter(lambda value: None)
        child = Interpreter(family_owner=root)
        with patch.object(type(root._scheduler), 'pending', new_callable=PropertyMock, return_value=1):
            with self.assertRaises(ValueError): child.close()
            self.assertFalse(child._family_released)
        with patch.object(root._scheduler, 'reset') as reset:
            child.close()
            reset.assert_not_called()
            with self.assertRaises(ValueError): child.execute("X = 1;")
            root.close()
            reset.assert_called_once()
        root.execute("X = 1;")
        self.assertEqual(root.variables["x"], 1)
        with self.assertRaises(ValueError): child.execute("X = 2;")

    def test_activation_is_constructed_in_family(self):
        root = Interpreter()
        child = root._activation_interpreter()
        self.assertIs(child._family_owner, root)
        self.assertIs(child._scheduler, root._scheduler)
        with self.assertRaises(ValueError): Interpreter(family_owner=child)
        root.close()
        with self.assertRaises(ValueError): Interpreter(family_owner=root)

    def test_child_construction_preserves_active_context(self):
        root = Interpreter()
        root._context_stack.append('server')
        child = root._activation_interpreter()
        self.assertEqual(child._context_stack, ['client', 'server'])

    def test_form_factory_common_access_and_independent_forms(self):
        app = ConfigurationApplication.from_files(module_files([('Tools', 'Function Double(Val X) Export Message(X * 2); Return X * 2; EndFunction', {})]), side='client')
        app.start()
        source = '&AtClient\nProcedure Open(Cancel) Message(Tools.Double(3)); EndProcedure'
        first = FormSession(source, bindings={'OnOpen': 'Open'}, interpreter_factory=app.form_interpreter_factory)
        second = FormSession(source, bindings={'OnOpen': 'Open'}, interpreter_factory=app.form_interpreter_factory)
        messages = []
        with app.event_messages(messages.append): first.open()
        self.assertEqual(messages, ['6'])
        first.interpreter.close()
        with app.event_messages(messages.append): second.open()
        self.assertEqual(messages, ['6', '6'])
        module = app._modules['tools', 'client'].interpreter
        self.assertFalse(hasattr(module, '_form_session'))
        self.assertNotIn('parameters', module.variables)
        self.assertNotIn('items', module.variables)

    def test_preflight_host_service_visible_to_common(self):
        opened = []
        files = module_files([('Tools', 'Procedure Show() Export OpenForm("Welcome"); EndProcedure', {})])
        app = ConfigurationApplication.from_files(files, side='client', host_services={
            'OpenForm': HostFunction('OpenForm', opened.append, returns_value=False)})
        app.start(); app.execute('Tools.Show();')
        self.assertEqual(opened, ['Welcome'])

    def test_server_process_has_no_client_module_or_app_start(self):
        output = []
        app = ConfigurationApplication.from_files(module_files([CLIENT], application='Message("startup");'),
                                                   side='server', output=output.append)
        self.assertTrue(app.start())
        self.assertEqual(output, [])
        self.assertNotIn(('tools', 'client'), app._modules)
        with self.assertRaises(ValueError):
            ConfigurationApplication.from_files(module_files(), side='server', host_services={
                'OpenForm': HostFunction('OpenForm', lambda: None)})

    def test_servercall_requires_transport_and_val_signature(self):
        files = module_files([('Service', 'Function F(Val X) Export Return X; EndFunction', SERVER)])
        with self.assertRaises(ValueError): ConfigurationApplication.from_files(files, side='client')
        files = module_files([('Service', 'Function F(X) Export Return X; EndFunction', SERVER)])
        with self.assertRaises(ValueError):
            ConfigurationApplication.from_files(files, side='client', server_exchange=lambda raw: raw)

    def test_split_client_command_uses_only_prebound_scalar_wire(self):
        files = module_files([('Service',
            'Function F(Val X) Export Message("server"); Return X + 1; EndFunction', SERVER)])
        server = ConfigurationApplication.from_files(files, side='server')
        self.addCleanup(server.close)
        server.start()
        endpoint = InvocationServer.from_handlers(server.server_endpoints, message_scope=server.event_messages)
        packets, output = [], []
        with ThreadPoolExecutor(max_workers=1) as transport:
            def exchange(raw):
                packets.append(raw)
                return transport.submit(endpoint.exchange, raw).result(timeout=5)
            client = ConfigurationApplication.from_files(files, side='client', server_exchange=exchange,
                                                        output=output.append)
            self.addCleanup(client.close)
            client.start()
            # Bad outer call is rejected even before the inner actual can send.
            with self.assertRaisesRegex(Exception, 'argument count mismatch'):
                client.execute('Service.F(Service.F(4), 0);')
            self.assertEqual(packets, [])
            self.assertEqual(output, [])
            client.execute('Message(Service.F(4));')
        self.assertEqual(output, ['server', '5'])
        self.assertEqual(len(packets), 1)
        self.assertNotIn(b'Service', packets[0])
        self.assertEqual(client._modules['service', 'server'].routine('F').body, [])

    def test_split_client_checks_stub_readiness_at_bind_and_after_actuals(self):
        from yadinassi.execution.direct.python_direct_configuration import ConfigurationBoundary
        from yadinassi.execution.direct.python_direct_configuration_commands import _Scope
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.types.values import NULL

        files = module_files([('Service', 'Function F(Val X) Export Return X; EndFunction', SERVER)])
        packets = []
        app = ConfigurationApplication.from_files(files, side='client', server_exchange=packets.append)
        self.addCleanup(app.close)
        app.start()
        receiver = app._modules['service', 'server']
        receiver.ready = False
        with self.assertRaises(BoundaryViolation):
            app.execute('Service.F(4);')
        self.assertEqual(packets, [])

        receiver.ready = True
        # The generated call binds and checks arity before actual evaluation.
        # Exercise the two phases explicitly so no other resolver can catch the
        # revocation before the already bound invocation has a chance to do so.
        scope = _Scope(app)
        scope.enter()
        try:
            boundary = ConfigurationBoundary(app, app.interpreter)
            boundary.enter()
            try:
                call = boundary.resolve_configuration_member_call(
                    boundary.external_get('Service'), 'F', argument_count=1)
                with self.assertRaises(BoundaryViolation):
                    call(NULL)  # A transport-capable value outside command scalar admission.

                def evaluate_actual():
                    receiver.ready = False
                    return Decimal(4)

                with self.assertRaises(BoundaryViolation):
                    call(evaluate_actual())
            finally:
                boundary.leave()
        finally:
            scope.leave()
        self.assertEqual(packets, [])

    def test_split_client_admits_reply_value_before_publishing_messages(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.execution.invocation import PROTOCOL
        from yadinassi.ui.protocol import decode_line, encode_line

        files = module_files([('Service', 'Function F(Val X) Export Return X; EndFunction', SERVER)])
        packets, output = [], []

        def exchange(raw):
            request = decode_line(raw)
            packets.append(request)
            first = len(packets) == 1
            return encode_line({'protocol': PROTOCOL, 'id': request['id'], 'status': 'ok',
                                'messages': ['not admitted'] if first else ['first', 'second'],
                                'value': {'type': 'Null'} if first else {'type': 'Number', 'value': '5'}})

        app = ConfigurationApplication.from_files(files, side='client', server_exchange=exchange,
                                                  output=output.append)
        self.addCleanup(app.close)
        app.start()
        with self.assertRaises(BoundaryViolation):
            app.execute('Message(Service.F(4));')
        self.assertEqual(len(packets), 1)
        self.assertEqual(output, [])
        app.execute('Message(Service.F(5));')
        self.assertEqual([request['id'] for request in packets], [1, 2])
        self.assertEqual(output, ['first', 'second', '5'])

    def test_remote_call_only_over_prebound_wire(self):
        files = module_files([('Service', 'Function F(Val X) Export Message("server"); Return X + 1; EndFunction', SERVER)])
        server = ConfigurationApplication.from_files(files, side='server'); server.start()
        endpoint = InvocationServer.from_handlers(server.server_endpoints, message_scope=server.event_messages)
        packets = []
        def exchange(raw):
            packets.append(raw)
            return endpoint.exchange(raw)
        output = []
        client = ConfigurationApplication.from_files(files, side='client', server_exchange=exchange, output=output.append)
        client.start(); client.execute('Message(Service.F(4));')
        self.assertEqual(output, ['server', '5'])
        self.assertEqual(len(packets), 1)
        stub = client._modules['service', 'server'].routine('F')
        self.assertEqual(stub.body, [])
        self.assertNotIn(b'Service', packets[0])
        self.assertNotIn(b'Function', packets[0])
        local = InvocationServer('&AtServerNoContext\nFunction Ping(Val X) Export Return Service.F(X); EndFunction',
            {1:'Ping'}, interpreter_factory=server.interpreter_factory)
        self.assertIs(local._interpreter._family_owner, server.interpreter)
        with server.event_messages(local._message):
            value = InvocationPort(local.exchange).invoke(local.bindings[0], [Decimal(9)])
        self.assertEqual(value, 10)

    def test_uncertain_remote_is_not_replayed(self):
        files = module_files([('Service', 'Function F(Val X) Export Return X; EndFunction', SERVER)])
        calls = []
        def broken(raw): calls.append(raw); raise OSError('lost')
        app = ConfigurationApplication.from_files(files, side='client', server_exchange=broken)
        app.start()
        for _ in range(2):
            with self.assertRaises(Exception): app.execute('Service.F(1);')
        self.assertEqual(len(calls), 1)

    def test_start_once_and_cancelled_start(self):
        files = module_files(application='Procedure BeforeStart(Cancel) Cancel = True; EndProcedure')
        app = ConfigurationApplication.from_files(files, side='client')
        self.assertFalse(app.start())
        with self.assertRaises(ValueError): app.start()
        with self.assertRaises(ValueError): app.form_interpreter_factory(None, print)

    def test_scoped_messages_restore_after_failure(self):
        outer, inner = [], []
        app = ConfigurationApplication.from_files(module_files([('Tools', 'Procedure Say() Export Message("hello"); EndProcedure', {})]), output=outer.append, side='client')
        app.start()
        with self.assertRaises(RuntimeError):
            with app.event_messages(inner.append):
                app.execute('Tools.Say();')
                raise RuntimeError()
        app.execute('Tools.Say();')
        self.assertEqual(inner, ['hello']); self.assertEqual(outer, ['hello'])

    def test_empty_profile_side_validation(self):
        with self.assertRaises(ValueError): ConfigurationApplication.from_files(module_files(), side='browser')
        with self.assertRaises(ValueError): ConfigurationApplication.from_files(module_files(), server_exchange=lambda raw: raw)
