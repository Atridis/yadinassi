"""Deterministic ownership/lifetime checks; no browser, sleep or user database."""
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import Mock

from yadinassi.ui.browser_session import BrowserSession, AttachmentError, MAX_ATTACHMENTS
from yadinassi.ui.local_app import LocalUIServer


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.host = BrowserSession('a' * 43, clock=lambda: self.now, lease_seconds=10, grace_seconds=3)
        self.writer = self.attach(1)

    def attach(self, instance, token=None):
        return self.host.attach('a' * 43 if token is None else token, f'{instance:032x}')

    def command(self, item, action, pending=False, generation=None):
        return self.host.command(item['credential'], item['attachment'], action,
                                 item['generation'] if generation is None else generation, pending)

    def dispatch(self, item):
        return self.host.dispatch(item['credential'], item['attachment'], item['generation'])

    def test_second_original_url_is_observer_not_independent_writer(self):
        other = self.attach(2)
        self.assertEqual((self.writer['role'], other['role']), ('writer', 'observer'))
        with self.assertRaisesRegex(AttachmentError, 'not_writer'):
            with self.dispatch(other): self.fail('must not dispatch')

    def test_takeover_fences_old_generation_before_effect(self):
        other = self.attach(2); other.update(self.command(other, 'takeover'))
        with self.assertRaisesRegex(AttachmentError, 'not_writer'):
            with self.dispatch(self.writer): self.fail('old writer')
        with self.dispatch(other): pass

    def test_launcher_is_not_an_rpc_credential(self):
        with self.assertRaisesRegex(AttachmentError, 'unauthorized'):
            with self.host.dispatch('a' * 43, self.writer['attachment'], self.writer['generation']): pass

    def test_resume_does_not_steal_live_owner(self):
        other = self.attach(2, self.writer['resume'])
        self.assertEqual(other['role'], 'observer')
        self.assertNotEqual(other['credential'], self.writer['credential'])

    def test_reload_after_detach_can_reclaim_without_business_retry(self):
        self.command(self.writer, 'detach')
        other = self.attach(2, self.writer['resume'])
        self.assertEqual(other['role'], 'writer')
        with self.assertRaisesRegex(AttachmentError, 'not_writer'):
            with self.dispatch(self.writer): pass

    def test_duplicate_attachment_admission_is_idempotent(self):
        self.assertEqual(self.attach(1), self.writer)
        resumed = self.attach(2, self.writer['resume'])
        self.assertEqual(self.attach(2, self.writer['resume']), resumed)
        self.assertEqual(len(self.host._attachments), 2)

    def test_foreign_resume_is_not_authority(self):
        with self.assertRaisesRegex(AttachmentError, 'unauthorized'): self.attach(2, 'b' * 43)

    def test_expired_resume_requires_original_launch_link(self):
        self.now = 86401
        with self.assertRaisesRegex(AttachmentError, 'unauthorized'):
            self.attach(2, self.writer['resume'])

    def test_capacity_is_bounded(self):
        for i in range(2, MAX_ATTACHMENTS + 1): self.attach(i)
        with self.assertRaisesRegex(AttachmentError, 'capacity'): self.attach(MAX_ATTACHMENTS + 1)

    def test_takeover_cannot_interrupt_admitted_rpc(self):
        other = self.attach(2)
        with self.dispatch(self.writer):
            with self.assertRaisesRegex(AttachmentError, 'busy'): self.command(other, 'takeover')

    def test_failed_admitted_rpc_keeps_unknown_outcome_across_takeover(self):
        other = self.attach(2)
        with self.assertRaisesRegex(OSError, 'lost'):
            with self.dispatch(self.writer): raise OSError('lost')
        with self.assertRaisesRegex(AttachmentError, 'outcome_unknown'): self.command(other, 'takeover')
        with self.assertRaisesRegex(AttachmentError, 'outcome_unknown'):
            with self.dispatch(self.writer): pass

    def test_lease_expiry_fences_bfcache_document(self):
        self.now = 11
        with self.assertRaisesRegex(AttachmentError, 'not_writer'):
            with self.dispatch(self.writer): pass
        self.assertEqual(self.command(self.writer, 'heartbeat')['role'], 'observer')

    def test_hidden_tab_heartbeat_is_not_detach(self):
        self.now = 9; self.command(self.writer, 'heartbeat')
        self.now = 18
        with self.dispatch(self.writer): pass

    def test_shutdown_never_runs_without_any_attachment(self):
        host = BrowserSession('b' * 43, clock=lambda: self.now)
        self.now = 10000; close = Mock(return_value=True)
        self.assertFalse(host.idle_shutdown(close)); close.assert_not_called()

    def test_detach_has_no_lifecycle_effect_and_grace_allows_return(self):
        close = Mock(return_value=True)
        self.command(self.writer, 'detach')
        self.now = 2; self.assertFalse(self.host.idle_shutdown(close))
        self.attach(2, self.writer['resume'])
        self.now = 4; self.assertFalse(self.host.idle_shutdown(close)); close.assert_not_called()

    def test_last_observer_prevents_shutdown(self):
        other = self.attach(2); self.command(self.writer, 'detach')
        self.now = 4; close = Mock(return_value=True)
        self.assertFalse(self.host.idle_shutdown(close)); close.assert_not_called()
        self.command(other, 'detach'); self.now = 8
        self.assertTrue(self.host.idle_shutdown(close)); close.assert_called_once_with()

    def test_pending_raw_input_retains_host_instead_of_discard(self):
        self.command(self.writer, 'detach', pending=True)
        self.now = 4; close = Mock(return_value=True)
        self.assertFalse(self.host.idle_shutdown(close)); close.assert_not_called()
        other = self.attach(2, self.writer['resume']); self.assertTrue(other['recovery'])

    def test_unknown_outcome_never_calls_idle_shutdown(self):
        with self.assertRaises(OSError):
            with self.dispatch(self.writer): raise OSError()
        self.command(self.writer, 'detach'); self.now = 4; close = Mock(return_value=True)
        self.assertFalse(self.host.idle_shutdown(close)); close.assert_not_called()

    def test_refused_lifecycle_is_not_repeated_every_tick(self):
        self.command(self.writer, 'detach'); self.now = 4; close = Mock(return_value=False)
        self.assertFalse(self.host.idle_shutdown(close))
        self.now = 8; self.assertFalse(self.host.idle_shutdown(close)); close.assert_called_once_with()
        self.assertTrue(self.attach(2)['recovery'])

    def test_closed_host_does_not_accept_new_tab(self):
        self.command(self.writer, 'detach'); self.now = 4
        self.assertTrue(self.host.idle_shutdown(lambda: True))
        with self.assertRaisesRegex(AttachmentError, 'closed'): self.attach(2)

    def test_invalid_identity_generation_and_pending_are_closed(self):
        for value in (True, -1, '1', 2**53):
            with self.assertRaisesRegex(AttachmentError, 'invalid_message'):
                self.command(self.writer, 'heartbeat', generation=value)
        with self.assertRaisesRegex(AttachmentError, 'invalid_message'):
            self.command(self.writer, 'heartbeat', pending='false')
        with self.assertRaisesRegex(AttachmentError, 'invalid_message'): self.host.attach('a' * 43, 'bad')


class AttachmentHTTPTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Mock()
        self.bridge.exchange.side_effect = lambda r: {'jsonrpc': '2.0', 'id': r['id'], 'result': {'state': {'kind': 'catalogs'}}}
        self.server = LocalUIServer(self.bridge, 'a' * 43, browser_session=True)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start(); self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def post(self, path, value, token=None, item=None, **extra):
        headers = {'Host': self.server.authority, 'Origin': self.server.origin,
                   'Content-Type': 'application/x-ndjson', 'X-Yadinassi-Session': token or self.server.token}
        if item:
            headers.update({'X-Yadinassi-Session': item['credential'],
                'X-Yadinassi-Attachment': item['attachment'], 'X-Yadinassi-Generation': str(item['generation'])})
        headers.update(extra)
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request('POST', path, json.dumps(value)+'\n', headers)
            r = connection.getresponse(); raw = r.read()
            try: value = json.loads(raw)
            except ValueError: value = raw
            return r.status, value
        finally: connection.close()

    def attach(self, n):
        status, r = self.post('/attachment', {'action': 'attach', 'instance': f'{n:032x}'})
        self.assertEqual(status, 200); return r

    def rpc(self, item=None):
        return self.post('/rpc', {'jsonrpc':'2.0','id':1,'method':'editor.hello','params':{}}, item=item)

    def test_original_capability_cannot_bypass_writer_profile(self):
        self.assertEqual(self.rpc()[0], 403); self.bridge.exchange.assert_not_called()

    def test_writer_rpc_and_observer_refusal_before_effect(self):
        first, second = self.attach(1), self.attach(2)
        self.assertEqual(self.rpc(first)[0], 200)
        self.assertEqual(self.rpc(second)[0], 409)
        self.assertEqual(self.bridge.exchange.call_count, 1)

    def test_origin_still_required_for_attachment(self):
        code, _ = self.post('/attachment', {'action':'attach','instance':'1'*32}, Origin='https://other.invalid')
        self.assertEqual(code, 403); self.assertEqual(len(self.server.attachments._attachments), 0)

    def test_detach_does_not_dispatch_close(self):
        first = self.attach(1)
        status, value = self.post('/attachment', {'action':'detach','generation':first['generation'],'pending':False}, item=first)
        self.assertEqual((status, value['role']), (200, 'observer')); self.bridge.exchange.assert_not_called()

    def test_takeover_invalidates_old_request(self):
        first, second = self.attach(1), self.attach(2)
        code, state = self.post('/attachment', {'action':'takeover','generation':second['generation'],'pending':False}, item=second)
        self.assertEqual(code, 200); second.update(state)
        self.assertEqual(self.rpc(first)[0], 409); self.assertEqual(self.rpc(second)[0], 200)
        self.assertEqual(self.bridge.exchange.call_count, 1)

    def test_profile_is_explicit_in_launch_url(self):
        self.assertTrue(self.server.launch_url.endswith('&attachment=1'))

    def test_attachment_body_is_closed(self):
        code, value = self.post('/attachment', {'action':'attach','instance':'1'*32,'source':'not allowed'})
        self.assertEqual(code, 409); self.assertEqual(value['error'], 'invalid_message')

    def test_business_exception_locks_without_exposing_payload(self):
        first = self.attach(1); self.bridge.exchange.side_effect = OSError('/private')
        code, value = self.rpc(first); self.assertEqual(code, 503); self.assertNotIn(b'/private', value)
        code, value = self.rpc(first); self.assertEqual(code, 409); self.assertEqual(value['error'], 'outcome_unknown')
        self.assertEqual(self.bridge.exchange.call_count, 1)


if __name__ == '__main__': unittest.main()
