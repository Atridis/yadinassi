"""Linux ownership/process tests using private temporary namespaces, not native proof.

No test here creates the public /tmp/onec-smoke pathname. Binary fixture bytes
and explicit UTF-8/LF child data are synthetic, not evidence from real 1C.
"""
import contextlib
import errno
import importlib.util
import io
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "native_infobase_fixture_under_test",
    Path(__file__).resolve().parents[1] / "scripts" / "native_infobase_fixture.py")
fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fixture)
LINUX = sys.platform.startswith("linux")


@unittest.skipUnless(LINUX, "Linux descriptor/process ownership only; no Windows security claim")
class OwnedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="owned-infobase-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "onec-smoke"
        self.db = self.root / "db"
        self.file = self.db / "1Cv8.1CD"

        def namespace():
            return (os.open(self.base.parent, fixture._directory_flags()),
                    os.open(self.base, fixture._directory_flags()))

        for patcher in (mock.patch.object(fixture, "_PARENT", self.base),
                        mock.patch.object(fixture, "_open_trusted_parent", side_effect=namespace)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_public_constructor_accepts_no_arbitrary_path(self):
        with self.assertRaises(TypeError):
            fixture.OwnedInfobase(self.base)
        with mock.patch.object(fixture, "_PARENT", Path("/tmp")):
            self.assertEqual(fixture.OwnedInfobase().directory, Path("/tmp/onec-smoke/db"))

    def test_exact_geometry_modes_readonly_verification_and_cleanup(self):
        real_open = os.open
        calls = []

        def traced_open(path, flags, *args, **kwargs):
            calls.append((path, flags))
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(fixture.os, "open", side_effect=traced_open):
            with fixture.OwnedInfobase() as owned:
                self.assertEqual(owned.directory, self.db)
                data = self.file.read_bytes()
                self.assertEqual(len(data), 12288)
                self.assertEqual(data[:12], b"1CDBMSV8\x08\x03\x08\x00")
                self.assertEqual(int.from_bytes(data[12:16], "little"), 3)
                self.assertEqual(data[16:20], b"\0" * 4)
                self.assertEqual(int.from_bytes(data[20:24], "little"), 4096)
                self.assertEqual(data[24:], b"\0" * (12288 - 24))
                self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(self.db.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)
                self.assertEqual(self.file.stat().st_nlink, 1)
                owned.verify()
        self.assertFalse(self.root.exists())
        reads = [flags for path, flags in calls if path == "1Cv8.1CD" and not flags & os.O_CREAT]
        self.assertTrue(reads)
        self.assertTrue(all(flags & os.O_NOFOLLOW and flags & os.O_ACCMODE == os.O_RDONLY
                            for flags in reads))
        creates = [flags for path, flags in calls if path == "1Cv8.1CD" and flags & os.O_CREAT]
        self.assertEqual(len(creates), 1)
        self.assertTrue(creates[0] & os.O_EXCL and creates[0] & os.O_NOFOLLOW)

    def test_sequential_owners_and_reentry_rejected(self):
        for _ in range(3):
            with fixture.OwnedInfobase() as owned:
                owned.verify()
            self.assertFalse(self.root.exists())
            with self.assertRaises(fixture.FixtureError):
                owned.__enter__()

    def test_every_collision_is_untouched_without_reads_after_eexist(self):
        target = self.base / "target"
        target.write_bytes(b"private target\n")
        real_mkdir = os.mkdir
        real_calls = {name: getattr(os, name) for name in ("stat", "fstat", "open", "read", "listdir")}
        for kind in ("file", "directory", "empty-directory", "fifo", "symlink", "dangling"):
            with self.subTest(kind=kind):
                if kind == "file":
                    self.root.write_bytes(b"private collision\n")
                elif kind in ("directory", "empty-directory"):
                    self.root.mkdir()
                    if kind == "directory":
                        (self.root / "do-not-read").write_bytes(b"private collision\n")
                elif kind == "fifo":
                    os.mkfifo(self.root)
                else:
                    self.root.symlink_to(target if kind == "symlink" else self.base / "absent")
                before = self.root.lstat()
                collided = False

                def mkdir(*args, **kwargs):
                    nonlocal collided
                    try:
                        return real_mkdir(*args, **kwargs)
                    except FileExistsError:
                        collided = True
                        raise

                def guarded(name):
                    def call(*args, **kwargs):
                        self.assertFalse(collided, "unexpected read after fixed-root collision: " + name)
                        return real_calls[name](*args, **kwargs)
                    return call

                with contextlib.ExitStack() as stack:
                    stack.enter_context(mock.patch.object(fixture.os, "mkdir", side_effect=mkdir))
                    for name in real_calls:
                        stack.enter_context(mock.patch.object(fixture.os, name, side_effect=guarded(name)))
                    with self.assertRaises(fixture.FixtureError) as caught:
                        fixture.OwnedInfobase().__enter__()
                self.assertEqual(caught.exception.code, "fixture_collision")
                self.assertTrue(collided)
                self.assertEqual(fixture._stable(self.root.lstat()), fixture._stable(before))
                self.assertEqual(target.read_bytes(), b"private target\n")
                if kind in ("directory", "empty-directory"):
                    if kind == "directory":
                        self.assertEqual((self.root / "do-not-read").read_bytes(), b"private collision\n")
                        (self.root / "do-not-read").unlink()
                    self.root.rmdir()
                else:
                    self.root.unlink()

    def test_nested_second_owner_collides_without_affecting_first(self):
        with fixture.OwnedInfobase() as first:
            before = self.file.read_bytes()
            with self.assertRaises(fixture.FixtureError) as caught:
                with fixture.OwnedInfobase():
                    self.fail("second owner must never enter")
            self.assertEqual(caught.exception.code, "fixture_collision")
            first.verify()
            self.assertEqual(self.file.read_bytes(), before)
        self.assertFalse(self.root.exists())

    def test_clean_abandoned_or_active_exit_fails_and_preserves_tree(self):
        for active in (False, True):
            with self.subTest(active=active):
                owned = fixture.OwnedInfobase().__enter__()
                if active:
                    owned._child_active = True
                else:
                    owned.abandon()
                with self.assertRaises(fixture.FixtureError) as caught:
                    owned.__exit__(None, None, None)
                self.assertEqual(caught.exception.code, "fixture_cleanup_failed")
                self.assertFalse(caught.exception.cleanup_safe)
                self.assertEqual(self.file.read_bytes(), fixture._FIXTURE_BYTES)
                import shutil
                shutil.rmtree(self.root)

    def test_abandoned_exit_preserves_original_body_exception(self):
        with self.assertRaisesRegex(RuntimeError, "body failure"):
            with fixture.OwnedInfobase() as owned:
                owned.abandon()
                raise RuntimeError("body failure")
        self.assertEqual(self.file.read_bytes(), fixture._FIXTURE_BYTES)

    def test_exception_inside_context_still_cleans_verified_fixture(self):
        with self.assertRaisesRegex(RuntimeError, "expected body failure"):
            with fixture.OwnedInfobase():
                raise RuntimeError("expected body failure")
        self.assertFalse(self.root.exists())

    def test_no_recursive_cleanup(self):
        with mock.patch("shutil.rmtree", side_effect=AssertionError("recursive deletion forbidden")):
            with fixture.OwnedInfobase():
                pass
        self.assertFalse(self.root.exists())

    def test_setup_directory_creation_failure_removes_only_empty_owned_root(self):
        mkdir = os.mkdir

        def fail_db(path, *args, **kwargs):
            if path == "db":
                raise OSError("synthetic private setup failure")
            return mkdir(path, *args, **kwargs)

        with mock.patch.object(fixture.os, "mkdir", side_effect=fail_db):
            with self.assertRaises(fixture.FixtureError) as caught:
                fixture.OwnedInfobase().__enter__()
        self.assertEqual(caught.exception.code, "fixture_setup_failed")
        self.assertNotIn("private", str(caught.exception))
        self.assertFalse(self.root.exists())

    def test_unpinned_created_directory_is_preserved(self):
        real_open = os.open
        for component in ("onec-smoke", "db"):
            with self.subTest(component=component):
                def fail_open(path, *args, **kwargs):
                    if path == component:
                        raise OSError("open denied")
                    return real_open(path, *args, **kwargs)

                with mock.patch.object(fixture.os, "open", side_effect=fail_open):
                    with self.assertRaises(fixture.FixtureError):
                        fixture.OwnedInfobase().__enter__()
                self.assertTrue(self.root.is_dir())
                if component == "db":
                    self.assertTrue(self.db.is_dir())
                    self.db.rmdir()
                self.root.rmdir()

    def test_file_open_failure_removes_known_empty_directories(self):
        real_open = os.open

        def fail_file(path, *args, **kwargs):
            if path == "1Cv8.1CD":
                raise OSError("create denied")
            return real_open(path, *args, **kwargs)

        with mock.patch.object(fixture.os, "open", side_effect=fail_file):
            with self.assertRaises(fixture.FixtureError):
                fixture.OwnedInfobase().__enter__()
        self.assertFalse(self.root.exists())

    def test_write_failure_cleans_known_partial_bytes(self):
        real_write = os.write
        for initial in (0, 13):
            with self.subTest(initial=initial):
                written = False

                def fail_write(fd, data):
                    nonlocal written
                    if initial and not written:
                        written = True
                        return real_write(fd, data[:initial])
                    raise OSError("synthetic write failure")

                with mock.patch.object(fixture.os, "write", side_effect=fail_write):
                    with self.assertRaises(fixture.FixtureError):
                        fixture.OwnedInfobase().__enter__()
                self.assertFalse(self.root.exists())

    def test_uncertain_partial_write_is_preserved(self):
        real_write = os.write

        def uncertain(fd, data):
            real_write(fd, b"unexpected bytes\n")
            raise OSError("synthetic uncertain result")

        with mock.patch.object(fixture.os, "write", side_effect=uncertain):
            with self.assertRaises(fixture.FixtureError):
                fixture.OwnedInfobase().__enter__()
        self.assertEqual(self.file.read_bytes(), b"unexpected bytes\n")

    def test_mutations_abandon_without_removing_any_entries(self):
        for mutation in ("replace", "symlink", "hardlink", "content", "extra-file",
                         "extra-root", "mode", "restored-bytes-mtime", "db-symlink", "root-symlink"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(
                    prefix="mutation-", dir=self.base) as temporary:
                # Each case owns an isolated private namespace, even if an
                # earlier assertion fails. No public fixed pathname is touched.
                case = Path(temporary)
                parent = case / "namespace"
                outside = case / "outside"
                parent.mkdir()
                outside.mkdir()
                root = parent / "onec-smoke"
                db = root / "db"
                file = db / "1Cv8.1CD"
                sentinel = outside / "sentinel"
                sentinel.write_bytes(b"outside sentinel\n")

                def namespace():
                    return (os.open(case, fixture._directory_flags()),
                            os.open(parent, fixture._directory_flags()))

                with mock.patch.object(fixture, "_PARENT", parent), \
                        mock.patch.object(fixture, "_open_trusted_parent", side_effect=namespace):
                    owned = fixture.OwnedInfobase()
                    try:
                        owned.__enter__()
                        if mutation == "replace":
                            file.unlink()
                            file.write_bytes(fixture._FIXTURE_BYTES)
                        elif mutation == "symlink":
                            file.unlink()
                            file.symlink_to(sentinel)
                        elif mutation == "hardlink":
                            os.link(file, outside / "linked")
                        elif mutation in ("content", "restored-bytes-mtime"):
                            original = file.stat()
                            file.write_bytes(b"changed\n")
                            if mutation == "restored-bytes-mtime":
                                file.write_bytes(fixture._FIXTURE_BYTES)
                                # Test observable metadata-change detection, not
                                # an unobservable history of writes and restores.
                                os.utime(file, ns=(original.st_atime_ns,
                                                 original.st_mtime_ns - 2_000_000_000),
                                         follow_symlinks=False)
                                self.assertNotEqual(file.stat().st_mtime_ns, original.st_mtime_ns)
                                self.assertEqual(file.read_bytes(), fixture._FIXTURE_BYTES)
                        elif mutation == "extra-file":
                            (db / "extra").write_bytes(b"keep\n")
                        elif mutation == "extra-root":
                            (root / "extra").mkdir()
                        elif mutation == "mode":
                            file.chmod(0o640)
                        elif mutation == "db-symlink":
                            db.rename(outside / "original-db")
                            db.symlink_to(outside, target_is_directory=True)
                        else:
                            root.rename(outside / "original-root")
                            root.symlink_to(outside, target_is_directory=True)
                        before = root.lstat()
                        with self.assertRaises(fixture.FixtureError) as caught:
                            owned.verify()
                        self.assertEqual(caught.exception.code, "fixture_changed")
                        with self.assertRaises(fixture.FixtureError) as exit_error:
                            owned.__exit__(None, None, None)
                        self.assertEqual(exit_error.exception.code, "fixture_cleanup_failed")
                        self.assertEqual(fixture._stable(root.lstat()), fixture._stable(before))
                        self.assertEqual(sentinel.read_bytes(), b"outside sentinel\n")
                    finally:
                        # Test-only disposal runs even after a failed assertion;
                        # production cleanup and uncertain-object rules are unchanged.
                        try:
                            owned._close_fds()
                        finally:
                            if root.is_symlink():
                                root.unlink()
                            elif root.exists():
                                import shutil
                                shutil.rmtree(root)

    def test_exit_itself_verifies_and_preserves_unknown_extra_entry(self):
        with self.assertRaises(fixture.FixtureError) as caught:
            with fixture.OwnedInfobase():
                (self.db / "extra").write_bytes(b"must remain\n")
        self.assertEqual(caught.exception.code, "fixture_cleanup_failed")
        self.assertEqual((self.db / "extra").read_bytes(), b"must remain\n")
        self.assertEqual(self.file.read_bytes(), fixture._FIXTURE_BYTES)

    def test_cleanup_failure_stops_without_recursive_fallback(self):
        with mock.patch.object(fixture.os, "unlink", side_effect=OSError("unlink denied")):
            with self.assertRaises(fixture.FixtureError) as caught:
                with fixture.OwnedInfobase():
                    pass
        self.assertEqual(caught.exception.code, "fixture_cleanup_failed")
        self.assertEqual(self.file.read_bytes(), fixture._FIXTURE_BYTES)

    def test_close_failure_still_closes_every_remaining_descriptor(self):
        owned = fixture.OwnedInfobase().__enter__()
        expected = [getattr(owned, name) for name in (
            "_file_fd", "_db_fd", "_root_fd", "_parent_fd", "_namespace_fd")]
        real_close = os.close
        closed = []

        def close(fd):
            real_close(fd)
            closed.append(fd)
            if fd == expected[0]:
                raise OSError("synthetic uncertain close")

        with mock.patch.object(fixture.os, "close", side_effect=close):
            with self.assertRaises(fixture.FixtureError) as caught:
                owned.__exit__(None, None, None)
        self.assertEqual(caught.exception.code, "fixture_cleanup_failed")
        self.assertEqual([fd for fd in closed if fd in expected], expected)
        self.assertTrue(owned._closed)
        self.assertTrue(all(getattr(owned, name) is None for name in (
            "_file_fd", "_db_fd", "_root_fd", "_parent_fd", "_namespace_fd")))

    def test_census_uncertainty_preserves_fixture_after_bounded_reap(self):
        with mock.patch.object(fixture, "_group_quiet", side_effect=OSError("census unavailable")):
            with self.assertRaises(fixture.FixtureError) as caught:
                with fixture.OwnedInfobase() as owned:
                    owned.run_child([sys.executable, "-c", "pass"], self.base, env={}, seconds=1,
                                    stdout_limit=1024, stderr_limit=1024)
        self.assertEqual(caught.exception.code, "interpreter_cleanup_uncertain")
        self.assertFalse(caught.exception.cleanup_safe)
        self.assertEqual(self.file.read_bytes(), fixture._FIXTURE_BYTES)

    def test_persistent_proc_esrch_preserves_fixture_after_bounded_reap(self):
        entry = types.SimpleNamespace(name="23456", path="/proc/23456")
        started = time.monotonic()
        # Only shorten the test shutdown cap; production remains exactly one second.
        with mock.patch.object(fixture, "_SHUTDOWN_SECONDS", 0.03), \
                mock.patch.object(fixture.os, "scandir", side_effect=lambda path: contextlib.nullcontext([entry])), \
                mock.patch.object(fixture, "open", create=True,
                                  side_effect=ProcessLookupError(errno.ESRCH, "synthetic vanished process")):
            with self.assertRaises(fixture.FixtureError) as caught:
                with fixture.OwnedInfobase() as owned:
                    owned.run_child([sys.executable, "-c", "pass"], self.base, env={}, seconds=1,
                                    stdout_limit=1024, stderr_limit=1024)
        self.assertEqual(caught.exception.code, "interpreter_cleanup_uncertain")
        self.assertFalse(caught.exception.cleanup_safe)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(self.file.read_bytes(), fixture._FIXTURE_BYTES)
        self.assertEqual(fixture._SHUTDOWN_SECONDS, 1.0)

    def test_child_uncertainty_preserves_fixture_but_safe_error_cleans(self):
        for safe in (True, False):
            with self.subTest(safe=safe):
                error = fixture.FixtureError("interpreter_timeout", cleanup_safe=safe)
                with mock.patch.object(fixture, "bounded_child", side_effect=error):
                    with self.assertRaises(fixture.FixtureError):
                        with fixture.OwnedInfobase() as owned:
                            owned.run_child(["unused"], self.base, env={}, seconds=1,
                                            stdout_limit=100, stderr_limit=100)
                self.assertEqual(self.root.exists(), not safe)

    def test_standalone_unsafe_child_error_also_blocks_context_cleanup(self):
        with self.assertRaises(fixture.FixtureError):
            with fixture.OwnedInfobase():
                raise fixture.FixtureError("interpreter_cleanup_uncertain", cleanup_safe=False)
        self.assertTrue(self.file.exists())

    def test_real_child_reads_exact_header_then_fixture_cleans(self):
        with fixture.OwnedInfobase() as owned:
            code, out, err = owned.run_child(
                [sys.executable, "-c", "import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())",
                 str(self.file)], self.base, env={"PYTHONUTF8": "1"}, seconds=2,
                stdout_limit=16384, stderr_limit=1024)
            self.assertEqual((code, out, err), (0, fixture._FIXTURE_BYTES, b""))
        self.assertFalse(self.root.exists())

    def test_child_content_mutation_is_detected_and_preserved(self):
        with self.assertRaises(fixture.FixtureError) as caught:
            with fixture.OwnedInfobase() as owned:
                owned.run_child([sys.executable, "-c",
                                 "import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(b'changed\\n')",
                                 str(self.file)], self.base, env={}, seconds=2,
                                stdout_limit=1024, stderr_limit=1024)
        self.assertEqual(caught.exception.code, "fixture_changed")
        self.assertEqual(self.file.read_bytes(), b"changed\n")


@unittest.skipUnless(LINUX, "Linux waitid(WNOWAIT) and process-group tests only")
class BoundedChildTests(unittest.TestCase):
    def run_child(self, source, *, seconds=2, stdout_limit=65536, stderr_limit=65536):
        return fixture.bounded_child([sys.executable, "-c", source], Path.cwd(),
                                     env={"LANG": "C.UTF-8", "PYTHONUTF8": "1"}, seconds=seconds,
                                     stdout_limit=stdout_limit, stderr_limit=stderr_limit)

    def test_exact_binary_stdout_stderr_and_success_code(self):
        result = self.run_child("import os;os.write(1,b'a\\x00\\xff\\r\\n');os.write(2,b'err\\n');raise SystemExit(7)")
        self.assertEqual(result, (7, b"a\x00\xff\r\n", b"err\n"))

    def test_explicit_utf8_lf_and_no_inherited_secret(self):
        with mock.patch.dict(os.environ, {"PRIVATE_TEST_SECRET": "do-not-inherit"}):
            result = self.run_child("import os,sys;sys.stdout.buffer.write(('Привет\\n'+os.environ.get('PRIVATE_TEST_SECRET','absent')+'\\n').encode('utf-8'))")
        self.assertEqual(result, (0, "Привет\nabsent\n".encode("utf-8"), b""))

    def test_empty_output_and_closed_pipes_do_not_skip_timeout(self):
        self.assertEqual(self.run_child("pass"), (0, b"", b""))
        started = time.monotonic()
        with self.assertRaises(fixture.FixtureError) as caught:
            self.run_child("import os,time;os.close(1);os.close(2);time.sleep(30)", seconds=0.05)
        self.assertEqual(caught.exception.code, "interpreter_timeout")
        self.assertTrue(caught.exception.cleanup_safe)
        self.assertLess(time.monotonic() - started, 2)

    def test_timeout_and_output_limits_have_verified_shutdown(self):
        for source, options, expected in (
                ("import time;time.sleep(30)", {"seconds": 0.05}, "interpreter_timeout"),
                ("import os;os.write(1,b'x'*100000)", {"stdout_limit": 13}, "interpreter_output_limit"),
                ("import os;os.write(2,b'x'*100000)", {"stderr_limit": 13}, "interpreter_output_limit")):
            with self.subTest(expected=expected, options=options):
                started = time.monotonic()
                with self.assertRaises(fixture.FixtureError) as caught:
                    self.run_child(source, **options)
                self.assertEqual(caught.exception.code, expected)
                self.assertTrue(caught.exception.cleanup_safe)
                self.assertLess(time.monotonic() - started, 2)

    def test_zero_output_limit_still_allows_empty_output(self):
        self.assertEqual(self.run_child("pass", stdout_limit=0, stderr_limit=0), (0, b"", b""))
        with self.assertRaises(fixture.FixtureError) as caught:
            self.run_child("print('x')", stdout_limit=0)
        self.assertEqual(caught.exception.code, "interpreter_output_limit")

    def test_exited_parent_retains_code_and_kills_closed_pipe_descendant(self):
        source = ("import os,time\n"
                  "pid=os.fork()\n"
                  "if pid == 0:\n"
                  " os.close(1);os.close(2);time.sleep(30);os._exit(0)\n"
                  "os.write(1,(str(pid)+'\\n').encode('ascii'))\n"
                  "os._exit(9)\n")
        code, out, err = self.run_child(source)
        self.assertEqual(code, 9)
        self.assertEqual(err, b"")
        pid = int(out.strip())
        try:
            raw = Path(f"/proc/{pid}/stat").read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            # procfs can remove the task between open and read: both ENOENT and
            # ESRCH mean the already-shut-down descendant is no longer present.
            pass
        else:
            self.assertIn(raw[raw.rfind(b") ") + 2:].split()[0], (b"Z", b"X", b"x"))

    def test_descendant_procfs_absence_only_does_not_weaken_live_or_access_checks(self):
        with mock.patch.object(self, "run_child", return_value=(9, b"123\n", b"")):
            for error in (FileNotFoundError(errno.ENOENT, "gone"),
                          ProcessLookupError(errno.ESRCH, "gone")):
                with self.subTest(error=type(error).__name__), mock.patch.object(Path, "read_bytes", side_effect=error):
                    self.test_exited_parent_retains_code_and_kills_closed_pipe_descendant()
            with mock.patch.object(Path, "read_bytes", side_effect=PermissionError(errno.EACCES, "denied")):
                with self.assertRaises(PermissionError):
                    self.test_exited_parent_retains_code_and_kills_closed_pipe_descendant()
            for state in (b"R", b"S", b"D", b"T"):
                with self.subTest(live_state=state), mock.patch.object(Path, "read_bytes", return_value=b"123 (child) " + state + b" 1"):
                    with self.assertRaises(AssertionError):
                        self.test_exited_parent_retains_code_and_kills_closed_pipe_descendant()

    def test_real_signals_all_precede_reap_and_no_hidden_wait_api(self):
        events = []
        killpg, waitpid = os.killpg, os.waitpid

        def kill(*args):
            events.append("kill")
            return killpg(*args)

        def reap(*args):
            result = waitpid(*args)
            if result[0]:
                events.append("reap")
            return result

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(fixture.os, "killpg", side_effect=kill))
            stack.enter_context(mock.patch.object(fixture.os, "waitpid", side_effect=reap))
            for name in ("__enter__", "__exit__", "wait", "poll", "communicate"):
                stack.enter_context(mock.patch.object(fixture.subprocess.Popen, name,
                                                       side_effect=AssertionError("hidden wait forbidden")))
            self.assertEqual(self.run_child("raise SystemExit(4)"), (4, b"", b""))
        self.assertEqual(events, ["kill", "reap"])

    def test_invalid_configuration_fails_before_spawn(self):
        defaults = {"env": {}, "seconds": 1, "stdout_limit": 1, "stderr_limit": 1}
        for key, value in (("seconds", 11), ("seconds", 0), ("seconds", float("nan")),
                           ("seconds", True), ("stdout_limit", 1048577), ("stderr_limit", 65537),
                           ("stdout_limit", -1), ("stderr_limit", True), ("env", None)):
            with self.subTest(key=key, value=value), mock.patch.object(fixture.subprocess, "Popen") as popen:
                with self.assertRaises(fixture.FixtureError) as caught:
                    fixture.bounded_child([sys.executable], Path.cwd(), **{**defaults, key: value})
                self.assertEqual(caught.exception.code, "interpreter_configuration_invalid")
                popen.assert_not_called()

    def test_unavailable_executable_is_finite_and_cleanup_safe(self):
        with self.assertRaises(fixture.FixtureError) as caught:
            fixture.bounded_child(["/nonexistent-native-fixture-test-executable"], Path.cwd(),
                                  env={}, seconds=1, stdout_limit=1, stderr_limit=1)
        self.assertEqual(caught.exception.code, "interpreter_unavailable")
        self.assertTrue(caught.exception.cleanup_safe)

    def test_nondefault_sigchld_is_rejected_before_spawn(self):
        with mock.patch.object(fixture.signal, "getsignal", return_value=signal.SIG_IGN), \
                mock.patch.object(fixture.subprocess, "Popen") as popen:
            with self.assertRaises(fixture.FixtureError):
                self.run_child("pass")
        popen.assert_not_called()

    def test_no_signal_after_lost_child_ownership(self):
        process = types.SimpleNamespace(pid=12345, returncode=None)
        with mock.patch.object(fixture, "_peek_exit", side_effect=ChildProcessError), \
                mock.patch.object(fixture.os, "killpg") as kill, \
                mock.patch.object(fixture.os, "waitpid") as reap:
            self.assertEqual(fixture._shutdown_child(process, time.monotonic() + 0.03), (None, False))
        kill.assert_not_called()
        reap.assert_not_called()

    def test_unreapable_child_has_bounded_shutdown_and_unsafe_result(self):
        process = types.SimpleNamespace(pid=12345, returncode=None)
        started = time.monotonic()
        with mock.patch.object(fixture, "_peek_exit", return_value=object()), \
                mock.patch.object(fixture, "_group_quiet", return_value=True), \
                mock.patch.object(fixture.os, "killpg") as kill, \
                mock.patch.object(fixture.os, "waitpid", return_value=(0, 0)):
            self.assertEqual(fixture._shutdown_child(process, started + 0.03), (None, False))
        self.assertLess(time.monotonic() - started, 0.3)
        self.assertIsNone(process.returncode)
        kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_unquiet_group_or_failed_census_never_claims_safe_cleanup(self):
        for census in (False, OSError("unreadable process")):
            with self.subTest(census=census):
                process = types.SimpleNamespace(pid=12345, returncode=None)
                effects = {"side_effect": census} if isinstance(census, OSError) else {"return_value": census}
                events = []
                with mock.patch.object(fixture, "_peek_exit", return_value=object()), \
                        mock.patch.object(fixture, "_group_quiet", **effects), \
                        mock.patch.object(fixture.os, "killpg", side_effect=lambda *a: events.append("kill")), \
                        mock.patch.object(fixture.os, "waitpid", side_effect=lambda *a: (events.append("reap") or (12345, 7 << 8))):
                    self.assertEqual(fixture._shutdown_child(process, time.monotonic() + 0.03), (7, False))
                self.assertEqual(events, ["kill", "reap"])
                self.assertEqual(process.returncode, 7)

    def test_failed_group_signal_is_not_reported_safe(self):
        process = types.SimpleNamespace(pid=12345, returncode=None)
        with mock.patch.object(fixture, "_peek_exit", return_value=object()), \
                mock.patch.object(fixture, "_group_quiet", return_value=True), \
                mock.patch.object(fixture.os, "killpg", side_effect=PermissionError), \
                mock.patch.object(fixture.os, "waitpid", return_value=(12345, 0)):
            self.assertEqual(fixture._shutdown_child(process, time.monotonic() + 0.03), (0, False))

    def test_interrupt_during_selector_work_still_reaps_before_propagating(self):
        real_popen = fixture.subprocess.Popen
        for interruption in (KeyboardInterrupt, SystemExit):
            with self.subTest(interruption=interruption):
                children = []

                def popen(*args, **kwargs):
                    child = real_popen(*args, **kwargs)
                    children.append(child)
                    return child

                with mock.patch.object(fixture.subprocess, "Popen", side_effect=popen), \
                        mock.patch.object(fixture.selectors.DefaultSelector, "select", side_effect=interruption):
                    with self.assertRaises(interruption):
                        self.run_child("import time;time.sleep(30)")
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].returncode)
                with self.assertRaises(ChildProcessError):
                    os.waitpid(children[0].pid, os.WNOHANG)

    def test_interrupt_during_shutdown_census_reaps_but_is_unsafe(self):
        real_popen = fixture.subprocess.Popen
        for interruption in (KeyboardInterrupt, SystemExit):
            with self.subTest(interruption=interruption):
                children = []

                def popen(*args, **kwargs):
                    child = real_popen(*args, **kwargs)
                    children.append(child)
                    return child

                with mock.patch.object(fixture.subprocess, "Popen", side_effect=popen), \
                        mock.patch.object(fixture, "_group_quiet", side_effect=interruption):
                    with self.assertRaises(fixture.FixtureError) as caught:
                        self.run_child("pass")
                self.assertEqual(caught.exception.code, "interpreter_cleanup_uncertain")
                self.assertFalse(caught.exception.cleanup_safe)
                self.assertIsNotNone(children[0].returncode)
                with self.assertRaises(ChildProcessError):
                    os.waitpid(children[0].pid, os.WNOHANG)

    def test_shutdown_uncertainty_propagates_as_finite_error(self):
        original = fixture._shutdown_child

        def actual_reap_but_report_uncertain(process, deadline):
            code, safe = original(process, deadline)
            self.assertTrue(safe)
            return code, False

        with mock.patch.object(fixture, "_shutdown_child", side_effect=actual_reap_but_report_uncertain):
            with self.assertRaises(fixture.FixtureError) as caught:
                self.run_child("pass")
        self.assertEqual(caught.exception.code, "interpreter_cleanup_uncertain")
        self.assertFalse(caught.exception.cleanup_safe)


