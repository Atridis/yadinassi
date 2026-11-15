import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


def configuration(call='Message(Catalogs.Items.Answer());', body='Function Answer() Export\nReturn 42;\nEndFunction', family='Catalog', folder='Catalogs', session=True):
    xml = ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><'+family+' uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Items</Name></Properties></'+family+'></MetaDataObject>').encode()
    files = {folder+'/Items.xml': xml}
    if body is not None:
        files[folder+'/Items/Ext/ManagerModule.bsl'] = body.encode()
    if session:
        files['Ext/SessionModule.bsl'] = ('Procedure SessionParametersSetting(Names)\n'+call+'\nEndProcedure').encode()
    return source(b'' if session else ('Procedure OnStart()\n'+call+'\nEndProcedure').encode(), files)


class SourceManagerModuleTests(unittest.TestCase):
    def run_app(self, config):
        output = []
        app = SourceApplication(config, output=output.append)
        self.addCleanup(app.close)
        app.start()
        return output

    def test_exported_server_call(self):
        self.assertEqual(self.run_app(configuration()), ['42'])

    def test_all_namespaces(self):
        for family, folder in [('Catalog','Catalogs'),('Document','Documents'),('Report','Reports'),('DataProcessor','DataProcessors')]:
            with self.subTest(family=family):
                self.assertEqual(self.run_app(configuration('Message('+folder+'.Items.Answer());',family=family,folder=folder)), ['42'])

    def test_private_routine_is_not_exported(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration(body='Function Answer()\nReturn 42;\nEndFunction'))

    def test_unused_broken_module_is_lazy(self):
        self.assertEqual(self.run_app(configuration('', 'broken ???')), [])

    def test_client_does_not_gain_server_access(self):
        with self.assertRaisesRegex(BSLError, 'synchronous server'):
            self.run_app(configuration(session=False))

    def test_missing_module_not_fake_storage(self):
        with self.assertRaisesRegex(BSLError, 'v4 scratch capability'):
            self.run_app(configuration('Catalogs.Items.CreateItem();', body=None))

    def test_missing_manager(self):
        with self.assertRaisesRegex(BSLError, 'Unknown source manager'):
            self.run_app(configuration('Catalogs.Missing.Answer();'))

    def test_unsupported_storage_method_not_synthesized(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration('Catalogs.Items.CreateItem();'))

    def test_runtime_error_keeps_manager_source(self):
        with self.assertRaisesRegex(BSLError, 'ManagerModule.bsl'):
            self.run_app(configuration(body='Function Answer() Export\nReturn NotImplementedService();\nEndFunction'))

    def test_local_namespace_shadowing(self):
        self.assertEqual(self.run_app(configuration('Catalogs = 7; Message(Catalogs);')), ['7'])

    def test_initialization_rejected_not_silently_ignored(self):
        with self.assertRaisesRegex(BSLError, 'initialization'):
            self.run_app(configuration(body='Message("bad");\nFunction Answer() Export\nReturn 42;\nEndFunction'))

    def test_repeated_call_same_module(self):
        self.assertEqual(self.run_app(configuration('Message(Catalogs.Items.Answer()); Message(Catalogs.Items.Answer());')), ['42','42'])
