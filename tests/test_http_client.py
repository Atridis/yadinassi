"""Owned loopback HTTP only; provisional ordinary semantics pending native40."""
from decimal import Decimal
import http.server
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from yadinassi import http_client as api
from yadinassi.http_client import BSLHTTPRequest as Request, BSLHTTPConnection as Connection
from yadinassi.file_io import BSLBinaryData as Binary, BSLTextEncoding
from yadinassi.maps import BSLMap
from yadinassi.runtime import Interpreter
from yadinassi.type_values import type_of
from yadinassi.values import BSLType


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args): pass
    def do_GET(self): self.reply()
    def do_POST(self): self.reply()
    def do_PUT(self): self.reply()
    def do_PATCH(self): self.reply()
    def do_DELETE(self): self.reply()
    def do_HEAD(self): self.reply()
    def do_OPTIONS(self): self.reply()
    def reply(self):
        count=int(self.headers.get('Content-Length','0'))
        if count>api.MAX_BODY: self.send_error(413);return
        body=self.rfile.read(count)
        status=404 if self.path=='/missing' else 302 if self.path=='/redirect' else 200
        data=(self.command.encode()+b':'+body) if self.path=='/echo' else self.path.encode('ascii')
        if self.path=='/text': data='Привет'.encode('cp1251')
        if self.path=='/large': data=b'x'*32
        truncated=self.path=='/truncated'
        self.send_response(status)
        self.send_header('Content-Type','text/plain; charset=windows-1251' if self.path=='/text' else 'text/plain; charset=utf-8')
        if self.path != '/close-delimited':
            self.send_header('Content-Length',str(len(data)+5 if truncated else len(data)))
        if self.path=='/duplicate-length': self.send_header('Content-Length','999')
        if self.path=='/mixed-framing': self.send_header('Transfer-Encoding','chunked')
        if self.path=='/unsupported-framing': self.send_header('Transfer-Encoding','gzip, chunked')
        if self.path=='/spaced-framing': self.send_header('Transfer-Encoding','chunked ')
        if self.path in ('/close-delimited','/connection-close'):
            self.send_header('Connection','close');self.close_connection=True
        self.send_header('X-Repeat','a');self.send_header('X-Repeat','b')
        if status==302:self.send_header('Location','/must-not-follow')
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(data)
        if truncated: self.close_connection=True


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.server.daemon_threads=True
        cls.thread=threading.Thread(target=cls.server.serve_forever,kwargs={'poll_interval':0.01},daemon=True)
        cls.thread.start();cls.port=cls.server.server_port
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)
        if cls.thread.is_alive(): raise AssertionError('owned HTTP fixture did not stop')
    def connection(self): return Connection('127.0.0.1',Decimal(self.port),timeout=Decimal(2))

    def test_all_seven_sync_methods_and_binary_body(self):
        for verb in ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS']:
            with self.subTest(verb=verb):
                request=Request('/echo');request.set_body_from_binary_data(Binary.from_bytes(b'a\0b'))
                connection=self.connection()
                response=(connection.call_http_method(verb,request) if verb=='OPTIONS' else getattr(connection,verb.lower())(request))
                self.assertEqual(response.get_member('StatusCode'),200)
                self.assertEqual(response.get_body_as_binary_data()._data,b'' if verb=='HEAD' else verb.encode()+b':a\0b')
                self.assertIs(type_of(response),BSLType.HTTP_RESPONSE)

    def test_status_redirect_headers_and_charset(self):
        response=self.connection().get(Request('/missing'))
        self.assertEqual(response.get_member('КодСостояния'),404)
        self.assertEqual(response.get_member('Headers').get('X-Repeat'),'b, a')
        response=self.connection().get(Request('/redirect'))
        self.assertEqual(response.get_member('StatusCode'),302)
        self.assertEqual(response.get_body_as_string(),'/redirect')
        self.assertEqual(self.connection().get(Request('/text')).get_body_as_string(),'Привет')

    def test_unicode_resource_and_percent_handling(self):
        response=self.connection().get(Request('/пример#x%segment?q=1'))
        self.assertEqual(response.get_body_as_string(),'/%D0%BF%D1%80%D0%B8%D0%BC%D0%B5%D1%80%23x%25segment?q=1')

    def test_empty_unset_and_explicit_text_body(self):
        request=Request()
        self.assertIsNone(request.get_body_as_string());self.assertIsNone(request.get_body_as_binary_data())
        self.assertIsNone(request.get_body_file_name())
        request.set_body_from_string('')
        self.assertEqual(request.get_body_as_string(),'');self.assertEqual(request.get_body_as_binary_data()._data,b'')
        request.set_body_from_string('hello')
        self.assertEqual(request.get_body_as_binary_data()._data,b'hello')
        self.assertEqual(request.get_body_as_string(),'hello')

    def test_bom_encoding_and_atomic_replacement(self):
        request=Request('/echo');request.set_body_from_string('Я','utf-16',api.BSLByteOrderMarkUse.AUTO)
        self.assertEqual(request.get_body_as_binary_data()._data,b'\xff\xfe/\x04')
        self.assertEqual(request.get_body_as_string(),'Я')
        request.set_body_from_string('a','utf-8',api.BSLByteOrderMarkUse.USE)
        self.assertEqual(request.get_body_as_binary_data()._data,b'\xef\xbb\xbfa')
        with self.assertRaises(UnicodeEncodeError): request.set_body_from_string('Я','ascii')
        self.assertEqual(request.get_body_as_string(),'a')
        with mock.patch.object(api,'MAX_BODY',3),mock.patch.object(api,'_encoded') as encoded:
            with self.assertRaises(ValueError):request.set_body_from_string('😀')
            encoded.assert_not_called()

    def test_owned_file_input_output_and_deferred_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'in.bin';target=root/'out.bin';source.write_bytes(b'old');target.write_bytes(b'keep')
            request=Request('/echo');request.set_body_file_name(str(source));source.write_bytes(b'new')
            self.assertEqual(request.get_body_as_string(),'new');self.assertEqual(request.get_body_as_binary_data()._data,b'new');self.assertEqual(request.get_body_file_name(),str(source))
            response=self.connection().post(request,str(target))
            self.assertEqual(target.read_bytes(),b'POST:new')
            self.assertEqual(response.get_body_file_name(),str(target));self.assertIsNone(response.get_body_as_string())
            self.assertIsNone(response.get_body_as_binary_data())
            self.assertEqual(request.get_body_as_stream()._read_bytes(3),b'new')
            request.set_body_from_string('released')

    def test_native_request_stream_live_body_cap_and_close(self):
        request=Request('/echo')
        with mock.patch.object(api,'MAX_BODY',3):
            stream=request.get_body_as_stream()
            self.assertIs(type(stream),api.BSLStream)
            self.assertTrue(stream.get_member('CanWrite'))
            stream._write_bytes(b'abc')
            self.assertEqual(request.get_body_as_binary_data()._data,b'abc')
            with self.assertRaises(ValueError):stream._write_bytes(b'd')
            self.assertEqual(stream.current_position(),3)
            self.assertEqual(request.get_body_as_string(),'abc')
            stream.close()
            with self.assertRaises(ValueError):stream._write_bytes(b'x')
        self.assertEqual(self.connection().post(request).get_body_as_string(),'POST:abc')
        request.set_body_from_string('Привет','windows-1251')
        self.assertEqual(request.get_body_as_string(),'\ufffd'*6)
        self.assertEqual(request.get_body_as_binary_data()._data,'Привет'.encode('cp1251'))

    def test_file_setter_atomic_admission_and_handle_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'body';source.write_bytes(b'abc')
            request=Request();request.set_body_from_string('before')
            with self.assertRaises(ValueError):request.set_body_file_name(str(root/'missing'))
            self.assertEqual(request.get_body_as_string(),'before')
            with mock.patch.object(api,'MAX_BODY',2):
                with self.assertRaises(ValueError):request.set_body_file_name(str(source))
            self.assertEqual(request.get_body_as_string(),'before')
            request.set_body_file_name(str(source));handle=request._file_handle
            self.assertFalse(handle.closed)
            self.assertEqual(request.get_body_as_binary_data()._data,b'abc')
            with self.assertRaises(ValueError):request.set_body_file_name(str(root))
            self.assertIs(request._file_handle,handle)
            self.assertEqual(request.get_body_as_string(),'abc')
            request.set_body_from_binary_data(Binary.from_bytes(b'replaced'))
            self.assertTrue(handle.closed)
            request.set_body_file_name(str(source));handle=request._file_handle
            del request
            self.assertTrue(handle.closed)

    def test_response_stream_readonly_independent(self):
        response=self.connection().get(Request('/text'))
        a=response.get_body_as_stream();b=response.get_body_as_stream()
        self.assertEqual(a._read_bytes(2),'Пр'.encode('cp1251'))
        self.assertEqual(b.current_position(),0)
        with self.assertRaises(ValueError):a._write_bytes(b'x')
        a.close();self.assertEqual(response.get_body_as_string(),'Привет');b.close()

    def test_header_mutation_checked_at_send_and_no_injection(self):
        headers=BSLMap();headers.insert('X-Test','a');request=Request('/echo',headers)
        self.assertIs(request.get_member('Headers'),headers)
        headers.insert('X-Test','bad\r\nNext: injected')
        with mock.patch.object(api,'_Connection') as transport:
            with self.assertRaises(ValueError):self.connection().get(request)
            transport.assert_not_called()
        headers.delete('X-Test');headers.insert('Content-Length','999')
        with self.assertRaises(ValueError):self.connection().get(request)

    def test_unsupported_features_do_not_connect_or_downgrade(self):
        with mock.patch.object(api,'_Connection') as transport:
            for kwargs in [dict(user='name'),dict(password='secret'),dict(proxy=object()),dict(secure_connection=object()),dict(use_os_authentication=True)]:
                with self.assertRaises(ValueError):Connection('localhost',**kwargs)
            for target in ['https://example.test/','//example.test/','/x\nBad']:
                with self.assertRaises(ValueError):self.connection().get(Request(target))
            for method in ['CONNECT','TRACE','GET\r\n']:
                with self.assertRaises(ValueError):self.connection().call_http_method(method,Request('/'))
            transport.assert_not_called()

    def test_size_error_keeps_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'out';target.write_bytes(b'keep')
            with mock.patch.object(api,'MAX_BODY',8),self.assertRaises(ValueError):
                self.connection().get(Request('/large'),str(target))
            self.assertEqual(target.read_bytes(),b'keep')

    def test_incomplete_response_does_not_replace_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'out';target.write_bytes(b'keep')
            with self.assertRaises(ValueError): self.connection().get(Request('/truncated'),str(target))
            self.assertEqual(target.read_bytes(),b'keep')

    def test_close_delimited_and_explicit_close(self):
        for target in ('/close-delimited','/connection-close'):
            self.assertEqual(self.connection().get(Request(target)).get_body_as_string(),target)

    def test_ambiguous_response_framing_keeps_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'out';target.write_bytes(b'keep')
            for path in ('/duplicate-length','/mixed-framing','/unsupported-framing','/spaced-framing'):
                with self.subTest(path=path),self.assertRaises(ValueError):
                    self.connection().get(Request(path),str(target))
                self.assertEqual(target.read_bytes(),b'keep')

    def test_finite_timeouts_no_env_proxy_and_properties(self):
        connection=Connection('localhost',self.port)
        self.assertEqual(connection.get_member('Timeout'),0)
        self.assertFalse(connection.get_member('UseOSAuthentication'))
        self.assertIsNone(connection.get_member('Proxy'))
        with self.assertRaises(ValueError):Connection('localhost',timeout=61)
        with self.assertRaises(ValueError):connection.set_member('Host','elsewhere')
        with mock.patch.dict('os.environ',{'HTTP_PROXY':'http://must-not-use.invalid:80','HTTPS_PROXY':'http://must-not-use.invalid:80'}):
            self.assertEqual(connection.get(Request('/')).get_body_as_string(),'/')

    def test_bsl_methods_types_optional_holes_and_codec_guards(self):
        out=[]
        Interpreter(out.append).execute(f'''C=New HTTPСоединение("127.0.0.1",{self.port},,,,2);
R=New HTTPЗапрос("/echo"); R.УстановитьТелоИзСтроки("abc",,ИспользованиеByteOrderMark.НеИспользовать);
S=C.ОтправитьДляОбработки(R,); Message(S.КодСостояния); Message(S.ПолучитьТелоКакСтроку());
Message(TypeOf(C)=Type("HTTPConnection")); Message(TypeOf(R)=Type("HTTPRequest"));
Message(TypeOf(S)=Type("HTTPResponse"));
Try ValueToStringInternal(R); Except Message("no-codec"); EndTry;''')
        self.assertEqual(out,['200','POST:abc','Да','Да','Да','no-codec'])


if __name__=='__main__':unittest.main()