@unittest.skipUnless(LINUX, "Linux process-census race handling only")
class ProcCensusRaceTests(unittest.TestCase):
    """Deterministic failures, not attribution of any historical flaky test."""

    @staticmethod
    def entry(pid):
        return types.SimpleNamespace(name=str(pid), path=f"/proc/{pid}")

    def test_transient_esrch_at_open_or_read_requires_later_complete_census(self):
        for stage in ("open", "read"):
            with self.subTest(stage=stage):
                process = types.SimpleNamespace(pid=12345, returncode=None)
                events = []
                reads = 0
                entries = [self.entry(23456), self.entry(23457)]

                def scan(path):
                    self.assertEqual(path, "/proc")
                    events.append("census")
                    return contextlib.nullcontext(entries)

                def opened(path, mode):
                    nonlocal reads
                    reads += 1
                    if reads == 1:
                        events.append("esrch_" + stage)
                        error = ProcessLookupError(errno.ESRCH, "synthetic vanished process")
                        if stage == "open":
                            raise error
                        stream = mock.MagicMock()
                        stream.__enter__.return_value.read.side_effect = error
                        return stream
                    events.append("read_" + path.split("/")[2])
                    return io.BytesIO(b"23456 (synthetic) Z 1 12345 12345\n")

                with mock.patch.object(fixture.os, "scandir", side_effect=scan), \
                        mock.patch.object(fixture, "open", create=True, side_effect=opened), \
                        mock.patch.object(fixture, "_peek_exit", return_value=object()), \
                        mock.patch.object(fixture.os, "killpg", side_effect=lambda *a: events.append("kill")), \
                        mock.patch.object(fixture.os, "waitpid", side_effect=lambda *a: (events.append("reap") or (12345, 9 << 8))):
                    self.assertEqual(fixture._shutdown_child(process, time.monotonic() + 0.2), (9, True))
                self.assertEqual(events, ["kill", "census", "esrch_" + stage, "census",
                                          "read_23456", "read_23457", "reap"])
                self.assertEqual(process.returncode, 9)
                self.assertEqual(fixture._SHUTDOWN_SECONDS, 1.0)

    def test_persistent_esrch_never_becomes_quiet_and_keeps_deadline(self):
        process = types.SimpleNamespace(pid=12345, returncode=None)
        entry = self.entry(23456)
        events = []
        started = time.monotonic()
        with mock.patch.object(fixture.os, "scandir", side_effect=lambda path: contextlib.nullcontext([entry])) as scans, \
                mock.patch.object(fixture, "open", create=True,
                                  side_effect=ProcessLookupError(errno.ESRCH, "synthetic vanished process")), \
                mock.patch.object(fixture, "_peek_exit", return_value=object()), \
                mock.patch.object(fixture.os, "killpg", side_effect=lambda *a: events.append("kill")), \
                mock.patch.object(fixture.os, "waitpid", side_effect=lambda *a: (events.append("reap") or (12345, 9 << 8))):
            self.assertEqual(fixture._shutdown_child(process, started + 0.03), (9, False))
        self.assertGreaterEqual(scans.call_count, 2)
        self.assertLess(time.monotonic() - started, 0.3)
        self.assertEqual(events, ["kill", "reap"])
        self.assertEqual(process.returncode, 9)
        self.assertEqual(fixture._SHUTDOWN_SECONDS, 1.0)

    def test_other_proc_errors_fail_closed_without_retry_or_false_success(self):
        for error in (PermissionError(errno.EACCES, "synthetic denied"),
                      OSError(errno.EIO, "synthetic IO failure"),
                      OSError(errno.EPERM, "synthetic prohibited")):
            for stage in ("open", "read"):
                with self.subTest(errno=error.errno, stage=stage):
                    process = types.SimpleNamespace(pid=12345, returncode=None)
                    entry = self.entry(23456)
                    stream = mock.MagicMock()
                    stream.__enter__.return_value.read.side_effect = error
                    effect = {"side_effect": error} if stage == "open" else {"return_value": stream}
                    events = []
                    with mock.patch.object(fixture.os, "scandir", side_effect=lambda path: contextlib.nullcontext([entry])) as scans, \
                            mock.patch.object(fixture, "open", create=True, **effect), \
                            mock.patch.object(fixture, "_peek_exit", return_value=object()), \
                            mock.patch.object(fixture.os, "killpg", side_effect=lambda *a: events.append("kill")), \
                            mock.patch.object(fixture.os, "waitpid", side_effect=lambda *a: (events.append("reap") or (12345, 0))):
                        self.assertEqual(fixture._shutdown_child(process, time.monotonic() + 0.1), (0, False))
                    self.assertEqual(scans.call_count, 1)
                    self.assertEqual(events, ["kill", "reap"])


