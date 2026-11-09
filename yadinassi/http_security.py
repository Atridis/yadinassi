"""Explicit HTTPS trust and proxy settings for the bounded HTTP transport.

These objects never install certificates, change OS settings, discover proxies,
or disable peer verification. They are not a complete native security API.
"""
import base64
from dataclasses import dataclass
from decimal import Decimal
import ipaddress
import os
import ssl
import sys
import warnings

from .values import BSLObject
from .file_io import _FileMethods, _methods, _open_regular, _file_errors
from .binary_streams import _number, _stream_path

MAX_CERTIFICATE_BYTES = 1024 * 1024
MAX_CREDENTIAL_BYTES = 4096


def server_name(value):
    if type(value) is not str or not value or len(value) > 253:
        raise ValueError('HTTP: требуется имя сервера')
    if any(c in value for c in '/\\@?# ') or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise ValueError('HTTP: требуется имя сервера без схемы, порта и пути')
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]
        ipaddress.IPv6Address(value)
    if ':' in value:
        # Do not let host:port strings override the separately validated port.
        if '%' in value:
            raise ValueError('HTTP: IPv6 zone identifiers are unsupported')
        ipaddress.IPv6Address(value)
    elif '[' in value or ']' in value:
        raise ValueError('HTTP: недопустимое имя сервера')
    else:
        value = value.encode('idna').decode('ascii')
        if len(value) > 253:
            raise ValueError('HTTP: превышен предел имени сервера')
    return value


def authority(host, port):
    return ('[' + host + ']' if ':' in host else host) + ':' + str(port)


def credentials(user=None, password=None):
    user = '' if user is None else user
    password = '' if password is None else password
    for value in (user, password):
        if type(value) is not str or len(value.encode('utf-8')) > MAX_CREDENTIAL_BYTES:
            raise ValueError('HTTP: недопустимые учетные данные')
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('HTTP: управляющие символы в учетных данных')
    if ':' in user or (password and not user):
        raise ValueError('HTTP: требуется имя пользователя без двоеточия')
    return user, password


def basic_authorization(user, password):
    if not user:
        return None
    return 'Basic ' + base64.b64encode((user + ':' + password).encode('utf-8')).decode('ascii')


class BSLFileCertificationAuthorityCertificates(BSLObject):
    @_file_errors
    def __init__(self, filename, password=None):
        if password is not None and (type(password) is not str or password != ''):
            raise ValueError('TLS: поддержаны только незашифрованные PEM сертификаты УЦ')
        with _open_regular(_stream_path(filename)) as stream:
            data = stream.read(MAX_CERTIFICATE_BYTES + 1)
        if not data or len(data) > MAX_CERTIFICATE_BYTES:
            raise ValueError('TLS: недопустимый размер файла сертификатов')
        # Accept certificate-only PEM, never ingest/store an accidental private key.
        text = data.decode('ascii')
        import re
        certificate = re.compile(r'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----')
        blocks = certificate.findall(text)
        if not blocks or certificate.sub('', text).strip():
            raise ValueError('TLS: требуется PEM файл только с сертификатами УЦ')
        self._pem = '\n'.join(blocks)
        self._context()  # Validate now; later file replacement cannot alter trust.

    def _context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=self._pem)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    def __str__(self):
        return 'СертификатыУдостоверяющихЦентровФайл'


class BSLOSCertificationAuthorityCertificates(BSLObject):
    def __str__(self):
        return 'СертификатыУдостоверяющихЦентровОС'

    def _context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # load_default_certs() honors SSL_CERT_FILE / SSL_CERT_DIR. Selecting
        # OS trust must not silently select a process-environment trust bundle.
        # Load Windows stores explicitly, then compiled-in OpenSSL locations.
        if sys.platform == 'win32':
            for store in ('CA', 'ROOT'):
                try:
                    certificates = ssl.enum_certificates(store)
                except PermissionError:
                    warnings.warn('TLS: Windows certificate store is unavailable')
                    continue
                for certificate, encoding, trust in certificates:
                    if encoding == 'x509_asn' and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
                        try:
                            context.load_verify_locations(cadata=certificate)
                        except ssl.SSLError:
                            warnings.warn('TLS: unsupported certificate in Windows store')
        paths = ssl.get_default_verify_paths()
        cafile = paths.openssl_cafile if paths.openssl_cafile and os.path.isfile(paths.openssl_cafile) else None
        capath = paths.openssl_capath if paths.openssl_capath and os.path.isdir(paths.openssl_capath) else None
        if cafile is not None or capath is not None:
            context.load_verify_locations(cafile=cafile, capath=capath)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context


class BSLOpenSSLSecureConnection(BSLObject):
    def __init__(self, client_certificate=None, certification_authority_certificates=None):
        if client_certificate is not None:
            raise ValueError('TLS: клиентские сертификаты пока не поддерживаются')
        if type(certification_authority_certificates) not in (
                BSLFileCertificationAuthorityCertificates, BSLOSCertificationAuthorityCertificates):
            # Native omission can disable verification. Refuse, never silently
            # reproduce that policy or substitute unrelated trust sources.
            raise ValueError('TLS: явно укажите сертификаты УЦ файла или ОС')
        self._authorities = certification_authority_certificates

    def __str__(self):
        return 'ЗащищенноеСоединениеOpenSSL'

    def get_member(self, name):
        key = name.casefold()
        if key in ('clientcertificate', 'сертификатклиента'):
            return None
        if key in ('certificationauthoritycertificates', 'сертификатыудостоверяющихцентров'):
            return self._authorities
        return super().get_member(name)

    def _context(self):
        return self._authorities._context()


@dataclass(frozen=True, repr=False)
class ProxySettings:
    host: str
    port: int
    user: str
    password: str


class BSLInternetProxy(_FileMethods):
    def __init__(self, default_proxy=None):
        if default_proxy is not None and default_proxy is not False:
            raise ValueError('HTTP: автоматические настройки прокси не поддерживаются')
        self._protocols = {}

    def __str__(self):
        return 'ИнтернетПрокси'

    @staticmethod
    def _protocol(value):
        if type(value) is not str or value.casefold() not in ('http', 'https'):
            raise ValueError('HTTP: поддержаны протоколы прокси http и https')
        return value.casefold()

    def set(self, protocol, server, port=None, user=None, password=None, use_os_authentication=None):
        protocol = self._protocol(protocol)
        host = server_name(server)
        port = 80 if port is None else _number(port, 65535, 1)
        user, password = credentials(user, password)
        if use_os_authentication is not None and use_os_authentication is not False:
            raise ValueError('HTTP: аутентификация ОС не поддерживается')
        self._protocols[protocol] = ProxySettings(host, port, user, password)

    def _settings(self, protocol):
        return self._protocols.get(self._protocol(protocol))

    def server(self, protocol):
        item = self._settings(protocol)
        return '' if item is None else item.host

    def port(self, protocol):
        item = self._settings(protocol)
        return Decimal(0 if item is None else item.port)

    def user(self, protocol):
        item = self._settings(protocol)
        return '' if item is None else item.user

    def password(self, protocol):
        item = self._settings(protocol)
        return '' if item is None else item.password

    def use_os_authentication(self, protocol):
        self._protocol(protocol)
        return False

    _methods = _methods(
        ('set', False, 'Set Установить'),
        ('server', True, 'Server Сервер'), ('port', True, 'Port Порт'),
        ('user', True, 'User Пользователь'), ('password', True, 'Password Пароль'),
        ('use_os_authentication', True, 'UseOSAuthentication ИспользоватьАутентификациюОС'))
