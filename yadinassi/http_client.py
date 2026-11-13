"""Bounded ordinary synchronous HTTP objects, without implicit credentials.

Explicit TLS trust, Basic authentication and HTTP proxies are supported. No
environment credentials, redirects, cookie jar, decompression or TLS fallback.
DNS resolution is OS-controlled and is NOT covered by the socket deadline.
!todo cancellable DNS, client certificates, async and advanced authentication.
"""
from decimal import Decimal
import http.client
import io
import os
import re
import socket
import time
from urllib.parse import quote

from .safe_mode import require_external_access
from .file_io import (BSLBinaryData, BSLTextEncoding, _FileMethods, _methods,
                      _encoding, _decode, _BOMS, _open_regular, _write_bytes, _file_errors)
from .binary_streams import (_Enum, _Namespace, _number, _stream_path, binary_data_stream,
                             BSLMemoryStream, BSLStream)
from .data_io import _encoded
from .maps import BSLMap
from .http_security import (BSLOpenSSLSecureConnection, BSLInternetProxy,
                            server_name, authority, credentials, basic_authorization)

MAX_BODY = 8 * 1024 * 1024
MAX_HEADER_BYTES = 65536
MAX_HEADERS = 100
MAX_TARGET = 8192
MAX_TIMEOUT = 60
DEFAULT_SOCKET_SECONDS = 30
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")


class BSLByteOrderMarkUse(_Enum):
    AUTO = ('Auto', 'Авто')
    USE = ('Use', 'Использовать')
    DONT_USE = ('DontUse', 'НеИспользовать')


BYTE_ORDER_MARK_USE = _Namespace(BSLByteOrderMarkUse)


def _text(value, cap=MAX_TARGET):
    if type(value) is not str: raise TypeError('HTTP: ожидается Строка')
    if len(value) > cap: raise ValueError('HTTP: превышен предел строки')
    return value


def _body(data):
    if type(data) is not bytes or len(data) > MAX_BODY:
        raise ValueError('HTTP: превышен предел тела')
    return data


def _headers(value):
    if type(value) is not BSLMap: raise TypeError('HTTP: заголовки должны быть Соответствием')
    if len(value._items) > MAX_HEADERS: raise ValueError('HTTP: слишком много заголовков')
    result = []; seen = set(); size = 0
    for key, val in value._items.values():
        key = _text(key, 256); val = _text(val, MAX_HEADER_BYTES)
        if not _TOKEN.fullmatch(key) or any(ord(c) < 32 or ord(c) == 127 for c in val):
            raise ValueError('HTTP: недопустимый заголовок')
        # HTTP/1.1 field values are octets; do not silently UTF8-encode them.
        encoded = val.encode('latin-1')
        lower = key.lower()
        if lower in seen: raise ValueError('HTTP: повторное имя заголовка')
        seen.add(lower); size += len(key) + len(encoded) + 4
        if size > MAX_HEADER_BYTES: raise ValueError('HTTP: превышен предел заголовков')
        result.append((key, val))
    return result


def _header_map(pairs):
    result = BSLMap(); names = {}
    size = 0
    if len(pairs) > MAX_HEADERS: raise ValueError('HTTP: слишком много заголовков ответа')
    for key, value in pairs:
        size += len(key) + len(value) + 4
        if size > MAX_HEADER_BYTES: raise ValueError('HTTP: превышен предел заголовков ответа')
        lower = key.lower(); original = names.setdefault(lower, key)
        previous = result.get(original)
        result.insert(original, value if previous is None else value + ', ' + previous)
    _headers(result)
    return result


def _response_framing(pairs):
    lengths = [v for k, v in pairs if k.lower() == 'content-length']
    transfers = [v for k, v in pairs if k.lower() == 'transfer-encoding']
    if len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
        raise ValueError('HTTP: неоднозначная длина ответа')
    if transfers and transfers[0].lower() != 'chunked':
        raise ValueError('HTTP: неподдерживаемое кодирование передачи')
    if lengths:
        value = lengths[0]
        if (not value.isascii() or not value.isdecimal() or len(value) > 8
                or int(value) > MAX_BODY):
            raise ValueError('HTTP: недопустимая длина ответа')


def _read_file(path):
    with _open_regular(_stream_path(path)) as stream:
        data = stream.read(MAX_BODY + 1)
    return _body(data)


def _charset(headers):
    for key, value in _headers(headers):
        if key.lower() == 'content-type':
            for part in value.split(';')[1:]:
                key, sep, text = part.strip().partition('=')
                if sep and key.lower() == 'charset':
                    return _encoding(text.strip().strip('"'))
    return 'utf-8'


