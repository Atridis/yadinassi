"""Bounded local renderer transport; no external browser/server or user database."""
import http.client
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from threading import Thread
import unittest
from unittest import mock

from ui_catalog_fixture import repository
from yadinassi.ui.local_app import LocalUIServer, RuntimeBridge, LocalTransportError, main
from yadinassi.ui.protocol import MAX_LINE_BYTES


class LocalRendererHTTPTests(unittest.TestCase):
    def setUp(self):
        self.bridge = mock.Mock()
        self.bridge.exchange.side_effect = lambda request: {'jsonrpc': '2.0', 'id': request['id'],
            'result': {'state': {'kind': 'catalogs'}}}
        self.server = LocalUIServer(self.bridge, 'a' * 43)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def request(self, method='POST', path='/rpc', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        body = b'{"jsonrpc":"2.0","id":1,"method":"editor.hello","params":{}}\n' if body is None else body
        values = {'Host': self.server.authority, 'Origin': self.server.origin,
            'Content-Type': 'application/x-ndjson', 'X-Yadinassi-Session': self.server.token,
            'Sec-Fetch-Site': 'same-origin'}
        values.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally: connection.close()

    def test_valid_request_and_security_headers(self):
        code, headers, raw = self.request()
        self.assertEqual(code, 200); self.assertEqual(json.loads(raw)['id'], 1)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_host_origin_capability_and_fetch_scope_rejected_before_dispatch(self):
        for headers in ({'Host': 'localhost:1234'}, {'Origin': 'https://other.invalid'},
                {'X-Yadinassi-Session': 'b' * 43}, {'Sec-Fetch-Site': 'cross-site'},
                {'Content-Type': 'text/plain'}):
            self.assertEqual(self.request(headers=headers)[0], 403)
        self.bridge.exchange.assert_not_called()

    def test_static_asset_allowlist_and_no_path_query_access(self):
        for path in ('/../pyproject.toml', '/app.js?x=1', '/database.sqlite', '/rpc'):
            self.assertEqual(self.request('GET', path)[0], 404)
        with mock.patch('yadinassi.ui.local_app.files') as assets:
            assets.return_value.joinpath.return_value.read_bytes.return_value = b'owned asset'
            code, headers, raw = self.request('GET', '/')
        self.assertEqual((code, raw), (200, b'owned asset'))
        self.bridge.exchange.assert_not_called()

    def test_no_cors_or_other_mutation_methods(self):
        for method in ('OPTIONS', 'PUT', 'DELETE'):
            # Rejection happens before body consumption. Do not race an unused
            # JSON upload with the deliberate connection close on Windows.
            code, headers, unused = self.request(method, body=b'')
            self.assertEqual(code, 405); self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.bridge.exchange.assert_not_called()

    def test_bounded_body_and_duplicate_json_reject_before_dispatch(self):
        # The server rejects the declared size before reading a body. Sending a
        # large body concurrently with that deliberate close races TCP reset on
        # some hosts and tests the client socket buffer, not this admission gate.
        self.assertEqual(self.request(body=b'', headers={'Content-Length': str(MAX_LINE_BYTES + 1)})[0], 413)
        self.assertEqual(self.request(body=b'{"id":1,"id":2}')[0], 503)
        self.assertEqual(self.request(body=b'{"jsonrpc":"2.0","id":true,"method":"editor.hello","params":{}}')[0], 400)
        self.bridge.exchange.assert_not_called()

    def test_finite_transport_failure_does_not_expose_details(self):
        self.bridge.exchange.side_effect = LocalTransportError('/private/token/database')
        code, unused, raw = self.request()
        self.assertEqual(code, 503); self.assertNotIn(b'/private', raw)
        self.assertEqual(self.bridge.exchange.call_count, 1)

    def test_missing_assets_are_finite(self):
        with mock.patch('yadinassi.ui.local_app.files', side_effect=OSError('/private/assets')):
            code, unused, raw = self.request('GET', '/')
        self.assertEqual(code, 503); self.assertNotIn(b'/private', raw)

    def test_duplicate_security_headers_are_rejected(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.putrequest('POST', '/rpc', skip_host=True)
            for name, value in (('Host', self.server.authority), ('Host', self.server.authority),
                    ('Origin', self.server.origin), ('Content-Type', 'application/x-ndjson'),
                    ('X-Yadinassi-Session', self.server.token), ('Content-Length', '2')):
                connection.putheader(name, value)
            connection.endheaders(b'{}')
            response = connection.getresponse(); self.assertEqual(response.status, 403); response.read()
        finally: connection.close()
        self.bridge.exchange.assert_not_called()


class LocalRendererRuntimeTests(unittest.TestCase):
    def test_real_child_reattaches_without_replaying_or_reopening_database(self):
        repository_object, path, unused, ids = repository(self); repository_object.close()
        bridge = RuntimeBridge(str(path)); self.addCleanup(bridge.close)
        hello = {'jsonrpc': '2.0', 'id': 1, 'method': 'editor.hello', 'params': {'protocol': 'yadinassi-editor/0'}}
        self.assertEqual(bridge.exchange(hello)['result']['revision'], 0)
        selected = bridge.exchange({'jsonrpc': '2.0', 'id': 2, 'method': 'editor.event',
            'params': {'event': 'selectCatalog', 'catalog': ids['category'], 'baseRevision': 0}})
        self.assertEqual(selected['result']['revision'], 1)
        reattached = bridge.exchange(hello)
        self.assertEqual(reattached['id'], 1)
        self.assertEqual(reattached['result']['revision'], 1)
        self.assertEqual(reattached['result']['state']['list']['catalog'], ids['category'])

    def test_child_failure_is_finite_and_does_not_create_database(self):
        repository_object, path, unused, ids = repository(self); repository_object.close()
        missing = path.parent / 'does-not-exist.sqlite'
        bridge = RuntimeBridge(str(missing)); self.addCleanup(bridge.close)
        with self.assertRaisesRegex(LocalTransportError, '^unavailable$'):
            bridge.exchange({'jsonrpc': '2.0', 'id': 1, 'method': 'editor.hello', 'params': {}})
        self.assertFalse(missing.exists()); self.assertTrue(bridge.failed)

    def test_main_never_opens_browser_without_explicit_option(self):
        with mock.patch('yadinassi.ui.local_app.RuntimeBridge') as runtime, \
                mock.patch('yadinassi.ui.local_app.LocalUIServer') as server, \
                mock.patch('yadinassi.ui.local_app.webbrowser.open') as browser, redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--f', 'owned.sqlite']), 0)
        browser.assert_not_called(); runtime.return_value.close.assert_called_once()
        server.return_value.server_close.assert_called_once()

    def test_cleanup_failure_is_finite_attempts_both_resources_and_fails(self):
        diagnostic = io.StringIO()
        with mock.patch('yadinassi.ui.local_app.RuntimeBridge') as runtime, \
                mock.patch('yadinassi.ui.local_app.LocalUIServer') as server, \
                redirect_stdout(io.StringIO()), redirect_stderr(diagnostic):
            server.return_value.server_close.side_effect = OSError('/private/socket')
            self.assertEqual(main(['--f', 'owned.sqlite']), 1)
        runtime.return_value.close.assert_called_once(); self.assertNotIn('/private', diagnostic.getvalue())

    def test_constructor_failure_closes_already_started_child(self):
        with mock.patch('yadinassi.ui.local_app.RuntimeBridge') as runtime, \
                mock.patch('yadinassi.ui.local_app.LocalUIServer', side_effect=OSError('/private/socket')), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--f', 'owned.sqlite']), 1)
        runtime.return_value.close.assert_called_once()

    def test_invalid_host_capability_rejected_before_bind(self):
        with self.assertRaises(ValueError): LocalUIServer(mock.Mock(), 'short')

    def test_whole_exchange_timeout_covers_blocked_pipe_write_and_cleanup(self):
        from threading import Event
        started, released = Event(), Event(); order = []
        child = mock.Mock(); child.poll.return_value = None
        def write(raw):
            started.set()
            if not released.wait(1): raise OSError('bounded fake pipe deadline')
            raise OSError('child terminated')
        child.stdin.write.side_effect = write
        child.stdin.close.side_effect = lambda: order.append('stdin_close')
        child.stdout.close.side_effect = lambda: order.append('stdout_close')
        def terminate():
            order.append('terminate'); child.poll.return_value = 0; released.set()
        child.terminate.side_effect = terminate
        with mock.patch('yadinassi.ui.local_app.subprocess.Popen', return_value=child), \
                mock.patch('yadinassi.ui.local_app.EXCHANGE_TIMEOUT', .02):
            bridge = RuntimeBridge('owned.sqlite')
            try:
                with self.assertRaises(LocalTransportError):
                    bridge.exchange({'jsonrpc': '2.0', 'id': 1, 'method': 'editor.hello', 'params': {}})
                self.assertTrue(started.wait(.5)); self.assertTrue(bridge.failed)
            finally: bridge.close()
        self.assertFalse(bridge._worker.is_alive())
        self.assertLess(order.index('terminate'), order.index('stdin_close'))
        self.assertEqual(child.stdin.write.call_count, 1)

    def test_partial_unbuffered_pipe_writes_are_completed_once(self):
        child = mock.Mock(); child.poll.return_value = 0; written = bytearray()
        def write(raw):
            size = min(3, len(raw)); written.extend(raw[:size]); return size
        child.stdin.write.side_effect = write
        child.stdout.readline.return_value = b'{"jsonrpc":"2.0","id":1,"result":{}}\n'
        with mock.patch('yadinassi.ui.local_app.subprocess.Popen', return_value=child) as create:
            bridge = RuntimeBridge('owned.sqlite')
            try:
                response = bridge.exchange({'jsonrpc': '2.0', 'id': 7, 'method': 'editor.hello', 'params': {}})
                self.assertEqual(response['id'], 7); self.assertEqual(json.loads(written)['id'], 1)
            finally: bridge.close()
        self.assertEqual(create.call_args.kwargs['bufsize'], 0)
        self.assertFalse(bridge._worker.is_alive())
