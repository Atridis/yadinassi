"""Mixed forms use the actual owned process, not a mocked transport."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from business_configuration_fixture import sources
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.configuration_app import ConfigurationController, ConfigurationProcess, PROTOCOL, load_application, main


class BusinessApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'source'; self.root.mkdir()
        self.files = sources()
        for path, data in self.files.items():
            target = self.root / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        self.path = Path(temporary.name) / 'business.sqlite'
        SQLiteCatalogBackend.create_business_application(self.path, self.files).close()
        self.process = ConfigurationProcess(self.root, self.path, business_application=True)
        self.addCleanup(self.process.close)
        self.app = ConfigurationController(load_application(self.root, business_application=True),
                                           self.process.exchange, business_application=True)
        self.addCleanup(self.app.close)
        self.rpc('hello', protocol=PROTOCOL)

    def rpc(self, method, **params):
        result = self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
        self.assertIsNone(result['error']); return result

    def entry(self, name): return self.app.names[name.casefold()]

    def test_startup_and_mixed_entry_owners(self):
        self.assertEqual(self.app.application_messages, ['4'])
        self.assertEqual(len(self.app.definitions), 4)
        for name in ('Catalog.Items.Form.Card', 'Document.Orders.Form.Card'):
            self.assertEqual(self.rpc('catalog', entry=self.entry(name))['state']['catalog']['rows'], [])

    def test_document_write_and_independent_catalog_lifetime(self):
        catalog = self.rpc('open', entry=self.entry('Catalog.Items.Form.Card'), request='catalog')['session']
        self.rpc('catalog', entry=self.entry('Document.Orders.Form.Card'))
        document = self.rpc('open', entry=self.entry('Document.Orders.Form.Card'), request='document')['session']
        def event(sid, event, **params):
            result = self.rpc('form', session=sid, request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
                'event':event,'revision':self.app.sessions[sid][0].session.revision,**params}})
            self.assertIsNone(result['form']['result']['error']); return result
        saved = event(document, 'command', control='SaveButton')
        self.assertEqual(len(saved['state']['catalog']['rows']), 1)
        event(document, 'close')
        self.assertIn(catalog, self.app.sessions)
        self.assertNotIn(document, self.app.sessions)
        self.assertFalse(self.app.application.interpreter._family_released)

    def test_old_profiles_do_not_activate_mixed_source(self):
        for flags in ({}, {'application_host':True}, {'document_objects':True}, {'catalog_objects':True}):
            with self.subTest(flags=flags), self.assertRaises(ValueError): load_application(self.root, **flags)

    def test_explicit_cli_requires_database_and_single_profile(self):
        for args in ([str(self.root),'--business-application'],
                     [str(self.root),'--business-application','--document-objects','--f',str(self.path)]):
            with mock.patch('sys.stderr'), self.assertRaises(SystemExit) as result: main(args)
            self.assertEqual(result.exception.code, 2)
