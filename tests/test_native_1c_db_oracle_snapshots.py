"""Offline synthetic-byte tests. No native platform execution or format proof."""
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / "scripts/native_1c_db_oracle/snapshots.py"
SPEC = importlib.util.spec_from_file_location("db_oracle_snapshots_under_test", MODULE)
snapshots = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshots)

POSIX_FILE_API = (
    os.name == "posix"
    and all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "fchmod"))
    and {os.open, os.stat, os.mkdir}.issubset(os.supports_dir_fd)
    and os.scandir in os.supports_fd
)


def stat_fields(info, **changes):
    fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
    fields.update(changes)
    return SimpleNamespace(**fields)


def normalize_fixture_owners(test):
    """Model fixed native UID/GID 1000 without chown or host-dependent policy."""
    real_stat, real_fstat, real_scandir = os.stat, os.fstat, os.scandir
    def owned(info):
        return stat_fields(info, st_uid=1000, st_gid=1000)
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
            ("stat", lambda *a, **kw: owned(real_stat(*a, **kw))),
            ("fstat", lambda *a, **kw: owned(real_fstat(*a, **kw))),
            ("scandir", scandir)):
        patch = mock.patch.object(snapshots.os, name, side_effect=replacement)
        patch.start()
        test.addCleanup(patch.stop)


