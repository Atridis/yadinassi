"""Configuration documents through the actual owned process and opaque UI RPC."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.protocol import encode_value
from yadinassi.ui.configuration_app import ConfigurationController, ConfigurationProcess, PROTOCOL, load_application, main

ROOT = Path(__file__).resolve().parents[1] / 'examples/configuration-document-forms'


class DocumentApplicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'documents.sqlite'
        files = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        SQLiteCatalogBackend.create_document_forms(self.path, files).close()
        self.process = ConfigurationProcess(ROOT, self.path, document_objects=True)
        self.addCleanup(self.process.close)
        self.app = ConfigurationController(load_application(ROOT, document_objects=True), self.process.exchange)
        self.addCleanup(self.app.close)
        self.rpc('hello', protocol=PROTOCOL)

    def rpc(self, method, **params):
        result = self.app.exchange({'jsonrpc': '2.0', 'id': 1, 'method': 'application.'+method, 'params': params})['result']
        self.assertIsNone(result['error']); return result

    def open(self, request='first', record=None):
        return self.rpc('open' if record is None else 'openRecord', entry=1, request=request,
                        **({} if record is None else {'record': record}))['session']

    def event(self, sid, event='command', **params):
        if event == 'cell': params['value'] = encode_value(params['value'])
        result = self.rpc('form', session=sid, request={'jsonrpc':'2.0', 'id':1, 'method':'form.event', 'params':{
            'event':event, 'revision':self.app.sessions[sid][0].session.revision, **params}})
        self.assertIsNone(result['form']['result']['error']); return result

    def test_actual_child_write_reopen_and_immediate_list_refresh(self):
        self.assertEqual(self.rpc('catalog', entry=1)['state']['catalog']['rows'], [])
        sid = self.open()
        self.event(sid, control='NewLineButton')
        self.event(sid, 'cell', control='LinesTable', row=1, column='Label', value='Owned process row')
        saved = self.event(sid, control='WriteButton')
        rows = saved['state']['catalog']['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {'key','number','date','deletionMark'})
        self.assertTrue(rows[0]['number']); self.assertNotIn(str(self.path), repr(saved))
        closed = self.event(sid, 'close')
        with self.assertRaisesRegex(ValueError, 'record is not in the selected catalog projection'):
            self.open('stale-second', rows[0]['key'])
        reopened = self.open('second', closed['state']['catalog']['rows'][0]['key'])
        form = self.app.sessions[reopened][0].session.form
        self.assertEqual(next(iter(form._tables.values()))._snapshot().rows[0][1][0], 'Owned process row')
        self.assertEqual(form._data['status'], 'Rows loaded: 1')

    def test_independent_unsaved_form_and_dirty_close(self):
        one, two = self.open(), self.open('second')
        self.event(two, control='NewLineButton')
        self.event(two, 'cell', control='LinesTable', row=1, column='Label', value='Do not overwrite')
        self.event(one, control='WriteButton')
        self.event(two, 'close')
        self.assertIn(two, self.app.sessions)
        self.assertEqual(next(iter(self.app.sessions[two][0].session.form._tables.values()))._snapshot().rows[0][1][0], 'Do not overwrite')
        self.event(two, control='WriteButton'); self.event(two, 'close')
        self.assertNotIn(two, self.app.sessions)

    def test_opaque_keys_never_accept_raw_document_identity(self):
        self.rpc('catalog', entry=1)
        with self.assertRaises(ValueError):
            self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.openRecord','params':{
                'entry':1,'request':'invalid','record':'00000000-0000-0000-0000-000000000001'}})
        self.assertEqual(self.app.sessions, {})

    def test_default_and_combined_activation_refused(self):
        for flags in ({}, {'catalog_objects':True}, {'document_objects':True,'application_host':True}):
            with self.assertRaises(ValueError): load_application(ROOT, **flags)

    def test_document_cli_requires_database_and_explicit_separate_profile(self):
        for args in ([str(ROOT),'--document-objects'], [str(ROOT),'--document-objects','--application-host','--f',str(self.path)]):
            with mock.patch('sys.stderr'), self.assertRaises(SystemExit) as result: main(args)
            self.assertEqual(result.exception.code, 2)


if __name__ == '__main__': unittest.main()
