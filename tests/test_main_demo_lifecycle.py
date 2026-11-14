"""Canonical demo lifecycle shares modules without acquiring database authority."""
import unittest
from yadinassi.invocation import InvocationServer
from yadinassi.configuration_main_demo import import_main_demo_configuration, PROFILE
from yadinassi.ui.main_demo import form_family
from test_main_demo_configuration import source

class MainDemoLifecycleTests(unittest.TestCase):
    def config(self): return import_main_demo_configuration(source(), profile=PROFILE)

    def test_shared_startup_crosses_server_boundary_once(self):
        server = form_family(self.config(), side='server')
        self.addCleanup(server.close)
        server.start()
        endpoint=InvocationServer.from_handlers(server.server_endpoints, message_scope=server.event_messages)
        output=[]; packets=[]
        def exchange(raw):
            packets.append(raw)
            return endpoint.exchange(raw)
        client = form_family(self.config(), side='client', output=output.append, server_exchange=exchange)
        self.addCleanup(client.close)
        client.start()
        self.assertEqual(output, ['Основная демо: справочники, документы и складские отчёты.'])
        self.assertEqual(len(packets), 1)
        with self.assertRaisesRegex(ValueError, 'start only once'):
            client.start()
        self.assertEqual(len(output), 1)
        self.assertEqual(len(packets), 1)

    def test_exact_module_source_is_required(self):
        for name in ('CommonModules/DemoTools/Ext/Module.bsl', 'CommonModules/DemoService/Ext/Module.bsl', 'Ext/ManagedApplicationModule.bsl'):
            with self.subTest(name=name):
                files=source(); files[name]+=b'\n'
                with self.assertRaises(ValueError): import_main_demo_configuration(files, profile=PROFILE)

    def test_lifecycle_never_accepts_database_context(self):
        with self.assertRaisesRegex(ValueError, 'memory-only'):
            form_family(self.config(), side='client', database_context=object())
