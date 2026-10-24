"""Independent synthetic headers only: these are not native 1C validation."""
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from yadinassi.storage import filedb
from yadinassi.storage.filedb import InspectionStatus as S, InspectionReason as R


def header(version=(8, 3, 8, 0), pages=3, page_size=4096, reserved=b'\0' * 4):
    return (b'1CDBMSV8' + bytes(version) + pages.to_bytes(4, 'little')
            + reserved + page_size.to_bytes(4, 'little'))


def metadata(size=12288, **changes):
    values = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600,
                  st_size=size, st_mtime_ns=3, st_ctime_ns=4)
    values.update(changes)
    return SimpleNamespace(**values)


class FileDBHeaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'offline.1CD'

    def make_file(self, raw=None, size=12288):
        with self.path.open('wb') as stream:
            stream.write(header() if raw is None else raw)
            stream.truncate(size)
        return self.path

    def result(self, raw=None, size=12288, **limits):
        return filedb.inspect_header(self.make_file(raw, size), **limits)

    def assert_reason(self, result, status, reason):
        self.assertEqual((result.status, result.reason), (status, reason))
        self.assertIsNone(result.header)

    def test_all_supported_page_sizes_and_immutable_facts(self):
        for size in (4096, 8192, 16384, 32768, 65536):
            with self.subTest(size=size):
                result = self.result(header(page_size=size), 3 * size)
                self.assertEqual(result.status, S.HEADER_LAYOUT_MATCH)
                self.assertEqual(result.header, filedb.FileDBHeader((8, 3, 8, 0), size, 3, 3 * size))
                self.assertIsNone(result.reason)
                with self.assertRaises(FrozenInstanceError):
                    result.status = S.IO_ERROR
                with self.assertRaises(FrozenInstanceError):
                    result.header.page_count = 5

    def test_old_format_ignores_extra_and_opaque_bytes(self):
        for extra in (b'\xff' * 4, b'\0' * 4, b'abcd'):
            raw = header((8, 2, 14, 0), reserved=b'\xffabc')[:20] + extra
            self.assertEqual(self.result(raw).header.page_size, 4096)
        self.assertEqual(self.result(header(reserved=b'\xffabc')).status, S.HEADER_LAYOUT_MATCH)

    def test_every_truncation(self):
        for version in ((8, 2, 14, 0), (8, 3, 8, 0)):
            for length in range(24):
                with self.subTest(version=version, length=length):
                    result = self.result(header(version)[:length], length)
                    reason = R.UNALIGNED_FILE if version == (8, 2, 14, 0) and length >= 20 else R.TRUNCATED_HEADER
                    self.assert_reason(result, S.INVALID_LAYOUT, reason)

    def test_unknown_format_dispatch_before_other_fields_and_limits(self):
        for version in ((8, 3, 8, 1), (8, 3, 9, 0), (255, 255, 255, 255)):
            for length in (12, 16, 20, 24):
                with self.subTest(version=version, length=length):
                    self.assert_reason(self.result(header(version, pages=0, page_size=0)[:length], length,
                                                   max_pages=1, max_file_bytes=1),
                                       S.UNSUPPORTED_FORMAT, R.UNKNOWN_VERSION)

    def test_bad_magic(self):
        self.assert_reason(self.result(b'BADMAGIC' + header()[8:]), S.INVALID_LAYOUT, R.BAD_MAGIC)

    def test_invalid_page_sizes(self):
        for size in (0, 1, 4095, 4097, 131072, (1 << 32) - 1):
            self.assert_reason(self.result(header(page_size=size)), S.INVALID_LAYOUT, R.INVALID_PAGE_SIZE)

    def test_layout_mismatch(self):
        self.assert_reason(self.result(size=12289), S.INVALID_LAYOUT, R.UNALIGNED_FILE)
        self.assert_reason(self.result(header(pages=4)), S.INVALID_LAYOUT, R.PAGE_COUNT_MISMATCH)
        self.assert_reason(self.result(header(pages=0)), S.INVALID_LAYOUT, R.PAGE_COUNT_MISMATCH)
        raw = bytearray(header())
        raw[12:16] = (3).to_bytes(4, 'big')
        self.assert_reason(self.result(raw), S.INVALID_LAYOUT, R.PAGE_COUNT_MISMATCH)
        raw = bytearray(header())
        raw[20:24] = (4096).to_bytes(4, 'big')
        self.assert_reason(self.result(raw), S.INVALID_LAYOUT, R.INVALID_PAGE_SIZE)

    def test_policy_limits_separate_from_layout_errors(self):
        for count in (1, 2):
            self.assert_reason(self.result(header(pages=count), count * 4096), S.POLICY_LIMIT, R.MINIMUM_PAGES)
        self.assert_reason(self.result(max_pages=2), S.POLICY_LIMIT, R.MAXIMUM_PAGES)
        self.assert_reason(self.result(max_file_bytes=12287), S.POLICY_LIMIT, R.MAXIMUM_FILE_BYTES)
        self.assertEqual(self.result(max_pages=3, max_file_bytes=12288).status, S.HEADER_LAYOUT_MATCH)
        self.assert_reason(self.result(header(pages=4), max_pages=2), S.INVALID_LAYOUT, R.PAGE_COUNT_MISMATCH)

    def test_limits_reject_bool_nonint_and_out_of_range_before_open(self):
        for name, ceiling in (('max_pages', (1 << 32) - 1), ('max_file_bytes', ((1 << 32) - 1) * 65536)):
            for value in (True, False, 0, -1, 1.0, '3', None, ceiling + 1):
                with self.subTest(name=name, value=value), mock.patch.object(filedb.os, 'open') as opened:
                    with self.assertRaises(ValueError):
                        filedb.inspect_header(self.path, **{name: value})
                    opened.assert_not_called()

    def inspect_mock(self, raw=None, before=None, after=None, **limits):
        before = before or metadata()
        with mock.patch.object(filedb.os, 'open', return_value=73) as opened, \
             mock.patch.object(filedb.os, 'read', side_effect=[header() if raw is None else raw, b'']) as read, \
             mock.patch.object(filedb.os, 'fstat', side_effect=[before, after or before]) as checked, \
             mock.patch.object(filedb.os, 'close') as closed:
            result = filedb.inspect_header('never-opened-private-path', **limits)
            self.assertEqual(opened.call_args.args[1] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), 0)
            expected_reads = [mock.call(73, 24)]
            raw_length = len(header() if raw is None else raw)
            if 0 < raw_length < 24:
                expected_reads.append(mock.call(73, 24 - raw_length))
            self.assertEqual(read.call_args_list, expected_reads)
            self.assertEqual(checked.call_args_list, [mock.call(73), mock.call(73)])
            closed.assert_called_once_with(73)
            return result

    def test_old_minimum_header_read_is_twenty_bytes(self):
        result = self.inspect_mock(header((8, 2, 14, 0))[:20])
        self.assertEqual(result.status, S.HEADER_LAYOUT_MATCH)
        self.assertEqual(result.header.page_size, 4096)

    def test_partial_reads_accumulate_without_exceeding_budget(self):
        raw = header()
        for chunks in ([raw[:1], raw[1:8], raw[8:20], raw[20:]],
                       [bytes([value]) for value in raw]):
            with self.subTest(lengths=[len(chunk) for chunk in chunks]), \
                 mock.patch.object(filedb.os, 'open', return_value=73), \
                 mock.patch.object(filedb.os, 'read', side_effect=chunks) as read, \
                 mock.patch.object(filedb.os, 'fstat', return_value=metadata()) as checked, \
                 mock.patch.object(filedb.os, 'close') as closed:
                result = filedb.inspect_header(self.path)
                self.assertEqual(result.status, S.HEADER_LAYOUT_MATCH)
                consumed = 0
                calls = []
                for chunk in chunks:
                    calls.append(mock.call(73, 24 - consumed))
                    consumed += len(chunk)
                self.assertEqual(consumed, 24)
                self.assertEqual(read.call_args_list, calls)
                self.assertEqual(checked.call_args_list, [mock.call(73), mock.call(73)])
                closed.assert_called_once_with(73)

    def test_partial_reads_stop_at_eof_and_report_truncation(self):
        raw = header()
        for length in range(24):
            chunks = [raw[index:index + 1] for index in range(length)] + [b'']
            with self.subTest(length=length), \
                 mock.patch.object(filedb.os, 'open', return_value=73), \
                 mock.patch.object(filedb.os, 'read', side_effect=chunks) as read, \
                 mock.patch.object(filedb.os, 'fstat', return_value=metadata()), \
                 mock.patch.object(filedb.os, 'close'):
                self.assert_reason(filedb.inspect_header(self.path), S.INVALID_LAYOUT, R.TRUNCATED_HEADER)
                self.assertEqual(read.call_args_list,
                                 [mock.call(73, 24 - index) for index in range(length + 1)])

    def test_uint32_max_no_allocation_or_count_based_reads(self):
        count = (1 << 32) - 1
        info = metadata(count * 65536)
        result = self.inspect_mock(header(pages=count, page_size=65536), info)
        self.assertEqual(result.header.page_count, count)
        self.assert_reason(self.inspect_mock(header(pages=count, page_size=65536), info, max_pages=3),
                           S.POLICY_LIMIT, R.MAXIMUM_PAGES)

    def test_every_metadata_change_wins_even_over_bad_header(self):
        for name in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            after = metadata(**{name: getattr(metadata(), name) + 1})
            self.assertEqual(self.inspect_mock(b'bad', after=after).status, S.CHANGED_DURING_READ)

    def test_real_read_bounded_and_content_unchanged(self):
        self.make_file(header(page_size=65536), 3 * 65536)
        before = self.path.read_bytes()
        real_read = os.read
        with mock.patch.object(filedb.os, 'read', wraps=real_read) as read:
            self.assertEqual(filedb.inspect_header(self.path).status, S.HEADER_LAYOUT_MATCH)
            self.assertEqual(read.call_count, 1)
            self.assertEqual(read.call_args.args[1], 24)
        self.assertEqual(self.path.read_bytes(), before)

    def test_io_errors_are_sanitized_and_descriptor_closed(self):
        self.assertEqual(filedb.inspect_header(self.path).status, S.IO_ERROR)
        for operation in ('read', 'fstat'):
            with mock.patch.object(filedb.os, 'open', return_value=73), \
                 mock.patch.object(filedb.os, 'fstat', return_value=metadata()), \
                 mock.patch.object(filedb.os, operation, side_effect=OSError('private-path-secret')), \
                 mock.patch.object(filedb.os, 'close') as closed:
                result = filedb.inspect_header('private-path-secret')
                self.assertEqual(result, filedb.HeaderInspection(S.IO_ERROR))
                self.assertNotIn('secret', repr(result))
                closed.assert_called_once_with(73)

    def test_nonregular_does_not_read(self):
        with mock.patch.object(filedb.os, 'open', return_value=73), \
             mock.patch.object(filedb.os, 'fstat', return_value=metadata(st_mode=stat.S_IFIFO)), \
             mock.patch.object(filedb.os, 'read') as read, \
             mock.patch.object(filedb.os, 'close') as closed:
            self.assertEqual(filedb.inspect_header(self.path).status, S.NOT_REGULAR_FILE)
            read.assert_not_called()
            closed.assert_called_once_with(73)

    def test_pure_decoder_matches_path_without_io(self):
        expected = self.result()
        with mock.patch.object(filedb.os, 'open', side_effect=AssertionError('no I/O')), \
             mock.patch.object(filedb.os, 'read', side_effect=AssertionError('no I/O')):
            self.assertEqual(filedb.decode_header(header(), 12288), expected)
            self.assertEqual(filedb.decode_header(header((8, 2, 14, 0))[:20], 12288).header.page_size, 4096)

    def test_pure_decoder_exact_types_and_bounded_prefix(self):
        class BytesSubclass(bytes): pass
        class IntSubclass(int): pass
        for raw in (bytearray(header()), memoryview(header()), BytesSubclass(header()),
                    header() + b'x', None, '1CDBMSV8'):
            with self.subTest(raw=type(raw)), self.assertRaises(ValueError):
                filedb.decode_header(raw, 12288)
        for size in (True, False, -1, 12288.0, '12288', None, IntSubclass(12288)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                filedb.decode_header(header(), size)
        self.assert_reason(filedb.decode_header(b'', 0), S.INVALID_LAYOUT, R.TRUNCATED_HEADER)
        for name, ceiling in (('max_pages', (1 << 32)-1),
                              ('max_file_bytes', ((1 << 32)-1)*65536)):
            for value in (True, 0, -1, 1.0, None, ceiling+1):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    filedb.decode_header(header(), 12288, **{name:value})

    def test_pure_decoder_unknown_version_has_no_geometry(self):
        result = filedb.decode_header(header((8, 3, 8, 1), pages=0, page_size=0),
                                      1 << 200, max_pages=1, max_file_bytes=1)
        self.assert_reason(result, S.UNSUPPORTED_FORMAT, R.UNKNOWN_VERSION)


if __name__ == '__main__':
    unittest.main()
