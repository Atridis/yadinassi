"""Owned synthetic header fixture for the fixed Linux native-smoke preflight.

This is header geometry, NOT a usable or validated 1C database. Ownership relies
on a trusted, single-job Linux host, / and /tmp owned by root or the effective
UID, and no malicious same-UID/root actor. Ownership alone proves no UID mapping.
The root directory must not be group/world writable; writable /tmp must be sticky.
mkdir-to-open and check-to-unlink are NOT atomic ownership
proofs against such an actor. The audited child must not escape its process group
or session; this module is not a sandbox for arbitrary executable code. No other
thread or signal handler may reap this helper's child: WNOWAIT must retain PID
ownership until our final waitpid. Ordinary local kernel/filesystem calls must remain responsive. No Windows claim is made.
"""
from __future__ import annotations

import errno
import math
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import time

_PARENT = Path("/tmp")
_ROOT_NAME = "onec-smoke"
_DB_NAME = "db"
_FILE_NAME = "1Cv8.1CD"
_PAGE_SIZE = 4096
_PAGE_COUNT = 3
_HEADER = (b"1CDBMSV8" + bytes((8, 3, 8, 0)) + _PAGE_COUNT.to_bytes(4, "little")
           + b"\0" * 4 + _PAGE_SIZE.to_bytes(4, "little"))
_FIXTURE_BYTES = _HEADER + b"\0" * (_PAGE_COUNT * _PAGE_SIZE - len(_HEADER))
_SHUTDOWN_SECONDS = 1.0
_POLL_SECONDS = 0.01
_MAX_PROC_ENTRIES = 32768
_ERROR_CODES = frozenset({
    "fixture_unavailable", "fixture_collision", "fixture_changed",
    "fixture_setup_failed", "fixture_cleanup_failed", "interpreter_timeout",
    "interpreter_output_limit", "interpreter_unavailable",
    "interpreter_cleanup_uncertain", "interpreter_configuration_invalid",
})


class FixtureError(Exception):
    """Finite public metadata only; cleanup_safe=False prohibits fixture removal."""

    def __init__(self, code: str, *, cleanup_safe: bool = True):
        if code not in _ERROR_CODES:
            raise ValueError("unknown fixture error code")
        self.code = code
        self.cleanup_safe = cleanup_safe
        super().__init__(code)


