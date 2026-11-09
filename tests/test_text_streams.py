"""Local bounded borrowed text stream profile; not native lifetime parity."""
import codecs
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi import file_io
from yadinassi.file_io import BSLTextReader as Reader, BSLTextWriter as Writer
from yadinassi.binary_streams import (BSLMemoryStream as Memory, BSLFileStream as File,
    BSLBinaryDataBuffer as Buffer, BSLPositionInStream as Origin,
    BSLFileOpenMode as Mode, BSLFileAccess as Access)
from yadinassi.text_streams import is_stream, read_snapshot, BinaryStreamSink


def source(data):
    stream = Memory()
    stream._write_bytes(data)
    stream.seek(0, Origin.BEGIN)
    return stream


class TextStreamTests(unittest.TestCase):
    def test_bilingual_constructor_and_open(self):
        for memory, writer, reader, write, read, close, opening, seek, origin in (
            ('MemoryStream', 'TextWriter', 'TextReader', 'WriteLine', 'ReadLine',
             'Close', 'Open', 'Seek', 'PositionInStream.Begin'),
            ('ПотокВПамяти', 'ЗаписьТекста', 'ЧтениеТекста', 'ЗаписатьСтроку',
             'ПрочитатьСтроку', 'Закрыть', 'Открыть', 'Перейти', 'ПозицияВПотоке.Начало')):
            for constructor in (True, False):
                with self.subTest(writer=writer, constructor=constructor):
                    vm = Interpreter(lambda _: None)
                    setup = f'w=New {writer}(s);' if constructor else f'w=New {writer}; w.{opening}(s);'
                    setup_r = f'r=New {reader}(s,"UTF-8");' if constructor else f'r=New {reader}; r.{opening}(s,"UTF-8");'
                    vm.execute(f's=New {memory}; {setup} w.{write}("Привет"); w.{close}();'
                               f's.{seek}(0,{origin}); {setup_r} answer=r.{read}(); r.{close}();')
                    self.assertEqual(vm.execute('answer'), 'Привет')
                    self.assertTrue(vm.execute('s.CanRead'))

    def test_utf8_default_and_no_bom(self):
        stream = Memory(); writer = Writer(stream)
        writer.write_line('Ж'); writer.close()
        self.assertEqual(bytes(stream._state.data), 'Ж\r\n'.encode())
        stream.seek(0, Origin.BEGIN)
        self.assertEqual(Reader(stream, 'UTF-8').read_line(), 'Ж')

    def test_reader_default_is_ansi_without_bom(self):
        self.assertEqual(Reader(source('Привет'.encode('cp1251'))).read(), 'Привет')

    def test_explicit_encoding_bom_and_splitters(self):
        for encoding, mark in (('UTF-8', codecs.BOM_UTF8),
                               ('UTF-16LE', codecs.BOM_UTF16_LE),
                               ('UTF-16BE', codecs.BOM_UTF16_BE)):
            with self.subTest(encoding=encoding):
                stream = Memory(); writer = Writer(stream, encoding, '|', '!', True)
                writer.write('Ж\n'); writer.write_line('Ю'); writer.close()
                self.assertTrue(bytes(stream._state.data).startswith(mark))
                stream.seek(0, Origin.BEGIN)
                reader = Reader(stream, None, '|', '!')
                self.assertEqual(reader.read_line(), 'Ж\nЮ')
                self.assertIsNone(reader.read_line())

    def test_read_snapshot_from_current_position_and_past_end(self):
        stream = source(b'prefix:text'); stream.seek(7, Origin.BEGIN)
        reader = Reader(stream)
        self.assertEqual(reader.read(), 'text')
        self.assertEqual(stream.current_position(), 11)
        stream.seek(20, Origin.BEGIN)
        self.assertIsNone(Reader(stream).read())
        self.assertEqual(stream.current_position(), 20)

    def test_constructor_reader_close_noop_and_open_close(self):
        stream = source(b'ab'); reader = Reader(stream)
        self.assertEqual(reader.read(Decimal(1)), 'a')
        reader.close(); reader.close()
        self.assertEqual(reader.read(), 'b')
        stream.seek(0, Origin.BEGIN); reader.open(stream)
        reader.close()
        with self.assertRaises(ValueError): reader.read()
        self.assertEqual(stream.size(), 2)

    def test_snapshot_independent_of_source_changes_and_close(self):
        stream = source(b'abc'); reader = Reader(stream)
        stream.seek(0, Origin.BEGIN); stream._write_bytes(b'xyz'); stream.close()
        self.assertEqual(reader.read(), 'abc')

    def test_writer_borrows_and_writes_at_current_position(self):
        stream = source(b'012345'); stream.seek(2, Origin.BEGIN)
        writer = Writer(stream, None, None, '', False)
        writer.write('ab'); writer.close(); writer.close()
        self.assertEqual(bytes(stream._state.data), b'01ab45')
        self.assertEqual(stream.current_position(), 4)
        stream._write_bytes(b'!')
        with self.assertRaises(ValueError): writer.write('x')

    def test_stream_fourth_and_fifth_arguments_not_file_append(self):
        stream = Memory()
        with self.assertRaises(TypeError): Writer(stream, None, None, True)
        with self.assertRaises(TypeError): Writer(stream, None, None, '', 'not a bool')
        self.assertEqual(stream.size(), 0)
        writer = Writer(stream, None, None, '', True)
        writer.write('a\n'); writer.close()
        self.assertEqual(bytes(stream._state.data), codecs.BOM_UTF8 + b'a\n')

    def test_file_overloads_preserve_append_and_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'text.txt'
            writer = Writer(str(path)); writer.write('a'); writer.close()
            writer.open(str(path), None, None, True, ''); writer.write('b\n'); writer.close()
            self.assertEqual(path.read_bytes(), codecs.BOM_UTF8 + b'ab\n')
            reader = Reader(str(path)); self.assertEqual(reader.read(), 'ab\n')
            reader.close()
            with self.assertRaises(ValueError): reader.read()

    def test_file_stream_roundtrip_borrowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'text.txt'
            stream = File(str(path), Mode.CREATE, Access.READ_WRITE)
            try:
                writer = Writer(stream); writer.write('Текст'); writer.close()
                stream.seek(0, Origin.BEGIN)
                reader = Reader(); reader.open(stream, 'UTF-8'); self.assertEqual(reader.read(), 'Текст')
                reader.close(); self.assertEqual(stream.size(), len('Текст'.encode()))
            finally:
                stream.close()

    def test_reader_decode_failure_restores_position_and_old_state(self):
        reader = Reader(source(b'old'))
        stream = source(b'!\xff'); stream.seek(1, Origin.BEGIN)
        with self.assertRaises(UnicodeError): reader.open(stream, 'UTF-8')
        self.assertEqual(stream.current_position(), 1)
        self.assertEqual(reader.read(), 'old')
        reader.open(stream, 'iso-8859-1')
        self.assertEqual(reader.read(), 'ÿ')

    def test_reader_validation_does_not_consume_or_replace(self):
        reader = Reader(source(b'old')); stream = source(b'new')
        for args in ((stream, 'unknown-codec'), (stream, None, ''),
                     (stream, None, None, None, True)):
            with self.assertRaises((ValueError, TypeError)): reader.open(*args)
            self.assertEqual(stream.current_position(), 0)
        self.assertEqual(reader.read(), 'old')
        with mock.patch.object(file_io, 'MAX_BYTES', 2), self.assertRaises(ValueError):
            reader.open(stream)
        self.assertEqual(stream.current_position(), 0)

    def test_snapshot_budget_preflight_and_transform_rollback(self):
        stream = source(b'abcd'); stream.seek(1, Origin.BEGIN)
        with mock.patch.object(stream, '_read_bytes', wraps=stream._read_bytes) as read:
            with self.assertRaises(ValueError): read_snapshot(stream, bytes, max_bytes=2)
            read.assert_not_called()
        self.assertEqual(stream.current_position(), 1)
        def fail(data):
            raise ValueError('invalid document')
        with self.assertRaises(ValueError): read_snapshot(stream, fail)
        self.assertEqual(stream.current_position(), 1)
        self.assertEqual(read_snapshot(stream, bytes, max_bytes=3), b'bcd')

    def test_admission_rejects_host_streams_and_subclasses(self):
        class Other(Memory): pass
        for stream in (io.BytesIO(b'a'), Other(), object()):
            self.assertFalse(is_stream(stream))
            with self.assertRaises(TypeError): read_snapshot(stream, bytes)
            with self.assertRaises(TypeError): BinaryStreamSink(stream)
            with self.assertRaises(TypeError): Reader(stream)
            with self.assertRaises(TypeError): Writer(stream)

    def test_closed_readonly_and_writeonly_streams(self):
        closed = Memory(); closed.close()
        for create in (Reader, Writer, BinaryStreamSink):
            with self.assertRaises(ValueError): create(closed)
        readonly = source(b'ab').get_readonly_stream()
        with self.assertRaises(ValueError): Writer(readonly)
        self.assertEqual(Reader(readonly).read(), 'ab')
        with tempfile.TemporaryDirectory() as directory:
            stream = File(str(Path(directory) / 'out'), Mode.CREATE, Access.WRITE)
            try:
                with self.assertRaises(ValueError): Reader(stream)
                self.assertEqual(stream.current_position(), 0)
            finally: stream.close()

    def test_failed_writer_reopen_preserves_old_writer(self):
        stream = Memory(); writer = Writer(stream)
        bad = Memory().get_readonly_stream()
        with self.assertRaises(ValueError): writer.open(bad)
        with self.assertRaises(ValueError): writer.open(Memory(), 'unknown')
        with self.assertRaises(ValueError): writer.open(Memory(Buffer(1)), None, None, '', True)
        writer.write('ok'); writer.close()
        self.assertEqual(bytes(stream._state.data), b'ok')

    def test_capacity_and_encoding_failures_leave_cursor_and_data(self):
        stream = Memory(Buffer(3)); writer = Writer(stream, 'ascii')
        writer.write('ab')
        for text in ('cd', 'Ж'):
            with self.assertRaises((ValueError, UnicodeError)): writer.write(text)
            self.assertEqual(stream.current_position(), 2)
            self.assertEqual(bytes(stream._state.data), b'ab\0')
        writer.write('c'); writer.close()
        self.assertEqual(bytes(stream._state.data), b'abc')

    def test_sink_releases_only_wrapper(self):
        stream = Memory(); sink = BinaryStreamSink(stream)
        self.assertEqual(sink.write(b'abc'), 3)
        sink.flush(); sink.close(); sink.close()
        self.assertEqual(stream.size(), 3)
        with self.assertRaises(ValueError): sink.write(b'x')
        with self.assertRaises(ValueError): sink.flush()

    def test_sink_invalid_data_and_dynamic_readonly(self):
        buffer = Buffer(4); stream = Memory(buffer); sink = BinaryStreamSink(stream)
        with self.assertRaises(TypeError): sink.write(bytearray(b'a'))
        buffer.set_readonly()
        with self.assertRaises(ValueError): sink.write(b'a')
        self.assertEqual(stream.current_position(), 0)
        sink.close()

    def test_reader_invalid_count_keeps_snapshot_cursor(self):
        reader = Reader(source(b'abc'))
        for size in (Decimal(-1), Decimal('1.2'), Decimal('NaN'), True):
            with self.assertRaises(TypeError): reader.read(size)
        self.assertEqual(reader.read(), 'abc')
