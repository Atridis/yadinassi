"""Optional loopback-only renderer plugin; the child runtime owns the database.

This is not the future yadinassi client/server protocol. Only static assets and
one bounded NDJSON proxy are exposed. The default BSL CLI never starts it.
"""
import argparse
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import os
from pathlib import Path
import secrets
import subprocess
import sys
from threading import BoundedSemaphore, Lock, Thread
from queue import Empty, Full, Queue
import webbrowser

from .protocol import MAX_COUNTER, MAX_LINE_BYTES, UIError, decode_line, encode_line
from .browser_session import BrowserSession, AttachmentError, PROTOCOL as ATTACHMENT_PROTOCOL


class LocalTransportError(ValueError):
    pass


EXCHANGE_TIMEOUT = 30


class RuntimeBridge:
    """One persistent child and sequential transport; never retries a write."""
    def __init__(self, database):
        environment = dict(os.environ)
        environment['PYTHONIOENCODING'] = 'utf-8'
        if getattr(sys, 'frozen', False):
            command = [sys.executable, '--catalog-ui-runtime', database]
        else:
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
            command = [sys.executable, '-m', 'yadinassi.ui.editor_stdio', database]
        self._start(command, environment)

    def _start(self, command, environment):
        self.child = subprocess.Popen(command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment, bufsize=0)
        self.gate = Lock()
        self.counter = 0
        self.started = False
        self.failed = False
        self._requests = Queue(maxsize=1)
        self._replies = Queue(maxsize=1)
        self._closed = False
        self._worker = Thread(target=self._pipe_worker, daemon=True)
        self._worker.start()

    def _pipe_worker(self):
        # One persistent worker bounds the complete write + read, including a
        # child which stops reading its stdin. No per-request thread accumulation.
        while not self._closed:
            raw = self._requests.get()
            if raw is None or self._closed:
                return
            try:
                remaining = memoryview(raw)
                while remaining:
                    count = self.child.stdin.write(remaining)
                    if not count: raise OSError('closed pipe')
                    remaining = remaining[count:]
                reply = self.child.stdout.readline(MAX_LINE_BYTES + 1)
            except (OSError, ValueError):
                reply = b''
            try: self._replies.put_nowait(reply)
            except Full: return
            if not reply or len(reply) > MAX_LINE_BYTES:
                return

    def exchange(self, request):
        if not self.gate.acquire(blocking=False): raise LocalTransportError('busy')
        try:
            if self._closed or self.failed or self.counter >= 4096: raise LocalTransportError('unavailable')
            self.counter += 1
            forwarded = {**request, 'id': self.counter}
            # A newly opened renderer reattaches by reading state, never replaying
            # the last event. Child request IDs belong to this persistent plugin.
            if (request['method'] == 'editor.hello' and self.started
                    and request['params'] == {'protocol': 'yadinassi-editor/0'}):
                forwarded.update(method='editor.snapshot', params={})
            self._requests.put_nowait(encode_line(forwarded))
            raw = self._replies.get(timeout=EXCHANGE_TIMEOUT)
            if not raw or len(raw) > MAX_LINE_BYTES: raise LocalTransportError('unavailable')
            response = decode_line(raw)
            if (type(response) is not dict or response.get('jsonrpc') != '2.0'
                    or type(response.get('id')) is not int or response['id'] != self.counter
                    or ('result' in response) == ('error' in response)):
                raise LocalTransportError('unavailable')
            if request['method'] == 'editor.hello' and 'result' in response:
                self.started = True
            return {**response, 'id': request['id']}
        except (OSError, UIError, LocalTransportError, Empty, Full):
            self.failed = True
            raise LocalTransportError('unavailable') from None
        finally:
            self.gate.release()

    def close(self):
        if self._closed: return
        self._closed = True
        idle = self.gate.acquire(blocking=False)
        try:
            # Never close a buffered pipe behind an active writer. Failed/busy
            # children terminate first, which releases blocked pipe operations.
            if (not idle or self.failed) and self.child.poll() is None:
                self.child.terminate()
            elif self.child.poll() is None:
                self.child.stdin.close()  # unbuffered: no implicit blocking flush
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.child.kill(); self.child.wait(timeout=5)
        finally:
            try: self._requests.put_nowait(None)
            except Full: pass
            self._worker.join(timeout=1)
            for stream in (self.child.stdin, self.child.stdout):
                try: stream.close()
                except OSError: pass
            if idle: self.gate.release()



_ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
           '/style.css': ('style.css', 'text/css; charset=utf-8'),
           '/LICENSE.txt': ('LICENSE.txt', 'text/plain; charset=utf-8')}
_CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


