"""Owned HTTP/TLS/proxy end-to-end workflows; certificates generated per run.

The openssl executable is needed only by this local TLS fixture. No keys or
credentials are shipped, no public network is used, and no trust store changes.
"""
import base64
from http import client as native_client, server as native_server
from pathlib import Path
import os
import select
import shutil
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import urlsplit

from yadinassi import Interpreter
from yadinassi import http_client as http
from yadinassi import http_security as security
from yadinassi.maps import BSLMap


class Origin(native_server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def do_GET(self): self.reply()
    def do_POST(self): self.reply()
    def do_PUT(self): self.reply()
    def do_PATCH(self): self.reply()
    def do_DELETE(self): self.reply()
    def do_HEAD(self): self.reply()
    def do_OPTIONS(self): self.reply()
    def reply(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        record = (self.command, self.path, dict(self.headers), body)
        self.server.records.append(record)
        if self.path == '/auth':
            data = self.headers.get('Authorization', '').encode()
        elif self.path == '/echo':
            data = self.command.encode() + b':' + body
        else:
            data = self.path.encode()
        self.send_response(302 if self.path == '/redirect' else 200)
        self.send_header('Content-Length', str(len(data)))
        if self.path == '/redirect': self.send_header('Location', 'http://must-not-follow.invalid/')
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(data)


class Proxy(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        line = self.rfile.readline(8192).decode('ascii').rstrip('\r\n')
        method, target, version = line.split(' ')
        headers = {}
        while True:
            line = self.rfile.readline(8192)
            if line == b'\r\n': break
            if not line: return
            key, _, value = line.decode('latin-1').partition(':')
            headers[key.lower()] = value.strip()
        self.server.records.append((method, target, dict(headers)))
        if self.server.reject:
            self.wfile.write(b'HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n'); self.wfile.flush(); return
        if method == 'CONNECT':
            if target != 'localhost:' + str(self.server.tls_port):
                raise AssertionError('proxy fixture only permits owned TLS target')
            upstream = socket.create_connection(('127.0.0.1', self.server.tls_port), 5)
            with upstream:
                self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n'); self.wfile.flush()
                sockets = [self.connection, upstream]
                while True:
                    ready, _, _ = select.select(sockets, [], [], 5)
                    if not ready: return
                    for source in ready:
                        data = source.recv(65536)
                        if not data: return
                        (upstream if source is self.connection else self.connection).sendall(data)
        else:
            parsed = urlsplit(target)
            if parsed.netloc != 'localhost:' + str(self.server.http_port):
                raise AssertionError('proxy fixture only permits owned HTTP target')
            body = self.rfile.read(int(headers.get('content-length', '0')))
            headers.pop('proxy-authorization', None)
            upstream = native_client.HTTPConnection('127.0.0.1', self.server.http_port, timeout=5)
            try:
                upstream.request(method, parsed.path + ('?' + parsed.query if parsed.query else ''), body, headers)
                response = upstream.getresponse(); data = response.read()
                self.wfile.write(('HTTP/1.1 %d OK\r\nContent-Length: %d\r\n\r\n' % (response.status, len(data))).encode() + data)
                self.wfile.flush()
            finally: upstream.close()


@unittest.skipUnless(shutil.which('openssl'), 'TLS loopback fixture needs openssl executable')
class HTTPSTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        # Do not inherit host OpenSSL/LibreSSL request extensions or defaults.
        config = cls.root / 'openssl.cnf'
        config.write_text('''[req]
distinguished_name = dn
[dn]
[ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
[server]
subjectAltName = DNS:localhost
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
''', encoding='ascii')
        def openssl(*args):
            result = subprocess.run([shutil.which('openssl'), *args], cwd=cls.root,
                                    env=dict(os.environ, OPENSSL_CONF=str(config)),
                                    capture_output=True, timeout=30)
            if result.returncode: raise AssertionError('TLS fixture certificate generation or verification failed')
        openssl('req', '-config', str(config), '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem', '-days', '2', '-subj', '/CN=Yadinassi Ephemeral Test CA', '-extensions', 'ca')
        openssl('req', '-config', str(config), '-newkey', 'rsa:2048', '-sha256', '-nodes', '-keyout', 'server.key', '-out', 'server.csr', '-subj', '/CN=localhost')
        openssl('x509', '-req', '-sha256', '-in', 'server.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-CAcreateserial', '-out', 'server.pem', '-days', '2', '-extfile', str(config), '-extensions', 'server')
        openssl('verify', '-CAfile', 'ca.pem', '-purpose', 'sslserver', 'server.pem')
        cls.ca = security.BSLFileCertificationAuthorityCertificates(str(cls.root / 'ca.pem'))
        cls.tls = security.BSLOpenSSLSecureConnection(None, cls.ca)
        cls.origin = native_server.ThreadingHTTPServer(('127.0.0.1', 0), Origin); cls.origin.records = []
        cls.secure = native_server.ThreadingHTTPServer(('127.0.0.1', 0), Origin); cls.secure.records = []
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cls.root / 'server.pem'), str(cls.root / 'server.key'))
        cls.secure.socket = context.wrap_socket(cls.secure.socket, server_side=True)
        cls.proxy = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Proxy)
        cls.proxy.http_port, cls.proxy.tls_port = cls.origin.server_port, cls.secure.server_port
        cls.proxy.records = []; cls.proxy.reject = False
        cls.servers = [cls.origin, cls.secure, cls.proxy]; cls.threads = []
        for server in cls.servers:
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
            thread.start(); cls.threads.append(thread)
        cls.addClassCleanup(cls.stop_servers)

    @classmethod
    def stop_servers(cls):
        for server in cls.servers: server.shutdown(); server.server_close()
        for thread in cls.threads:
            thread.join(3)
            if thread.is_alive(): raise AssertionError('owned fixture did not stop')

    def setUp(self):
        self.origin.records.clear(); self.secure.records.clear(); self.proxy.records.clear(); self.proxy.reject = False

    def connection(self, **kwargs):
        return http.BSLHTTPConnection('localhost', self.secure.server_port, timeout=3, secure_connection=self.tls, **kwargs)

    def proxy_settings(self, protocol='https'):
        proxy = security.BSLInternetProxy(False)
        proxy.set(protocol, '127.0.0.1', self.proxy.server_address[1], 'proxy-demo', 'proxy-test')
        return proxy

    def test_https_all_seven_methods_with_binary_bodies(self):
        for method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
            request = http.BSLHTTPRequest('/echo'); request.set_body_from_string('a\x00b')
            result = self.connection().call_http_method(method, request)
            self.assertEqual(result.get_member('StatusCode'), 200)
            self.assertEqual(result.get_body_as_string(), '' if method == 'HEAD' else method + ':a\x00b')

    def test_https_basic_and_explicit_bearer(self):
        result = self.connection(user='demo', password='test').get(http.BSLHTTPRequest('/auth'))
        self.assertEqual(result.get_body_as_string(), 'Basic ZGVtbzp0ZXN0')
        headers = BSLMap(); headers.insert('Authorization', 'Bearer synthetic-test-token')
        result = self.connection().get(http.BSLHTTPRequest('/auth', headers))
        self.assertEqual(result.get_body_as_string(), 'Bearer synthetic-test-token')

    def test_plain_http_basic_is_explicit(self):
        connection = http.BSLHTTPConnection('localhost', self.origin.server_port, 'demo', 'test', timeout=3)
        self.assertEqual(connection.get(http.BSLHTTPRequest('/auth')).get_body_as_string(), 'Basic ZGVtbzp0ZXN0')

    def test_https_untrusted_ca_never_sends_auth_body_or_output(self):
        tls = security.BSLOpenSSLSecureConnection(None, security.BSLOSCertificationAuthorityCertificates())
        connection = http.BSLHTTPConnection('localhost', self.secure.server_port, 'demo', 'test', timeout=3, secure_connection=tls)
        target = self.root / 'protected'; target.write_bytes(b'keep')
        request = http.BSLHTTPRequest('/echo'); request.set_body_from_string('must-not-send')
        # An environment-only CA must not silently replace explicitly selected OS trust.
        with mock.patch.dict('os.environ', {'SSL_CERT_FILE': str(self.root / 'ca.pem'), 'SSL_CERT_DIR': str(self.root)}):
            with self.assertRaises(ValueError): connection.post(request, str(target))
        self.assertEqual(self.secure.records, [])
        self.assertEqual(target.read_bytes(), b'keep')

    def test_hostname_mismatch_never_sends_origin_request(self):
        connection = http.BSLHTTPConnection('127.0.0.1', self.secure.server_port, timeout=3, secure_connection=self.tls)
        with self.assertRaises(ValueError): connection.get(http.BSLHTTPRequest('/'))
        self.assertEqual(self.secure.records, [])

    def test_ca_snapshot_survives_file_replacement(self):
        path = self.root / 'copy.pem'; path.write_bytes((self.root / 'ca.pem').read_bytes())
        ca = security.BSLFileCertificationAuthorityCertificates(str(path)); path.write_bytes(b'replaced')
        tls = security.BSLOpenSSLSecureConnection(None, ca)
        connection = http.BSLHTTPConnection('localhost', self.secure.server_port, timeout=3, secure_connection=tls)
        self.assertEqual(connection.get(http.BSLHTTPRequest('/snapshot')).get_body_as_string(), '/snapshot')

    def test_https_output_file_and_request_file(self):
        source, target = self.root / 'body', self.root / 'response'
        source.write_bytes(b'file\x00bytes')
        request = http.BSLHTTPRequest('/echo'); request.set_body_file_name(str(source))
        try:
            response = self.connection().post(request, str(target))
            self.assertEqual(target.read_bytes(), b'POST:file\x00bytes')
            self.assertEqual(response.get_body_file_name(), str(target))
        finally: request.set_body_from_string('release')

    def test_https_redirects_are_returned_without_following_or_auth_forwarding(self):
        response = self.connection(user='demo', password='test').get(http.BSLHTTPRequest('/redirect'))
        self.assertEqual(response.get_member('StatusCode'), 302)
        self.assertEqual(len(self.secure.records), 1)

    def test_http_proxy_absolute_form_and_distinct_auth(self):
        connection = http.BSLHTTPConnection('localhost', self.origin.server_port, 'demo', 'test', self.proxy_settings('http'), 3)
        response = connection.get(http.BSLHTTPRequest('/auth?x=1'))
        method, target, headers = self.proxy.records[0]
        self.assertEqual(target, 'http://localhost:%d/auth?x=1' % self.origin.server_port)
        self.assertEqual(headers['proxy-authorization'], security.basic_authorization('proxy-demo', 'proxy-test'))
        self.assertEqual(headers['authorization'], security.basic_authorization('demo', 'test'))
        self.assertNotIn('Proxy-Authorization', self.origin.records[0][2])
        self.assertEqual(response.get_member('StatusCode'), 200)

    def test_connect_tunnel_carries_proxy_auth_only_then_verified_origin_auth(self):
        response = self.connection(user='demo', password='test', proxy=self.proxy_settings()).get(http.BSLHTTPRequest('/auth'))
        self.assertEqual(response.get_body_as_string(), 'Basic ZGVtbzp0ZXN0')
        method, target, headers = self.proxy.records[0]
        self.assertEqual(method, 'CONNECT')
        self.assertEqual(target, 'localhost:%d' % self.secure.server_port)
        self.assertIn('proxy-authorization', headers)
        self.assertNotIn('authorization', headers)
        self.assertNotIn('Proxy-Authorization', self.secure.records[0][2])

    def test_connect_failure_does_not_send_origin_credentials_or_body(self):
        self.proxy.reject = True
        request = http.BSLHTTPRequest('/echo'); request.set_body_from_string('must-not-send')
        with self.assertRaises(ValueError): self.connection(user='demo', password='test', proxy=self.proxy_settings()).post(request)
        self.assertEqual(self.secure.records, [])
        self.assertNotIn('authorization', self.proxy.records[0][2])

    def test_protocol_specific_proxy_no_implicit_environment_or_fallback(self):
        with mock.patch.dict('os.environ', {'HTTPS_PROXY': 'http://must-not-use.invalid', 'ALL_PROXY': 'http://must-not-use.invalid'}):
            response = self.connection(proxy=self.proxy_settings('http')).get(http.BSLHTTPRequest('/direct'))
        self.assertEqual(response.get_body_as_string(), '/direct')
        self.assertEqual(self.proxy.records, [])

    def test_bsl_https_proxy_workflow(self):
        output = []; vm = Interpreter(output.append)
        vm.variables['ca_path'] = str(self.root / 'ca.pem')
        vm.execute('''
Ca=New FileCertificationAuthorityCertificates(ca_path);
Tls=New ЗащищенноеСоединениеOpenSSL(,Ca);
P=New InternetProxy(False); P.Set("https","127.0.0.1",%d);
C=New HTTPСоединение("localhost",%d,"demo","test",P,3,Tls);
R=C.Get(New HTTPRequest("/auth")); Message(R.StatusCode); Message(R.GetBodyAsString());
''' % (self.proxy.server_address[1], self.secure.server_port))
        self.assertEqual(output, ['200', 'Basic ZGVtbzp0ZXN0'])


if __name__ == '__main__': unittest.main()