def _linux_required() -> None:
    if not sys.platform.startswith("linux") or not all(hasattr(os, name) for name in (
            "O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "waitid", "WNOWAIT")):
        raise FixtureError("fixture_unavailable")


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _core(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _stable(info) -> tuple:
    return _core(info) + (info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_trusted_parent() -> tuple[int, int]:
    """Private seam replaced only by offline tests; production always pins /tmp."""
    trusted_owners = {0, os.geteuid()}
    root_fd = os.open("/", _directory_flags())
    try:
        root = os.fstat(root_fd)
        if root.st_uid not in trusted_owners or stat.S_IMODE(root.st_mode) & 0o022:
            raise FixtureError("fixture_unavailable")
        parent_fd = os.open("tmp", _directory_flags(), dir_fd=root_fd)
        try:
            parent = os.fstat(parent_fd)
            if (parent.st_uid not in trusted_owners or (stat.S_IMODE(parent.st_mode) & 0o022
                                     and not parent.st_mode & stat.S_ISVTX)):
                raise FixtureError("fixture_unavailable")
        except BaseException:
            os.close(parent_fd)
            raise
        return root_fd, parent_fd
    except BaseException:
        os.close(root_fd)
        raise


class OwnedInfobase:
    """Exclusively create /tmp/onec-smoke, verify it, and remove only owned entries.

    A pre-existing root, of ANY kind, is not inspected, reused or deleted.
    Uncertain partial setup, mutation, child shutdown or cleanup preserves the
    remaining tree. There is no recursive deletion, lock or stale-root recovery.
    """

    def __init__(self):
        self._namespace_fd = self._parent_fd = self._root_fd = self._db_fd = None
        self._file_fd = None
        self._namespace_info = self._parent_info = None
        self._root_info = self._db_info = self._file_info = None
        self._root_created = self._db_created = self._file_created = False
        self._expected = b""
        self._snapshot = None
        self._abandoned = False
        self._entered = False
        self._closed = False
        self._child_active = False

    @property
    def directory(self) -> Path:
        return _PARENT / _ROOT_NAME / _DB_NAME

    def abandon(self) -> None:
        """Withhold deletion when child shutdown or filesystem identity is uncertain."""
        self._abandoned = True

    def __enter__(self):
        _linux_required()
        if self._entered or self._closed:
            raise FixtureError("fixture_setup_failed")
        self._entered = True
        try:
            self._namespace_fd, self._parent_fd = _open_trusted_parent()
            self._namespace_info = os.fstat(self._namespace_fd)
            self._parent_info = os.fstat(self._parent_fd)
            try:
                os.mkdir(_ROOT_NAME, 0o700, dir_fd=self._parent_fd)
            except FileExistsError:
                # Deliberately no stat/open/listdir/read on the colliding pathname.
                raise FixtureError("fixture_collision") from None
            self._root_created = True
            self._root_fd = os.open(_ROOT_NAME, _directory_flags(), dir_fd=self._parent_fd)
            self._root_info = os.fstat(self._root_fd)
            os.fchmod(self._root_fd, 0o700)
            self._root_info = os.fstat(self._root_fd)
            os.mkdir(_DB_NAME, 0o700, dir_fd=self._root_fd)
            self._db_created = True
            self._db_fd = os.open(_DB_NAME, _directory_flags(), dir_fd=self._root_fd)
            self._db_info = os.fstat(self._db_fd)
            os.fchmod(self._db_fd, 0o700)
            self._db_info = os.fstat(self._db_fd)
            self._file_fd = os.open(_FILE_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                    | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self._db_fd)
            self._file_created = True
            self._file_info = os.fstat(self._file_fd)
            os.fchmod(self._file_fd, 0o600)
            self._file_info = os.fstat(self._file_fd)
            while len(self._expected) < len(_FIXTURE_BYTES):
                count = os.write(self._file_fd, _FIXTURE_BYTES[len(self._expected):])
                if count <= 0:
                    raise OSError("short fixture write")
                self._expected += _FIXTURE_BYTES[len(self._expected):len(self._expected) + count]
                self._file_info = os.fstat(self._file_fd)
            # All verification reads use a separate O_RDONLY, no-follow descriptor.
            self._verify_tree()
            self._snapshot = tuple(_stable(os.fstat(fd)) for fd in (
                self._root_fd, self._db_fd, self._file_fd))
            self.verify()
            return self
        except BaseException as error:
            try:
                if self._root_created:
                    self._cleanup()
            except (FixtureError, OSError):
                self.abandon()
            finally:
                self._close_fds()
            if isinstance(error, FixtureError):
                raise
            if isinstance(error, (OSError, ValueError)):
                raise FixtureError("fixture_setup_failed") from None
            raise

    def _check_directory(self, fd, parent_fd, name, original, links) -> None:
        if fd is None or original is None:
            raise FixtureError("fixture_changed")
        current = os.fstat(fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISDIR(current.st_mode) or _core(current) != _core(original)
                or _core(named) != _core(current) or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o700 or current.st_nlink != links
                or named.st_nlink != links):
            raise FixtureError("fixture_changed")

    def _verify_namespace(self) -> None:
        root = os.fstat(self._namespace_fd)
        parent = os.fstat(self._parent_fd)
        # Production _PARENT.name is exactly 'tmp'; the private test seam pins an
        # equally trusted temporary namespace instead of touching the fixed path.
        named = os.stat(_PARENT.name, dir_fd=self._namespace_fd, follow_symlinks=False)
        if (_core(root) != _core(self._namespace_info)
                or _core(parent) != _core(self._parent_info)
                or _core(named) != _core(parent)):
            raise FixtureError("fixture_changed")

    def _verify_tree(self) -> None:
        self._verify_namespace()
        self._check_directory(self._root_fd, self._parent_fd, _ROOT_NAME,
                              self._root_info, 3 if self._db_created else 2)
        if sorted(os.listdir(self._root_fd)) != ([_DB_NAME] if self._db_created else []):
            raise FixtureError("fixture_changed")
        if not self._db_created:
            return
        self._check_directory(self._db_fd, self._root_fd, _DB_NAME, self._db_info, 2)
        if sorted(os.listdir(self._db_fd)) != ([_FILE_NAME] if self._file_created else []):
            raise FixtureError("fixture_changed")
        if not self._file_created:
            return
        if self._file_fd is None or self._file_info is None:
            raise FixtureError("fixture_changed")
        pinned = os.fstat(self._file_fd)
        if (not stat.S_ISREG(pinned.st_mode) or _stable(pinned) != _stable(self._file_info)
                or pinned.st_uid != os.geteuid() or pinned.st_nlink != 1
                or stat.S_IMODE(pinned.st_mode) != 0o600 or pinned.st_size != len(self._expected)):
            raise FixtureError("fixture_changed")
        fd = os.open(_FILE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=self._db_fd)
        try:
            before = os.fstat(fd)
            if _stable(before) != _stable(pinned):
                raise FixtureError("fixture_changed")
            chunks = bytearray()
            while len(chunks) <= len(self._expected):
                chunk = os.read(fd, min(4096, len(self._expected) + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if bytes(chunks) != self._expected or _stable(os.fstat(fd)) != _stable(before):
                raise FixtureError("fixture_changed")
            named = os.stat(_FILE_NAME, dir_fd=self._db_fd, follow_symlinks=False)
            if _stable(named) != _stable(before):
                raise FixtureError("fixture_changed")
        finally:
            os.close(fd)
        if self._snapshot is not None and tuple(_stable(os.fstat(fd)) for fd in (
                self._root_fd, self._db_fd, self._file_fd)) != self._snapshot:
            raise FixtureError("fixture_changed")

    def verify(self) -> None:
        if self._closed or self._abandoned or not self._entered:
            raise FixtureError("fixture_changed")
        try:
            self._verify_tree()
        except (OSError, FixtureError, ValueError, TypeError):
            self.abandon()
            raise FixtureError("fixture_changed") from None

    def run_child(self, args, cwd, *, env, seconds, stdout_limit, stderr_limit):
        """Verify both sides and never clean a fixture after uncertain shutdown."""
        self.verify()
        self._child_active = True
        try:
            result = bounded_child(args, cwd, env=env, seconds=seconds,
                                   stdout_limit=stdout_limit, stderr_limit=stderr_limit)
        except FixtureError as error:
            if not error.cleanup_safe:
                self.abandon()
            else:
                self.verify()
            raise
        except BaseException:
            self.abandon()
            raise
        else:
            self.verify()
            return result
        finally:
            self._child_active = False

    def _cleanup(self) -> None:
        if self._abandoned or self._child_active:
            return
        try:
            self._verify_tree()
            if self._file_created:
                os.unlink(_FILE_NAME, dir_fd=self._db_fd)
                self._file_created = False
            if self._db_created:
                self._check_directory(self._db_fd, self._root_fd, _DB_NAME, self._db_info, 2)
                if os.listdir(self._db_fd):
                    raise FixtureError("fixture_changed")
                os.rmdir(_DB_NAME, dir_fd=self._root_fd)
                self._db_created = False
            self._check_directory(self._root_fd, self._parent_fd, _ROOT_NAME, self._root_info, 2)
            if os.listdir(self._root_fd):
                raise FixtureError("fixture_changed")
            self._verify_namespace()
            os.rmdir(_ROOT_NAME, dir_fd=self._parent_fd)
            self._root_created = False
        except (OSError, FixtureError, ValueError, TypeError):
            self.abandon()
            raise FixtureError("fixture_cleanup_failed") from None

    def _close_fds(self) -> None:
        failed = False
        for name in ("_file_fd", "_db_fd", "_root_fd", "_parent_fd", "_namespace_fd"):
            fd = getattr(self, name)
            if fd is not None:
                # Do not retry close after an uncertain result: that descriptor
                # number may already be available for reuse. Still close others.
                setattr(self, name, None)
                try:
                    os.close(fd)
                except OSError:
                    failed = True
        self._closed = True
        if failed:
            raise FixtureError("fixture_cleanup_failed")

    def __exit__(self, error_type, error, traceback):
        if isinstance(error, FixtureError) and not error.cleanup_safe:
            self.abandon()
        try:
            if error is None and (self._abandoned or self._child_active):
                raise FixtureError("fixture_cleanup_failed", cleanup_safe=False)
            self._cleanup()
        finally:
            self._close_fds()
        return False


def _peek_exit(pid: int):
    """Observe without reaping, retaining PID/process-group ownership."""
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)


def _group_quiet(pid: int, deadline: float) -> bool:
    """No live session/group members; checked BEFORE direct-child reap.

    Zombies cannot access files. Audited children may not detach their session;
    an unexpected live separate group within the session is also not quiet.
    """
    with os.scandir("/proc") as entries:
        for index, entry in enumerate(entries):
            if index >= _MAX_PROC_ENTRIES or time.monotonic() >= deadline:
                raise OSError("process census bound")
            if not entry.name.isascii() or not entry.name.isdigit():
                continue
            try:
                with open(entry.path + "/stat", "rb") as stream:
                    raw = stream.read(8193)
            except FileNotFoundError:
                continue
            except ProcessLookupError:
                # A proc entry can disappear after open but before read. This
                # pass is NOT proof of quiet: retry the complete census within
                # the existing shutdown deadline, without signaling again.
                return False
            if len(raw) > 8192 or b") " not in raw:
                raise OSError("process census invalid")
            fields = raw[raw.rfind(b") ") + 2:].split()
            if len(fields) < 4 or len(fields[0]) != 1:
                raise OSError("process census invalid")
            group, session = int(fields[2]), int(fields[3])
            if (group == pid or session == pid) and fields[0] not in (b"Z", b"X", b"x"):
                return False
    return True


def _shutdown_child(process, deadline: float) -> tuple[int | None, bool]:
    """One group kill while owned, bounded quiet check, then nonblocking reap.

    There is never a signal after waitpid consumes the child. In particular, no
    Popen context manager, poll(), wait(), communicate() or unbounded final wait.
    A failed quiet/reap check is explicitly unsafe for fixture cleanup.
    """
    try:
        _peek_exit(process.pid)  # ECHILD means ownership was lost: do not signal.
    except (OSError, ChildProcessError, KeyboardInterrupt, SystemExit):
        return None, False
    signaled = True
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except (OSError, KeyboardInterrupt, SystemExit):
        signaled = False
    quiet = False
    try:
        while time.monotonic() < deadline:
            exited = _peek_exit(process.pid)
            if exited is not None and _group_quiet(process.pid, deadline):
                quiet = True
                break
            time.sleep(min(_POLL_SECONDS, max(0, deadline - time.monotonic())))
    except (OSError, ChildProcessError, ValueError, KeyboardInterrupt, SystemExit):
        quiet = False
    # Even on a failed census, attempt a bounded reap. Nothing signals afterward.
    while True:
        try:
            pid, status = os.waitpid(process.pid, os.WNOHANG)
        except (OSError, ChildProcessError, KeyboardInterrupt, SystemExit):
            return None, False
        if pid == process.pid:
            code = os.waitstatus_to_exitcode(status)
            process.returncode = code
            return code, signaled and quiet
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, False
        time.sleep(min(_POLL_SECONDS, remaining))


def bounded_child(args, cwd, *, env, seconds, stdout_limit, stderr_limit):
    """Run only an audited Linux child with supplied, caller-sanitized environment.

    Execution is at most ten seconds and 1 MiB/64 KiB output. Shutdown gets a
    separate one-second cap; a non-reapable child reports cleanup_safe=False.
    These are userspace deadlines, not guarantees against a stalled kernel call.
    """
    _linux_required()
    if (type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 10
            or type(stdout_limit) is not int or not 0 <= stdout_limit <= 1_048_576
            or type(stderr_limit) is not int or not 0 <= stderr_limit <= 65_536
            or type(env) is not dict or any(type(k) is not str or type(v) is not str for k, v in env.items())
            or type(args) not in (list, tuple) or not args or any(type(arg) is not str for arg in args)
            or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL):
        raise FixtureError("interpreter_configuration_invalid")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    deadline = time.monotonic() + seconds
    try:
        process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, close_fds=True)
    except (OSError, ValueError):
        raise FixtureError("interpreter_unavailable") from None
    selector = None
    failure = None
    safe = False
    code = None

    def read_ready(until):
        for key, _ in selector.select(min(_POLL_SECONDS, max(0, until - time.monotonic()))):
            remaining = limits[key.data] - len(buffers[key.data])
            try:
                chunk = os.read(key.fd, min(4096, remaining + 1))
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            buffers[key.data].extend(chunk)
            if len(buffers[key.data]) > limits[key.data]:
                raise FixtureError("interpreter_output_limit")

    try:
        selector = selectors.DefaultSelector()
        for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while _peek_exit(process.pid) is None:
            if time.monotonic() >= deadline:
                raise FixtureError("interpreter_timeout")
            if selector.get_map():
                read_ready(deadline)
            else:
                time.sleep(min(_POLL_SECONDS, max(0, deadline - time.monotonic())))
    except BaseException as error:
        failure = error
    finally:
        shutdown_deadline = time.monotonic() + _SHUTDOWN_SECONDS
        try:
            code, safe = _shutdown_child(process, shutdown_deadline)
            if safe and failure is None:
                while selector.get_map():
                    if time.monotonic() >= shutdown_deadline:
                        safe = False
                        break
                    read_ready(shutdown_deadline)
        except FixtureError as error:
            failure = error
        except BaseException as error:
            safe = False
            if failure is None:
                failure = error
        finally:
            for resource in (selector, process.stdout, process.stderr):
                if resource is not None:
                    try:
                        resource.close()
                    except OSError:
                        if failure is None:
                            failure = FixtureError("interpreter_unavailable")
    if not safe:
        raise FixtureError("interpreter_cleanup_uncertain", cleanup_safe=False) from None
    if failure is not None:
        if isinstance(failure, FixtureError):
            raise failure
        if isinstance(failure, (OSError, ValueError)):
            raise FixtureError("interpreter_unavailable") from None
        raise failure
    return code, bytes(buffers["stdout"]), bytes(buffers["stderr"])