class _Handler(BaseHTTPRequestHandler):
    asset_directory = 'catalog'
    methods = ('editor.hello', 'editor.snapshot', 'editor.event')
    protocol_version = 'HTTP/1.1'
    server_version = 'YadinassiLocalUI'
    sys_version = ''

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *unused):
        pass  # Never log capability URLs, paths, request bodies or database data.

    def _reply(self, status, body=b'Request rejected\n', kind='text/plain; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', _CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body); self.wfile.flush()

    def _host(self):
        return self.headers.get_all('Host') == [self.server.authority]

    def do_GET(self):
        if not self._host(): return self._reply(403)
        asset = _ASSETS.get(self.path)
        if asset is None: return self._reply(404)
        try: body = files('yadinassi.ui').joinpath('assets', self.asset_directory, asset[0]).read_bytes()
        except (OSError, ValueError): return self._reply(503)
        return self._reply(200, body, asset[1])

    def do_POST(self):
        attachment = self.path == '/attachment' and self.server.attachments is not None
        if (not self._host() or (self.path != '/rpc' and not attachment)
                or self.headers.get_all('Origin') != [self.server.origin]
                or self.headers.get_all('Content-Type') != ['application/x-ndjson']
                or self.headers.get('Sec-Fetch-Site', 'same-origin') != 'same-origin'):
            return self._reply(403)
        tokens = self.headers.get_all('X-Yadinassi-Session')
        if (tokens is None or len(tokens) != 1 or not 32 <= len(tokens[0]) <= 128
                or not tokens[0].isascii()
                or (self.server.attachments is None and not secrets.compare_digest(tokens[0], self.server.token))):
            return self._reply(403)
        lengths = self.headers.get_all('Content-Length')
        if lengths is None or len(lengths) != 1 or self.headers.get_all('Transfer-Encoding'):
            return self._reply(411)
        if not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 6:
            return self._reply(413)
        length = int(lengths[0])
        if not 1 <= length <= (8192 if attachment else MAX_LINE_BYTES): return self._reply(413)
        self.connection.settimeout(5)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length: return self._reply(400)
            request = decode_line(raw)
            if attachment:
                return self._attachment_request(tokens[0], request)
            if (type(request) is not dict or set(request) != {'jsonrpc', 'id', 'method', 'params'}
                    or request['jsonrpc'] != '2.0' or type(request['id']) is not int
                    or not 1 <= request['id'] <= MAX_COUNTER or type(request['params']) is not dict
                    or request['method'] not in self.methods):
                return self._reply(400)
            guard = nullcontext()
            if self.server.attachments is not None:
                identity = self._attachment_identity()
                epochs = self.headers.get_all('X-Yadinassi-Generation')
                if (epochs is None or len(epochs) != 1 or not epochs[0].isascii()
                        or not epochs[0].isdigit() or len(epochs[0]) > 16):
                    raise AttachmentError('invalid_message')
                guard = self.server.attachments.dispatch(tokens[0], identity, int(epochs[0]))
            with guard:
                response = self.server.bridge.exchange(request)
                result = encode_line(response)
                self.server.last_response = response
                if (self.server.attachments is not None
                        and response.get('result', {}).get('state', {}).get('kind') == 'closed'):
                    self.server.attachments.mark_closed()
        except AttachmentError as error:
            return self._attachment_error(str(error))
        except (UIError, ValueError, OSError, TypeError):
            return self._reply(503)
        try:
            self._reply(200, result, 'application/x-ndjson; charset=utf-8')
        finally:
            # A completed close still releases owned resources if its HTTP reply
            # is lost. Never keep a closed form/database alive for a dead browser.
            if response.get('result', {}).get('state', {}).get('kind') == 'closed':
                Thread(target=self.server.shutdown, daemon=True).start()

    def _attachment_identity(self):
        values = self.headers.get_all('X-Yadinassi-Attachment')
        if values is None or len(values) != 1 or len(values[0]) > 32:
            raise AttachmentError('unauthorized')
        return values[0]

    def _attachment_error(self, code):
        return self._reply(403 if code == 'unauthorized' else 409,
            encode_line({'protocol': ATTACHMENT_PROTOCOL, 'error': code}),
            'application/x-ndjson; charset=utf-8')

    def _attachment_request(self, token, request):
        if type(request) is not dict:
            raise AttachmentError('invalid_message')
        if request.get('action') == 'attach':
            if set(request) != {'action', 'instance'}:
                raise AttachmentError('invalid_message')
            result = self.server.attachments.attach(token, request['instance'])
        else:
            if set(request) != {'action', 'generation', 'pending'}:
                raise AttachmentError('invalid_message')
            result = self.server.attachments.command(token, self._attachment_identity(),
                request['action'], request['generation'], request['pending'])
        return self._reply(200, encode_line(result), 'application/x-ndjson; charset=utf-8')

    def do_OPTIONS(self): self._reply(405)
    def do_PUT(self): self._reply(405)
    def do_DELETE(self): self._reply(405)


class LocalUIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, bridge, token=None, *, handler=_Handler, browser_session=False,
                 idle_close=None):
        self.bridge = bridge
        self._connections = BoundedSemaphore(8)
        self.token = secrets.token_urlsafe(32) if token is None else token
        if type(self.token) is not str or not 32 <= len(self.token) <= 128 or not self.token.isascii():
            raise ValueError('invalid local UI capability')
        if type(browser_session) is not bool or (idle_close is not None and not callable(idle_close)):
            raise ValueError('invalid browser lifecycle profile')
        self.attachments = BrowserSession(self.token) if browser_session else None
        self._idle_close = idle_close if idle_close is not None else self._close_known_idle
        self.last_response = None
        super().__init__(('127.0.0.1', 0), handler)
        self.authority = f'127.0.0.1:{self.server_port}'
        self.origin = 'http://' + self.authority

    def process_request(self, request, address):
        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self._connections.release()

    def handle_error(self, request, address):
        # Network errors must not print request/capability/path-bearing tracebacks.
        pass

    def service_actions(self):
        if self.attachments is None or self._idle_close is None:
            return
        try:
            closed = self.attachments.idle_shutdown(self._idle_close)
        except (AttachmentError, ValueError, OSError):
            return
        if closed:
            # service_actions executes in serve_forever's thread; shutdown must
            # run elsewhere, or HTTPServer would deadlock waiting for itself.
            Thread(target=self.shutdown, daemon=True).start()

    def _close_known_idle(self):
        """Existing bounded UI profiles can close only a provably idle snapshot.

        No snapshot/error recovery is fabricated here, and no save/discard event
        is selected. The ordinary close handler may still cancel the operation.
        """
        response = self.last_response
        result = response.get('result') if type(response) is dict else None
        if type(result) is not dict or result.get('error') is not None:
            return False
        state = result.get('state')
        if type(state) is not dict or state.get('uncertain'):
            return False
        protocol = result.get('protocol')
        if protocol == 'yadinassi-editor/0':
            editor = state.get('editor')
            if state.get('kind') == 'editor':
                if (type(editor) is not dict or editor.get('dirty') is not False
                        or editor.get('saveState') not in ('new', 'saved', 'unchanged')):
                    return False
            elif state.get('kind') not in ('catalogs', 'list'):
                return False
            if type(result.get('revision')) is not int:
                return False
            method, params = 'editor.event', {'event':'close','baseRevision':result['revision']}
        elif protocol == 'yadinassi-form-ui/1':
            if state.get('dirty') is not False or type(state.get('revision')) is not int:
                return False
            method, params = 'form.event', {'event':'close','revision':state['revision']}
        elif protocol in ('yadinassi-orders-workspace/1', 'yadinassi-reference-orders/1'):
            if state.get('sessions') != []:
                return False
            method, params = 'workspace.close', {}
        else:
            return False
        response = self.bridge.exchange({'jsonrpc':'2.0','id':1,'method':method,'params':params})
        encode_line(response)
        self.last_response = response
        return response.get('result', {}).get('state', {}).get('kind') == 'closed'

    @property
    def launch_url(self):
        return self.origin + '/#session=' + self.token + ('&attachment=1' if self.attachments is not None else '')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Optional local catalog editor. Plain yadinassi BSL mode is unchanged.')
    parser.add_argument('--f', required=True, metavar='SQLITE_FILE', help='Existing supported local SQLite application')
    parser.add_argument('--open-browser', action='store_true', help='Explicitly open the launch URL in your browser')
    parser.add_argument('--browser-session', action='store_true', help='Single writer attachment, reconnect and safe idle lifetime')
    args = parser.parse_args(argv)
    bridge = server = None
    try:
        bridge = RuntimeBridge(args.f)
        server = LocalUIServer(bridge, browser_session=args.browser_session)
        print('Yadinassi catalog editor — local-only; references are read-only.')
        print('Open this per-launch URL (do not share it):')
        print(server.launch_url, flush=True)
        if args.open_browser: webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Local catalog editor unavailable.', file=sys.stderr)
        return 1
    finally:
        cleanup_failed = False
        for owned, method in ((server, 'server_close'), (bridge, 'close')):
            try:
                if owned is not None: getattr(owned, method)()
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            print('Local catalog editor cleanup failed.', file=sys.stderr)
            return 1


if __name__ == '__main__': raise SystemExit(main())
