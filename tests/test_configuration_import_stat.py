"""Compatible stat identities without dropping same-API mutation guards."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import os
import stat
import tempfile
import unittest
from unittest.mock import patch
import yadinassi.configuration_import as reader
from sqlite_catalog_fixture import configuration_files


def info(source=None, **changes):
    names = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size',
             'st_mtime_ns', 'st_ctime_ns', 'st_birthtime_ns', 'st_file_attributes')
    values = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600,
                  st_nlink=1, st_size=10, st_mtime_ns=20, st_ctime_ns=30,
                  st_birthtime_ns=30, st_file_attributes=0)
    if source is not None:
        values = {name: getattr(source, name, None if name == 'st_birthtime_ns' else 0)
                  for name in names}
    values.update(changes)
    return SimpleNamespace(**values)


class ImportStatTests(unittest.TestCase):
    @contextmanager
    def source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name, content in configuration_files().items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            yield root

    def test_windows_cross_api_ctime_distinction_and_posix_guard(self):
        before, opened = info(), info(st_ctime_ns=40)
        with patch.object(reader.sys, 'platform', 'win32'):
            self.assertTrue(reader._path_matches_descriptor(before, opened))
            self.assertFalse(reader._path_matches_descriptor(before, info(st_birthtime_ns=31)))
            self.assertFalse(reader._path_matches_descriptor(before, info(st_birthtime_ns=None)))
            self.assertTrue(reader._path_matches_descriptor(info(st_birthtime_ns=None), info(st_birthtime_ns=None, st_ctime_ns=40)))
        with patch.object(reader.sys, 'platform', 'linux'):
            self.assertFalse(reader._path_matches_descriptor(before, opened))
        self.assertNotEqual(reader._snapshot(before), reader._snapshot(opened))

    def test_cross_api_identity_and_timestamp_changes_still_refuse(self):
        for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns'):
            with self.subTest(field=field), patch.object(reader.sys, 'platform', 'win32'):
                self.assertFalse(reader._path_matches_descriptor(info(), info(**{field: 999})))
        for field in ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size',
                      'st_mtime_ns', 'st_ctime_ns', 'st_birthtime_ns', 'st_file_attributes'):
            with self.subTest(field=field):
                self.assertNotEqual(reader._snapshot(info()), reader._snapshot(info(**{field:999})))

    def test_same_file_windows_split_ctime_imports_without_retry(self):
        real_stat, real_fstat = os.stat, os.fstat
        def by_path(*args, **kwargs):
            result = real_stat(*args, **kwargs)
            return info(result, st_birthtime_ns=100, st_ctime_ns=100)
        def by_fd(fd):
            return info(real_fstat(fd), st_birthtime_ns=100, st_ctime_ns=200)
        with self.source() as root, patch.object(reader.sys, 'platform', 'win32'), patch.object(reader.os, 'stat', by_path), patch.object(reader.os, 'fstat', by_fd):
            self.assertEqual(reader.load_configuration_directory(root).name, 'OwnedApplication')

    def test_same_descriptor_change_during_read_refuses(self):
        real_fstat = os.fstat
        for field in ('st_ctime_ns', 'st_mtime_ns', 'st_size', 'st_ino', 'st_nlink'):
            calls = []
            def by_fd(fd):
                result = real_fstat(fd); calls.append(fd)
                return info(result, **({field: getattr(result, field) + 1} if len(calls) == 2 else {}))
            with self.subTest(field=field), self.source() as root, patch.object(reader.os, 'fstat', by_fd):
                with self.assertRaisesRegex(ValueError, '^configuration source changed$'):
                    reader.load_configuration_directory(root)
                self.assertEqual(len(calls), 2)

    def test_path_replacement_or_link_change_after_open_refuses(self):
        real_stat = os.stat
        for field in ('st_ino', 'st_dev', 'st_ctime_ns', 'st_nlink', 'st_file_attributes'):
            calls = []
            def by_path(*args, **kwargs):
                result = real_stat(*args, **kwargs)
                if stat.S_ISREG(result.st_mode):
                    calls.append(args[0])
                    if len(calls) == 2:
                        return info(result, **{field: getattr(result, field, 0) + 1})
                return result
            with self.subTest(field=field), self.source() as root, patch.object(reader.os, 'stat', by_path):
                with self.assertRaisesRegex(ValueError, '^configuration source changed$'):
                    reader.load_configuration_directory(root)
                self.assertEqual(len(calls), 2)
