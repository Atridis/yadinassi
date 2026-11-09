"""Explicit security-object and transport policy tests; no outside endpoints."""
from decimal import Decimal
import ssl
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from yadinassi import Interpreter, BSLError
from yadinassi import http_client as http
from yadinassi import http_security as api
from yadinassi.maps import BSLMap
from yadinassi.type_values import type_of
from yadinassi.values import BSLType


class SecurityObjectTests(unittest.TestCase):
    def test_os_trust_enforces_peer_hostname_and_minimum_tls(self):
        context = api.BSLOSCertificationAuthorityCertificates()._context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_os_trust_uses_compiled_paths_and_windows_server_auth_roots(self):
        paths = ssl.DefaultVerifyPaths('/env/ca.pem', '/env/certs', 'SSL_CERT_FILE', '/compiled/ca.pem', 'SSL_CERT_DIR', '/compiled/certs')
        entries = [(b'root', 'x509_asn', True), (b'server', 'x509_asn', {ssl.Purpose.SERVER_AUTH.oid}),
                   (b'client', 'x509_asn', {ssl.Purpose.CLIENT_AUTH.oid}), (b'pkcs7', 'pkcs_7_asn', True)]
        with mock.patch.object(api.sys, 'platform', 'win32'), mock.patch.object(api.ssl, 'SSLContext') as factory, \
                mock.patch.object(api.ssl, 'enum_certificates', return_value=entries, create=True), \
                mock.patch.object(api.ssl, 'get_default_verify_paths', return_value=paths), \
                mock.patch.object(api.os.path, 'isfile', return_value=True), mock.patch.object(api.os.path, 'isdir', return_value=True):
            context = api.BSLOSCertificationAuthorityCertificates()._context()
        self.assertEqual(context.load_verify_locations.call_args_list, [
            mock.call(cadata=b'root'), mock.call(cadata=b'server'),
            mock.call(cadata=b'root'), mock.call(cadata=b'server'),
            mock.call(cafile='/compiled/ca.pem', capath='/compiled/certs')])
        context.load_default_certs.assert_not_called()

    def test_no_implicit_tls_key_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'must-not-log'
            with mock.patch.dict('os.environ', {'SSLKEYLOGFILE': str(path)}):
                context = api.BSLOSCertificationAuthorityCertificates()._context()
                self.assertIsNone(context.keylog_filename)
            self.assertFalse(path.exists())

    def test_explicit_trust_is_required_and_client_certificates_rejected(self):
        for args in [(), (None,), (None, None), (None, True), (object(), api.BSLOSCertificationAuthorityCertificates())]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                api.BSLOpenSSLSecureConnection(*args)

    def test_tls_readonly_properties_and_type_identity(self):
        ca = api.BSLOSCertificationAuthorityCertificates()
        tls = api.BSLOpenSSLSecureConnection(None, ca)
        self.assertIs(tls.get_member('CertificationAuthorityCertificates'), ca)
        self.assertIsNone(tls.get_member('СертификатКлиента'))
        self.assertIs(type_of(tls), BSLType.OPENSSL_SECURE_CONNECTION)
        self.assertIs(type_of(ca), BSLType.OS_CA_CERTIFICATES)
        with self.assertRaises(ValueError): tls.set_member('ClientCertificate', None)
        with self.assertRaises(ValueError): tls.get_member('_context')

    def test_https_default_port_properties_and_explicit_override(self):
        tls = api.BSLOpenSSLSecureConnection(None, api.BSLOSCertificationAuthorityCertificates())
        c = http.BSLHTTPConnection('example.invalid', secure_connection=tls, user='demo', password='test')
        self.assertEqual(c.get_member('Port'), 443)
        self.assertIs(c.get_member('SecureConnection'), tls)
        self.assertTrue(c.get_member('Защищенное'))
        self.assertEqual(c.get_member('User'), 'demo')
        self.assertEqual(c.get_member('Password'), 'test')
        self.assertEqual(http.BSLHTTPConnection('example.invalid', 8443, secure_connection=tls)._port, 8443)

    def test_file_ca_rejects_absent_empty_nonpem_and_private_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ca.pem'
            for body in [b'', b'not a certificate', b'-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----', b'\xff']:
                path.write_bytes(body)
                with self.subTest(body=body), self.assertRaises((ValueError, UnicodeError)):
                    api.BSLFileCertificationAuthorityCertificates(str(path))
            with self.assertRaises(ValueError): api.BSLFileCertificationAuthorityCertificates(str(path.parent))
            with self.assertRaises(ValueError): api.BSLFileCertificationAuthorityCertificates(str(path / 'absent'))

    def test_ca_encryption_and_size_refused_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ca.pem'; path.write_bytes(b'12345')
            with mock.patch.object(api, '_open_regular') as opened:
                with self.assertRaises(ValueError): api.BSLFileCertificationAuthorityCertificates(str(path), 'password')
                opened.assert_not_called()
            with mock.patch.object(api, 'MAX_CERTIFICATE_BYTES', 4):
                with self.assertRaises(ValueError): api.BSLFileCertificationAuthorityCertificates(str(path))

    def test_explicit_proxy_and_protocol_getters(self):
        proxy = api.BSLInternetProxy(False)
        self.assertEqual(proxy.server('http'), '')
        self.assertEqual(proxy.port('https'), 0)
        proxy.set('HTTPS', '127.0.0.1', Decimal(3128), 'proxy-user', 'proxy-pass', False)
        self.assertEqual(proxy.server('https'), '127.0.0.1')
        self.assertEqual(proxy.port('https'), 3128)
        self.assertEqual(proxy.user('https'), 'proxy-user')
        self.assertEqual(proxy.password('https'), 'proxy-pass')
        self.assertFalse(proxy.use_os_authentication('https'))
        self.assertIs(type_of(proxy), BSLType.INTERNET_PROXY)
        self.assertIs(http.BSLHTTPConnection('example.invalid', proxy=proxy).get_member('Proxy'), proxy)

    def test_proxy_atomic_set_and_protocol_isolation(self):
        proxy = api.BSLInternetProxy(); proxy.set('http', 'localhost', 8080)
        before = proxy._settings('http')
        for kwargs in [dict(port=0), dict(server='http://wrong'), dict(user='a:b'), dict(use_os_authentication=True)]:
            args = dict(protocol='http', server='localhost', port=3128); args.update(kwargs)
            with self.assertRaises(ValueError): proxy.set(**args)
            self.assertIs(proxy._settings('http'), before)
        self.assertIsNone(proxy._settings('https'))
        proxy.set('http', 'localhost')
        self.assertEqual(proxy.port('http'), 80)

    def test_proxy_environment_automatic_and_other_protocols_refused(self):
        for value in (True, 1, 'false'):
            with self.assertRaises(ValueError): api.BSLInternetProxy(value)
        proxy = api.BSLInternetProxy()
        for protocol in ('ftp', 'socks5', None, 'http://'):
            with self.assertRaises(ValueError): proxy.set(protocol, 'localhost')
        with self.assertRaises(ValueError): proxy.set_member('BypassProxyOnLocal', True)

    def test_credentials_are_bounded_explicit_and_basic_is_utf8(self):
        self.assertEqual(api.credentials(), ('', ''))
        self.assertIsNone(api.basic_authorization('', ''))
        self.assertEqual(api.basic_authorization('demo', 'test'), 'Basic ZGVtbzp0ZXN0')
        self.assertEqual(api.basic_authorization('ю', 'я'), 'Basic 0Y460Y8=')
        for args in [('bad:name', ''), ('', 'password'), ('a\r\nb', 'x'), ('u', '\x00'), (True, ''), ('u', 'x' * 4097)]:
            with self.subTest(args=args), self.assertRaises(ValueError): api.credentials(*args)

    def test_server_name_idna_ipv6_and_authority(self):
        self.assertEqual(api.server_name('пример.рф'), 'xn--e1afmkfd.xn--p1ai')
        self.assertEqual(api.server_name('[::1]'), '::1')
        self.assertEqual(api.authority('::1', 443), '[::1]:443')
        for name in ('host:80', 'https://host', 'host/path', 'user@host', 'x\t', '[bad]', 'fe80::1%eth0'):
            with self.subTest(name=name), self.assertRaises(ValueError): api.server_name(name)

    def test_conflicting_or_forbidden_auth_headers_precede_connection(self):
        headers = BSLMap(); headers.insert('Authorization', 'Bearer synthetic-token')
        request = http.BSLHTTPRequest('/', headers)
        with mock.patch.object(http, '_Connection') as transport:
            with self.assertRaises(ValueError): http.BSLHTTPConnection('example.invalid', user='demo').get(request)
            headers.delete('Authorization'); headers.insert('Proxy-Authorization', 'Basic synthetic')
            with self.assertRaises(ValueError): http.BSLHTTPConnection('example.invalid').get(request)
            transport.assert_not_called()

    def test_generated_auth_headers_count_toward_budget(self):
        with mock.patch.object(http, 'MAX_HEADER_BYTES', 20), mock.patch.object(http, '_Connection') as transport:
            with self.assertRaises(ValueError): http.BSLHTTPConnection('example.invalid', user='demo', password='test').get(http.BSLHTTPRequest('/'))
            transport.assert_not_called()

    def test_bilingual_bsl_types_properties_and_optional_holes(self):
        output = []
        Interpreter(output.append).execute('''
Ca=New СертификатыУдостоверяющихЦентровОС;
Tls=New OpenSSLSecureConnection(,Ca);
P=New ИнтернетПрокси(Ложь); P.Установить("https","localhost",3128,,,Ложь);
C=New HTTPConnection("example.invalid",,,,P,,Tls);
Message(TypeOf(Tls)=Type("ЗащищенноеСоединениеOpenSSL"));
Message(TypeOf(P)=Type("InternetProxy")); Message(P.Порт("https"));
Message(C.Port); Message(C.IsSecure); Message(Tls.СертификатКлиента=Undefined);
''')
        self.assertEqual(output, ['Да', 'Да', '3\xa0128', '443', 'Да', 'Да'])

    def test_new_objects_do_not_gain_codecs_or_host_reflection(self):
        vm = Interpreter(lambda _: None)
        vm.execute('P=New InternetProxy(False); Ca=New OSCertificationAuthorityCertificates; Tls=New OpenSSLSecureConnection(,Ca);')
        for code in ('ValueToStringInternal(P)', 'ValueToStringInternal(Ca)', 'ValueToStringInternal(Tls)', 'Tls._context()', 'P._protocols', 'Ca._context()'):
            with self.subTest(code=code), self.assertRaises(BSLError): vm.execute(code)

    def test_proxy_procedure_expression_and_required_holes_guard_side_effects(self):
        vm = Interpreter(lambda _: None); vm.execute('P=New InternetProxy(False);')
        calls = []; vm.register_function('Effect', lambda: calls.append(1) or 'http')
        for code in ('x=P.Set(Effect(),"localhost");', 'P.Set(,"localhost");', 'P.Set("http",,80);'):
            with self.subTest(code=code), self.assertRaises(BSLError): vm.execute(code)
        self.assertEqual(calls, [])


if __name__ == '__main__': unittest.main()