class BSLHTTPRequest(_FileMethods):
    def __init__(self, resource_address='', headers=None):
        self._address = _text(resource_address)
        self._headers = BSLMap() if headers is None else headers
        _headers(self._headers)
        self._body = None; self._file = None; self._file_handle = None

    def __str__(self): return 'HTTPЗапрос'
    def get_member(self, name):
        key = name.casefold()
        if key in ('resourceaddress', 'адресресурса'): return self._address
        if key in ('headers', 'заголовки'): return self._headers
        return super().get_member(name)
    def set_member(self, name, value):
        key = name.casefold()
        if key in ('resourceaddress', 'адресресурса'):
            self._address = _text(value); return
        if key in ('headers', 'заголовки'):
            _headers(value); self._headers = value; return
        return super().set_member(name, value)
    def set_body_from_string(self, text, encoding=None, bom=None):
        text = _text(text, MAX_BODY); codec = _encoding(encoding, 'utf-8')
        if bom is None: bom = BSLByteOrderMarkUse.AUTO
        if type(bom) is not BSLByteOrderMarkUse: raise TypeError('HTTP: ожидается ИспользованиеByteOrderMark')
        width = (sum(1 if ord(c)<128 else 2 if ord(c)<2048 else 3 if ord(c)<65536 else 4 for c in text) if codec=='utf-8' else
                 2*sum(1+(ord(c)>65535) for c in text) if codec.startswith('utf-16') else len(text))
        if width>MAX_BODY: raise ValueError('HTTP: превышен предел тела')
        data = _encoded(text, codec)
        auto = encoding is BSLTextEncoding.UTF16 or (type(encoding) is str and encoding.casefold().replace('_','-') in ('utf-16','utf16'))
        if bom is BSLByteOrderMarkUse.USE or (bom is BSLByteOrderMarkUse.AUTO and auto):
            mark = next((b for b,c in _BOMS if c == codec), b'')
            if len(data) + len(mark) > MAX_BODY: raise ValueError('HTTP: превышен предел тела')
            data = mark + data
        _body(data); replacement = bytearray(data)
        self._release_file(); self._body, self._file = replacement, None
    def _release_file(self):
        handle = self._file_handle
        self._file_handle = None
        if handle is not None: handle.close()
    def __del__(self):
        handle = getattr(self, '_file_handle', None)
        if handle is not None: handle.close()
    def set_body_from_binary_data(self, data):
        if type(data) is not BSLBinaryData: raise TypeError('HTTP: ожидается ДвоичныеДанные')
        replacement = bytearray(_body(data._data))
        self._release_file(); self._body, self._file = replacement, None
    @_file_errors
    def set_body_file_name(self, path):
        path = _stream_path(_text(path))
        # Official API opens now, reads at send/getter. Keep the admitted file,
        # rather than reopening a potentially replaced pathname later.
        handle = _open_regular(path)
        try:
            if os.fstat(handle.fileno()).st_size > MAX_BODY:
                raise ValueError('HTTP: превышен предел тела')
        except BaseException:
            handle.close(); raise
        self._release_file(); self._file_handle = handle
        self._file, self._body = path, None
    def get_body_file_name(self): return self._file
    def get_body_as_binary_data(self):
        data = self._bytes()
        return None if data is None else BSLBinaryData.from_bytes(data)
    def get_body_as_string(self):
        data = self._bytes()
        if data is None: return None
        # Native HT13: default decoding is UTF-8 with replacement, independent
        # of SetBodyFromString's encoding; ordinary BOM detection still applies.
        codec = 'utf-8'
        for mark, detected in _BOMS:
            if data.startswith(mark): codec, data = detected, data[len(mark):]; break
        return data.decode(codec, errors='replace')
    def get_body_as_stream(self):
        if self._file is not None:
            # !todo Writable file-backed body streams require separate native
            # lifetime/authority calibration; keep the existing readonly snapshot.
            return binary_data_stream(BSLBinaryData.from_bytes(self._bytes()))
        if self._body is None: self._body = bytearray()
        memory = BSLMemoryStream()
        memory._state.data = self._body
        memory._state.capacity = MAX_BODY
        result = BSLStream.__new__(BSLStream)
        result._state, result._readonly, result._closed = memory._state, False, False
        # !todo Multiple request-stream cursor and body-replacement alias
        # lifetime semantics are not established by the single-stream HT18.
        return result
    @_file_errors
    def _bytes(self):
        if self._file_handle is not None:
            require_external_access("read HTTP body file")
            self._file_handle.seek(0)
            return _body(self._file_handle.read(MAX_BODY + 1))
        return None if self._body is None else _body(bytes(self._body))
    _methods = _methods(
        ('set_body_from_string', False, 'SetBodyFromString УстановитьТелоИзСтроки'),
        ('set_body_from_binary_data', False, 'SetBodyFromBinaryData УстановитьТелоИзДвоичныхДанных'),
        ('set_body_file_name', False, 'SetBodyFileName УстановитьИмяФайлаТела'),
        ('get_body_file_name', True, 'GetBodyFileName ПолучитьИмяФайлаТела'),
        ('get_body_as_string', True, 'GetBodyAsString ПолучитьТелоКакСтроку'),
        ('get_body_as_binary_data', True, 'GetBodyAsBinaryData ПолучитьТелоКакДвоичныеДанные'),
        ('get_body_as_stream', True, 'GetBodyAsStream ПолучитьТелоКакПоток'))


