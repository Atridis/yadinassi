"""The shipped mixed application crosses the real owned server boundary."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.configuration_app import ConfigurationController, ConfigurationProcess, PROTOCOL, load_application
from yadinassi.ui.protocol import encode_value

ROOT = Path(__file__).resolve().parents[1] / 'examples/configuration-business-application'


class BusinessExampleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'business.sqlite'
        files = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        SQLiteCatalogBackend.create_business_application(self.path, files).close()
        self.process = ConfigurationProcess(ROOT, self.path, business_application=True)
        self.addCleanup(self.process.close)
        self.app = ConfigurationController(load_application(ROOT, business_application=True),
                                           self.process.exchange, business_application=True)
        self.addCleanup(self.app.close)
        self.started = self.rpc('hello', protocol=PROTOCOL)
        self.welcome = next(iter(self.app.sessions))

    def rpc(self, method, **params):
        result = self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
        self.assertIsNone(result['error']); return result

    def event(self, sid, event='command', **params):
        if 'value' in params: params['value'] = encode_value(params['value'])
        result = self.rpc('form', session=sid, request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
            'event':event,'revision':self.app.sessions[sid][0].session.revision,**params}})
        self.assertIsNone(result['form']['result']['error']); return result

    def navigate(self, control):
        before = set(self.app.sessions); self.event(self.welcome, control=control)
        added = set(self.app.sessions) - before
        self.assertEqual(len(added), 1); return added.pop()

    def entry(self, name): return self.app.names[name.casefold()]

    def test_startup_servercall_and_commonmodule_navigation(self):
        self.assertEqual(self.started['state']['messages'], ['Calculated in the owned server process', '8'])
        details = self.navigate('DetailsButton')
        self.assertIn('Products, categories', self.app.sessions[details][0].session.form._data['messagetext'])
        self.assertEqual(len(self.app.definitions), 5)

    def test_mixed_declared_forms_share_lifetime_not_form_context(self):
        product = self.navigate('NewProductButton')
        category = self.navigate('NewCategoryButton')
        order = self.navigate('NewOrderButton')
        self.event(category, 'close')
        self.assertIn(product, self.app.sessions); self.assertIn(order, self.app.sessions)
        self.assertNotIn(category, self.app.sessions)
        module = self.app.application._modules['tools', 'client'].interpreter
        self.assertNotIn('object', module.variables); self.assertNotIn('items', module.variables)

    def test_catalog_preparation_write_and_immediate_selected_list(self):
        self.rpc('catalog', entry=self.entry('Catalog.Products.Form.Card'))
        product = self.navigate('NewProductButton')
        self.event(product, 'change', control='CodeInput', value='P1')
        self.event(product, 'change', control='DescriptionInput', value='  Product  ')
        self.event(product, 'change', control='PriceInput', value=Decimal('12.5'))
        saved = self.event(product, control='SaveButton')
        self.assertEqual(saved['state']['catalog']['rows'][0]['description'], 'Product')
        self.assertEqual(self.app.sessions[product][0].session.form._data['status'], 'saved')

    def test_document_lines_durable_reopen_and_dirty_close(self):
        entry = self.entry('Document.Orders.Form.Card'); self.rpc('catalog', entry=entry)
        order = self.navigate('NewOrderButton')
        self.event(order, control='NewLineButton')
        self.event(order, 'cell', control='LinesTable', row=1, column='Label', value='Durable business line')
        self.event(order, 'close'); self.assertIn(order, self.app.sessions)
        saved = self.event(order, control='WriteButton')
        record = saved['state']['catalog']['rows'][0]['key']
        closed = self.event(order, 'close')
        with self.assertRaisesRegex(ValueError, 'record is not in the selected catalog projection'):
            self.rpc('openRecord', entry=entry, request='stale-reopen', record=record)
        record = closed['state']['catalog']['rows'][0]['key']
        reopened = self.rpc('openRecord', entry=entry, request='reopen', record=record)['session']
        form = self.app.sessions[reopened][0].session.form
        self.assertEqual(form._data['status'], 'Rows loaded: 1')
        self.assertEqual(next(iter(form._tables.values()))._snapshot().rows[0][1][0], 'Durable business line')

    def test_clean_mixed_family_closes_without_terminating_sibling_early(self):
        self.navigate('NewOrderButton'); self.navigate('NewCategoryButton')
        for sid in tuple(self.app.sessions): self.event(sid, 'close')
        self.assertEqual(self.rpc('close')['state']['kind'], 'closed')
