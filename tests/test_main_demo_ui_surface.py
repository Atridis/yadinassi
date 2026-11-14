"""Explicit document surface of the unified demo; navigation is tested separately."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_main_demo_configuration import source, ROOT
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.configuration_app import (load_application, ConfigurationBroker,
    ConfigurationController, ConfigurationProcess, PROTOCOL)
from yadinassi.ui.protocol import encode_line, decode_line
from yadinassi.ui.database_launch import binding, configuration_route

class MainDemoUISurfaceTests(unittest.TestCase):
    def test_loader_has_declared_document_and_common_forms_and_rejects_mixed_grants(self):
        forms = load_application(ROOT/'examples/demo', main_demo_application=True)
        self.assertEqual(len(forms.forms), 5)
        self.assertEqual(sum(f.document_schema is not None for f in forms.forms.values()), 2)
        with self.assertRaises(ValueError):
            load_application(ROOT/'examples/demo', main_demo_application=True, inventory_enum_application=True)

    def test_generated_document_columns_have_russian_captions_without_renaming_schema(self):
        forms = load_application(ROOT/'examples/demo', main_demo_application=True)
        for name in ('document.receipt.form.card', 'document.issue.form.card'):
            columns = forms.forms[name].tables[0].columns
            self.assertEqual([(c.name, c.title) for c in columns], [
                ('Product', 'Номенклатура'), ('Quantity', 'Количество'),
                ('Amount', 'Сумма'), ('Unit', 'Единица измерения')])
        # The exact main-demo adapter changes display only, not global loader.
        self.assertEqual(len(forms.forms), 5)

    def test_real_broker_controller_document_open_write_and_close(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'demo.sqlite'
            config = import_main_demo_configuration(source(), profile=PROFILE)
            with SQLiteDBContext.create_main_demo(path, config) as context:
                expected = binding(context.backend.launch_snapshot())
            forms = load_application(ROOT/'examples/demo', main_demo_application=True)
            broker = ConfigurationBroker(forms, path, main_demo_application=True,
                launch_binding=expected, launch_route='main-demo')
            def exchange(raw):
                request = decode_line(raw)
                result = broker.exchange({k:request[k] for k in ('operation','session','payload')})
                return encode_line({'id':request['id'],'session':request['session'],'result':result,'error':None})
            app = ConfigurationController(forms, exchange, main_demo_application=True)
            def rpc(method, **params):
                return app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
            try:
                self.assertIsNone(rpc('hello', protocol=PROTOCOL)['error'])
                opened = rpc('open', entry=app.names['document.receipt.form.card'], request='new');self.assertIsNone(opened['error'])
                sid = opened['session'];self.assertIsNotNone(sid)
                table = next(item for item in opened['form']['result']['state']['items'] if item['kind'] == 'table')
                self.assertEqual([column['title'] for column in table['columns']], ['Номенклатура', 'Количество', 'Сумма', 'Единица измерения'])
                written = rpc('form', session=sid, request={'jsonrpc':'2.0','id':1,'method':'form.event',
                    'params':{'event':'command','control':'WriteButton','revision':app.sessions[sid][0].session.revision}})
                self.assertIsNone(written['error']);self.assertIsNone(written['form']['result']['error'])
                self.assertEqual(broker.posting_configuration, config)
            finally:
                app.close();broker.close()

    def test_child_process_forwards_exact_profile_and_binding(self):
        with patch.object(ConfigurationProcess, '_start') as start:
            ConfigurationProcess(ROOT/'examples/demo', 'demo.sqlite', main_demo_application=True, launch_binding='binding')
        command = start.call_args.args[0]
        self.assertIn('--main-demo-application', command)
        self.assertNotIn('--inventory-enum-application', command)
        self.assertEqual(command[-2:], ['--launch-binding','binding'])
        self.assertEqual(configuration_route(main_demo_application=True), 'main-demo')