class BSLHTTPResponse(_FileMethods):
    def __init__(self, *args): raise TypeError('HTTPОтвет создаётся HTTPСоединением')
    @classmethod
    def _create(cls, status, headers, body, filename=None):
        result = cls.__new__(cls)
        result._status, result._headers = status, _header_map(headers)
        result._body, result._file = _body(body), filename
        return result
    def __str__(self): return 'HTTPОтвет'
    def get_member(self, name):
        key = name.casefold()
        if key in ('statuscode', 'кодсостояния'): return Decimal(self._status)
        if key in ('headers', 'заголовки'): return self._headers
        return super().get_member(name)
    def get_body_file_name(self): return self._file
    def get_body_as_binary_data(self):
        return None if self._file is not None else BSLBinaryData.from_bytes(self._body)
    def get_body_as_string(self, encoding=None):
        if self._file is not None: return None
        return _decode(self._body, _charset(self._headers) if encoding is None else encoding, 'utf-8')
    def get_body_as_stream(self):
        if self._file is not None: return None
        return binary_data_stream(BSLBinaryData.from_bytes(self._body))
    _methods = _methods(
        ('get_body_file_name', True, 'GetBodyFileName ПолучитьИмяФайлаТела'),
        ('get_body_as_string', True, 'GetBodyAsString ПолучитьТелоКакСтроку'),
        ('get_body_as_binary_data', True, 'GetBodyAsBinaryData ПолучитьТелоКакДвоичныеДанные'),
        ('get_body_as_stream', True, 'GetBodyAsStream ПолучитьТелоКакПоток'))


class _DeadlineReader(io.RawIOBase):
    def __init__(self, sock, deadline):
        super().__init__(); self._sock = sock; self._deadline = deadline
        self._raw = sock.makefile('rb', buffering=0)
    def readable(self): return True
    def readinto(self, buffer):
        require_external_access("read HTTP socket")
        remaining = self._deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('HTTP socket deadline')
        self._sock.settimeout(remaining)
        return self._raw.readinto(buffer)
    def close(self):
        if not self.closed:
            self._raw.close()
        super().close()


class _ResponseSocket:
    def __init__(self, sock, deadline): self.sock, self.deadline = sock, deadline
    def makefile(self, mode):
        if mode != 'rb': raise ValueError('HTTP reader mode')
        return io.BufferedReader(_DeadlineReader(self.sock, self.deadline))