@unittest.skipUnless(LINUX, "Linux trusted namespace metadata only")
class TrustedNamespaceTests(unittest.TestCase):
    """Exercise production ancestor validation with mocked FDs, no fixed-root I/O."""

    @staticmethod
    def info(uid, mode):
        return types.SimpleNamespace(st_uid=uid, st_mode=stat.S_IFDIR | mode)

    def test_root_or_effective_uid_owned_namespaces_are_accepted(self):
        for root_uid in (0, 1000):
            for tmp_uid in (0, 1000):
                for tmp_mode in (0o700, 0o755, 0o1700, 0o1775, 0o1777):
                    with self.subTest(root_uid=root_uid, tmp_uid=tmp_uid, tmp_mode=oct(tmp_mode)):
                        with mock.patch.object(fixture.os, "geteuid", return_value=1000), \
                                mock.patch.object(fixture.os, "open", side_effect=(70, 71)) as opened, \
                                mock.patch.object(fixture.os, "fstat", side_effect=(
                                    self.info(root_uid, 0o755), self.info(tmp_uid, tmp_mode))), \
                                mock.patch.object(fixture.os, "close") as closed, \
                                mock.patch.object(fixture.os, "mkdir") as mkdir:
                            self.assertEqual(fixture._open_trusted_parent(), (70, 71))
                        self.assertEqual(opened.call_args_list, [
                            mock.call("/", fixture._directory_flags()),
                            mock.call("tmp", fixture._directory_flags(), dir_fd=70)])
                        self.assertTrue(fixture._directory_flags() & os.O_NOFOLLOW)
                        self.assertTrue(fixture._directory_flags() & os.O_DIRECTORY)
                        closed.assert_not_called()
                        mkdir.assert_not_called()

    def test_foreign_owners_are_rejected_even_with_restrictive_modes(self):
        cases = ((1000, 2000, 1000), (1000, 0, 2000), (0, 1000, 0), (0, 0, 1000))
        for effective_uid, root_uid, tmp_uid in cases:
            with self.subTest(effective_uid=effective_uid, root_uid=root_uid, tmp_uid=tmp_uid):
                with mock.patch.object(fixture.os, "geteuid", return_value=effective_uid), \
                        mock.patch.object(fixture.os, "open", side_effect=(70, 71)) as opened, \
                        mock.patch.object(fixture.os, "fstat", side_effect=(
                            self.info(root_uid, 0o755), self.info(tmp_uid, 0o755))), \
                        mock.patch.object(fixture.os, "close") as closed, \
                        mock.patch.object(fixture.os, "mkdir") as mkdir:
                    with self.assertRaises(fixture.FixtureError) as caught:
                        fixture._open_trusted_parent()
                self.assertEqual(caught.exception.code, "fixture_unavailable")
                root_rejected = root_uid not in {0, effective_uid}
                self.assertEqual(opened.call_count, 1 if root_rejected else 2)
                self.assertEqual(closed.call_args_list,
                                 [mock.call(70)] if root_rejected else [mock.call(71), mock.call(70)])
                mkdir.assert_not_called()

    def test_writable_root_is_rejected_with_or_without_sticky_bit(self):
        for mode in (0o775, 0o757, 0o777, 0o1777):
            with self.subTest(mode=oct(mode)):
                with mock.patch.object(fixture.os, "geteuid", return_value=1000), \
                        mock.patch.object(fixture.os, "open", return_value=70) as opened, \
                        mock.patch.object(fixture.os, "fstat", return_value=self.info(1000, mode)), \
                        mock.patch.object(fixture.os, "close") as closed:
                    with self.assertRaises(fixture.FixtureError) as caught:
                        fixture._open_trusted_parent()
                self.assertEqual(caught.exception.code, "fixture_unavailable")
                opened.assert_called_once_with("/", fixture._directory_flags())
                closed.assert_called_once_with(70)

    def test_writable_nonsticky_tmp_is_rejected(self):
        for owner in (0, 1000):
            for mode in (0o775, 0o757, 0o777, 0o733):
                with self.subTest(owner=owner, mode=oct(mode)):
                    with mock.patch.object(fixture.os, "geteuid", return_value=1000), \
                            mock.patch.object(fixture.os, "open", side_effect=(70, 71)), \
                            mock.patch.object(fixture.os, "fstat", side_effect=(
                                self.info(owner, 0o755), self.info(owner, mode))), \
                            mock.patch.object(fixture.os, "close") as closed:
                        with self.assertRaises(fixture.FixtureError) as caught:
                            fixture._open_trusted_parent()
                    self.assertEqual(caught.exception.code, "fixture_unavailable")
                    self.assertEqual(closed.call_args_list, [mock.call(71), mock.call(70)])


class PlatformAndErrorTests(unittest.TestCase):
    def test_nonlinux_is_explicitly_unsupported_without_filesystem_touch(self):
        with mock.patch.object(fixture.sys, "platform", "win32"), \
                mock.patch.object(fixture.os, "mkdir") as mkdir:
            with self.assertRaises(fixture.FixtureError) as caught:
                fixture.OwnedInfobase().__enter__()
        self.assertEqual(caught.exception.code, "fixture_unavailable")
        mkdir.assert_not_called()

    def test_error_vocabulary_cannot_include_arbitrary_details(self):
        with self.assertRaises(ValueError):
            fixture.FixtureError("private executable output")
        for code in fixture._ERROR_CODES:
            self.assertEqual(str(fixture.FixtureError(code)), code)


if __name__ == "__main__":
    unittest.main()