class DatabaseEntryValidationTests(unittest.TestCase):
    def info(self, **changes):
        fields = dict(st_mode=stat.S_IFREG | 0o600, st_nlink=1, st_size=0,
                      st_uid=1000, st_gid=1000)
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_entry_enums_are_fixed_and_complete(self):
        self.assertEqual(snapshots.ENTRY_CLASSES, (
            "database", "cfl_database", "cfl_temp_database", "cfl_lock", "cfl_temp_lock",
            "cfl_session_lock", "base_1cl", "temp_1cd", "temp_1cl", "session_history", "event_log", "other"))
        self.assertEqual(snapshots.ENTRY_SHAPES, (
            "owned_regular_zero", "owned_regular_nonzero", "unowned_regular_zero",
            "unowned_regular_nonzero", "symlink", "hardlink", "link_count", "directory",
            "special", "invalid_size"))

    def test_typed_error_retains_only_bounded_fields(self):
        for entry_class in snapshots.ENTRY_CLASSES:
            for shape in snapshots.ENTRY_SHAPES:
                error = snapshots.DatabaseEntryError(entry_class, shape)
                self.assertIsInstance(error, snapshots.OracleError)
                self.assertEqual(vars(error), {"kind": "invalid_input",
                                              "entry_class": entry_class, "shape": shape})
                self.assertEqual(error.args, ("invalid_input",))
                self.assertEqual(str(error), "invalid_input")

    def test_typed_error_rejects_unknown_text_and_nonexact_strings(self):
        class StringSubclass(str):
            pass
        for value in (True, False, None, 1, [], {}, "PRIVATE PATH",
                      StringSubclass("database")):
            with self.subTest(field="entry_class", value=value):
                with self.assertRaisesRegex(ValueError, "^invalid entry class$"):
                    snapshots.DatabaseEntryError(value, "owned_regular_zero")
        for value in (True, False, None, 1, [], {}, "PRIVATE CONTENT",
                      StringSubclass("owned_regular_zero")):
            with self.subTest(field="shape", value=value):
                with self.assertRaisesRegex(ValueError, "^invalid entry shape$"):
                    snapshots.DatabaseEntryError("database", value)

    def test_shape_classifier_is_finite_and_links_precede_ownership(self):
        cases = (
            ({}, "owned_regular_zero"),
            ({"st_size": 1}, "owned_regular_nonzero"),
            ({"st_uid": 0}, "unowned_regular_zero"),
            ({"st_gid": 0, "st_size": 1}, "unowned_regular_nonzero"),
            ({"st_mode": stat.S_IFLNK, "st_nlink": 2}, "symlink"),
            ({"st_nlink": 2, "st_uid": 0}, "hardlink"),
            ({"st_nlink": 0, "st_gid": 0}, "link_count"),
            ({"st_nlink": -1}, "link_count"),
            ({"st_mode": stat.S_IFDIR, "st_nlink": 2}, "directory"),
            ({"st_mode": stat.S_IFIFO}, "special"),
            ({"st_mode": stat.S_IFSOCK}, "special"),
            ({"st_size": -1, "st_uid": 0}, "invalid_size"),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertEqual(snapshots._entry_shape(self.info(**changes)), expected)

    def test_name_classifier_is_exact_not_a_suffix_rule(self):
        cases = {
            "1Cv8.1CD": "database", "1Cv8.1CD.cfl": "cfl_database",
            "1Cv8tmp.1CD.cfl": "cfl_temp_database", "1Cv8.1CL.cfl": "cfl_lock",
            "1Cv8tmp.1CL.cfl": "cfl_temp_lock", "1Cv8snc.1CL.cfl": "cfl_session_lock", "1Cv8snc.1CD": "session_history",
            "1Cv8.1CL": "base_1cl", "1Cv8tmp.1CD": "temp_1cd",
            "1Cv8tmp.1CL": "temp_1cl", "1Cv8tmp.1cl": "other",
            "1Cv8.1CL.extra": "other", "1Cv8tmp.1CD.extra": "other",
            "1Cv8Log": "event_log", "1cv8.1cd.cfl": "other",
            "1Cv8.1CD.CFL": "other", "1Cv8snc.1CD.cfl": "other",
            "secret-name.cfl": "other", "1Cv8.1CD.cfl.extra": "other",
        }
        for name, expected in cases.items():
            self.assertEqual(snapshots._entry_class(name), expected)
            self.assertEqual(snapshots.diagnostic_entry_class(name), expected)

    def test_diagnostic_basename_is_exact_ascii_and_fullmatch_bounded(self):
        class StringSubclass(str):
            pass
        accepted = ("1Cv8", "1Cv8.1CL", "1Cv8tmp.1CD", "1Cv8.A-z_9",
                    "1Cv8" + "A" * 48)
        rejected = (None, True, False, 1, [], {}, b"1Cv8.1CL", "", "1Cv",
                    "1cv8.1CL", "1Cv8" + "A" * 49, "1Cv8" + "A" * 50,
                    "1Cv8\n", "1Cv8.1CL\n", "1Cv8\r", "1Cv8\t", "1Cv8\0",
                    "1Cv8\ud800", "1Cv8é", "1Cv8名", "1Cv8/file", "1Cv8\\file",
                    "/1Cv8.1CL", "1Cv8:file", StringSubclass("1Cv8.1CL"))
        for value in accepted:
            self.assertIs(snapshots.valid_diagnostic_basename(value), True)
        for value in rejected:
            with self.subTest(value=value):
                self.assertIs(snapshots.valid_diagnostic_basename(value), False)
                if value is not None:  # None is the explicit no-capture sentinel.
                    with self.assertRaisesRegex(ValueError, "^invalid entry basename$"):
                        snapshots.DatabaseEntryError("other", "owned_regular_zero",
                                                     basename=value)

    def test_optional_basename_is_class_bound_without_io_or_error_text(self):
        with mock.patch.object(snapshots.os, "open", side_effect=AssertionError("no I/O")), \
                mock.patch.object(snapshots.os, "stat", side_effect=AssertionError("no I/O")), \
                mock.patch.object(snapshots.os, "scandir", side_effect=AssertionError("no I/O")):
            for name in ("1Cv8", "1Cv8.1CL", "1Cv8tmp.1CD", "1Cv8tmp.1CL",
                         "1Cv8snc.1CD", "1Cv8.1CD", "1Cv8Log", "1Cv8.1CD.cfl"):
                entry_class = snapshots.diagnostic_entry_class(name)
                error = snapshots.DatabaseEntryError(entry_class, "owned_regular_zero",
                                                       basename=name)
                self.assertEqual(vars(error), {"kind": "invalid_input",
                                              "entry_class": entry_class,
                                              "shape": "owned_regular_zero", "basename": name})
                self.assertEqual(error.args, ("invalid_input",))
                self.assertEqual(str(error), "invalid_input")
                wrong_class = "other" if entry_class != "other" else "database"
                with self.assertRaisesRegex(ValueError, "^invalid entry basename$"):
                    snapshots.DatabaseEntryError(wrong_class, "owned_regular_zero", basename=name)
        for shape in snapshots.ENTRY_SHAPES:
            if shape != "owned_regular_zero":
                with self.subTest(shape=shape):
                    with self.assertRaisesRegex(ValueError, "^invalid entry basename$"):
                        snapshots.DatabaseEntryError("base_1cl", shape, basename="1Cv8.1CL")
        self.assertFalse(hasattr(snapshots.DatabaseEntryError(
            "base_1cl", "owned_regular_zero", basename=None), "basename"))

    def test_capture_source_flag_requires_exact_bool_before_io(self):
        with mock.patch.object(snapshots, "_copy_database") as copy_database, \
                mock.patch.object(snapshots, "_path", side_effect=AssertionError("no I/O")):
            for value in (None, 0, 1, "true", "false", [], {}, object()):
                with self.subTest(value=value):
                    with self.assertRaises(snapshots.OracleError) as failure:
                        snapshots.freeze_database(Path("source"), Path("destination"),
                                                  quiescent=lambda: True,
                                                  capture_source_name=value)
                    self.assertEqual(vars(failure.exception), {"kind": "invalid_input"})
            copy_database.assert_not_called()


@unittest.skipUnless(POSIX_FILE_API, "Native Linux snapshot filesystem API is unavailable")
class AncillaryInventoryTests(unittest.TestCase):
    NAMES = ("1Cv8.1CD.cfl", "1Cv8tmp.1CD.cfl", "1Cv8.1CL.cfl", "1Cv8tmp.1CL.cfl", "1Cv8snc.1CL.cfl")
    TREE_NAMES = ("1Cv8Log", "synthetic-tree", "1Cv8.1CL", "1cv8.1cd", "private\né")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "live"
        self.source.mkdir()
        self.db = self.source / "1Cv8.1CD"
        self.data = b"synthetic bytes only" * 5000
        self.db.write_bytes(self.data)
        self.frozen = self.root / "frozen"

        normalize_fixture_owners(self)

    def cleanup(self):
        for current, directories, _ in os.walk(self.root):
            os.chmod(current, 0o700)
            for directory in directories:
                path = Path(current) / directory
                if not path.is_symlink():
                    os.chmod(path, 0o700)
        self.temp.cleanup()

    def cfl(self, name=None):
        path = self.source / (name or self.NAMES[0])
        path.touch()
        return path

    def freeze(self, **kwargs):
        return snapshots.freeze_database(self.source, self.frozen,
                                         quiescent=kwargs.get("quiescent", lambda: True),
                                         capture_source_name=kwargs.get("capture_source_name", False))

    def assert_kind(self, kind, action):
        with self.assertRaises(snapshots.OracleError) as failure:
            action()
        self.assertEqual(failure.exception.kind, kind)
        self.assertEqual(str(failure.exception), kind)
        return failure.exception

    def assert_entry(self, entry_class, shape, action=None):
        error = self.assert_kind("invalid_input", action or self.freeze)
        self.assertIsInstance(error, snapshots.DatabaseEntryError)
        self.assertEqual((error.entry_class, error.shape), (entry_class, shape))
        self.assertEqual(set(vars(error)), {"kind", "entry_class", "shape"})

    @contextmanager
    def tree_case(self, name):
        """Give each parameterized adversarial case an isolated live source."""
        previous = self.source, self.db, self.frozen
        case = Path(tempfile.mkdtemp(prefix="tree-case-", dir=self.root)).resolve()
        self.source = case / "live"
        self.source.mkdir()
        self.db = self.source / "1Cv8.1CD"
        self.db.write_bytes(self.data)
        self.frozen = case / "frozen"
        tree = self.source / name
        tree.mkdir()
        try:
            yield tree
        finally:
            self.source, self.db, self.frozen = previous

    def test_each_exact_cfl_name_is_accepted_without_reading_content(self):
        real_read, real_open = snapshots.os.read, snapshots.os.open
        opened = []
        for index, name in enumerate(self.NAMES):
            with self.subTest(name=name):
                path = self.cfl(name)
                inode = path.stat().st_ino
                self.frozen = self.root / f"frozen-{index}"
                def read(descriptor, size):
                    self.assertNotEqual(os.fstat(descriptor).st_ino, inode)
                    return real_read(descriptor, size)
                def open_file(name, flags, *args, **kwargs):
                    if name in self.NAMES:
                        opened.append(flags)
                        self.assertIsNotNone(kwargs.get("dir_fd"))
                    return real_open(name, flags, *args, **kwargs)
                with mock.patch.object(snapshots.os, "read", side_effect=read), \
                        mock.patch.object(snapshots.os, "open", side_effect=open_file):
                    result = self.freeze()
                self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())
                self.assertEqual([p.name for p in self.frozen.iterdir()], ["1Cv8.1CD"])
                self.assertEqual(path.stat().st_size, 0)
                path.unlink()
        self.assertGreaterEqual(len(opened), len(self.NAMES) * 3)  # Before copy and both rechecks.
        for flags in opened:
            self.assertEqual(flags & (os.O_NOFOLLOW | os.O_NONBLOCK),
                             os.O_NOFOLLOW | os.O_NONBLOCK)
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)

    def test_all_five_with_logs_stay_private_and_never_enter_frozen_or_clone(self):
        paths = [self.cfl(name) for name in self.NAMES]
        log = self.source / "1Cv8Log"
        log.mkdir()
        (log / "events.lgp").write_bytes(b"PRIVATE SYNTHETIC LOG")
        before = [snapshots._signature(path.stat()) for path in paths]
        result = self.freeze()
        clone = self.root / "observer"
        snapshots.clone_database(self.frozen, clone, budget_root=self.root)
        self.assertEqual(before, [snapshots._signature(path.stat()) for path in paths])
        for directory in (self.frozen, clone):
            self.assertEqual([p.name for p in directory.iterdir()], ["1Cv8.1CD"])
        self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})
        for private in (*self.NAMES, "1Cv8Log", "PRIVATE"):
            self.assertNotIn(private, str(result))

    def test_each_cfl_injected_into_frozen_source_is_rejected_for_clone(self):
        self.freeze()
        self.frozen.chmod(0o700)
        for name in self.NAMES:
            with self.subTest(name=name):
                path = self.frozen / name
                path.touch()
                self.assert_entry(snapshots._entry_class(name), "owned_regular_zero",
                                  lambda: snapshots.clone_database(
                                      self.frozen, self.root / "observer", budget_root=self.root))
                self.assertFalse((self.root / "observer").exists())
                path.unlink()

    def test_nonempty_root_sidecar_is_accepted_without_reading_its_content(self):
        path = self.cfl()
        path.write_bytes(b"PRIVATE CONTENT")
        inode = path.stat().st_ino
        real_read = snapshots.os.read
        def read(descriptor, length):
            self.assertNotEqual(os.fstat(descriptor).st_ino, inode)
            return real_read(descriptor, length)
        with mock.patch.object(snapshots.os, "read", side_effect=read):
            result = self.freeze()
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(path.read_bytes(), b"PRIVATE CONTENT")
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_owner_group_and_invalid_metadata_are_rejected(self):
        self.cfl()
        real_scandir = snapshots.os.scandir
        for changes, shape in (({"st_uid": 0}, "unowned_regular_zero"),
                               ({"st_gid": 0}, "unowned_regular_zero"),
                               ({"st_size": -1}, "invalid_size"),
                               ({"st_nlink": 0}, "link_count"),
                               ({"st_nlink": 2}, "hardlink")):
            with self.subTest(changes=changes):
                @contextmanager
                def scandir(descriptor):
                    with real_scandir(descriptor) as entries:
                        entries = list(entries)
                    for entry in entries:
                        if entry.name == self.NAMES[0]:
                            initial = entry.stat(follow_symlinks=False)
                            entry.stat = lambda **kw: stat_fields(initial, **changes)
                    yield iter(entries)
                with mock.patch.object(snapshots.os, "scandir", side_effect=scandir):
                    self.assert_entry("cfl_database", shape)
                self.assertFalse(self.frozen.exists())

    def test_symlink_hardlink_fifo_are_rejected_but_owned_directory_is_ancillary(self):
        path = self.source / self.NAMES[0]
        path.symlink_to("/dev/zero")
        self.assert_entry("cfl_database", "symlink")
        path.unlink()
        outside = self.root / "outside-alias"
        outside.touch()
        os.link(outside, path)
        self.assert_entry("cfl_database", "hardlink")
        path.unlink()
        os.mkfifo(path)
        self.assert_entry("cfl_database", "special")
        path.unlink()
        path.mkdir()
        result = self.freeze()
        self.assertEqual(result["bytes"], len(self.data))
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_case_suffix_unknown_and_session_history_are_structurally_accepted(self):
        names = ("1cv8.1cd.cfl", "1Cv8.1CD.CFL", "1Cv8.1CD.cfl.extra",
                 "unknown.cfl", "1Cv8snc.1CD.cfl", "1Cv8snc.1CD",
                 "1Cv8snc.1CL", "1Cv8SNC.1CL.cfl", "1Cv8snc.1CL.cfl.extra")
        for name in names:
            self.cfl(name).write_bytes(b"PRIVATE SIDECAR")
        result = self.freeze()
        self.assertEqual(result["bytes"], len(self.data))
        for name in names:
            self.assertNotIn(name, str(result))
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_database_and_log_symlink_rejects_are_typed(self):
        self.db.unlink()
        self.db.symlink_to("/dev/zero")
        self.assert_entry("database", "symlink")
        self.db.unlink()
        self.db.write_bytes(self.data)
        log = self.source / "1Cv8Log"
        log.symlink_to(self.root, target_is_directory=True)
        self.assert_entry("event_log", "symlink")

    def test_legacy_capture_flag_does_not_emit_accepted_empty_names(self):
        names = ("1Cv8", "1Cv8.1CL", "1Cv8tmp.1CD", "1Cv8tmp.1CL",
                 "1Cv8snc.1CD", "1Cv8unknown_-", "1Cv8" + "A" * 48)
        for name in names:
            self.cfl(name)
        result = self.freeze(capture_source_name=True)
        self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_capture_flag_does_not_change_structural_admission(self):
        self.cfl("1Cv8.1CL")
        for index, capture in enumerate((False, True)):
            self.frozen = self.root / f"frozen-{index}"
            result = self.freeze(capture_source_name=capture)
            self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})

    def test_diagnostic_basename_rules_do_not_limit_structural_admission(self):
        names = ("1cv8.1CL", "private", "1Cv8.1CL\n", "1Cv8é", "1Cv8\\file",
                 "1Cv8:file", "1Cv8" + "A" * 49, "1Cv8" + "A" * 50)
        for name in names:
            self.cfl(name)
        result = self.freeze(capture_source_name=True)
        self.assertEqual(result["bytes"], len(self.data))
        self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})

    def test_opt_in_never_captures_unowned_or_invalid_metadata(self):
        name = "1Cv8.1CL"
        self.cfl(name)
        real_scandir = snapshots.os.scandir
        for changes, shape in (({"st_uid": 0}, "unowned_regular_zero"),
                               ({"st_gid": 0}, "unowned_regular_zero"),
                               ({"st_uid": 0, "st_size": 1}, "unowned_regular_nonzero"),
                               ({"st_size": -1}, "invalid_size"),
                               ({"st_nlink": 0}, "link_count"),
                               ({"st_nlink": 2}, "hardlink")):
            with self.subTest(changes=changes):
                @contextmanager
                def scandir(descriptor):
                    with real_scandir(descriptor) as entries:
                        entries = list(entries)
                    for entry in entries:
                        if entry.name == name:
                            initial = entry.stat(follow_symlinks=False)
                            entry.stat = lambda **kw: stat_fields(initial, **changes)
                    yield iter(entries)
                with mock.patch.object(snapshots.os, "scandir", side_effect=scandir), \
                        mock.patch.object(snapshots.os, "read",
                                          side_effect=AssertionError("must not read")):
                    self.assert_entry("base_1cl", shape, lambda: self.freeze(
                        capture_source_name=True))
                self.assertFalse(self.frozen.exists())

    def test_opt_in_never_captures_links_fifo_or_accepted_owned_directory(self):
        path = self.source / "1Cv8.1CL"
        path.symlink_to("/dev/zero")
        self.assert_entry("base_1cl", "symlink", lambda: self.freeze(capture_source_name=True))
        path.unlink()
        outside = self.root / "outside-alias"
        outside.touch()
        os.link(outside, path)
        self.assert_entry("base_1cl", "hardlink", lambda: self.freeze(capture_source_name=True))
        path.unlink()
        os.mkfifo(path)
        self.assert_entry("base_1cl", "special", lambda: self.freeze(capture_source_name=True))
        path.unlink()
        path.mkdir()
        result = self.freeze(capture_source_name=True)
        self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_opt_in_does_not_capture_database_or_nested_log_rejection(self):
        self.db.unlink()
        self.db.symlink_to("/dev/zero")
        self.assert_entry("database", "symlink", lambda: self.freeze(capture_source_name=True))
        self.db.unlink()
        self.db.write_bytes(self.data)
        log = self.source / "1Cv8Log"
        log.mkdir()
        (log / "1Cv8.1CL").symlink_to("/dev/zero")
        error = self.assert_kind("invalid_input", lambda: self.freeze(capture_source_name=True))
        self.assertEqual(vars(error), {"kind": "invalid_input"})
        self.assertFalse(self.frozen.exists())

    def test_opt_in_missing_database_or_disappearing_entry_has_no_basename(self):
        self.db.unlink()
        error = self.assert_kind("invalid_input", lambda: self.freeze(capture_source_name=True))
        self.assertEqual(vars(error), {"kind": "invalid_input"})
        self.db.write_bytes(self.data)
        self.cfl("1Cv8.1CL")
        real_scandir = snapshots.os.scandir
        @contextmanager
        def scandir(descriptor):
            with real_scandir(descriptor) as entries:
                entries = list(entries)
            for entry in entries:
                if entry.name == "1Cv8.1CL":
                    entry.stat = mock.Mock(side_effect=FileNotFoundError("private path"))
            yield iter(entries)
        with mock.patch.object(snapshots.os, "scandir", side_effect=scandir):
            error = self.assert_kind("invalid_input", lambda: self.freeze(
                capture_source_name=True))
        self.assertEqual(vars(error), {"kind": "invalid_input"})
        self.assertFalse(self.frozen.exists())

    def test_capture_flag_cannot_relax_strict_frozen_inventory(self):
        self.cfl("1Cv8.1CL")
        with snapshots._directory(self.source) as descriptor:
            inventories = [snapshots._database_contents(descriptor, capture_zero_name=capture)
                           for capture in (False, True, None, 1, "true")]
            self.assertTrue(all(value == inventories[0] for value in inventories))
            self.assert_entry("base_1cl", "owned_regular_zero", lambda: snapshots._database_contents(
                descriptor, allow_ancillary=False, capture_zero_name=True))

    def test_opt_in_is_only_used_by_first_source_inventory_never_clone(self):
        self.cfl()
        original = snapshots._database_contents
        calls = []
        def inventory(descriptor, **kwargs):
            calls.append((os.fstat(descriptor).st_ino, kwargs.get("capture_zero_name", False)))
            return original(descriptor, **kwargs)
        with mock.patch.object(snapshots, "_database_contents", side_effect=inventory):
            result = self.freeze(capture_source_name=True)
            self.assertEqual(calls, [(self.source.stat().st_ino, True),
                                     (self.source.stat().st_ino, False),
                                     (self.frozen.stat().st_ino, False),
                                     (self.source.stat().st_ino, False)])
            calls.clear()
            snapshots.clone_database(self.frozen, self.root / "observer", budget_root=self.root)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(capture is False for _, capture in calls))
        self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})

    def test_destination_and_both_source_rechecks_reject_new_entries(self):
        original = snapshots._database_contents
        for index in (2, 3, 4):
            with self.subTest(inventory=index):
                self.frozen = self.root / f"frozen-{index}"
                calls = 0
                path = (self.frozen if index == 3 else self.source) / "1Cv8.1CL"
                def inventory(descriptor, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == index:
                        path.touch()
                        self.assertIs(kwargs.get("capture_zero_name", False), False)
                    return original(descriptor, **kwargs)
                with mock.patch.object(snapshots, "_database_contents", side_effect=inventory):
                    error = self.assert_kind("invalid_input" if index == 3 else "snapshot_changed",
                                             lambda: self.freeze(capture_source_name=True))
                self.assertFalse(hasattr(error, "basename"))
                self.assertEqual(calls, index)
                self.frozen.chmod(0o700)
                path.unlink()

    def test_clone_cannot_capture_injected_eligible_basename(self):
        self.freeze(capture_source_name=True)
        self.frozen.chmod(0o700)
        (self.frozen / "1Cv8.1CL").touch()
        clone = self.root / "observer"
        self.assert_entry("base_1cl", "owned_regular_zero", lambda: snapshots.clone_database(
            self.frozen, clone, budget_root=self.root))
        self.assertFalse(clone.exists())

    def test_empty_cfl_never_substitutes_for_before_or_after_quiescence(self):
        self.cfl()
        for index, results in enumerate(([False], [True, False], [True, True, False])):
            with self.subTest(results=results):
                self.frozen = self.root / f"frozen-{index}"
                quiet = mock.Mock(side_effect=results)
                self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(quiescent=quiet))
                self.assertEqual(quiet.call_count, len(results))

    def test_membership_change_in_either_direction_is_snapshot_changed(self):
        path = self.cfl()
        for index, mutate in enumerate((path.unlink, path.touch)):
            with self.subTest(index=index):
                self.frozen = self.root / f"frozen-{index}"
                # Mutate only at the first quiescence boundary.
                called = False
                def quiescent():
                    nonlocal called
                    if not called:
                        called = True
                        mutate()
                    return True
                self.assert_kind("snapshot_changed", lambda: self.freeze(quiescent=quiescent))

    def test_sidecar_size_change_after_initial_inventory_is_rejected(self):
        path = self.cfl()
        real_write = snapshots._write_all
        def write(descriptor, block):
            real_write(descriptor, block)
            path.write_bytes(b"PRIVATE MUTATION")
        with mock.patch.object(snapshots, "_write_all", side_effect=write):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_empty_same_path_replacement_after_inventory_is_snapshot_changed(self):
        path = self.cfl()
        def quiet():
            path.unlink()
            path.touch()
            return True
        self.assert_kind("snapshot_changed", lambda: self.freeze(quiescent=quiet))

    def test_descriptor_owner_change_is_detected_even_with_unchanged_other_fields(self):
        path = self.cfl()
        inode = path.stat().st_ino
        real_fstat = snapshots.os.fstat
        def fstat(descriptor):
            info = real_fstat(descriptor)
            return stat_fields(info, st_uid=0) if info.st_ino == inode else info
        with mock.patch.object(snapshots.os, "fstat", side_effect=fstat):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_anchored_entry_owner_change_is_detected_even_with_unchanged_other_fields(self):
        self.cfl()
        real_stat = snapshots.os.stat
        def anchored_stat(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            return (stat_fields(info, st_gid=0)
                    if path == self.NAMES[0] and kwargs.get("dir_fd") is not None else info)
        with mock.patch.object(snapshots.os, "stat", side_effect=anchored_stat):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_entry_replacement_between_stat_and_open_is_detected(self):
        path = self.cfl()
        real_open = snapshots.os.open
        changed = False
        def open_file(name, flags, *args, **kwargs):
            nonlocal changed
            if name == self.NAMES[0] and not changed:
                changed = True
                path.unlink()
                os.mkfifo(path)
            return real_open(name, flags, *args, **kwargs)
        with mock.patch.object(snapshots.os, "open", side_effect=open_file):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertTrue(changed)
        self.assertFalse(self.frozen.exists())

    def test_shared_ancillary_caps_are_not_increased(self):
        self.assertEqual(snapshots.MAX_ANCILLARY_BYTES, 16 * 1024 * 1024)
        self.assertEqual(snapshots.MAX_ANCILLARY_FILES, 64)
        self.assertEqual(snapshots.MAX_ANCILLARY_ENTRIES, 128)
        self.assertEqual(snapshots.MAX_ANCILLARY_DEPTH, 2)
        self.assertEqual(snapshots.MAX_TREE_ENTRIES, 4096)
        self.assertEqual(snapshots.MAX_TREE_DEPTH, 16)

    def test_root_sidecars_and_multiple_trees_are_never_read_hashed_or_chmodded(self):
        side = self.cfl("arbitrary-private-sidecar")
        side.write_bytes(b"PRIVATE ROOT SIDECAR")
        private_paths = [side]
        for name in self.TREE_NAMES:
            tree = self.source / name
            nested = tree / "one" / "two"
            nested.mkdir(parents=True)
            private_file = nested / "arbitrary-private-file"
            private_file.write_bytes(b"PRIVATE NESTED FILE")
            # Only the exact database name at the source root is a payload.
            nested_database = tree / "1Cv8.1CD"
            nested_database.write_bytes(b"PRIVATE ANCILLARY, NOT A DATABASE PAYLOAD")
            private_paths.extend((tree, tree / "one", nested, private_file, nested_database))
        before = {path: snapshots._signature(path.stat()) for path in private_paths}
        private_inodes = {path.stat().st_ino for path in private_paths}
        real_read, real_digest, real_chmod = snapshots.os.read, snapshots._digest, snapshots.os.fchmod
        def no_private(action):
            def checked(descriptor, *args):
                self.assertNotIn(os.fstat(descriptor).st_ino, private_inodes)
                return action(descriptor, *args)
            return checked
        with mock.patch.object(snapshots.os, "read", side_effect=no_private(real_read)), \
                mock.patch.object(snapshots, "_digest", side_effect=no_private(real_digest)), \
                mock.patch.object(snapshots.os, "fchmod", side_effect=no_private(real_chmod)):
            result = self.freeze()
            clone = self.root / "observer"
            snapshots.clone_database(self.frozen, clone, budget_root=self.root)
        self.assertEqual({path: snapshots._signature(path.stat()) for path in private_paths}, before)
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertNotIn("private", str(result))
        for directory in (self.frozen, clone):
            self.assertEqual([entry.name for entry in directory.iterdir()], ["1Cv8.1CD"])
            self.assertEqual((directory / "1Cv8.1CD").read_bytes(), self.data)

    def test_inventory_itself_never_reads_or_hashes_even_nonempty_ancillary_files(self):
        self.cfl("root-private").write_bytes(b"ROOT")
        expected = {(), ("root-private",)}
        for name in self.TREE_NAMES:
            tree = self.source / name
            tree.mkdir()
            (tree / "file-private").write_bytes(b"PRIVATE")
            expected.update(((name,), (name, "file-private")))
        with snapshots._directory(self.source) as descriptor, \
                mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no payload I/O")), \
                mock.patch.object(snapshots, "_digest", side_effect=AssertionError("no digest")):
            inventory = snapshots._database_contents(descriptor)
        self.assertEqual(set(inventory), expected)
        self.assertTrue(all(value[1] is None for value in inventory.values()))
        self.assertNotIn(("1Cv8.1CD",), inventory)

    def test_shared_file_count_accepts_64_and_rejects_65_across_multiple_trees(self):
        trees = [self.source / name for name in self.TREE_NAMES]
        for tree in trees:
            tree.mkdir()
        parents = [self.source, *trees]
        for index in range(snapshots.MAX_ANCILLARY_FILES):
            (parents[index % len(parents)] / f"private-{index}").touch()
        with snapshots._directory(self.source) as descriptor:
            snapshots._database_contents(descriptor)
            (trees[-1] / "one-too-many").touch()
            self.assert_kind("artifact_limit", lambda: snapshots._database_contents(descriptor))
        self.assertFalse(self.frozen.exists())

    def test_shared_entry_count_includes_root_sidecars_and_each_tree_root(self):
        self.cfl("one-root-file")
        trees = [self.source / name for name in self.TREE_NAMES]
        for tree in trees:
            tree.mkdir()
        for index in range(snapshots.MAX_ANCILLARY_ENTRIES - len(trees) - 1):
            (trees[index % len(trees)] / f"empty-{index}").mkdir()
        with snapshots._directory(self.source) as descriptor:
            inventory = snapshots._database_contents(descriptor)
            self.assertEqual(len(inventory), snapshots.MAX_ANCILLARY_ENTRIES + 1)  # Plus source root.
            (trees[-1] / "one-too-many").mkdir()
            self.assert_kind("artifact_limit", lambda: snapshots._database_contents(descriptor))
        self.assertFalse(self.frozen.exists())

    def test_shared_byte_limit_is_metadata_only_and_exact_across_multiple_trees(self):
        side = self.cfl("root-private")
        paths = [side]
        for name in self.TREE_NAMES:
            tree = self.source / name
            tree.mkdir()
            paths.append(tree / "file-private")
        portion, remainder = divmod(snapshots.MAX_ANCILLARY_BYTES, len(paths))
        for index, path in enumerate(paths):
            with path.open("wb") as stream:
                stream.truncate(portion + (remainder if index == 0 else 0))
        with snapshots._directory(self.source) as descriptor, \
                mock.patch.object(snapshots.os, "read", side_effect=AssertionError("metadata only")):
            snapshots._database_contents(descriptor)
            with paths[-1].open("r+b") as stream:
                stream.truncate(portion + 1)
            self.assert_kind("artifact_limit", lambda: snapshots._database_contents(descriptor))
        self.assertFalse(self.frozen.exists())

    def test_root_sidecar_cannot_exceed_existing_raw_file_or_live_budget(self):
        side = self.cfl("root-private")
        with side.open("wb") as stream:
            stream.truncate(snapshots.MAX_FILE_BYTES + 1)
        with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("must not read")):
            self.assert_kind("artifact_limit", self.freeze)
        side.write_bytes(b"private")
        with mock.patch.object(snapshots, "MAX_LIVE_BYTES", len(self.data) * 2 + side.stat().st_size - 1):
            self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_wrong_owner_or_group_rejects_nested_regular_files_and_directories(self):
        real_scandir = snapshots.os.scandir
        for name in self.TREE_NAMES:
            with self.tree_case(name) as tree:
                nested = tree / "nested"
                nested.mkdir()
                private_file = nested / "private"
                private_file.write_bytes(b"NONEMPTY")
                for target in (tree, nested, private_file):
                    for field in ("st_uid", "st_gid"):
                        with self.subTest(name=name, target=target.name, field=field):
                            inode = target.stat().st_ino
                            @contextmanager
                            def scandir(descriptor):
                                with real_scandir(descriptor) as entries:
                                    entries = list(entries)
                                for entry in entries:
                                    info = entry.stat(follow_symlinks=False)
                                    if info.st_ino == inode:
                                        entry.stat = lambda info=info, **kw: stat_fields(info, **{field: 0})
                                yield iter(entries)
                            with mock.patch.object(snapshots.os, "scandir", side_effect=scandir), \
                                    mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                                self.assert_kind("invalid_input", self.freeze)
                            self.assertFalse(self.frozen.exists())

    def test_source_root_owner_and_group_are_checked_without_chown(self):
        inode = self.source.stat().st_ino
        real_fstat = snapshots.os.fstat
        for field in ("st_uid", "st_gid"):
            def fstat(descriptor):
                info = real_fstat(descriptor)
                return stat_fields(info, **{field: 0}) if info.st_ino == inode else info
            with mock.patch.object(snapshots.os, "fstat", side_effect=fstat), \
                    mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                self.assert_kind("invalid_input", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_directory_owner_change_is_compared_even_with_identical_other_fields(self):
        log = self.source / "1Cv8Log"
        log.mkdir()
        real_stat = snapshots.os.stat
        def stat_path(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            return (stat_fields(info, st_gid=0)
                    if path == "1Cv8Log" and kwargs.get("dir_fd") is not None else info)
        with mock.patch.object(snapshots.os, "stat", side_effect=stat_path):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_root_owner_change_during_inventory_is_compared_explicitly(self):
        with snapshots._directory(self.source) as descriptor:
            real_fstat = snapshots.os.fstat
            calls = 0
            def fstat(opened):
                nonlocal calls
                info = real_fstat(opened)
                if opened == descriptor:
                    calls += 1
                    if calls > 1:
                        return stat_fields(info, st_uid=0)
                return info
            with mock.patch.object(snapshots.os, "fstat", side_effect=fstat):
                self.assert_kind("snapshot_changed", lambda: snapshots._database_contents(descriptor))

    def test_ancillary_mode_change_between_inventory_passes_is_rejected(self):
        side = self.cfl("private-sidecar")
        real_write = snapshots._write_all
        changed = False
        def write(descriptor, block):
            nonlocal changed
            real_write(descriptor, block)
            if not changed:
                changed = True
                side.chmod(0o400)
        with mock.patch.object(snapshots, "_write_all", side_effect=write):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertTrue(changed)

    def test_arbitrary_nonempty_sidecar_in_frozen_source_is_rejected_before_reading(self):
        self.freeze()
        self.frozen.chmod(0o700)
        (self.frozen / "arbitrary-private-sidecar").write_bytes(b"PRIVATE")
        clone = self.root / "observer"
        with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
            self.assert_entry("other", "owned_regular_nonzero", lambda: snapshots.clone_database(
                self.frozen, clone, budget_root=self.root))
        self.assertFalse(clone.exists())

    def test_initial_census_follows_stable_database_open_and_precedes_all_reads(self):
        real_open, real_read = snapshots.os.open, snapshots.os.read
        database_opened = False
        checks = 0
        reads = 0
        def opened(name, *args, **kwargs):
            nonlocal database_opened
            descriptor = real_open(name, *args, **kwargs)
            if name == "1Cv8.1CD" and os.fstat(descriptor).st_ino == self.db.stat().st_ino:
                database_opened = True
            return descriptor
        def quiet():
            nonlocal checks
            self.assertTrue(database_opened)
            if checks == 0:
                self.assertEqual(reads, 0)
                self.assertFalse(self.frozen.exists())
            checks += 1
            return True
        def read(descriptor, size):
            nonlocal reads
            self.assertGreaterEqual(checks, 1)
            reads += 1
            return real_read(descriptor, size)
        with mock.patch.object(snapshots.os, "open", side_effect=opened), \
                mock.patch.object(snapshots.os, "read", side_effect=read):
            self.freeze(quiescent=quiet)
        self.assertEqual(checks, 3)
        self.assertGreater(reads, 0)

    def test_ancestor_identity_change_is_rejected_even_when_leaf_inode_is_preserved(self):
        ancestor = self.root / "ancestor"
        ancestor.mkdir()
        leaf = ancestor / "leaf"
        leaf.mkdir()
        old = self.root / "old-ancestor"
        with self.assertRaises(snapshots.OracleError) as failure:
            with snapshots._directory(leaf) as descriptor:
                original = snapshots._identity(os.fstat(descriptor))
                ancestor.rename(old)
                ancestor.mkdir()
                (old / "leaf").rename(leaf)
                self.assertEqual(snapshots._identity(leaf.stat()), original)
        self.assertEqual(failure.exception.kind, "snapshot_changed")

    def test_exact_database_directory_is_rejected_before_ancillary_admission(self):
        self.db.unlink()
        self.db.mkdir()
        (self.db / "private-file").write_bytes(b"NOT A DATABASE PAYLOAD")
        with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")), \
                mock.patch.object(snapshots, "_digest", side_effect=AssertionError("no digest")):
            self.assert_entry("database", "directory")
        self.assertFalse(self.frozen.exists())

    def test_nested_database_name_never_substitutes_for_missing_root_payload(self):
        self.db.unlink()
        for name in self.TREE_NAMES:
            tree = self.source / name
            tree.mkdir()
            (tree / "1Cv8.1CD").write_bytes(b"PRIVATE ANCILLARY")
        with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
            self.assert_kind("invalid_input", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_unknown_trees_reject_links_and_special_files_without_reads(self):
        for name in self.TREE_NAMES:
            for kind in ("root_symlink", "file_symlink", "directory_symlink", "hardlink", "fifo"):
                with self.subTest(name=name, kind=kind), self.tree_case(name) as tree:
                    target = tree / "private"
                    if kind == "root_symlink":
                        tree.rmdir()
                        tree.symlink_to(self.root, target_is_directory=True)
                    elif kind == "file_symlink":
                        target.symlink_to(self.db)
                    elif kind == "directory_symlink":
                        target.symlink_to(self.root, target_is_directory=True)
                    elif kind == "hardlink":
                        outside = self.source.parent / "outside-private"
                        outside.write_bytes(b"PRIVATE")
                        os.link(outside, target)
                    else:
                        os.mkfifo(target)
                    with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                        self.assert_kind("invalid_input", self.freeze)
                    self.assertFalse(self.frozen.exists())

    def test_unknown_tree_files_reject_invalid_metadata_without_reads(self):
        real_scandir = snapshots.os.scandir
        changes_list = ({"st_nlink": 0}, {"st_nlink": -1}, {"st_nlink": 2},
                        {"st_size": -1}, {"st_mode": stat.S_IFSOCK})
        for name in self.TREE_NAMES:
            with self.tree_case(name) as tree:
                target = tree / "private"
                target.write_bytes(b"PRIVATE")
                inode = target.stat().st_ino
                for changes in changes_list:
                    with self.subTest(name=name, changes=changes):
                        @contextmanager
                        def scandir(descriptor):
                            with real_scandir(descriptor) as entries:
                                entries = list(entries)
                            for entry in entries:
                                info = entry.stat(follow_symlinks=False)
                                if info.st_ino == inode:
                                    entry.stat = lambda info=info, **kw: stat_fields(info, **changes)
                            yield iter(entries)
                        with mock.patch.object(snapshots.os, "scandir", side_effect=scandir), \
                                mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                            self.assert_kind("invalid_input", self.freeze)
                        self.assertFalse(self.frozen.exists())

    def test_unknown_tree_open_flags_are_descriptor_anchored_and_no_follow(self):
        real_open = snapshots.os.open
        for name in self.TREE_NAMES:
            with self.subTest(name=name), self.tree_case(name) as tree:
                nested = tree / "nested"
                nested.mkdir()
                (nested / "private-file").write_bytes(b"PRIVATE")
                seen = []
                def opened(path, flags, *args, **kwargs):
                    if path in (name, "nested", "private-file"):
                        seen.append(path)
                        self.assertIsNotNone(kwargs.get("dir_fd"))
                        self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
                        self.assertEqual(flags & (os.O_NOFOLLOW | os.O_NONBLOCK),
                                         os.O_NOFOLLOW | os.O_NONBLOCK)
                        if path != "private-file":
                            self.assertTrue(flags & os.O_DIRECTORY)
                    return real_open(path, flags, *args, **kwargs)
                with snapshots._directory(self.source) as descriptor, \
                        mock.patch.object(snapshots.os, "open", side_effect=opened), \
                        mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                    snapshots._database_contents(descriptor)
                self.assertEqual(set(seen), {name, "nested", "private-file"})

    def test_unknown_tree_directory_owner_changes_are_compared_at_both_checks(self):
        real_fstat, real_stat = snapshots.os.fstat, snapshots.os.stat
        for name in self.TREE_NAMES:
            with self.tree_case(name) as tree:
                nested = tree / "nested"
                nested.mkdir()
                for target in (tree, nested):
                    for field in ("st_uid", "st_gid"):
                        for check in ("fstat", "stat"):
                            with self.subTest(name=name, target=target.name, field=field, check=check):
                                inode = target.stat().st_ino
                                original = real_fstat if check == "fstat" else real_stat
                                def changed(*args, **kwargs):
                                    info = original(*args, **kwargs)
                                    return stat_fields(info, **{field: 0}) if info.st_ino == inode else info
                                with mock.patch.object(snapshots.os, check, side_effect=changed), \
                                        mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                                    self.assert_kind("snapshot_changed", self.freeze)
                                self.assertFalse(self.frozen.exists())

    def test_unknown_tree_directory_swap_is_rejected_before_or_after_open(self):
        real_open = snapshots.os.open
        for name in self.TREE_NAMES:
            for position in ("root", "nested"):
                for replacement in ("before_directory", "before_symlink", "before_fifo", "after_directory"):
                    with self.subTest(name=name, position=position, replacement=replacement), \
                            self.tree_case(name) as tree:
                        target = tree if position == "root" else tree / "nested"
                        if position == "nested":
                            target.mkdir()
                        moved = self.source.parent / "moved-private"
                        changed = False
                        def replace():
                            target.rename(moved)
                            if replacement == "before_symlink":
                                target.symlink_to(moved, target_is_directory=True)
                            elif replacement == "before_fifo":
                                os.mkfifo(target)
                            else:
                                target.mkdir()
                        def opened(path, flags, *args, **kwargs):
                            nonlocal changed
                            match = path == target.name and not changed
                            if match:
                                changed = True
                                if replacement != "after_directory":
                                    replace()
                            descriptor = real_open(path, flags, *args, **kwargs)
                            if match and replacement == "after_directory":
                                replace()
                            return descriptor
                        with mock.patch.object(snapshots.os, "open", side_effect=opened), \
                                mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                            expected = "invalid_input" if replacement in ("before_symlink", "before_fifo") else "snapshot_changed"
                            self.assert_kind(expected, self.freeze)
                        self.assertTrue(changed)
                        self.assertFalse(self.frozen.exists())

    def test_each_tree_has_depth_two_boundary_without_resetting_below_root(self):
        for name in self.TREE_NAMES:
            with self.subTest(name=name), self.tree_case(name) as tree:
                deepest = tree / "one" / "two"
                deepest.mkdir(parents=True)
                (deepest / "private").write_bytes(b"PRIVATE")
                with snapshots._directory(self.source) as descriptor, \
                        mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                    inventory = snapshots._database_contents(descriptor)
                    self.assertIn((name, "one", "two", "private"), inventory)
                    (deepest / "three").mkdir()
                    self.assert_kind("artifact_limit", lambda: snapshots._database_contents(descriptor))
                self.assertFalse(self.frozen.exists())

    def test_tree_membership_and_metadata_changes_fail_both_source_rechecks(self):
        original = snapshots._database_contents
        for name in self.TREE_NAMES:
            for inventory_index in (2, 4):
                for mutation in ("add", "remove", "file_content", "directory_mode"):
                    with self.subTest(name=name, index=inventory_index, mutation=mutation), \
                            self.tree_case(name) as tree:
                        private_file = tree / "private"
                        private_file.write_bytes(b"PRIVATE")
                        calls = 0
                        def inventory(descriptor, **kwargs):
                            nonlocal calls
                            calls += 1
                            if calls == inventory_index:
                                if mutation == "add":
                                    (tree / "new-private").touch()
                                elif mutation == "remove":
                                    private_file.unlink()
                                elif mutation == "file_content":
                                    private_file.write_bytes(b"CHANGED PRIVATE")
                                else:
                                    tree.chmod(0o500)
                            return original(descriptor, **kwargs)
                        with mock.patch.object(snapshots, "_database_contents", side_effect=inventory):
                            self.assert_kind("snapshot_changed", self.freeze)
                        self.assertEqual(calls, inventory_index)

    def test_all_tree_names_are_rejected_in_frozen_source_before_clone_reads(self):
        for name in self.TREE_NAMES:
            with self.subTest(name=name), self.tree_case(name):
                self.freeze()
                self.frozen.chmod(0o700)
                (self.frozen / name).mkdir()
                clone = self.frozen.parent / "observer"
                with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads")):
                    self.assert_entry(snapshots._entry_class(name), "directory",
                                      lambda: snapshots.clone_database(self.frozen, clone,
                                                                       budget_root=self.root))
                self.assertFalse(clone.exists())

    def test_all_tree_names_are_rejected_in_frozen_and_clone_destinations(self):
        original = snapshots._database_contents
        for name in self.TREE_NAMES:
            for mode in ("freeze", "clone"):
                with self.subTest(name=name, mode=mode), self.tree_case(name):
                    if mode == "clone":
                        self.freeze()
                    destination = self.frozen if mode == "freeze" else self.frozen.parent / "observer"
                    calls = 0
                    def inventory(descriptor, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == 3:
                            self.assertIs(kwargs["allow_ancillary"], False)
                            (destination / name).mkdir()
                        return original(descriptor, **kwargs)
                    with mock.patch.object(snapshots, "_database_contents", side_effect=inventory):
                        action = (self.freeze if mode == "freeze" else
                                  lambda: snapshots.clone_database(self.frozen, destination,
                                                                   budget_root=self.root))
                        self.assert_entry(snapshots._entry_class(name), "directory", action)
                    self.assertEqual(calls, 3)


@unittest.skipUnless(POSIX_FILE_API, "Native Linux snapshot filesystem API is unavailable")
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "live"
        self.source.mkdir()
        self.db = self.source / "1Cv8.1CD"
        self.data = b"synthetic fixture, not a native database" * 4000
        self.db.write_bytes(self.data)
        self.frozen = self.root / "frozen"
        normalize_fixture_owners(self)

    def _cleanup(self):
        # Frozen directories deliberately have no write permission.
        for current, directories, _ in os.walk(self.temp.name):
            os.chmod(current, 0o700)
            for directory in directories:
                path = Path(current) / directory
                if not path.is_symlink():
                    os.chmod(path, 0o700)
        self.temp.cleanup()

    def assert_kind(self, kind, action):
        with self.assertRaises(snapshots.OracleError) as failure:
            action()
        self.assertEqual(failure.exception.kind, kind)
        self.assertEqual(str(failure.exception), kind)

    def freeze(self, **kwargs):
        return snapshots.freeze_database(self.source, self.frozen,
                                         quiescent=kwargs.get("quiescent", lambda: True))

    def test_limits_are_independent_fixed_values(self):
        self.assertEqual(snapshots.MAX_FILE_BYTES, 64 * 1024 * 1024)
        self.assertEqual(snapshots.MAX_LIVE_BYTES, 512 * 1024 * 1024)
        self.assertEqual(snapshots.WINDOW_BYTES, 64 * 1024)

    def test_frozen_copy_is_verified_read_only_and_source_unchanged(self):
        before = self.db.stat()
        quiet = mock.Mock(return_value=True)
        summary = self.freeze(quiescent=quiet)
        self.assertEqual(summary, {
            "bytes": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest(),
            "header": "unknown", "page_analysis": "unsupported"})
        self.assertEqual(quiet.call_count, 3)
        self.assertEqual(self.db.read_bytes(), self.data)
        self.assertEqual(self.db.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.db.stat().st_ino, before.st_ino)
        self.assertEqual((self.frozen / "1Cv8.1CD").read_bytes(), self.data)
        self.assertEqual(stat.S_IMODE((self.frozen / "1Cv8.1CD").stat().st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(self.frozen.stat().st_mode), 0o500)

    def test_clone_is_writable_fresh_and_does_not_modify_frozen_source(self):
        physical = self.freeze()
        clone = self.root / "observer"
        self.assertIsNone(snapshots.clone_database(self.frozen, clone, budget_root=self.root))
        self.assertEqual(stat.S_IMODE((clone / "1Cv8.1CD").stat().st_mode), 0o600)
        (clone / "1Cv8.1CD").write_bytes(b"native observer can change its own clone")
        self.assertEqual(snapshots.file_summary(self.frozen / "1Cv8.1CD"), physical)
        self.assert_kind("stale_evidence", lambda: snapshots.clone_database(
            self.frozen, clone, budget_root=self.root))

    def test_clone_rejects_nonfrozen_source(self):
        self.assert_kind("invalid_input", lambda: snapshots.clone_database(
            self.source, self.root / "observer", budget_root=self.root))

    def test_false_initial_quiescence_rejected_before_any_payload_read_or_destination(self):
        quiet = mock.Mock(return_value=False)
        with mock.patch.object(snapshots.os, "read", side_effect=AssertionError("must not read")):
            self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(quiescent=quiet))
        self.assertEqual(quiet.call_count, 1)
        self.assertFalse(self.frozen.exists())

    def test_quiescence_still_required_immediately_before_and_after_copy(self):
        for index, values in enumerate(([True, False], [True, True, False])):
            self.frozen = self.root / f"frozen-{index}"
            quiet = mock.Mock(side_effect=values)
            self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(quiescent=quiet))
            self.assertEqual(quiet.call_count, len(values))
            expected_size = 0 if len(values) == 2 else len(self.data)
            self.assertEqual((self.frozen / "1Cv8.1CD").stat().st_size, expected_size)

    def test_truthy_nonboolean_is_not_quiescence(self):
        self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(quiescent=lambda: 1))

    def test_quiescence_exception_is_sanitized(self):
        self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(
            quiescent=mock.Mock(side_effect=RuntimeError("PRIVATE PASSWORD PATH"))))

    def test_live_writer_rejected_even_with_stable_mtime(self):
        initial = self.db.stat()
        real_write = snapshots._write_all
        changed = False

        def write(descriptor, block):
            nonlocal changed
            real_write(descriptor, block)
            if not changed:
                changed = True
                with self.db.open("r+b") as source:
                    source.seek(0)
                    source.write(b"!")
                os.utime(self.db, ns=(initial.st_atime_ns, initial.st_mtime_ns))

        with mock.patch.object(snapshots, "_write_all", side_effect=write):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertEqual(self.db.stat().st_mtime_ns, initial.st_mtime_ns)

    def test_digest_recheck_catches_mutation_when_metadata_check_is_mocked_stable(self):
        real_write = snapshots._write_all
        changed = False

        def write(descriptor, block):
            nonlocal changed
            real_write(descriptor, block)
            if not changed:
                changed = True
                with self.db.open("r+b") as source:
                    source.write(b"!")

        with mock.patch.object(snapshots, "_write_all", side_effect=write), \
                mock.patch.object(snapshots, "_unchanged"):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_source_replaced_at_pre_copy_callback(self):
        def quiet():
            self.db.unlink()
            self.db.write_bytes(self.data)
            return True
        self.assert_kind("snapshot_changed", lambda: self.freeze(quiescent=quiet))

    def test_source_truncated_during_copy(self):
        def quiet():
            self.db.write_bytes(b"")
            return True
        self.assert_kind("snapshot_changed", lambda: self.freeze(quiescent=quiet))

    def test_destination_corruption_is_detected_by_readback(self):
        real_write = snapshots._write_all
        def corrupt(descriptor, block):
            real_write(descriptor, b"?" * len(block))
        with mock.patch.object(snapshots, "_write_all", side_effect=corrupt):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_destination_identity_change_with_identical_bytes_is_rejected(self):
        real_summary = snapshots.file_summary
        def replace_after_summary(path):
            result = real_summary(path)
            path.unlink()
            path.write_bytes(self.data)
            path.chmod(0o400)
            return result
        with mock.patch.object(snapshots, "file_summary", side_effect=replace_after_summary):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_destination_file_cannot_be_overwritten(self):
        self.frozen.mkdir()
        sentinel = self.frozen / "1Cv8.1CD"
        sentinel.write_bytes(b"retain existing data")
        self.assert_kind("stale_evidence", self.freeze)
        self.assertEqual(sentinel.read_bytes(), b"retain existing data")

    def test_destination_directory_must_be_absent_even_if_empty(self):
        self.frozen.mkdir()
        self.assert_kind("stale_evidence", self.freeze)

    def test_database_symlink_is_rejected_without_reading_target(self):
        self.db.unlink()
        self.db.symlink_to("/dev/zero")
        self.assert_kind("invalid_input", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_symlink_parent_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        self.assert_kind("invalid_input", lambda: snapshots.file_summary(alias / "1Cv8.1CD"))

    def test_destination_symlink_is_rejected(self):
        self.frozen.symlink_to(self.source, target_is_directory=True)
        self.assert_kind("invalid_input", self.freeze)
        self.assertEqual(self.db.read_bytes(), self.data)

    def test_hardlinked_database_is_rejected(self):
        os.link(self.db, self.root / "alias")
        self.assert_kind("invalid_input", self.freeze)

    def test_fifo_is_rejected_without_blocking(self):
        self.db.unlink()
        os.mkfifo(self.db)
        self.assert_kind("invalid_input", self.freeze)

    def test_owned_regular_sidefiles_are_metadata_only_without_name_whitelist(self):
        for name in ("1Cv8.1CL", "lock", "extra.log"):
            (self.source / name).write_bytes(b"PRIVATE SYNTHETIC SIDECAR")
        result = self.freeze()
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_extra_owned_directory_is_ancillary_and_not_copied(self):
        (self.source / "extra").mkdir()
        result = self.freeze()
        self.assertEqual(result["bytes"], len(self.data))
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_traversal_and_non_sibling_destination_rejected(self):
        self.assert_kind("invalid_input", lambda: snapshots.file_summary(
            self.source / ".." / "live" / "1Cv8.1CD"))
        other = self.root / "other"
        other.mkdir()
        self.assert_kind("invalid_input", lambda: snapshots.freeze_database(
            self.source, other / "nested", quiescent=lambda: True))

    def test_invalid_path_encoding_and_nul_are_sanitized(self):
        for name in ("private\0file", "private\ud800file"):
            self.assert_kind("invalid_input", lambda: snapshots.file_summary(self.root / name))

    def test_clone_stays_inside_budget_root(self):
        self.freeze()
        self.assert_kind("invalid_input", lambda: snapshots.clone_database(
            self.frozen, self.root.parent / "unrelated-target", budget_root=self.root))
        self.assert_kind("invalid_input", lambda: snapshots.clone_database(
            self.frozen, self.frozen / "nested", budget_root=self.root))

    def test_unknown_empty_truncated_and_page_like_headers_never_decode(self):
        for fixture in (b"", b"1C", b"1CDBMSV8" + b"\0" * 23,
                        b"\xff" * 4096, b"\0" * 65537):
            with self.subTest(size=len(fixture)):
                self.db.write_bytes(fixture)
                summary = snapshots.file_summary(self.db)
                self.assertEqual(summary["header"], "unknown")
                self.assertEqual(summary["page_analysis"], "unsupported")
                self.assertEqual(set(summary), {"bytes", "sha256", "header", "page_analysis"})
                self.assertEqual(summary["bytes"], len(fixture))
                self.assertEqual(summary["sha256"], hashlib.sha256(fixture).hexdigest())

    def test_hashing_reads_only_bounded_chunks(self):
        real_read = snapshots.os.read
        sizes = []
        def read(descriptor, length):
            sizes.append(length)
            return real_read(descriptor, length)
        with mock.patch.object(snapshots.os, "read", side_effect=read):
            snapshots.file_summary(self.db)
        self.assertGreater(len(sizes), 2)
        self.assertEqual(set(sizes), {snapshots.WINDOW_BYTES})

    def test_per_file_limit_before_read_or_destination_creation(self):
        with self.db.open("wb") as stream:
            stream.truncate(snapshots.MAX_FILE_BYTES + 1)
        self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_budget_counts_all_regular_logs_and_raw_artifacts(self):
        logs = self.root / "logs"
        logs.mkdir()
        (logs / "output.log").write_bytes(b"raw sensitive log" * 20)
        expected = len(self.data) + len(b"raw sensitive log" * 20)
        self.assertEqual(snapshots.budget_check(self.root), expected)
        with mock.patch.object(snapshots, "MAX_LIVE_BYTES", expected):
            self.assertEqual(snapshots.budget_check(self.root), expected)
            self.assert_kind("artifact_limit", lambda: snapshots.budget_check(self.root, 1))

    def test_pre_copy_budget_prevents_destination_creation(self):
        with mock.patch.object(snapshots, "MAX_LIVE_BYTES", len(self.data) * 2 - 1):
            self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_budget_exhaustion_during_copy_is_rejected(self):
        real_write = snapshots._write_all
        def grow_other_file(descriptor, block):
            real_write(descriptor, block)
            (self.root / "native.log").write_bytes(b"L" * len(self.data))
        with mock.patch.object(snapshots, "MAX_LIVE_BYTES", len(self.data) * 2), \
                mock.patch.object(snapshots, "_write_all", side_effect=grow_other_file):
            self.assert_kind("artifact_limit", self.freeze)

    def test_budget_rejects_bool_negative_symlink_and_hardlink(self):
        for additional in (True, -1, "1"):
            self.assert_kind("artifact_limit", lambda: snapshots.budget_check(self.root, additional))
        alias = self.root / "alias"
        alias.symlink_to(self.db)
        self.assert_kind("invalid_input", lambda: snapshots.budget_check(self.root))
        alias.unlink()
        os.link(self.db, alias)
        self.assert_kind("invalid_input", lambda: snapshots.budget_check(self.root))

    def test_budget_traversal_is_bounded(self):
        with mock.patch.object(snapshots, "MAX_TREE_ENTRIES", 1):
            self.assert_kind("artifact_limit", lambda: snapshots.budget_check(self.root))
        with mock.patch.object(snapshots, "MAX_TREE_DEPTH", 0):
            self.assert_kind("artifact_limit", lambda: snapshots.budget_check(self.root))

    def test_os_errors_have_no_private_text(self):
        with mock.patch.object(snapshots.os, "read", side_effect=OSError("SECRET PATH")):
            self.assert_kind("invalid_input", lambda: snapshots.file_summary(self.db))

    def log(self, name="1Cv8.lgf", content=b"PRIVATE SYNTHETIC EVENT LOG"):
        directory = self.source / "1Cv8Log"
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_known_log_inventory_is_metadata_only_and_never_copied_or_reported(self):
        log = self.log()
        nested = self.log("year/month/events.lgp", b"SECOND PRIVATE EVENT")
        before = (log.read_bytes(), nested.read_bytes(), log.stat().st_mtime_ns)
        result = self.freeze()
        self.assertEqual(set(result), {"bytes", "sha256", "header", "page_analysis"})
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn("1Cv8Log", str(result))
        self.assertEqual([path.name for path in self.frozen.iterdir()], ["1Cv8.1CD"])
        self.assertEqual((log.read_bytes(), nested.read_bytes(), log.stat().st_mtime_ns), before)
        clone = self.root / "observer"
        snapshots.clone_database(self.frozen, clone, budget_root=self.root)
        self.assertEqual([path.name for path in clone.iterdir()], ["1Cv8.1CD"])

    def test_empty_known_log_directory_is_optional_not_quiescence_evidence(self):
        (self.source / "1Cv8Log").mkdir()
        self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(quiescent=lambda: False))

    def test_log_basename_can_be_regular_metadata_only_sidecar(self):
        (self.source / "1Cv8Log").write_bytes(b"PRIVATE SIDECAR NOT A DIRECTORY")
        result = self.freeze()
        self.assertEqual(result["bytes"], len(self.data))
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_log_directory_symlink_is_rejected(self):
        (self.source / "1Cv8Log").symlink_to(self.root, target_is_directory=True)
        self.assert_kind("invalid_input", self.freeze)

    def test_log_file_symlink_and_directory_symlink_are_rejected(self):
        directory = self.source / "1Cv8Log"
        directory.mkdir()
        link = directory / "unsafe"
        link.symlink_to(self.db)
        self.assert_kind("invalid_input", self.freeze)
        link.unlink()
        link.symlink_to(self.root, target_is_directory=True)
        self.assert_kind("invalid_input", self.freeze)

    def test_log_hardlink_is_rejected_even_if_alias_is_outside_inventory(self):
        log = self.log()
        os.link(log, self.root / "outside-log-alias")
        self.assert_kind("invalid_input", self.freeze)

    def test_log_special_file_is_rejected_without_blocking(self):
        directory = self.source / "1Cv8Log"
        directory.mkdir()
        os.mkfifo(directory / "event-pipe")
        self.assert_kind("invalid_input", self.freeze)

    def test_log_depth_and_entry_inventory_are_bounded(self):
        self.log("one/two/three/events.lgp", b"")
        self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_log_file_count_is_bounded_including_empty_files(self):
        for index in range(snapshots.MAX_ANCILLARY_FILES + 1):
            self.log(f"{index}.lgp", b"")
        self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_log_empty_directory_count_is_bounded(self):
        directory = self.source / "1Cv8Log"
        directory.mkdir()
        for index in range(snapshots.MAX_ANCILLARY_ENTRIES + 1):
            (directory / str(index)).mkdir()
        self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_log_total_byte_budget_is_enforced_before_copy(self):
        log = self.log(content=b"")
        with log.open("wb") as stream:
            stream.truncate(snapshots.MAX_ANCILLARY_BYTES + 1)
        self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_log_file_cannot_exceed_unchanged_raw_file_limit(self):
        log = self.log(content=b"")
        with log.open("wb") as stream:
            stream.truncate(snapshots.MAX_FILE_BYTES + 1)
        self.assert_kind("artifact_limit", self.freeze)

    def test_logs_also_count_toward_global_live_budget(self):
        log = self.log()
        limit = len(self.data) * 2 + log.stat().st_size - 1
        with mock.patch.object(snapshots, "MAX_LIVE_BYTES", limit):
            self.assert_kind("artifact_limit", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_log_content_mutation_during_copy_rejected_with_stable_mtime(self):
        log = self.log()
        initial = log.stat()
        real_write = snapshots._write_all
        changed = False
        def write(descriptor, block):
            nonlocal changed
            real_write(descriptor, block)
            if not changed:
                changed = True
                with log.open("r+b") as stream:
                    stream.write(b"!")
                os.utime(log, ns=(initial.st_atime_ns, initial.st_mtime_ns))
        with mock.patch.object(snapshots, "_write_all", side_effect=write):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertEqual(log.stat().st_mtime_ns, initial.st_mtime_ns)

    def test_metadata_only_boundary_does_not_claim_to_detect_identical_metadata_changes(self):
        log = self.log()
        inode = log.stat().st_ino
        real_write, real_signature, real_read = snapshots._write_all, snapshots._signature, snapshots.os.read
        changed = False
        def write(descriptor, block):
            nonlocal changed
            real_write(descriptor, block)
            if not changed:
                changed = True
                with log.open("r+b") as stream:
                    stream.write(b"!")
        def stable_signature(info):
            value = real_signature(info)
            return value[:-2] + (0, 0) if info.st_ino == inode else value
        def read(descriptor, length):
            self.assertNotEqual(os.fstat(descriptor).st_ino, inode)
            return real_read(descriptor, length)
        with mock.patch.object(snapshots, "_write_all", side_effect=write), \
                mock.patch.object(snapshots, "_signature", side_effect=stable_signature), \
                mock.patch.object(snapshots.os, "read", side_effect=read):
            result = self.freeze()
        self.assertTrue(changed)
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())

    def test_new_log_file_during_copy_is_rejected(self):
        self.log()
        real_write = snapshots._write_all
        def write(descriptor, block):
            real_write(descriptor, block)
            self.log("new.lgp", b"new")
        with mock.patch.object(snapshots, "_write_all", side_effect=write):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_log_metadata_mutation_during_initial_inventory_is_rejected(self):
        log = self.log()
        target_inode = log.stat().st_ino
        real_open = snapshots.os.open
        changed = False
        def opened(name, flags, *args, **kwargs):
            nonlocal changed
            descriptor = real_open(name, flags, *args, **kwargs)
            if os.fstat(descriptor).st_ino == target_inode and not changed:
                changed = True
                log.write_bytes(b"changed metadata")
            return descriptor
        with mock.patch.object(snapshots.os, "open", side_effect=opened), \
                mock.patch.object(snapshots.os, "read", side_effect=AssertionError("no reads yet")):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertTrue(changed)
        self.assertFalse(self.frozen.exists())

    def test_unknown_owned_directory_can_coexist_with_known_log(self):
        self.log()
        (self.source / "1Cv8.1CL").mkdir()
        result = self.freeze()
        self.assertEqual(result["bytes"], len(self.data))
        self.assertEqual([entry.name for entry in self.frozen.iterdir()], ["1Cv8.1CD"])

    def test_log_injection_into_frozen_source_is_not_accepted_for_clone(self):
        self.freeze()
        self.frozen.chmod(0o700)
        (self.frozen / "1Cv8Log").mkdir()
        self.frozen.chmod(0o500)
        self.assert_kind("invalid_input", lambda: snapshots.clone_database(
            self.frozen, self.root / "observer", budget_root=self.root))

    def test_error_enum_cannot_retain_arbitrary_text(self):
        self.assertEqual(str(snapshots.OracleError("snapshot_changed")), "snapshot_changed")
        with self.assertRaisesRegex(ValueError, "^invalid error kind$"):
            snapshots.OracleError("private unbounded message")


@unittest.skipUnless(POSIX_FILE_API, "Native Linux snapshot filesystem API is unavailable")
class ByteWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def compare(self, predecessor, control, treatment):
        paths = []
        for name, content in zip(("predecessor", "control", "treatment"),
                                 (predecessor, control, treatment)):
            path = self.root / name
            path.write_bytes(content)
            paths.append(path)
        return snapshots.compare_files(*paths)

    def invalid(self, report):
        with self.assertRaises(snapshots.OracleError) as failure:
            snapshots.validate_comparison(report)
        self.assertEqual(failure.exception.kind, "invalid_input")

    def test_identical_and_empty_files_have_zero_changes(self):
        for content in (b"", b"unchanged" * 10000):
            report = self.compare(content, content, content)
            self.assertEqual(report["control"]["unchanged_bytes"], len(content))
            self.assertEqual(report["control"]["changed_bytes"], 0)
            self.assertEqual(report["treatment"]["changed_windows"], 0)
            self.assertEqual(report["byte_windows"]["overlap_sample"], [])
            snapshots.validate_comparison(report)

    def test_changed_added_and_removed_count_common_prefix_and_tails(self):
        report = self.compare(b"abcdef", b"aXcdef++", b"aYc")
        self.assertEqual(report["control"], {
            "changed_bytes": 1, "unchanged_bytes": 5, "added_bytes": 2,
            "removed_bytes": 0, "size_delta": 2, "changed_windows": 1})
        self.assertEqual(report["treatment"], {
            "changed_bytes": 1, "unchanged_bytes": 2, "added_bytes": 0,
            "removed_bytes": 3, "size_delta": -3, "changed_windows": 1})
        self.assertEqual(report["byte_windows"]["overlap_count"], 1)
        self.assertEqual(report["interpretation"], "physical_byte_differences_not_causation")
        self.assertNotIn("pages", str(report))

    def test_controls_can_have_churn_without_causal_subtraction(self):
        width = snapshots.WINDOW_BYTES
        before = bytearray(b"a" * (width * 3 + 1))
        control, treatment = bytearray(before), bytearray(before)
        control[0] = ord("x")
        control[width] = ord("y")
        treatment[0] = ord("z")
        treatment[width * 2] = ord("k")
        report = self.compare(before, control, treatment)
        self.assertEqual(report["control"]["changed_bytes"], 2)
        self.assertEqual(report["treatment"]["changed_bytes"], 2)
        self.assertEqual(report["byte_windows"], {
            "window_bytes": width, "count": 4, "overlap_count": 1,
            "control_only_count": 1, "treatment_only_count": 1,
            "overlap_sample": [0], "control_only_sample": [1], "treatment_only_sample": [2]})

    def test_tail_only_changes_can_share_the_predecessor_final_window(self):
        width = snapshots.WINDOW_BYTES
        report = self.compare(b"a" * (width + 3), b"a" * width, b"a" * (width + 10))
        self.assertEqual(report["control"]["removed_bytes"], 3)
        self.assertEqual(report["treatment"]["added_bytes"], 7)
        self.assertEqual(report["byte_windows"]["overlap_sample"], [1])

    def test_validator_requires_tail_windows_even_with_very_few_added_bytes(self):
        width = snapshots.WINDOW_BYTES
        report = self.compare(b"a" * (width - 1), b"a" * (width + 1), b"a" * (width - 1))
        self.assertEqual(report["control"]["changed_windows"], 2)
        report["control"]["changed_windows"] = 1
        report["byte_windows"]["control_only_count"] = 1
        report["byte_windows"]["control_only_sample"] = [0]
        self.invalid(report)

    def test_validator_requires_disjoint_changed_prefix_and_aligned_tail_windows(self):
        width = snapshots.WINDOW_BYTES
        report = self.compare(b"a" * width, b"b" * width + b"+", b"a" * width)
        self.assertEqual(report["control"]["changed_windows"], 2)
        report["control"]["changed_windows"] = 1
        report["byte_windows"]["control_only_count"] = 1
        report["byte_windows"]["control_only_sample"] = [0]
        self.invalid(report)

    def test_samples_are_capped_sorted_and_fixed_memory(self):
        width = snapshots.WINDOW_BYTES
        report = self.compare(b"a" * (width * 20), b"b" * (width * 20), b"c" * (width * 20))
        self.assertEqual(report["byte_windows"]["overlap_count"], 20)
        self.assertEqual(report["byte_windows"]["overlap_sample"], list(range(16)))
        self.assertEqual(report["control"]["changed_bytes"], width * 20)

    def test_same_file_aliases_are_rejected(self):
        path = self.root / "same"
        path.write_bytes(b"same")
        with self.assertRaises(snapshots.OracleError):
            snapshots.compare_files(path, path, path)

    def test_mutation_while_comparing_is_rejected(self):
        self.compare(b"a" * 100, b"a" * 100, b"b" * 100)
        real_count = snapshots._count_bytes
        def count(before, after, counters):
            (self.root / "predecessor").write_bytes(b"z" * 100)
            return real_count(before, after, counters)
        with mock.patch.object(snapshots, "_count_bytes", side_effect=count):
            with self.assertRaises(snapshots.OracleError) as failure:
                snapshots.compare_files(*(self.root / name for name in (
                    "predecessor", "control", "treatment")))
        self.assertEqual(failure.exception.kind, "snapshot_changed")

    def test_validator_rejects_unknown_and_impossible_fields(self):
        valid = self.compare(b"abc", b"abc+", b"aXc")
        mutations = [
            lambda r: r.update(path="secret"),
            lambda r: r.update(predecessor_bytes=True),
            lambda r: r.update(predecessor_bytes=-1),
            lambda r: r.update(treatment_bytes=snapshots.MAX_FILE_BYTES + 1),
            lambda r: r.update(interpretation="row_pages"),
            lambda r: r["control"].update(changed_bytes=1),
            lambda r: r["control"].update(added_bytes=0),
            lambda r: r["control"].update(removed_bytes=1),
            lambda r: r["control"].update(size_delta=2),
            lambda r: r["control"].update(changed_windows=2),
            lambda r: r["control"].update(changed_windows=0),
            lambda r: r["control"].update(unchanged_bytes=float("nan")),
            lambda r: r["byte_windows"].update(window_bytes=4096),
            lambda r: r["byte_windows"].update(count=2),
            lambda r: r["byte_windows"].update(overlap_count=0),
            lambda r: r["byte_windows"].update(overlap_sample=[1]),
            lambda r: r["byte_windows"].update(overlap_sample=[True]),
            lambda r: r["byte_windows"].update(overlap_sample=[]),
            lambda r: r["byte_windows"].update(overlap_sample=[0, 0]),
            lambda r: r["byte_windows"].update(overlap_sample=[-1]),
            lambda r: r["byte_windows"].update(overlap_sample=["private"]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                report = copy.deepcopy(valid)
                mutate(report)
                self.invalid(report)

    def test_validator_rejects_too_many_sample_indices_and_overlap_between_samples(self):
        width = snapshots.WINDOW_BYTES
        valid = self.compare(b"a" * width * 20, b"b" * width * 20, b"a" * width * 20)
        valid["byte_windows"]["control_only_sample"] = list(range(17))
        self.invalid(valid)
        valid = self.compare(b"a" * width * 2, b"b" * width + b"a" * width,
                             b"a" * width + b"b" * width)
        valid["byte_windows"]["treatment_only_sample"] = [0]
        self.invalid(valid)


@unittest.skipUnless(POSIX_FILE_API, "Native Linux snapshot filesystem API is unavailable")
class ObservationalPairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.before = self.root / "before"
        self.after = self.root / "after"

    def compare(self, before, after):
        self.before.write_bytes(before)
        self.after.write_bytes(after)
        return snapshots.compare_pair(self.before, self.after)

    def test_exact_before_after_schema_never_claims_matched_control(self):
        result = self.compare(b"abcdef", b"aXcdef++")
        self.assertEqual(result, {
            "predecessor_bytes": 6, "treatment_bytes": 8,
            "treatment": {"changed_bytes": 1, "unchanged_bytes": 5,
                          "added_bytes": 2, "removed_bytes": 0,
                          "size_delta": 2, "changed_windows": 1},
            "byte_windows": {"window_bytes": 65536, "count": 1,
                             "changed_count": 1, "changed_sample": [0]},
            "interpretation": "observational_before_after_not_causation",
        })
        self.assertNotIn("control", str(result))
        snapshots.validate_pair(result)

    def test_empty_identical_added_and_removed_bytes(self):
        for before, after in ((b"", b""), (b"", b"new"), (b"old", b""), (b"same", b"same")):
            with self.subTest(before=before, after=after):
                result = self.compare(before, after)
                counters = result["treatment"]
                self.assertEqual(counters["changed_bytes"], 0)
                self.assertEqual(counters["added_bytes"], max(len(after) - len(before), 0))
                self.assertEqual(counters["removed_bytes"], max(len(before) - len(after), 0))
                self.assertEqual(counters["unchanged_bytes"], min(len(before), len(after)))

    def test_observational_samples_are_bounded_sorted_byte_windows(self):
        width = snapshots.WINDOW_BYTES
        result = self.compare(b"a" * width * 20, b"b" * width * 20)
        self.assertEqual(result["byte_windows"]["changed_count"], 20)
        self.assertEqual(result["byte_windows"]["changed_sample"], list(range(16)))
        self.assertEqual(result["treatment"]["changed_bytes"], width * 20)

    def test_observational_tail_can_span_two_windows_with_two_bytes(self):
        width = snapshots.WINDOW_BYTES
        result = self.compare(b"a" * (width - 1), b"a" * (width + 1))
        self.assertEqual(result["treatment"]["added_bytes"], 2)
        self.assertEqual(result["byte_windows"]["changed_sample"], [0, 1])

    def test_observational_pair_still_rejects_same_inode_and_symlinks(self):
        self.before.write_bytes(b"synthetic")
        with self.assertRaises(snapshots.OracleError):
            snapshots.compare_pair(self.before, self.before)
        self.after.symlink_to(self.before)
        with self.assertRaises(snapshots.OracleError):
            snapshots.compare_pair(self.before, self.after)

    def test_observational_pair_rejects_mutation_during_streaming(self):
        self.before.write_bytes(b"abc")
        self.after.write_bytes(b"def")
        real_count = snapshots._count_bytes
        def mutate(before, after, counters):
            self.before.write_bytes(b"xxx")
            return real_count(before, after, counters)
        with mock.patch.object(snapshots, "_count_bytes", side_effect=mutate):
            with self.assertRaises(snapshots.OracleError) as failure:
                snapshots.compare_pair(self.before, self.after)
        self.assertEqual(failure.exception.kind, "snapshot_changed")


class PortablePairValidationTests(unittest.TestCase):
    def valid(self):
        return {
            "predecessor_bytes": 6, "treatment_bytes": 8,
            "treatment": {"changed_bytes": 1, "unchanged_bytes": 5,
                          "added_bytes": 2, "removed_bytes": 0,
                          "size_delta": 2, "changed_windows": 1},
            "byte_windows": {"window_bytes": 65536, "count": 1,
                             "changed_count": 1, "changed_sample": [0]},
            "interpretation": "observational_before_after_not_causation",
        }

    def invalid(self, result):
        with self.assertRaises(snapshots.OracleError) as failure:
            snapshots.validate_pair(result)
        self.assertEqual(str(failure.exception), "invalid_input")

    def test_valid_pair_schema_is_nonmutating(self):
        result = self.valid()
        initial = copy.deepcopy(result)
        self.assertIsNone(snapshots.validate_pair(result))
        self.assertEqual(result, initial)

    def test_pair_rejects_unknown_control_keys_claims_and_scalar_types(self):
        for key, value in (("control", {}), ("control_bytes", 6),
                           ("predecessor_bytes", True), ("treatment_bytes", float("nan")),
                           ("interpretation", "physical_byte_differences_not_causation")):
            with self.subTest(key=key):
                result = self.valid()
                result[key] = value
                self.invalid(result)
        for result in (None, [], True, {}, "PRIVATE RAW CONTENT"):
            self.invalid(result)

    def test_pair_rejects_inconsistent_and_unbounded_counters(self):
        for key, value in (("changed_bytes", 2), ("unchanged_bytes", -1),
                           ("added_bytes", 0), ("removed_bytes", 1),
                           ("size_delta", 0), ("changed_windows", 2),
                           ("changed_bytes", snapshots.MAX_FILE_BYTES + 1)):
            with self.subTest(key=key, value=value):
                result = self.valid()
                result["treatment"][key] = value
                self.invalid(result)

    def test_pair_rejects_bad_window_counts_samples_and_page_assumption(self):
        for key, value in (("window_bytes", 4096), ("count", 2), ("changed_count", 0),
                           ("changed_sample", []), ("changed_sample", [1]),
                           ("changed_sample", [True]), ("changed_sample", [0, 0]),
                           ("changed_sample", list(range(17))), ("overlap_count", 0)):
            with self.subTest(key=key, value=value):
                result = self.valid()
                result["byte_windows"][key] = value
                self.invalid(result)


class PortableValidationTests(unittest.TestCase):
    """No POSIX I/O: these exact-schema gates run on every supported CI OS."""

    def valid(self):
        return {
            "predecessor_bytes": 3, "control_bytes": 4, "treatment_bytes": 3,
            "control": {"changed_bytes": 0, "unchanged_bytes": 3, "added_bytes": 1,
                        "removed_bytes": 0, "size_delta": 1, "changed_windows": 1},
            "treatment": {"changed_bytes": 1, "unchanged_bytes": 2, "added_bytes": 0,
                          "removed_bytes": 0, "size_delta": 0, "changed_windows": 1},
            "byte_windows": {"window_bytes": 65536, "count": 1, "overlap_count": 1,
                             "control_only_count": 0, "treatment_only_count": 0,
                             "overlap_sample": [0], "control_only_sample": [],
                             "treatment_only_sample": []},
            "interpretation": "physical_byte_differences_not_causation",
        }

    def invalid(self, report):
        with self.assertRaises(snapshots.OracleError) as failure:
            snapshots.validate_comparison(report)
        self.assertEqual(str(failure.exception), "invalid_input")

    def test_fixed_limits_and_safe_errors(self):
        self.assertEqual(snapshots.MAX_FILE_BYTES, 64 * 1024 * 1024)
        self.assertEqual(snapshots.MAX_LIVE_BYTES, 512 * 1024 * 1024)
        self.assertEqual(snapshots.WINDOW_BYTES, 65536)
        self.assertEqual(snapshots.MAX_ANCILLARY_BYTES, 16 * 1024 * 1024)
        self.assertEqual(snapshots.MAX_ANCILLARY_FILES, 64)
        self.assertEqual(snapshots.MAX_ANCILLARY_ENTRIES, 128)
        self.assertEqual(snapshots.MAX_ANCILLARY_DEPTH, 2)
        for kind in snapshots.FAILURE_KINDS:
            self.assertEqual(str(snapshots.OracleError(kind)), kind)
        with self.assertRaisesRegex(ValueError, "^invalid error kind$"):
            snapshots.OracleError("PRIVATE PATH")

    def test_valid_hand_calculated_counters(self):
        self.assertIsNone(snapshots.validate_comparison(self.valid()))

    def test_unknown_fields_and_types_rejected(self):
        for key, value in (("predecessor_bytes", True), ("control_bytes", float("nan")),
                           ("treatment_bytes", "3"), ("interpretation", "row_pages"),
                           ("raw_bytes", "PRIVATE DATA")):
            with self.subTest(key=key):
                report = self.valid()
                report[key] = value
                self.invalid(report)
        for invalid in (None, [], True, {}, "PRIVATE DATA"):
            self.invalid(invalid)

    def test_impossible_byte_counters_rejected(self):
        for branch, key, value in (("control", "changed_bytes", 1),
                                   ("control", "added_bytes", 0),
                                   ("control", "size_delta", -1),
                                   ("treatment", "removed_bytes", 1),
                                   ("treatment", "changed_windows", 0),
                                   ("treatment", "unchanged_bytes", 4)):
            with self.subTest(branch=branch, key=key):
                report = self.valid()
                report[branch][key] = value
                self.invalid(report)

    def test_impossible_window_counters_and_indices_rejected(self):
        for key, value in (("window_bytes", 4096), ("count", 2), ("overlap_count", 0),
                           ("overlap_sample", [True]), ("overlap_sample", [1]),
                           ("overlap_sample", [0, 0]), ("overlap_sample", []),
                           ("overlap_sample", [float("inf")])):
            with self.subTest(key=key, value=value):
                report = self.valid()
                report["byte_windows"][key] = value
                self.invalid(report)


if __name__ == "__main__":
    unittest.main()
