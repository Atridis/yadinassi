"""Finite headless session and independent client, not native form semantics."""
import io
from contextlib import redirect_stderr
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from ui_catalog_fixture import repository
from yadinassi.catalog_backend import BackendError, Capabilities
from uuid import UUID
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from scripts.ui_catalog_bridge import main as bridge_main
from scripts.ui_catalog_client import HeadlessCatalogClient
from yadinassi.ui.browser import CatalogBrowserSession
from yadinassi.ui.protocol import MAX_LINE_BYTES, PROTOCOL, CatalogRef, encode_line, encode_value

ROOT = Path(__file__).resolve().parents[1]


class UIBrowserTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.path, self.before, self.source = repository(self)
        self.session = CatalogBrowserSession(self.repo)
        self.client = HeadlessCatalogClient(self.session.exchange)

    def request(self, request_id, method='ui.event', **params):
        return [json.loads(line) for line in self.session.exchange(encode_line({
            'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}))]

    def event(self, request_id, revision=0, event='close', **values):
        return self.request(request_id, formId='catalog-browser', baseRevision=revision,
                            event=event, **values)

    def error(self, messages, code):
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['error']['data']['reason'], code)

    def test_independent_client_complete_navigation_and_resync(self):
        hello = self.client.hello()
        self.assertFalse(hello['capabilities']['canWrite'])
        state = self.client.event('selectCatalog', catalog=self.source['product'])
        self.assertEqual(state['state']['list']['total'], 3)
        view = self.repo.load(self.source['product'])
        target = self.repo.load(self.source['category']).cards[0].reference
        source_card, source_field = next((card, field) for card in view.cards
            for field, value in zip(card.fields, card.values) if value == target)
        state = self.client.event('openCard', reference=encode_value(source_card.reference))
        self.assertEqual(state['state']['kind'], 'card')
        state = self.client.event('followReference', field=source_field.name)
        self.assertEqual(state['state']['card']['reference'], encode_value(target))
        self.assertEqual(self.client.request('ui.snapshot', {}), state)
        self.client.event('page', offset=1, limit=1)
        self.assertEqual(self.client.snapshot['state']['list']['rows'], [])
        self.client.event('close')
        self.assertTrue(self.client.closed)
        self.error(self.request(8, 'ui.snapshot'), 'closed')
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_version_handshake_sequence_and_consumed_failure_id(self):
        self.error(self.event(1), 'handshake')
        self.error(self.request(2, 'ui.hello', protocol='yadinassi-ui/1'), 'version')
        self.assertEqual(len(self.request(3, 'ui.hello', protocol=PROTOCOL)), 2)
        self.error(self.request(3, 'ui.snapshot'), 'sequence')
        self.error(self.request(4, 'ui.hello', protocol=PROTOCOL), 'handshake')
        self.assertEqual(self.request(5, 'ui.snapshot')[0]['result']['revision'], 0)

    def test_stale_event_never_reads_or_changes_revision(self):
        self.client.hello()
        with mock.patch.object(self.repo, 'load', side_effect=AssertionError('must not load')):
            self.error(self.event(2, revision=1, event='selectCatalog',
                                 catalog=self.repo.inventory()[0].identity), 'stale_revision')
        self.assertEqual(self.request(3, 'ui.snapshot')[0]['result']['revision'], 0)

    def test_invalid_events_and_forged_cross_catalog_refs(self):
        state = self.client.hello()
        catalogs = state['state']['catalogs']
        self.client.event('selectCatalog', catalog=self.source['product'])
        reference = {**self.client.snapshot['state']['list']['rows'][0]['reference'],
                     'catalog': self.source['category']}
        self.error(self.event(3, revision=1, event='openCard', reference=reference), 'catalog_identity')
        self.error(self.event(4, revision=1, event='followReference', field='Description'), 'reference_field')
        self.error(self.event(5, revision=1, event='page', offset=999, limit=1), 'page')
        self.error(self.event(6, revision=1, event='Write'), 'invalid_message')
        self.assertEqual(self.request(7, 'ui.snapshot')[0]['result']['revision'], 1)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_encoding_failure_does_not_publish_partial_state(self):
        self.client.hello()
        with mock.patch.object(self.session, '_state', return_value={'oversize': 'x' * 9000}):
            self.error(self.event(2, event='selectCatalog',
                catalog=self.repo.inventory()[0].identity), 'message_limit')
        state = self.request(3, 'ui.snapshot')[0]['result']['snapshot']
        self.assertEqual(state['revision'], 0)
        self.assertEqual(state['state']['kind'], 'catalogs')

    def test_nested_entry_is_rejected_without_consuming_outer_id(self):
        self.client.hello()
        original = self.repo.load
        def reentrant(identity):
            self.error(self.event(999), 'busy')
            return original(identity)
        with mock.patch.object(self.repo, 'load', side_effect=reentrant):
            self.assertEqual(len(self.event(2, event='selectCatalog',
                catalog=self.repo.inventory()[0].identity)), 2)
        self.assertEqual(self.request(3, 'ui.snapshot')[0]['result']['revision'], 1)

    def test_internal_error_is_finite_no_trace_path_or_partial_state(self):
        self.client.hello()
        with mock.patch.object(self.repo, 'load', side_effect=RuntimeError('/private/path secret')):
            messages = self.event(2, event='selectCatalog', catalog=self.repo.inventory()[0].identity)
        self.error(messages, 'internal_error')
        self.assertNotIn('private', json.dumps(messages))
        self.assertEqual(self.request(3, 'ui.snapshot')[0]['result']['revision'], 0)

    def test_closed_view_rejects_cached_snapshot_but_can_close_session(self):
        self.client.hello()
        self.repo.close()
        messages = self.request(2, 'ui.snapshot')
        self.error(messages, 'catalog_unavailable')
        self.assertEqual(messages[0]['error']['data']['capability'], 'not-established')
        self.assertEqual(len(self.event(3)), 2)

    def test_request_budget(self):
        self.client.hello()
        self.session._requests = 4096
        self.error(self.request(2, 'ui.snapshot'), 'request_limit')

    def test_client_notifications_have_no_reply_or_effect_and_unknown_method_is_rpc_error(self):
        self.client.hello()
        notification = encode_line({'jsonrpc': '2.0', 'method': 'ui.event', 'params': {
            'formId': 'catalog-browser', 'baseRevision': 0, 'event': 'close'}})
        self.assertEqual(self.session.exchange(notification), ())
        messages = self.request(2, 'callProcedure', handler='Save')
        self.error(messages, 'method_not_found')
        self.assertEqual(messages[0]['error']['code'], -32601)
        self.assertEqual(self.request(3, 'ui.snapshot')[0]['result']['revision'], 0)

    def test_stdio_example_and_oversized_input_termination(self):
        hello = encode_line({'jsonrpc': '2.0', 'id': 1, 'method': 'ui.hello',
                             'params': {'protocol': PROTOCOL}})
        target = io.BytesIO()
        self.assertEqual(bridge_main([str(self.path)], source=io.BytesIO(hello), target=target), 0)
        messages = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]['method'], 'ui.open')
        target = io.BytesIO()
        self.assertEqual(bridge_main([str(self.path)],
            source=io.BytesIO(b'x' * (MAX_LINE_BYTES + 1) + hello), target=target), 1)
        self.assertEqual(len(target.getvalue().splitlines()), 1)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_source_tree_subprocess_client_uses_public_wire_only(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/ui_catalog_client.py'),
                                 str(self.path)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b'')
        states = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([state['state']['kind'] for state in states], ['catalogs', 'list', 'card'])
        self.assertFalse(states[-1]['capabilities']['canWrite'])
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_bridge_opens_readonly_and_closes_backend_on_eof_oversize_and_broken_pipe(self):
        hello = encode_line({'jsonrpc': '2.0', 'id': 1, 'method': 'ui.hello',
                             'params': {'protocol': PROTOCOL}})
        opened = []
        def open_backend(path, *, read_only):
            self.assertTrue(read_only)
            backend = SQLiteCatalogBackend(path, read_only=read_only)
            opened.append(backend)
            self.assertFalse(backend.capabilities().catalog_update)
            return backend
        class BrokenTarget:
            def write(self, raw): raise BrokenPipeError('private failure detail')
            def flush(self): pass
        for source, target, expected in ((hello, io.BytesIO(), 0),
                (b'x' * (MAX_LINE_BYTES + 1), io.BytesIO(), 1),
                (hello, BrokenTarget(), 1)):
            diagnostic = io.StringIO()
            with mock.patch('scripts.ui_catalog_bridge.SQLiteCatalogBackend', side_effect=open_backend), redirect_stderr(diagnostic):
                self.assertEqual(bridge_main([str(self.path)], source=io.BytesIO(source), target=target), expected)
            self.assertNotIn('private failure detail', diagnostic.getvalue())
            with self.assertRaisesRegex(BackendError, '^closed$'): opened[-1].begin_read()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_bridge_cleanup_failures_are_finite_and_attempt_backend_close(self):
        hello = encode_line({'jsonrpc': '2.0', 'id': 1, 'method': 'ui.hello',
                             'params': {'protocol': PROTOCOL}})
        for view_error, backend_error in ((BackendError('storage_error'), None),
                                          (None, OSError('/private/backend-detail'))):
            view = mock.Mock(database_id=UUID(int=7), configuration_generation=1)
            view.catalogs.return_value = ()
            view.close.side_effect = view_error
            backend = mock.Mock()
            backend.capabilities.return_value = Capabilities()
            backend.begin_read.return_value = view
            backend.close.side_effect = backend_error
            diagnostic = io.StringIO()
            with mock.patch('scripts.ui_catalog_bridge.SQLiteCatalogBackend', return_value=backend), redirect_stderr(diagnostic):
                self.assertEqual(bridge_main([str(self.path)], source=io.BytesIO(hello), target=io.BytesIO()), 1)
            view.close.assert_called_once_with()
            backend.close.assert_called_once_with()
            self.assertEqual(diagnostic.getvalue(), 'Headless catalog cleanup failed.\n')

    def test_bridge_constructor_rejection_keeps_backend_close_ownership(self):
        backend = mock.Mock()
        diagnostic = io.StringIO()
        with mock.patch('scripts.ui_catalog_bridge.SQLiteCatalogBackend', return_value=backend), \
             mock.patch('scripts.ui_catalog_bridge.CatalogRepository', side_effect=TypeError('/private/constructor')), \
             redirect_stderr(diagnostic):
            self.assertEqual(bridge_main([str(self.path)], source=io.BytesIO(), target=io.BytesIO()), 1)
        backend.close.assert_called_once_with()
        self.assertNotIn('/private/', diagnostic.getvalue())

    def test_bridge_missing_database_never_creates_or_leaks_path(self):
        missing = self.path.parent / 'private-missing.sqlite'
        diagnostic = io.StringIO()
        with redirect_stderr(diagnostic):
            self.assertEqual(bridge_main([str(missing)], source=io.BytesIO(), target=io.BytesIO()), 1)
        self.assertFalse(missing.exists())
        self.assertNotIn('private-missing', diagnostic.getvalue())

    def test_independent_client_rejects_forged_ids_and_snapshot_revisions_before_mutation(self):
        original = {'formId': 'catalog-browser', 'revision': 2, 'state': {}, 'capabilities': {}}
        for result_revision, snapshot_revision, form_id, reply_id in (
                (2, 2, 'other-form', 1), (2, 1, 'catalog-browser', 1),
                (3, 3, 'catalog-browser', 1), (1, 1, 'catalog-browser', 1),
                (True, True, 'catalog-browser', 1), (2, 2, 'catalog-browser', True)):
            reply = {'jsonrpc': '2.0', 'id': reply_id, 'result': {
                'protocol': PROTOCOL, 'revision': result_revision,
                'snapshot': {**original, 'formId': form_id, 'revision': snapshot_revision}}}
            client = HeadlessCatalogClient(lambda raw: (encode_line(reply),))
            client.snapshot, client.revision = original, 2
            with self.assertRaises(ValueError): client.request('ui.snapshot', {})
            self.assertIs(client.snapshot, original)
            self.assertEqual(client.revision, 2)
            self.assertFalse(client.closed)

    def test_independent_client_rejects_boolean_patch_revision(self):
        self.client.hello()
        original = self.client.snapshot
        self.client.exchange = lambda raw: tuple(encode_line(message) for message in (
            {'jsonrpc': '2.0', 'id': 2, 'result': {'protocol': PROTOCOL, 'revision': 1}},
            {'jsonrpc': '2.0', 'method': 'ui.patch', 'params': {
                'formId': 'catalog-browser', 'baseRevision': False, 'revision': True, 'state': {}}}))
        with self.assertRaises(ValueError): self.client.event('close')
        self.assertIs(self.client.snapshot, original)
        self.assertEqual(self.client.revision, 0)


if __name__ == '__main__': unittest.main()
