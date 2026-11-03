"""Closed public-data loopback oracle fixture; no external destinations or logs.

Only the owning native HTTP lane may start this fixture. It neither starts 1C nor
changes the container's network namespace/security settings. Native sessions stay
sequential; this single HTTP server handles requests one at a time.
"""
from contextlib import contextmanager
import http.server
import io
import time
import threading

MAX_REQUESTS = 128
MAX_BODY = 8192
MAX_HEADERS = 100
MAX_HEADER_BYTES = 16384
SOCKET_SECONDS = 2
METHODS = frozenset(('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'))


class FixtureError(ValueError):
    pass


class _Server(http.server.HTTPServer):
    allow_reuse_address = False
    def __init__(self):
        self.requests_seen = 0
        self.failure = False
        super().__init__(('127.0.0.1', 0), _Handler)
    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(SOCKET_SECONDS)
        return sock, address
    def handle_error(self, request, client_address):
        self.failure = True  # Never print request data, addresses or tracebacks.


class _Reader(io.RawIOBase):
    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self.raw = sock.makefile('rb', buffering=0)
        self.deadline = time.monotonic() + SOCKET_SECONDS
    def readable(self): return True
    def readinto(self, target):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('fixture_request_timeout')
        self.sock.settimeout(remaining)
        return self.raw.readinto(target)
    def close(self):
        if not self.closed: self.raw.close()
        super().close()


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'OwnedHTTPFixture/1'
    sys_version = ''
    def setup(self):
        super().setup()
        self.rfile.close()
        self.rfile = io.BufferedReader(_Reader(self.connection))
    def log_message(self, *args):
        pass
    def send_error(self, code, message=None, explain=None):
        self.close_connection = True
        self.send_response_only(400)
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
    def do_GET(self): self._reply()
    def do_HEAD(self): self._reply()
    def do_POST(self): self._reply()
    def do_PUT(self): self._reply()
    def do_PATCH(self): self._reply()
    def do_DELETE(self): self._reply()
    def do_OPTIONS(self): self._reply()
    def _reply(self):
        self.close_connection = True
        self.server.requests_seen += 1
        if self.server.requests_seen > MAX_REQUESTS:
            self.server.failure = True
            self.send_error(400); return
        headers = list(self.headers.items())
        if (len(headers) > MAX_HEADERS or
            sum(len(k) + len(v) + 4 for k, v in headers) > MAX_HEADER_BYTES or
            self.headers.get('Transfer-Encoding') is not None or
            len(self.headers.get_all('Content-Length', [])) > 1):
            self.server.failure = True
            self.send_error(400); return
        length = self.headers.get('Content-Length', '0')
        if not length.isascii() or not length.isdecimal() or len(length) > 5:
            self.server.failure = True
            self.send_error(400); return
        count = int(length)
        if count > MAX_BODY:
            self.server.failure = True
            self.send_error(400); return
        request = self.rfile.read(count)
        if len(request) != count:
            self.server.failure = True
            self.send_error(400); return
        status = 200; kind = 'text/plain; charset=utf-8'; extra = []
        if self.path == '/text': data = 'я😀'.encode('utf-8')
        elif self.path == '/latin':
            data = 'Привет'.encode('cp1251'); kind = 'text/plain; charset=windows-1251'
        elif self.path == '/binary': data = b'\x00\xffA'; kind = 'application/octet-stream'
        elif self.path == '/empty': status = 204; data = b''
        elif self.path == '/missing': status = 404; data = b'missing'
        elif self.path == '/redirect':
            status = 302; data = b'redirect'; extra = [('Location', '/text')]
        elif self.path == '/verbs' and self.command == 'OPTIONS': data = b'OPTIONS'
        elif self.path == '/echo':
            data = request; kind = 'application/octet-stream'; extra = [('X-Method', self.command)]
        elif self.path == '/headers':
            data = b'ok'; extra = [('X-Fixture', 'owned'), ('X-Dup', 'a'), ('X-Dup', 'b')]
        elif self.path == '/query?a=1': data = b'query'
        else:
            self.server.failure = True
            self.send_error(400); return
        self.send_response_only(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Connection', 'close')
        for name, value in extra: self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD' and status != 204: self.wfile.write(data)


@contextmanager
def owned_fixture():
    server = _Server()
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={'poll_interval': 0.05}, daemon=True)
    try:
        thread.start()
    except BaseException:
        server.server_close()
        raise
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(SOCKET_SECONDS + 1)
        if thread.is_alive(): raise FixtureError('fixture_cleanup_failed')
        if server.failure: raise FixtureError('fixture_request_failed')
