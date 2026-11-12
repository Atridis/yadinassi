"""Effect-boundary regressions; not native SafeMode parity evidence."""
from contextlib import contextmanager
from pathlib import Path
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import Mock, patch
from yadinassi import safe_mode, file_io, zip_archives, http_client, http_security
from yadinassi.binary_streams import BSLFileStream, BSLMemoryStream, BSLFileOpenMode, BSLPositionInStream
from yadinassi.json_processing import BSLJSONWriter, BSLJSONReader
from yadinassi.xml_writer import BSLXMLWriter

@contextmanager
def restricted():
    token = safe_mode._CURRENT.set(Mock(active=lambda: True))
    try:
        yield
    finally:
        safe_mode._CURRENT.reset(token)

class SafeModeIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data'
        self.path.write_bytes(b'abc')

    def denied(self, function):
        with restricted(), self.assertRaisesRegex(ValueError, 'safe mode forbids'):
            function()

    def test_file_open_and_metadata(self):
        f = file_io.BSLFile(str(self.path))
        for function in (f.exists, f.is_file, f.is_directory, f.size,
                         lambda: file_io._read_bytes(str(self.path)),
                         lambda: file_io._write_bytes(str(self.path), b'bad')):
            self.denied(function)
        self.assertEqual(self.path.read_bytes(), b'abc')

    def test_directory_mutations_and_listing(self):
        other = str(self.path.parent / 'other')
        for function in (lambda: file_io.create_directory(other),
                         lambda: file_io.copy_file(str(self.path), other),
                         lambda: file_io.move_file(str(self.path), other),
                         lambda: file_io.find_files(str(self.path)),
                         lambda: file_io.delete_files(str(self.path)),
                         file_io.temp_files_dir, file_io.temp_file_name):
            self.denied(function)
        self.assertFalse(Path(other).exists())
        self.assertTrue(self.path.exists())

    def test_preexisting_live_file_stream(self):
        stream = BSLFileStream(str(self.path), BSLFileOpenMode.OPEN)
        self.addCleanup(stream.close)
        from yadinassi.data_io import BSLDataReader
        from yadinassi.text_streams import BinaryStreamSink
        reader = BSLDataReader(stream)
        alias = reader.source_stream()
        sink = BinaryStreamSink(stream)
        for function in (lambda: stream._read_bytes(1), lambda: stream._write_bytes(b'z'),
                         lambda: stream.set_size(0), stream.flush,
                         reader.read_byte, lambda: alias._read_bytes(1),
                         lambda: sink.write(b"bad")):
            self.denied(function)
        self.assertEqual(self.path.read_bytes(), b'abc')

    def test_file_stream_constructor_guard(self):
        self.denied(lambda: BSLFileStream(str(self.path), BSLFileOpenMode.TRUNCATE))
        self.assertEqual(self.path.read_bytes(), b'abc')

    def test_memory_stream_remains_usable(self):
        with restricted():
            stream = BSLMemoryStream()
            stream._write_bytes(b'abc')
            stream.seek(0, BSLPositionInStream.BEGIN)
            self.assertEqual(stream._read_bytes(3), b'abc')

    def test_json_file_deferred_commit(self):
        writer = BSLJSONWriter(); writer.open_file(str(self.path)); writer.write_value(Decimal(1))
        self.denied(writer.close)
        self.assertEqual(self.path.read_bytes(), b'')
        writer._release_file()

    def test_xml_file_deferred_commit(self):
        writer = BSLXMLWriter(); writer.open_file(str(self.path))
        writer.write_start_element('root'); writer.write_end_element()
        self.denied(writer.close)
        self.assertEqual(self.path.read_bytes(), b'')
        writer._dispose()

    def test_memory_json_xml_remain_usable(self):
        with restricted():
            writer = BSLJSONWriter(); writer.set_string(); writer.write_value(Decimal(1))
            self.assertEqual(writer.close(), '1')
            xml = BSLXMLWriter(); xml.set_string(); xml.write_start_element('root'); xml.write_end_element()
            self.assertIn('root', xml.close())

    def test_json_separate_opener_guard(self):
        self.denied(lambda: BSLJSONReader().open_file(str(self.path)))

    def test_preexisting_text_writer(self):
        writer = file_io.BSLTextWriter(str(self.path))
        self.addCleanup(writer.close)
        before = self.path.read_bytes()
        self.denied(lambda: writer.write('bad'))
        self.assertEqual(self.path.read_bytes(), before)

    def test_zip_actual_helpers_guard(self):
        for function in (lambda: zip_archives._host_path(str(self.path)),
                         lambda: zip_archives._read_file(self.path),
                         lambda: zip_archives._write_file(self.path, b'bad'),
                         lambda: list(zip_archives._scan_files(self.path.parent, '*', False))):
            self.denied(function)
        self.assertEqual(self.path.read_bytes(), b'abc')

    def test_preexisting_http_file_body(self):
        request = http_client.BSLHTTPRequest('/')
        request.set_body_file_name(str(self.path))
        self.denied(request._bytes)
        request._file_handle.close()

    def test_http_dns_and_preexisting_socket_send_guard(self):
        conn = http_client._Connection('example.invalid', 80, 5)
        with patch.object(http_client.socket, 'getaddrinfo') as dns:
            self.denied(conn.connect); dns.assert_not_called()
        conn.sock = Mock()
        self.denied(lambda: conn.send(b'bad'))
        conn.sock.sendall.assert_not_called()
        reader = http_client._DeadlineReader.__new__(http_client._DeadlineReader)
        reader._raw = Mock(); reader._sock = Mock()
        self.denied(lambda: reader.readinto(bytearray(1)))
        reader._raw.readinto.assert_not_called()

    def test_os_trust_load_guard(self):
        with patch.object(http_security.ssl, 'SSLContext') as context:
            self.denied(http_security.BSLOSCertificationAuthorityCertificates()._context)
            context.assert_not_called()

class ShortWriteTests(unittest.TestCase):
    class Sink:
        def __init__(self): self.data = bytearray(); self.calls = 0
        def write(self, data):
            self.calls += 1
            count = min(2, len(data))
            self.data.extend(data[:count])
            return count

    def test_partial_progress_commits_every_byte(self):
        sink = self.Sink()
        file_io._write_all(sink, b'abcdefg')
        self.assertEqual(sink.data, b'abcdefg')
        self.assertEqual(sink.calls, 4)

    def test_zero_none_and_invalid_progress_fail_without_retry(self):
        for progress in (0, None, -1, 100, True):
            with self.subTest(progress=progress):
                sink = Mock(); sink.write.return_value = progress
                with self.assertRaisesRegex(ValueError, 'запись не завершена'):
                    file_io._write_all(sink, b'abc')
                sink.write.assert_called_once()

    def test_os_error_is_reported(self):
        sink = Mock(); sink.write.side_effect = OSError('disk error')
        with self.assertRaises(ValueError):
            file_io._write_all(sink, b'abc')
        sink.write.assert_called_once()

    def test_safe_guard_precedes_first_write(self):
        sink = Mock()
        with restricted(), self.assertRaisesRegex(ValueError, 'safe mode forbids'):
            file_io._write_all(sink, b'abc')
        sink.write.assert_not_called()

    def test_empty_write_has_no_external_effect(self):
        sink = Mock()
        with restricted():
            file_io._write_all(sink, b'')
        sink.write.assert_not_called()
