"""Descriptor adapter tests, not native multirow/cursor acceptance evidence."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi.database_context import FileDBContext
from yadinassi.storage import catalog_reader
from yadinassi.storage.filedb_catalog import UnsupportedLayout


class CatalogRowsContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / '1Cv8.1CD'
        self.path.write_bytes(b'bounded offline fixture')
        self.context = FileDBContext(self.path.parent)

    def test_readonly_descriptor_offsets_result_and_close(self):
        result = object()
        callbacks = []

        def read(read_at, size, *, catalog_name):
            self.assertEqual(size, self.path.stat().st_size)
            self.assertEqual(catalog_name, 'Products')
            self.assertEqual(read_at(8, 7), b'offline')
            self.assertEqual(read_at(0, 7), b'bounded')
            callbacks.append(read_at)
            return result

        before = self.path.read_bytes()
        with mock.patch.object(catalog_reader, 'read_catalog_rows', side_effect=read), \
             mock.patch.object(os, 'open', wraps=os.open) as opened, \
             mock.patch.object(os, 'close', wraps=os.close) as closed:
            self.assertIs(self.context.catalog_rows('Products'), result)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(closed.call_count, 1)
        self.assertEqual(opened.call_args.args[1] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), 0)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(OSError):
            callbacks[0](0, 1)

    def test_source_change_rejects_result_and_closes(self):
        def change(*args, **kwargs):
            with self.path.open('ab') as stream:
                stream.write(b'changed')
            return object()
        with mock.patch.object(catalog_reader, 'read_catalog_rows', side_effect=change), \
             mock.patch.object(os, 'close', wraps=os.close) as closed:
            with self.assertRaisesRegex(ValueError, 'source_changed'):
                self.context.catalog_rows('Products')
        self.assertEqual(closed.call_count, 1)

    def test_reader_error_is_finite_and_descriptor_closed(self):
        with mock.patch.object(catalog_reader, 'read_catalog_rows',
                               side_effect=UnsupportedLayout('nonreserved_free_slot')), \
             mock.patch.object(os, 'close', wraps=os.close) as closed:
            with self.assertRaisesRegex(ValueError, '^file database catalog inspection failed: nonreserved_free_slot$'):
                self.context.catalog_rows('Products')
        self.assertEqual(closed.call_count, 1)

    def test_missing_image_has_no_path_or_os_error_details(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, '^file database catalog inspection failed: file_io_failed$'):
            self.context.catalog_rows('Products')

    def test_unsupported_path_is_lazy_and_does_not_open(self):
        with mock.patch.object(os, 'open', side_effect=AssertionError('unexpected open')):
            context = FileDBContext('invalid"directory')
            with self.assertRaisesRegex(ValueError, '^unsupported file database directory$'):
                context.catalog_rows('Products')

    def test_directory_is_not_a_regular_image(self):
        self.path.unlink()
        self.path.mkdir()
        # POSIX can open a directory, Windows may reject os.open directly.
        with self.assertRaisesRegex(ValueError, '(not_regular_file|file_io_failed)$'):
            self.context.catalog_rows('Products')

    def test_fallback_private_seek_reader(self):
        if not hasattr(os, 'pread'):
            self.skipTest('host already uses fallback')
        pread = os.pread
        del os.pread
        try:
            def read(read_at, size, *, catalog_name):
                self.assertEqual(read_at(8, 7), b'offline')
                self.assertEqual(read_at(0, 7), b'bounded')
                return 'result'
            with mock.patch.object(catalog_reader, 'read_catalog_rows', side_effect=read):
                self.assertEqual(self.context.catalog_rows('Products'), 'result')
        finally:
            os.pread = pread


if __name__ == '__main__':
    unittest.main()
