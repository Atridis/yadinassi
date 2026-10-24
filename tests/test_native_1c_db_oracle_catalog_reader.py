"""Pinned-descriptor synthetic mechanics, not native compatibility evidence."""
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_standalone(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


snapshots = load_standalone(
    'catalog_snapshot_subject', ROOT / 'scripts/native_1c_db_oracle/snapshots.py')
reader = load_standalone('catalog_reader_subject', ROOT / 'yadinassi/storage/filedb_catalog.py')
POSIX = (os.name == 'posix'
         and all(hasattr(os, name) for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK', 'pread'))
         and {os.open, os.stat, os.mkdir}.issubset(os.supports_dir_fd)
         and os.scandir in os.supports_fd)


def synthetic_catalog_bytes():
    """Small independent hand-built catalog with two physical field names."""
    page = 8192
    raw = bytearray(4 * page)
    u32 = lambda value: value.to_bytes(4, 'little')
    raw[:24] = b'1CDBMSV8' + bytes((8, 3, 8, 0)) + u32(4) + b'OPAQ' + u32(page)
    raw[2 * page:2 * page + 28] = (
        b'\x1c\xfd\0\0' + u32(1) + u32(2) + u32(3) + page.to_bytes(8, 'little') + u32(3))
    catalog = b'en_US'.ljust(32, b'\0') + u32(1) + u32(2)
    descriptor = ('{"SyntheticTable",0,{"Fields",{"ID","B",0,16,0,""},'
                  '{"Code","N",0,9,0,""}},{"Indexes"},'
                  '{"Recordlock","0"},{"Files",0,0,0}}').encode('utf-8')
    for block, payload in ((1, catalog), (2, descriptor)):
        start = 3 * page + block * 256
        raw[start:start + 6 + len(payload)] = u32(0) + len(payload).to_bytes(2, 'little') + payload
    return bytes(raw)


def normalize_owners(test):
    """Model the harness's fixed UID/GID without depending on the test host."""
    real_stat, real_fstat, real_scandir = os.stat, os.fstat, os.scandir

    def owned(info):
        fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        return SimpleNamespace(**dict(fields, st_uid=1000, st_gid=1000))

    class Entry:
        def __init__(self, entry):
            self.entry = entry

        def __getattr__(self, name):
            return getattr(self.entry, name)

        def stat(self, **kwargs):
            return owned(self.entry.stat(**kwargs))

    @contextmanager
    def scandir(path):
        with real_scandir(path) as entries:
            yield (Entry(entry) for entry in entries)

    for name, replacement in (
            ('stat', lambda *args, **kwargs: owned(real_stat(*args, **kwargs))),
            ('fstat', lambda *args, **kwargs: owned(real_fstat(*args, **kwargs))),
            ('scandir', scandir)):
        patch = mock.patch.object(snapshots.os, name, side_effect=replacement)
        patch.start()
        test.addCleanup(patch.stop)


class StandaloneCatalogTests(unittest.TestCase):
    def test_staged_reader_needs_no_interpreter_or_package_import(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); import filedb_catalog, snapshots; "
            "assert not any(n == 'yadinassi' or n.startswith('yadinassi.') for n in sys.modules); "
            "assert 'pyuca' not in sys.modules and 'prompt_toolkit' not in sys.modules; "
            "assert callable(snapshots.inspect_frozen_catalog); "
            "assert filedb_catalog.CatalogLimits().max_read_bytes == 64 * 1024 * 1024")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / 'filedb_catalog.py').write_bytes(
                (ROOT / 'yadinassi/storage/filedb_catalog.py').read_bytes())
            (target / 'snapshots.py').write_bytes(
                (ROOT / 'scripts/native_1c_db_oracle/snapshots.py').read_bytes())
            result = subprocess.run(
                [sys.executable, '-I', '-S', '-B', '-c', code, str(target)],
                capture_output=True, text=True, encoding='utf-8', timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(POSIX, 'Native Linux pinned-descriptor operations are unavailable')
class PinnedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup)
        normalize_owners(self)
        self.live = self.root / 'live'
        self.live.mkdir()
        self.data = synthetic_catalog_bytes()
        (self.live / snapshots.DATABASE_NAME).write_bytes(self.data)
        self.frozen = self.root / 'frozen'
        self.freeze_summary = snapshots.freeze_database(self.live, self.frozen, quiescent=lambda: True)
        self.path = self.frozen / snapshots.DATABASE_NAME
        self.limits = reader.CatalogLimits()

    def cleanup(self):
        for current, directories, _ in os.walk(self.root):
            os.chmod(current, 0o700)
            for name in directories:
                path = Path(current) / name
                if not path.is_symlink():
                    path.chmod(0o700)
        self.temp.cleanup()

    def inspect(self, **kwargs):
        options = dict(quiescent=lambda: True, read_catalog=reader.read_catalog, limits=self.limits)
        options.update(kwargs)
        return snapshots.inspect_frozen_catalog(self.frozen, **options)

    def assert_kind(self, kind, action):
        with self.assertRaises(snapshots.OracleError) as caught:
            action()
        self.assertEqual(caught.exception.kind, kind)
        self.assertEqual(str(caught.exception), kind)
        return caught.exception

    def test_real_reader_uses_one_fd_between_hashes_and_quiescence_checks(self):
        events, opened, read_fds, pread_fds = [], [], [], []
        real_open, real_read, real_pread, real_digest = os.open, os.read, os.pread, snapshots._digest

        def open_file(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if os.fspath(path) == snapshots.DATABASE_NAME:
                opened.append(fd)
                self.assertTrue(args[0] & os.O_NOFOLLOW)
            return fd

        def read(fd, amount):
            read_fds.append(fd)
            events.append('hash_read')
            return real_read(fd, amount)

        def pread(fd, amount, offset):
            pread_fds.append(fd)
            events.append('catalog_read')
            self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), len(self.data))
            return real_pread(fd, amount, offset)

        def digest(fd, size):
            events.append('hash_start')
            return real_digest(fd, size)

        def quiet():
            events.append('quiet')
            return True

        with mock.patch.object(os, 'open', side_effect=open_file), \
                mock.patch.object(os, 'read', side_effect=read), \
                mock.patch.object(os, 'pread', side_effect=pread), \
                mock.patch.object(snapshots, '_digest', side_effect=digest), \
                mock.patch.object(reader, 'inspect_catalog', side_effect=AssertionError('no reopen')):
            hook = mock.Mock()
            summary, catalog = self.inspect(quiescent=quiet, before_read=hook)
        self.assertEqual(summary, {key: self.freeze_summary[key] for key in ('bytes', 'sha256')})
        self.assertEqual(summary['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual([table.name for table in catalog.tables], ['SyntheticTable'])
        self.assertEqual([field.name for field in catalog.tables[0].fields], ['ID', 'Code'])
        self.assertGreater(catalog.usage.read_bytes, 0)
        self.assertEqual(len(opened), 1)
        self.assertEqual(set(read_fds + pread_fds), set(opened))
        self.assertEqual(hook.call_count, len(pread_fds))
        self.assertEqual(events[0], 'quiet')
        self.assertEqual(events[-1], 'quiet')
        hashes = [index for index, value in enumerate(events) if value == 'hash_start']
        catalog_reads = [index for index, value in enumerate(events) if value == 'catalog_read']
        self.assertEqual(len(hashes), 2)
        self.assertTrue(all(hashes[0] < index < hashes[1] for index in catalog_reads))
        with self.assertRaises(OSError):
            os.fstat(opened[0])
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_non_quiescent_before_first_payload_prevents_all_reads(self):
        for value in (False, None, 1):
            with self.subTest(value=value), \
                    mock.patch.object(os, 'read', side_effect=AssertionError('no payload')), \
                    mock.patch.object(os, 'pread', side_effect=AssertionError('no payload')):
                self.assert_kind('snapshot_not_quiescent', lambda: self.inspect(quiescent=lambda: value))
        self.assert_kind('snapshot_not_quiescent', lambda: self.inspect(
            quiescent=mock.Mock(side_effect=RuntimeError('PRIVATE'))))

    def test_final_quiescence_is_required_after_success_and_reader_failure(self):
        for decoder in (reader.read_catalog, mock.Mock(side_effect=reader.InvalidStructure('file_signature'))):
            with self.subTest(decoder=decoder):
                quiet = mock.Mock(side_effect=(True, False))
                self.assert_kind('snapshot_not_quiescent', lambda: self.inspect(
                    quiescent=quiet, read_catalog=decoder))
                self.assertEqual(quiet.call_count, 2)

    def test_initial_hash_failure_still_rechecks_quiescence_and_closes_fd(self):
        quiet = mock.Mock(return_value=True)
        fds = []

        def digest(fd, size):
            fds.append(fd)
            raise snapshots.OracleError('snapshot_changed')

        with mock.patch.object(snapshots, '_digest', side_effect=digest):
            self.assert_kind('snapshot_changed', lambda: self.inspect(quiescent=quiet))
        self.assertEqual(quiet.call_count, 2)
        with self.assertRaises(OSError):
            os.fstat(fds[0])

    def test_writable_directory_file_ancillary_and_live_inputs_are_rejected(self):
        for path in (self.frozen, self.path):
            mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(mode | stat.S_IWUSR)
            self.assert_kind('invalid_input', self.inspect)
            path.chmod(mode)
        self.assert_kind('invalid_input', lambda: snapshots.inspect_frozen_catalog(
            self.live, quiescent=lambda: True, read_catalog=reader.read_catalog, limits=self.limits))
        self.frozen.chmod(0o700)
        (self.frozen / 'unexpected').write_bytes(b'PRIVATE')
        self.frozen.chmod(0o500)
        self.assert_kind('invalid_input', self.inspect)

    def test_symlink_hardlink_and_ancestor_symlink_are_rejected(self):
        self.frozen.chmod(0o700)
        self.path.unlink()
        self.path.symlink_to(self.live / snapshots.DATABASE_NAME)
        self.frozen.chmod(0o500)
        self.assert_kind('invalid_input', self.inspect)
        self.frozen.chmod(0o700)
        self.path.unlink()
        os.link(self.live / snapshots.DATABASE_NAME, self.path)
        self.frozen.chmod(0o500)
        self.assert_kind('invalid_input', self.inspect)
        link = self.root / 'linked'
        link.symlink_to(self.frozen, target_is_directory=True)
        self.assert_kind('invalid_input', lambda: snapshots.inspect_frozen_catalog(
            link, quiescent=lambda: True, read_catalog=reader.read_catalog, limits=self.limits))

    def test_oversized_file_is_rejected_before_payload_access(self):
        with mock.patch.object(snapshots, 'MAX_FILE_BYTES', len(self.data) - 1), \
                mock.patch.object(os, 'read', side_effect=AssertionError('no payload')):
            self.assert_kind('artifact_limit', self.inspect)

    def test_real_reader_failure_preserves_final_hash_and_closes_fd(self):
        self.path.chmod(0o600)
        invalid = bytearray(self.data)
        invalid[8:12] = bytes((8, 3, 8, 1))
        self.path.write_bytes(invalid)
        self.path.chmod(0o400)
        real_digest = snapshots._digest
        fds = []

        def digest(fd, size):
            fds.append(fd)
            return real_digest(fd, size)

        quiet = mock.Mock(return_value=True)
        with mock.patch.object(snapshots, '_digest', side_effect=digest), \
                self.assertRaises(reader.UnsupportedLayout) as caught:
            self.inspect(quiescent=quiet)
        self.assertEqual(caught.exception.code, 'storage_version')
        self.assertEqual(len(fds), 2)
        self.assertEqual(len(set(fds)), 1)
        self.assertEqual(quiet.call_count, 2)
        with self.assertRaises(OSError):
            os.fstat(fds[0])

    def test_real_reader_limits_are_preserved(self):
        with self.assertRaises(reader.ResourceLimit) as caught:
            self.inspect(limits=reader.CatalogLimits(max_read_bytes=1))
        self.assertEqual(caught.exception.code, 'read_bytes')

    def test_changed_bytes_override_success_or_private_reader_failure(self):
        for raises in (False, True):
            with self.subTest(raises=raises):
                def changed(read_at, size, *, limits):
                    result = reader.read_catalog(read_at, size, limits=limits)
                    self.path.chmod(0o600)
                    with self.path.open('r+b') as file:
                        file.seek(size - 1)
                        file.write(b'X' if not raises else b'Y')
                    self.path.chmod(0o400)
                    if raises:
                        raise reader.InvalidStructure('PRIVATE')
                    return result
                self.assert_kind('snapshot_changed', lambda: self.inspect(read_catalog=changed))

    def test_digest_change_is_rejected_even_if_metadata_checks_are_mocked_stable(self):
        with mock.patch.object(snapshots, '_digest', side_effect=('a' * 64, 'b' * 64)), \
                mock.patch.object(snapshots, '_unchanged'):
            self.assert_kind('snapshot_changed', self.inspect)

    def test_replaced_database_is_rejected_even_with_identical_bytes(self):
        def replaced(read_at, size, *, limits):
            result = reader.read_catalog(read_at, size, limits=limits)
            self.frozen.chmod(0o700)
            replacement = self.frozen / 'replacement'
            replacement.write_bytes(self.data)
            replacement.chmod(0o400)
            replacement.replace(self.path)
            self.frozen.chmod(0o500)
            return result
        self.assert_kind('snapshot_changed', lambda: self.inspect(read_catalog=replaced))

    def test_replaced_frozen_directory_is_rejected_even_on_reader_failure(self):
        def replaced(read_at, size, *, limits):
            reader.read_catalog(read_at, size, limits=limits)
            self.frozen.rename(self.root / 'moved')
            self.frozen.mkdir()
            (self.frozen / snapshots.DATABASE_NAME).write_bytes(self.data)
            (self.frozen / snapshots.DATABASE_NAME).chmod(0o400)
            self.frozen.chmod(0o500)
            raise reader.InvalidStructure('PRIVATE')
        self.assert_kind('snapshot_changed', lambda: self.inspect(read_catalog=replaced))

    def test_reader_callback_is_bounded_and_cannot_outlive_the_descriptor(self):
        callbacks = []

        def checked(read_at, size, *, limits):
            callbacks.append(read_at)
            for offset, length in ((-1, 1), (0, -1), (size, 1), (size + 1, 0),
                                   (0, size + 1), (True, 1), (0, False), (0.0, 1)):
                with mock.patch.object(os, 'pread', side_effect=AssertionError('no invalid I/O')):
                    self.assert_kind('invalid_input', lambda: read_at(offset, length))
            self.assertEqual(read_at(size, 0), b'')
            return reader.read_catalog(read_at, size, limits=limits)

        self.inspect(read_catalog=checked)
        with mock.patch.object(os, 'pread', side_effect=AssertionError('no closed-fd I/O')):
            self.assert_kind('invalid_input', lambda: callbacks[0](0, 24))

    def test_deadline_and_io_failures_still_check_integrity_and_close_fd(self):
        for kind in ('timeout', 'snapshot_changed', 'unexpected_failure'):
            real_digest = snapshots._digest
            fds = []

            def digest(fd, size):
                fds.append(fd)
                return real_digest(fd, size)

            hook = (mock.Mock(side_effect=snapshots.OracleError('timeout')) if kind == 'timeout'
                    else mock.Mock(side_effect=RuntimeError('PRIVATE')) if kind == 'unexpected_failure'
                    else None)
            pread = (mock.Mock(side_effect=OSError('PRIVATE')) if kind == 'snapshot_changed'
                     else os.pread)
            with self.subTest(kind=kind), \
                    mock.patch.object(snapshots, '_digest', side_effect=digest), \
                    mock.patch.object(os, 'pread', side_effect=pread):
                self.assert_kind(kind, lambda: self.inspect(before_read=hook))
            self.assertEqual(len(fds), 2)
            with self.assertRaises(OSError):
                os.fstat(fds[0])

    def test_noncallable_inputs_fail_before_filesystem_access(self):
        for field in ('quiescent', 'read_catalog', 'before_read'):
            with self.subTest(field=field), \
                    mock.patch.object(snapshots, '_path', side_effect=AssertionError('no I/O')):
                self.assert_kind('invalid_input', lambda: self.inspect(**{field: False}))


if __name__ == '__main__':
    unittest.main()
