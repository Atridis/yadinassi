"""Explicit editing wire version and authoritative outcomes, including failures."""
import io
import json
from contextlib import redirect_stderr
from unittest import mock
import unittest

from ui_catalog_fixture import repository
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.catalog_editor import CatalogEditorApplication
from yadinassi.ui.editor_protocol import CatalogEditorSession, PROTOCOL
from yadinassi.ui.protocol import encode_line, encode_value
from scripts.ui_catalog_editor_bridge import main as bridge_main


class CatalogEditorProtocolTests(unittest.TestCase):
    def setUp(self):
        old, self.path, self.before, self.ids = repository(self); old.close()
        self.app = CatalogEditorApplication(SQLiteDBContext(self.path))
        self.addCleanup(self.app.close)
        self.session = CatalogEditorSession(self.app)
        self.request_id = 0

    def request(self, method, **params):
        self.request_id += 1
        return json.loads(self.session.exchange(encode_line({'jsonrpc': '2.0', 'id': self.request_id,
            'method': method, 'params': params})))

    def hello(self): return self.request('editor.hello', protocol=PROTOCOL)
    def event(self, event, **params):
        return self.request('editor.event', event=event, baseRevision=self.session.revision, **params)
    def open_new(self):
        self.hello(); self.event('selectCatalog', catalog=self.ids['category']); self.event('create')

    def test_separate_version_and_exact_authority(self):
        self.assertIn('error', self.request('editor.hello', protocol='yadinassi-ui/0'))
        self.assertIn('result', self.hello())
        for method, params in (('eval', {'source': 'Message(1)'}), ('editor.snapshot', {'path': '/private'}),
                ('editor.event', {'event': 'command', 'baseRevision': 0, 'control': 'SaveButton', 'handler': 'Write'})):
            self.assertIn('error', self.request(method, **params))
        self.assertEqual(self.session.revision, 0)

    def test_postcommit_list_refresh_error_has_no_success_ack_and_recovers(self):
        self.open_new()
        self.event('change', control='InputData0', value=encode_value('20'))
        with mock.patch.object(self.app, '_load', side_effect=OSError('/private/read-failure')):
            failed = self.event('command', control='SaveButton')
        self.assertNotIn('result', failed)
        self.assertEqual(failed['error']['data']['reason'], 'refresh_required')
        state = failed['error']['data']['snapshot']['state']
        self.assertIsNone(state['list'])
        self.assertEqual(state['editor']['saveState'], 'committed')
        self.assertTrue(state['editor']['editingLocked'])
        self.assertNotIn('/private/', json.dumps(failed))
        from yadinassi.sqlite_catalog import _View
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('must not replay write')):
            recovered = self.event('command', control='SaveButton')['result']
        self.assertEqual(recovered['state']['list']['total'], 2)
        self.assertEqual(recovered['state']['editor']['saveState'], 'saved')

    def test_complete_wire_create_save_and_authoritative_error_snapshot(self):
        self.open_new()
        self.event('change', control='InputData0', value=encode_value('10'))
        rejected = self.event('command', control='SaveButton')
        data = rejected['error']['data']
        self.assertEqual(data['reason'], 'duplicate_code')
        self.assertEqual(data['snapshot']['revision'], self.session.revision)
        self.assertTrue(data['snapshot']['state']['editor']['dirty'])
        self.event('change', control='InputData0', value=encode_value('20'))
        saved = self.event('command', control='SaveButton')['result']
        self.assertEqual(saved['state']['editor']['saveState'], 'saved')
        self.assertFalse(saved['state']['editor']['isNew'])
        self.assertIn('result', self.event('closeCard'))
        self.assertEqual(self.app.snapshot()['state']['list']['total'], 2)

    def test_stale_and_duplicate_requests_do_not_dispatch(self):
        self.hello(); self.event('selectCatalog', catalog=self.ids['category'])
        with mock.patch.object(self.app, 'event', side_effect=AssertionError('must not dispatch')):
            reply = self.request('editor.event', event='create', baseRevision=0)
            self.assertEqual(reply['error']['data']['reason'], 'stale_revision')
            repeated = self.session.exchange(encode_line({'jsonrpc': '2.0', 'id': self.request_id,
                'method': 'editor.event', 'params': {'event': 'create', 'baseRevision': self.session.revision}}))
            self.assertEqual(json.loads(repeated)['error']['data']['reason'], 'sequence')

    def test_handler_error_retains_mutation_and_updated_form_snapshot(self):
        self.open_new()
        form = self.app.editor.form; invoke = form._invoke
        def failed(handler, side, arguments):
            result = invoke(handler, side, arguments)
            if handler == 'SaveCommand':
                form.form.set_member('Data1', 'mutated before error')
                raise RuntimeError('/private/handler-secret')
            return result
        before = form.revision
        with mock.patch.object(form, '_invoke', failed): reply = self.event('command', control='SaveButton')
        snapshot = reply['error']['data']['snapshot']['state']['editor']
        self.assertEqual(snapshot['formRevision'], before + 1)
        self.assertEqual(snapshot['fields'][1]['value']['value'], 'mutated before error')
        self.assertNotIn('/private/', json.dumps(reply))

    def test_close_error_returns_current_open_state_not_closed_ack(self):
        self.open_new()
        form = self.app.editor.form; event = form._event
        def failed(name, arguments):
            if name == 'onclose': raise OSError('/private/close-secret')
            return event(name, arguments)
        before = form.revision
        with mock.patch.object(form, '_event', failed): reply = self.event('closeCard')
        snapshot = reply['error']['data']['snapshot']['state']['editor']
        self.assertEqual(snapshot['state'], 'open')
        self.assertEqual(snapshot['formRevision'], before + 1)
        self.assertNotIn('/private/', json.dumps(reply))

    def test_boolean_counters_and_unknown_reference_input_are_rejected(self):
        self.hello()
        revision = self.session.revision
        for params in ({'event': 'create', 'baseRevision': True},
                       {'event': 'change', 'baseRevision': 0, 'control': 'InputCategory',
                        'value': {'type': 'Object', 'value': 'not admitted'}}):
            self.assertIn('error', self.request('editor.event', **params))
        self.assertEqual(self.session.revision, revision)

    def test_nested_request_is_busy_and_cannot_execute_save_twice(self):
        self.open_new(); self.event('change', control='InputData0', value=encode_value('20'))
        original = self.app.editor.object.write
        def nested():
            reply = self.session.exchange(encode_line({'jsonrpc': '2.0', 'id': 999,
                'method': 'editor.event', 'params': {'event': 'command', 'control': 'SaveButton',
                                                   'baseRevision': self.session.revision}}))
            self.assertEqual(json.loads(reply)['error']['data']['reason'], 'busy')
            original()
        with mock.patch.object(self.app.editor.object, 'write', nested): self.event('command', control='SaveButton')
        self.event('closeCard')
        self.assertEqual(self.app.snapshot()['state']['list']['total'], 2)

    def test_bridge_uses_explicit_file_and_does_not_create_missing_database(self):
        target = io.BytesIO()
        hello = encode_line({'jsonrpc': '2.0', 'id': 1, 'method': 'editor.hello', 'params': {'protocol': PROTOCOL}})
        self.assertEqual(bridge_main([str(self.path)], source=io.BytesIO(hello), target=target), 0)
        self.assertEqual(json.loads(target.getvalue())['result']['protocol'], PROTOCOL)
        missing = self.path.parent / 'missing.sqlite'; diagnostic = io.StringIO()
        with redirect_stderr(diagnostic):
            self.assertEqual(bridge_main([str(missing)], source=io.BytesIO(), target=io.BytesIO()), 1)
        self.assertFalse(missing.exists()); self.assertNotIn(str(missing), diagnostic.getvalue())

    def test_boolean_deletion_mark_wire_roundtrip_discard_and_list(self):
        self.hello(); self.event('selectCatalog', catalog=self.ids['category'])
        reference = self.app.snapshot()['state']['list']['rows'][0]['reference']
        self.event('openCard', reference=reference)
        field = next(f for f in self.app.editor.snapshot()['fields'] if f['name'] == 'DeletionMark')
        before = self.app.editor.snapshot()
        wrong = self.event('change', control=field['control'], value=encode_value('true'))
        self.assertEqual(wrong['error']['data']['reason'], 'invalid_value')
        self.assertEqual(self.app.editor.snapshot(), before)
        changed = self.event('change', control=field['control'], value=encode_value(True))
        self.assertTrue(changed['result']['state']['editor']['dirty'])
        self.event('command', control='CancelButton')
        row = self.app.snapshot()['state']['list']['rows'][0]
        self.assertEqual(row['deletionMark'], encode_value(False))
        self.event('openCard', reference=reference)
        self.event('change', control=field['control'], value=encode_value(True))
        saved = self.event('command', control='SaveButton')
        self.assertIn('result', saved)
        self.event('closeCard')
        row = self.app.snapshot()['state']['list']['rows'][0]
        self.assertEqual(row['reference'], reference)
        self.assertEqual(row['deletionMark'], encode_value(True))