class _Connection(http.client.HTTPConnection):
    def __init__(self, host, port, seconds, *, tls_context=None, proxy=None):
        super().__init__(host, port, timeout=seconds)
        self.seconds = seconds; self.deadline = None
        self._tls_context, self._proxy = tls_context, proxy
    def connect(self):
        require_external_access("connect HTTP socket")
        # OS name resolution has its own platform policy and may exceed this
        # socket budget. !todo cancellation-aware resolver, not orphan threads.
        peer_host = self._proxy.host if self._proxy is not None else self.host
        peer_port = self._proxy.port if self._proxy is not None else self.port
        addresses = socket.getaddrinfo(peer_host, peer_port, 0, socket.SOCK_STREAM)
        if len(addresses) > 32: raise ValueError('HTTP: слишком много адресов сервера')
        self.deadline = time.monotonic() + self.seconds
        last = None
        for family, kind, proto, _, address in addresses:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError('HTTP socket deadline')
            sock = socket.socket(family, kind, proto)
            try:
                sock.settimeout(remaining); sock.connect(address); self.sock = sock; break
            except OSError as error:
                last = error; sock.close()
        else:
            raise OSError('HTTP connection failed') from last
        try:
            if self._tls_context is not None:
                if self._proxy is not None:
                    self._connect_tunnel()
                self._set_remaining_timeout()
                self.sock = self._tls_context.wrap_socket(self.sock, server_hostname=self.host)
        except BaseException:
            self.close()
            raise

    def _set_remaining_timeout(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('HTTP socket deadline')
        self.sock.settimeout(remaining)

    def _connect_tunnel(self):
        destination = authority(self.host, self.port)
        lines = ['CONNECT ' + destination + ' HTTP/1.1', 'Host: ' + destination]
        authentication = basic_authorization(self._proxy.user, self._proxy.password)
        if authentication is not None:
            lines.append('Proxy-Authorization: ' + authentication)
        self.send(('\r\n'.join(lines) + '\r\n\r\n').encode('ascii'))
        response = self.response_class(self.sock, method='CONNECT')
        try:
            # Parse only the proxy response head. No origin request/body/auth is
            # sent until CONNECT and the verified TLS handshake both succeed.
            version, status, reason = response._read_status()
            if status != 200:
                raise ValueError('HTTP: прокси отказал в CONNECT')
            pairs = []; size = 0
            while True:
                line = response.fp.readline(MAX_HEADER_BYTES + 1)
                size += len(line)
                if size > MAX_HEADER_BYTES or not line.endswith(b'\r\n'):
                    raise ValueError('HTTP: недопустимый ответ CONNECT')
                if line == b'\r\n':
                    break
                if len(pairs) >= MAX_HEADERS or line[:1] in (b' ', b'\t'):
                    raise ValueError('HTTP: недопустимые заголовки CONNECT')
                name, separator, value = line[:-2].partition(b':')
                if not separator:
                    raise ValueError('HTTP: недопустимый заголовок CONNECT')
                pairs.append((name.decode('ascii'), value.strip(b' \t').decode('latin-1')))
            _header_map(pairs)
            if any(key.lower() == 'transfer-encoding' or
                   (key.lower() == 'content-length' and value != '0') for key, value in pairs):
                raise ValueError('HTTP: тело ответа CONNECT не поддерживается')
        finally:
            response.close()

    def send(self, data):
        require_external_access("send HTTP data")
        if self.sock is None: self.connect()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('HTTP socket deadline')
        self.sock.settimeout(remaining)
        return super().send(data)
    def response_class(self, sock, debuglevel=0, method=None, url=None):
        return http.client.HTTPResponse(_ResponseSocket(sock, self.deadline), debuglevel, method, url)


class BSLHTTPConnection(_FileMethods):
    def __init__(self, host, port=None, user=None, password=None, proxy=None,
                 timeout=None, secure_connection=None, use_os_authentication=None):
        host = server_name(host)
        user, password = credentials(user, password)
        if proxy is not None and type(proxy) is not BSLInternetProxy:
            raise ValueError('HTTP: ожидается ИнтернетПрокси')
        if secure_connection is not None and type(secure_connection) is not BSLOpenSSLSecureConnection:
            raise ValueError('HTTP: ожидается ЗащищенноеСоединениеOpenSSL')
        if use_os_authentication is not None and use_os_authentication is not False:
            raise ValueError('HTTP: аутентификация ОС не поддерживается')
        self._host = host
        self._port = (443 if secure_connection is not None else 80) if port is None else _number(port,65535,1)
        self._timeout = 0 if timeout is None else _number(timeout,MAX_TIMEOUT)
        self._user, self._password = user, password
        self._proxy, self._secure = proxy, secure_connection

    def __str__(self): return 'HTTPСоединение'
    def get_member(self, name):
        key = name.casefold()
        values = {'host':self._host,'сервер':self._host,'port':Decimal(self._port),'порт':Decimal(self._port),
                  'timeout':Decimal(self._timeout),'таймаут':Decimal(self._timeout),'user':self._user,'пользователь':self._user,
                  'password':self._password,'пароль':self._password,'proxy':self._proxy,'прокси':self._proxy,
                  'secureconnection':self._secure,'защищенноесоединение':self._secure,
                  'issecure':self._secure is not None,'защищенное':self._secure is not None,
                  'useosauthentication':False,'использоватьаутентификациюос':False}
        if key in values: return values[key]
        return super().get_member(name)
    def call_http_method(self, method, request, output_file=None):
        require_external_access("HTTP request")
        method = _text(method,32)
        if not _TOKEN.fullmatch(method) or method.upper() in ('CONNECT','TRACE'):
            raise ValueError('HTTP: метод не поддерживается')
        if type(request) is not BSLHTTPRequest: raise TypeError('HTTP: ожидается HTTPЗапрос')
        target = _text(request._address)
        if not target.startswith('/') or target.startswith('//') or any(ord(c)<32 or ord(c)==127 for c in target):
            raise ValueError('HTTP: ожидается относительный адрес ресурса с /')
        # Preserve valid percent escapes; encode stray '%' rather than guess.
        target = re.sub(r'%(?![0-9a-fA-F]{2})','%25',target)
        target = quote(target,safe="/%?=&;:+,$@!~*'()-._")
        if len(target)>MAX_TARGET: raise ValueError('HTTP: превышен предел адреса')
        body = request._bytes(); pairs = _headers(request._headers); headers = {}
        for key,value in pairs:
            lower = key.lower()
            if lower in ('transfer-encoding','expect','host','proxy-authorization','cookie'):
                raise ValueError('HTTP: специальный заголовок пока не поддерживается')
            if lower == 'authorization' and self._user:
                raise ValueError('HTTP: два источника Authorization')
            if lower=='content-length' and value != str(len(body or b'')):
                raise ValueError('HTTP: Content-Length не соответствует телу')
            if lower=='connection' and value.lower()!='close': raise ValueError('HTTP: постоянное соединение пока не поддерживается')
            headers[key] = value
        authentication = basic_authorization(self._user, self._password)
        if authentication is not None:
            headers['Authorization'] = authentication
        headers['Connection']='close'
        protocol = 'https' if self._secure is not None else 'http'
        proxy = self._proxy._settings(protocol) if self._proxy is not None else None
        if proxy is not None and self._secure is None:
            authentication = basic_authorization(proxy.user, proxy.password)
            if authentication is not None:
                headers['Proxy-Authorization'] = authentication
            target = 'http://' + authority(self._host, self._port) + target
        # Generated headers count toward the same admission budget.
        _header_map(list(headers.items()))
        filename = None if output_file is None else _text(output_file)
        filename = _stream_path(filename) if filename else None
        seconds = self._timeout or DEFAULT_SOCKET_SECONDS
        context = self._secure._context() if self._secure is not None else None
        connection = _Connection(self._host,self._port,seconds,tls_context=context,proxy=proxy)
        try:
            connection.request(method,target,body=body,headers=headers)
            response = connection.getresponse()
            try:
                response_headers = response.getheaders(); _header_map(response_headers)
                _response_framing(response_headers)
                if response.length is not None and response.length>MAX_BODY:
                    raise ValueError('HTTP: превышен предел тела ответа')
                chunks=[]; total=0
                while True:
                    chunk=response.read1(min(65536,MAX_BODY-total+1))
                    if not chunk: break
                    total+=len(chunk)
                    if total>MAX_BODY: raise ValueError('HTTP: превышен предел тела ответа')
                    chunks.append(chunk)
                if response.length not in (None, 0):
                    raise ValueError('HTTP: неполное тело ответа')
                data=b''.join(chunks)
                result=BSLHTTPResponse._create(response.status,response_headers,data,filename)
            finally: response.close()
        except (OSError,http.client.HTTPException) as error:
            raise ValueError('HTTP: ошибка соединения или ответа') from error
        finally: connection.close()
        # No response output file is touched until the whole bounded response
        # validates. Ordinary disk write failure is not a transaction guarantee.
        if filename is not None: _write_bytes(filename,data)
        return result
    def get(self, request, output_file=None): return self.call_http_method('GET',request,output_file)
    def post(self, request, output_file=None): return self.call_http_method('POST',request,output_file)
    def put(self, request): return self.call_http_method('PUT',request)
    def patch(self, request): return self.call_http_method('PATCH',request)
    def delete(self, request): return self.call_http_method('DELETE',request)
    def head(self, request): return self.call_http_method('HEAD',request)
    _methods = _methods(
        ('call_http_method',True,'CallHTTPMethod ВызватьHTTPМетод'),
        ('get',True,'Get Получить'),('post',True,'Post ОтправитьДляОбработки'),
        ('put',True,'Put Записать'),('patch',True,'Patch Изменить'),
        ('delete',True,'Delete Удалить'),('head',True,'Head ПолучитьЗаголовки'))
