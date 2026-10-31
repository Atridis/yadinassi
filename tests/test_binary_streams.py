"""Ordinary binary workflow and bounded owned-file tests; not native evidence."""
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.binary_streams import (
    BSLBinaryDataBuffer as Buffer, BSLMemoryStream as Memory,
    BSLFileStream as File, BSLStream, BSLByteOrder as Order,
    BSLFileOpenMode as Mode, BSLFileAccess as Access,
    BSLPositionInStream as Origin, binary_data_to_buffer, buffer_to_binary_data,
    MAX_BYTES)
from yadinassi.file_io import BSLBinaryData
from yadinassi.type_values import type_of
from yadinassi.values import BSLType
from yadinassi import serialization


class BufferTests(unittest.TestCase):
    def test_index_iteration_and_unsigned_integer_endian(self):
        b = Buffer(16)
        for width in (2, 4, 8):
            value = (1 << (width*8)) - 2
            b._write_int(1, Decimal(value), width, Order.BIG)
            self.assertEqual(b._read_int(1, width, Order.BIG), value)
            self.assertEqual(b.get(width), 254)
        b.write32(0, 16909060)
        self.assertEqual(list(b)[:4], [4, 3, 2, 1])
        b.set_member('ПорядокБайтов', Order.BIG)
        self.assertEqual(b.read32(0), 67305985)
        b.set_index(0, 99); self.assertEqual(b.get_index(0), 99)

    def test_shared_slice_vs_copies_and_overlapping_write(self):
        b = Buffer.from_bytes(b'abcde', Order.BIG)
        view = b.get_slice(1, 3); view.set(0, 90)
        self.assertEqual(bytes(b._view), b'aZcde')
        copied = b.read(0, 3); copied.set(0, 0)
        self.assertEqual(b.get(0), ord('a'))
        self.assertIs(copied._order, Order.BIG)
        b.write(1, b.get_slice(0, 4))
        self.assertEqual(bytes(b._view), b'aaZcd')
        self.assertEqual(bytes(b.reverse()._view), b'dcZaa')
        self.assertEqual(bytes(b.concat(view)._view), b'aaZcdaZc')

    def test_readonly_copy_and_validation_leave_data_unchanged(self):
        b = Buffer.from_bytes(b'1234'); b.set_readonly()
        for operation in (lambda: b.set(0, 0), lambda: b.write16(0, 0),
                          lambda: b.write(0, Buffer(1))):
            with self.assertRaises(ValueError): operation()
        self.assertEqual(bytes(b._view), b'1234')
        b.copy().set(0, 0)
        with self.assertRaises(ValueError): b.get_slice(0).set(0, 0)

    def test_invalid_numbers_sizes_and_hostile_equality_are_rejected(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('host equality called')
        for value in (-1, MAX_BYTES+1, True, '2', Decimal('NaN'), Decimal('Infinity'), Decimal('1.5'), Hostile()):
            with self.subTest(value=type(value)), self.assertRaises((ValueError, TypeError)):
                Buffer(value)
        b = Buffer(4)
        for args in ((-1, 2), (3, 2), (0, MAX_BYTES+1)):
            with self.assertRaises(ValueError): b.get_slice(*args)
        for value in (-1, 256, True):
            with self.assertRaises(ValueError): b.set(0, value)
        with self.assertRaises(ValueError): b.write16(0, 65536)
        with self.assertRaises(TypeError): b.write16(0, 1, 'little')

    def test_copy_and_concat_resource_bounds(self):
        with mock.patch('yadinassi.binary_streams.MAX_BYTES', 8):
            a = Buffer.from_bytes(b'12345')
            with self.assertRaises(ValueError): a.concat(a)
        self.assertEqual(bytes(a._view), b'12345')


class MemoryTests(unittest.TestCase):
    def test_capacity_is_not_size_read_eof_and_seek(self):
        m = Memory(100); self.assertEqual(m.size(), 0)
        m.write(Buffer.from_bytes(b'abcdef'), 1, 4)
        self.assertEqual((m.size(), m.current_position()), (4, 4))
        self.assertEqual(m.seek(-2, Origin.END), 2)
        result = Buffer.from_bytes(b'.......')
        self.assertEqual(m.read(result, 2, 5), 2)
        self.assertEqual(bytes(result._view), b'..de...')
        self.assertEqual(m.read(result, 0, 1), 0)
        self.assertEqual(m.seek(-1, Origin.CURRENT), 3)
        self.assertEqual(m.seek(1), 1)

    def test_buffer_stream_shares_storage_and_is_fixed_capacity(self):
        b = Buffer.from_bytes(b'abcd'); m = Memory(b)
        m.write(Buffer.from_bytes(b'Z'), 0, 1)
        self.assertEqual(b.get(0), ord('Z'))
        b.set(1, ord('Q')); m.seek(0)
        out = Buffer(4); m.read(out, 0, 4)
        self.assertEqual(bytes(out._view), b'ZQcd')
        with self.assertRaises(ValueError): m.write(out, 0, 1)
        self.assertEqual(m.current_position(), 4)
        b.set_readonly()
        self.assertFalse(m.get_member('CanWrite'))
        with self.assertRaises(ValueError): m.write(out, 0, 0)

    def test_readonly_view_shares_cursor_and_rejects_mutations(self):
        m = Memory(Buffer.from_bytes(b'abcd')); view = m.get_readonly_stream()
        self.assertIs(type(view), BSLStream)
        self.assertFalse(view.get_member('CanWrite'))
        view.seek(2); self.assertEqual(m.current_position(), 2)
        out = Buffer(1); view.read(out, 0, 1)
        self.assertEqual(m.current_position(), 3)
        self.assertEqual(out.get(0), ord('c'))
        with self.assertRaises(ValueError): view.write(out, 0, 1)
        with self.assertRaises(ValueError): view.set_size(0)

    def test_copy_consumes_remaining_and_prevalidates_destination(self):
        m = Memory(Buffer.from_bytes(b'abcde')); m.seek(1)
        dest = Memory(); self.assertEqual(m.copy_to(dest, 3), 3)
        self.assertEqual(dest.close_and_get_binary_data()._data, b'bcd')
        self.assertEqual(m.current_position(), 4)
        fixed = Memory(Buffer(0))
        with self.assertRaises(ValueError): m.copy_to(fixed)
        self.assertEqual(m.current_position(), 4)
        with self.assertRaises(ValueError): m.copy_to(m)

    def test_size_gaps_and_limits_are_bounded(self):
        m = Memory(); m.set_size(4); self.assertEqual(m.size(), 4)
        m.seek(7); m.write(Buffer.from_bytes(b'Q'), 0, 1)
        self.assertEqual(m.size(), 8)
        m.set_size(2); self.assertEqual(m.size(), 2)
        # Gap bytes are unspecified by 1C: deliberately assert no byte values.
        with self.assertRaises(ValueError): m.seek(MAX_BYTES+1)
        with self.assertRaises(ValueError): m.set_size(MAX_BYTES+1)
        with self.assertRaises(ValueError): m.seek(-1)
        m.seek(MAX_BYTES)
        with self.assertRaises(ValueError): m.write(Buffer(1), 0, 1)
        self.assertEqual(m.size(), 2)

    def test_close_and_binary_data_bridges_are_snapshots(self):
        b = Buffer.from_bytes(b'abc'); data = buffer_to_binary_data(b)
        b.set(0, 0); self.assertEqual(data._data, b'abc')
        b2 = binary_data_to_buffer(data); b2.set(0, 1)
        self.assertEqual(data._data, b'abc')
        a, other = data.open_stream_for_read(), data.open_stream_for_read()
        a.seek(2); self.assertEqual(other.current_position(), 0)
        m = Memory(); data.write(m)
        self.assertEqual(m.close_and_get_binary_data()._data, b'abc')
        m.close()
        for operation in (m.size, m.flush, m.current_position, m.get_readonly_stream,
                          m.close_and_get_binary_data, lambda: m.get_member('CanRead')):
            with self.assertRaises(ValueError): operation()

    def test_read_validation_does_not_advance_or_mutate(self):
        m = Memory(Buffer.from_bytes(b'abc')); target = Buffer(2)
        with self.assertRaises(ValueError): m.read(target, 1, 2)
        self.assertEqual(m.current_position(), 0)
        target.set_readonly()
        with self.assertRaises(ValueError): m.read(target, 0, 1)
        self.assertEqual(m.current_position(), 0)
        self.assertEqual(bytes(target._view), b'\0\0')


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='binary-stream-owned-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data.bin'
    def stream(self, mode=Mode.OPEN, access=None):
        stream = File(str(self.path), mode, access)
        self.addCleanup(stream.close)
        return stream

    def test_create_write_read_copy_flush_reopen(self):
        f = self.stream(Mode.CREATE); f.write(Buffer.from_bytes(b'abcdef'), 0, 6)
        f.flush(); self.assertEqual(self.path.read_bytes(), b'abcdef')
        f.seek(1); m = Memory(); self.assertEqual(f.copy_to(m, 3), 3)
        self.assertEqual(m.close_and_get_binary_data()._data, b'bcd')
        f.close(); f.close()
        r = self.stream(access=Access.READ); b = Buffer(8)
        self.assertEqual(r.read(b, 1, 7), 6)
        self.assertEqual(bytes(b._view), b'\0abcdef\0')
        with self.assertRaises(ValueError): r.set_size(1)
        with self.assertRaises(ValueError): r.write(b, 0, 1)

    def test_all_six_open_modes_and_no_truncation_on_invalid_access(self):
        with self.assertRaises(ValueError): self.stream()
        f = self.stream(Mode.CREATE_NEW); f.close(); self.path.write_bytes(b'abc')
        with self.assertRaises(ValueError): self.stream(Mode.CREATE_NEW)
        self.assertEqual(self.path.read_bytes(), b'abc')
        f = self.stream(Mode.OPEN_OR_CREATE); self.assertEqual(f.size(), 3); f.close()
        f = self.stream(Mode.APPEND); self.assertEqual(f.current_position(), 3)
        f.write(Buffer.from_bytes(b'd'), 0, 1); f.close()
        self.assertEqual(self.path.read_bytes(), b'abcd')
        with self.assertRaises(ValueError): self.stream(Mode.TRUNCATE, Access.READ)
        self.assertEqual(self.path.read_bytes(), b'abcd')
        f = self.stream(Mode.TRUNCATE); self.assertEqual(f.size(), 0); f.close()
        self.path.unlink(); f = self.stream(Mode.APPEND); self.assertEqual(f.size(), 0)

    def test_write_only_and_binary_data_stream_write(self):
        f = self.stream(Mode.CREATE, Access.WRITE)
        BSLBinaryData.from_bytes(b'12').write(f)
        with self.assertRaises(ValueError): f.read(Buffer(2), 0, 1)
        with self.assertRaises(ValueError): f.get_readonly_stream()
        f.set_size(1); f.close(); self.assertEqual(self.path.read_bytes(), b'1')

    def test_nonregular_and_url_rejected(self):
        with self.assertRaises(ValueError): File(self.temp.name, Mode.OPEN)
        with self.assertRaises(ValueError): File('https://example.invalid/file', Mode.OPEN)
        if hasattr(os, 'mkfifo'):
            fifo = Path(self.temp.name) / 'owned.fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError): File(str(fifo), Mode.OPEN)

    def test_network_and_windows_device_names_rejected_before_open(self):
        paths = (r"\\server\share\a.bin", "//server/share/a.bin", r"\\.\pipe\named",
                 r"\\?\UNC\server\share\a.bin", r"\??\C:\a.bin", "NUL", "nul.txt",
                 r"C:\owned\COM1", r"C:\owned\LPT9.log", "CONIN$", "AUX ", "NUL:", "NUL .txt", "file:stream")
        for path in paths:
            with self.subTest(path=path), mock.patch('yadinassi.binary_streams.os.open') as opened:
                with self.assertRaises(ValueError): File(path, Mode.OPEN)
                opened.assert_not_called()

    def test_oversized_existing_file_rejected_before_truncation(self):
        with self.path.open('wb') as f: f.truncate(MAX_BYTES+1)
        with self.assertRaises(ValueError): self.stream(Mode.CREATE)
        self.assertEqual(self.path.stat().st_size, MAX_BYTES+1)

    def test_invalid_arguments_do_not_touch_file(self):
        self.path.write_bytes(b'KEEP')
        for mode, access in (('Create', None), (Mode.CREATE, True), (Mode.CREATE, -1)):
            with self.assertRaises((ValueError, TypeError)): File(str(self.path), mode, access)
            self.assertEqual(self.path.read_bytes(), b'KEEP')


class RuntimeTests(unittest.TestCase):
    def test_bilingual_registration_index_foreach_and_type_policy(self):
        output = []
        Interpreter(output=output.append).execute('''
Б = Новый БуферДвоичныхДанных(4, ПорядокБайтов.BigEndian);
Б.ЗаписатьЦелое32(0, 16909060); Б[0] = 9;
С = 0; Для Каждого Байт Из Б Цикл С = С + Байт; КонецЦикла;
Сообщить(С); Сообщить(Б.Перевернуть().Получить(0));
П = Новый MemoryStream(Б); Сообщить(TypeOf(П) = Type("ПотокВПамяти"));
Д = GetBinaryDataFromBinaryDataBuffer(Б);
Сообщить(GetBinaryDataBufferFromBinaryData(Д).Size);
П.Закрыть();
''')
        self.assertEqual(output, ['18', '4', 'Да', '4'])
        for value, kind in ((Buffer(0), BSLType.BINARY_DATA_BUFFER), (Memory(), BSLType.MEMORY_STREAM),
                            (Order.BIG, BSLType.BYTE_ORDER), (Mode.CREATE, BSLType.FILE_OPEN_MODE),
                            (Access.READ, BSLType.FILE_ACCESS), (Origin.END, BSLType.POSITION_IN_STREAM)):
            self.assertIs(type_of(value), kind)
            self.assertIn(kind, serialization._UNSUPPORTED_CODEC_TYPES)


if __name__ == '__main__': unittest.main()
