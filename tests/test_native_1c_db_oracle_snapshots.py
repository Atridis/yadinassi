"""Offline synthetic-byte tests. No native platform execution or format proof."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
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
        self.assertEqual(quiet.call_count, 2)
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

    def test_false_quiescence_rejected_before_copy(self):
        quiet = mock.Mock(return_value=False)
        self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(quiescent=quiet))
        self.assertEqual(quiet.call_count, 1)
        self.assertEqual((self.frozen / "1Cv8.1CD").stat().st_size, 0)

    def test_false_quiescence_after_copy_rejected(self):
        self.assert_kind("snapshot_not_quiescent", lambda: self.freeze(
            quiescent=mock.Mock(side_effect=[True, False])))

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

    def test_every_unexpected_sidefile_is_rejected(self):
        for name in ("1Cv8.1CL", "lock", "extra.log"):
            with self.subTest(name=name):
                side = self.source / name
                side.write_bytes(b"")
                self.assert_kind("invalid_input", self.freeze)
                side.unlink()

    def test_extra_directory_is_rejected(self):
        (self.source / "extra").mkdir()
        self.assert_kind("invalid_input", self.freeze)

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

    def test_only_known_log_inventory_is_allowed_and_never_copied_or_reported(self):
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

    def test_known_log_name_must_be_a_real_directory(self):
        (self.source / "1Cv8Log").write_bytes(b"not a directory")
        self.assert_kind("invalid_input", self.freeze)

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

    def test_log_hash_recheck_rejects_change_even_when_timestamps_are_mocked_stable(self):
        log = self.log()
        real_write, real_signature = snapshots._write_all, snapshots._signature
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
            return value[:-2] + (0, 0)
        with mock.patch.object(snapshots, "_write_all", side_effect=write), \
                mock.patch.object(snapshots, "_signature", side_effect=stable_signature):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_new_log_file_during_copy_is_rejected(self):
        self.log()
        real_write = snapshots._write_all
        def write(descriptor, block):
            real_write(descriptor, block)
            self.log("new.lgp", b"new")
        with mock.patch.object(snapshots, "_write_all", side_effect=write):
            self.assert_kind("snapshot_changed", self.freeze)

    def test_log_read_mutation_is_rejected_during_initial_inventory(self):
        log = self.log()
        target_inode = log.stat().st_ino
        real_digest = snapshots._digest
        def digest(descriptor, size):
            result = real_digest(descriptor, size)
            if os.fstat(descriptor).st_ino == target_inode:
                log.write_bytes(b"!" * size)
            return result
        with mock.patch.object(snapshots, "_digest", side_effect=digest):
            self.assert_kind("snapshot_changed", self.freeze)
        self.assertFalse(self.frozen.exists())

    def test_unknown_sibling_remains_rejected_even_with_known_log(self):
        self.log()
        (self.source / "1Cv8.1CL").write_bytes(b"")
        self.assert_kind("invalid_input", self.freeze)

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
