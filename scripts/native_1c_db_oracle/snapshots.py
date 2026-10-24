"""Bounded physical evidence for disposable, synthetic file infobases.

This is deliberately not a 1CD/CF/DT parser. Every header is unknown; fixed
64-KiB *byte windows* are not database pages, and differences imply no cause.
The controller owns process supervision: matching hashes cannot establish
quiescence. Frozen copies must never be passed to a native platform process.

A failure may include one explicitly enabled, bounded ASCII root basename;
no failure exposes an OS error, path, or file bytes.
A failed copy may leave its newly created destination for controller cleanup;
it is never returned as verified, and a retry cannot overwrite it.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Callable, Iterator

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_LIVE_BYTES = 512 * 1024 * 1024
WINDOW_BYTES = 64 * 1024
MAX_SAMPLES = 16
MAX_TREE_ENTRIES = 4096
MAX_TREE_DEPTH = 16
DATABASE_NAME = "1Cv8.1CD"
# Official event-log location, not permission to parse or export its contents:
# https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Administration/DBMS/Data_structure_in_1C_Enterprise_8/?language=en
ANCILLARY_NAME = "1Cv8Log"
# Exact, case-sensitive source-only metadata exceptions. These files are never
# read, copied, or exported, and their presence is not proof of quiescence.
_CFL_CLASSES = {
    "1Cv8.1CD.cfl": "cfl_database",
    "1Cv8tmp.1CD.cfl": "cfl_temp_database",
    "1Cv8.1CL.cfl": "cfl_lock",
    "1Cv8tmp.1CL.cfl": "cfl_temp_lock",
}
_DIAGNOSTIC_BASENAME = re.compile(r"^1Cv8[A-Za-z0-9_.-]{0,48}$", re.ASCII)
ENTRY_CLASSES = (
    "database", "cfl_database", "cfl_temp_database", "cfl_lock", "cfl_temp_lock",
    "base_1cl", "temp_1cd", "temp_1cl", "session_history", "event_log", "other",
)
ENTRY_SHAPES = (
    "owned_regular_zero", "owned_regular_nonzero", "unowned_regular_zero",
    "unowned_regular_nonzero", "symlink", "hardlink", "link_count", "directory",
    "special", "invalid_size",
)
MAX_ANCILLARY_BYTES = 16 * 1024 * 1024
MAX_ANCILLARY_FILES = 64
MAX_ANCILLARY_ENTRIES = 128  # Also bound empty directories and inventory memory.
MAX_ANCILLARY_DEPTH = 2  # Log root is depth zero; no deeper descendants.
FAILURE_KINDS = frozenset({
    "invalid_input", "provenance_mismatch", "permission_mismatch",
    "unsupported_platform_command", "process_failed", "timeout",
    "invalid_dump_result", "stale_evidence", "artifact_missing",
    "artifact_limit", "invalid_marker", "logical_mismatch",
    "snapshot_not_quiescent", "snapshot_changed", "invalid_header",
    "cleanup_unverified", "unexpected_failure", "transport_invalid",
    "metadata_rejected", "version_mismatch", "registry_credentials_missing",
    "container_unavailable",
})


class OracleError(Exception):
    """An allowlisted, transport-safe error; untrusted text is never retained."""

    def __init__(self, kind: str):
        if type(kind) is not str or kind not in FAILURE_KINDS:
            raise ValueError("invalid error kind")
        self.kind = kind
        super().__init__(kind)


class DatabaseEntryError(OracleError):
    """Fixed enums, optionally binding an owned empty entry's bounded basename."""

    def __init__(self, entry_class: str, shape: str, *, basename: str | None = None):
        if type(entry_class) is not str or entry_class not in ENTRY_CLASSES:
            raise ValueError("invalid entry class")
        if type(shape) is not str or shape not in ENTRY_SHAPES:
            raise ValueError("invalid entry shape")
        if basename is not None:
            if (not valid_diagnostic_basename(basename)
                    or shape != "owned_regular_zero"
                    or _entry_class(basename) != entry_class):
                raise ValueError("invalid entry basename")
            self.basename = basename
        self.entry_class = entry_class
        self.shape = shape
        super().__init__("invalid_input")


def _entry_class(name: str) -> str:
    if name == DATABASE_NAME:
        return "database"
    if name in _CFL_CLASSES:
        return _CFL_CLASSES[name]
    if name == "1Cv8.1CL":
        return "base_1cl"
    if name == "1Cv8tmp.1CD":
        return "temp_1cd"
    if name == "1Cv8tmp.1CL":
        return "temp_1cl"
    if name == "1Cv8snc.1CD":
        return "session_history"
    if name == ANCILLARY_NAME:
        return "event_log"
    return "other"


def valid_diagnostic_basename(value: object) -> bool:
    """Validate diagnostic text only, without accepting or accessing a file."""
    return type(value) is str and _DIAGNOSTIC_BASENAME.fullmatch(value) is not None


def diagnostic_entry_class(name: str) -> str:
    """Bind a validated diagnostic basename to its finite class, without I/O."""
    return _entry_class(name)


def _entry_shape(info: os.stat_result) -> str:
    if stat.S_ISLNK(info.st_mode):
        return "symlink"
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    if not stat.S_ISREG(info.st_mode):
        return "special"
    if info.st_nlink > 1:
        return "hardlink"
    if info.st_nlink != 1:
        return "link_count"
    if info.st_size < 0:
        return "invalid_size"
    owner = "owned" if (info.st_uid, info.st_gid) == (1000, 1000) else "unowned"
    return owner + ("_regular_zero" if info.st_size == 0 else "_regular_nonzero")


def _path(value: Path) -> Path:
    try:
        path = Path(value)
        if ".." in path.parts or "\0" in os.fspath(path):
            raise OracleError("invalid_input")
        os.fsencode(path)  # Reject paths this host cannot encode before any I/O.
        return Path(os.path.abspath(path))
    except (TypeError, ValueError, OSError):
        raise OracleError("invalid_input") from None


def _identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino)


def _signature(info: os.stat_result) -> tuple:
    # ctime also catches a same-size write whose mtime was deliberately restored.
    return (_identity(info), info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _regular(info: os.stat_result, *, entry_class: str | None = None) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        if entry_class is not None:
            raise DatabaseEntryError(entry_class, _entry_shape(info))
        raise OracleError("invalid_input")
    if info.st_size < 0 or info.st_size > MAX_FILE_BYTES:
        raise OracleError("artifact_limit")


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    """Walk every component with O_NOFOLLOW; never resolve a symlink ancestor."""
    path = _path(path)
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    except OSError:
        raise OracleError("invalid_input") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _check_directory(path: Path, descriptor: int) -> None:
    with _directory(path) as current:
        if _identity(os.fstat(current)) != _identity(os.fstat(descriptor)):
            raise OracleError("snapshot_changed")


@contextmanager
def _file(path: Path) -> Iterator[tuple[int, os.stat_result, int]]:
    path = _path(path)
    with _directory(path.parent) as parent:
        descriptor = None
        try:
            initial = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            _regular(initial)
            # NONBLOCK prevents a file-to-FIFO race from hanging before fstat.
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=parent)
            if _signature(os.fstat(descriptor)) != _signature(initial):
                raise OracleError("snapshot_changed")
            yield descriptor, initial, parent
        except FileNotFoundError:
            raise OracleError("artifact_missing") from None
        except OSError:
            raise OracleError("invalid_input") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)


def _unchanged(path: Path, descriptor: int, initial: os.stat_result, parent: int) -> None:
    try:
        latest = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (_signature(latest) != _signature(initial)
                or _signature(os.fstat(descriptor)) != _signature(initial)):
            raise OracleError("snapshot_changed")
        _check_directory(path.parent, parent)
    except OSError:
        raise OracleError("snapshot_changed") from None


def _digest(descriptor: int, size: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    count = 0
    while True:
        chunk = os.read(descriptor, WINDOW_BYTES)
        if not chunk:
            break
        count += len(chunk)
        if count > size or count > MAX_FILE_BYTES:
            raise OracleError("snapshot_changed")
        digest.update(chunk)
    if count != size:
        raise OracleError("snapshot_changed")
    return digest.hexdigest()


def _summary(size: int, digest: str) -> dict:
    return {"bytes": size, "sha256": digest, "header": "unknown",
            "page_analysis": "unsupported"}


def file_summary(path: Path) -> dict:
    """Hash a stable regular file without interpreting or returning any bytes."""
    path = _path(path)
    try:
        with _file(path) as (descriptor, initial, parent):
            digest = _digest(descriptor, initial.st_size)
            _unchanged(path, descriptor, initial, parent)
            # A second bounded pass rejects content changes even if metadata lies.
            if _digest(descriptor, initial.st_size) != digest:
                raise OracleError("snapshot_changed")
            _unchanged(path, descriptor, initial, parent)
            return _summary(initial.st_size, digest)
    except OSError:
        raise OracleError("snapshot_changed") from None


def budget_check(root: Path, additional: int = 0) -> int:
    """Count all regular files, including logs, with bounded tree traversal.

    Hard links, symlinks, special files, excessive tree size and excessive depth
    fail closed. Return current live bytes, not the reservation. The controller
    must serialize writers; a scan is not an allocation lock or filesystem quota.
    """
    if type(additional) is not int or not 0 <= additional <= MAX_LIVE_BYTES:
        raise OracleError("artifact_limit")
    root = _path(root)
    total = 0
    entries = 0

    def walk(descriptor: int, depth: int) -> None:
        nonlocal total, entries
        if depth > MAX_TREE_DEPTH:
            raise OracleError("artifact_limit")
        before = os.fstat(descriptor)
        with os.scandir(descriptor) as children:
            for entry in children:
                entries += 1
                if entries > MAX_TREE_ENTRIES:
                    raise OracleError("artifact_limit")
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=descriptor)
                    try:
                        if _identity(os.fstat(child)) != _identity(info):
                            raise OracleError("snapshot_changed")
                        walk(child, depth + 1)
                        if _identity(os.stat(entry.name, dir_fd=descriptor,
                                             follow_symlinks=False)) != _identity(info):
                            raise OracleError("snapshot_changed")
                    finally:
                        os.close(child)
                else:
                    _regular(info)
                    total += info.st_size
                    if total + additional > MAX_LIVE_BYTES:
                        raise OracleError("artifact_limit")
        after = os.fstat(descriptor)
        if (_identity(before), before.st_mtime_ns, before.st_ctime_ns) != (
                _identity(after), after.st_mtime_ns, after.st_ctime_ns):
            raise OracleError("snapshot_changed")

    try:
        with _directory(root) as descriptor:
            walk(descriptor, 0)
            _check_directory(root, descriptor)
        if total + additional > MAX_LIVE_BYTES:
            raise OracleError("artifact_limit")
        return total
    except OSError:
        raise OracleError("invalid_input") from None


def _database_contents(descriptor: int, *, allow_ancillary: bool = True,
                       capture_zero_name: bool = False) -> dict:
    """Private stable inventory; ancillary content and digests never escape.

    Only the optional event-log directory and four exact empty, single-link CFL
    files owned by uid/gid 1000 are tolerated in a live source. CFL content is
    never read; no ancillary entry is copied into a snapshot or clone.
    Presence/absence is not quiescence evidence.
    These stricter limits do not increase the raw-file or cumulative-live caps.
    Opted-in diagnostics can name only one rejected, owned empty root entry.
    """
    root_before = os.fstat(descriptor)
    inventory = {(): (_signature(root_before), None)}
    files = entries_count = total = 0

    def cfl(name: str, initial: os.stat_result) -> None:
        shape = _entry_shape(initial)
        if shape != "owned_regular_zero":
            raise DatabaseEntryError(_entry_class(name), shape)

        def signature(info: os.stat_result) -> tuple:
            # Ownership is deliberately checked in addition to the full file
            # signature, not inferred from ctime or the running user's uid.
            return _signature(info) + (info.st_uid, info.st_gid)

        expected = signature(initial)
        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=descriptor)
        try:
            if signature(os.fstat(child)) != expected:
                raise OracleError("snapshot_changed")
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (signature(current) != expected or
                    signature(os.fstat(child)) != expected):
                raise OracleError("snapshot_changed")
            inventory[(name,)] = (expected, None)
        finally:
            os.close(child)

    def walk(parent: int, name: str, relative: tuple, initial: os.stat_result,
             depth: int) -> None:
        nonlocal files, entries_count, total
        if depth > MAX_ANCILLARY_DEPTH:
            raise OracleError("artifact_limit")
        if not stat.S_ISDIR(initial.st_mode):
            raise OracleError("invalid_input")
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            if _signature(os.fstat(child)) != _signature(initial):
                raise OracleError("snapshot_changed")
            inventory[relative] = (_signature(initial), None)
            with os.scandir(child) as children:
                for entry in children:
                    entries_count += 1
                    if entries_count > MAX_ANCILLARY_ENTRIES:
                        raise OracleError("artifact_limit")
                    info = entry.stat(follow_symlinks=False)
                    key = relative + (entry.name,)
                    if stat.S_ISDIR(info.st_mode):
                        walk(child, entry.name, key, info, depth + 1)
                        continue
                    _regular(info)
                    files += 1
                    total += info.st_size
                    if files > MAX_ANCILLARY_FILES or total > MAX_ANCILLARY_BYTES:
                        raise OracleError("artifact_limit")
                    reader = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=child)
                    try:
                        if _signature(os.fstat(reader)) != _signature(info):
                            raise OracleError("snapshot_changed")
                        digest = _digest(reader, info.st_size)
                        current = os.stat(entry.name, dir_fd=child, follow_symlinks=False)
                        if (_signature(current) != _signature(info) or
                                _signature(os.fstat(reader)) != _signature(info)):
                            raise OracleError("snapshot_changed")
                        inventory[key] = (_signature(info), digest)
                    finally:
                        os.close(reader)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (_signature(current) != _signature(initial) or
                    _signature(os.fstat(child)) != _signature(initial)):
                raise OracleError("snapshot_changed")
        finally:
            os.close(child)

    database_seen = False
    with os.scandir(descriptor) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if entry.name == DATABASE_NAME:
                _regular(info, entry_class="database")
                database_seen = True
            elif entry.name == ANCILLARY_NAME and allow_ancillary:
                if not stat.S_ISDIR(info.st_mode):
                    raise DatabaseEntryError("event_log", _entry_shape(info))
                walk(descriptor, entry.name, (entry.name,), info, 0)
            elif entry.name in _CFL_CLASSES and allow_ancillary:
                cfl(entry.name, info)
            else:
                shape = _entry_shape(info)
                basename = (entry.name if capture_zero_name is True and allow_ancillary
                            and shape == "owned_regular_zero"
                            and valid_diagnostic_basename(entry.name) else None)
                raise DatabaseEntryError(_entry_class(entry.name), shape, basename=basename)
    if not database_seen:
        raise OracleError("invalid_input")
    if _signature(os.fstat(descriptor)) != _signature(root_before):
        raise OracleError("snapshot_changed")
    return inventory


def _quiescent(check: Callable[[], bool]) -> None:
    try:
        quiet = check()
    except Exception:
        raise OracleError("snapshot_not_quiescent") from None
    if quiet is not True:
        raise OracleError("snapshot_not_quiescent")


def _write_all(descriptor: int, chunk: bytes) -> None:
    view = memoryview(chunk)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OracleError("snapshot_changed")
        view = view[written:]


def _copy_database(source: Path, destination: Path, root: Path,
                   quiescent: Callable[[], bool] | None, *, frozen: bool,
                   capture_source_name: bool = False) -> dict:
    source_file = source / DATABASE_NAME
    with _directory(source) as source_dir, _directory(destination.parent) as dest_parent:
        source_inventory = _database_contents(source_dir, allow_ancillary=frozen,
                                              capture_zero_name=capture_source_name)
        with _file(source_file) as (reader, initial, source_parent):
            if not frozen and initial.st_mode & 0o222:
                raise OracleError("invalid_input")
            before_digest = _digest(reader, initial.st_size)
            _unchanged(source_file, reader, initial, source_parent)
            budget_check(root, initial.st_size)
            try:
                os.mkdir(destination.name, 0o700, dir_fd=dest_parent)
            except FileExistsError:
                raise OracleError("stale_evidence") from None
            dest_dir = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=dest_parent)
            try:
                writer = os.open(DATABASE_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | os.O_NOFOLLOW, 0o600, dir_fd=dest_dir)
                try:
                    copied = hashlib.sha256()
                    count = 0
                    os.lseek(reader, 0, os.SEEK_SET)
                    if quiescent is not None:
                        _quiescent(quiescent)
                    while True:
                        chunk = os.read(reader, WINDOW_BYTES)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > initial.st_size:
                            raise OracleError("snapshot_changed")
                        budget_check(root, len(chunk))
                        _write_all(writer, chunk)
                        copied.update(chunk)
                    os.fsync(writer)
                    if quiescent is not None:
                        _quiescent(quiescent)
                    if count != initial.st_size or copied.hexdigest() != before_digest:
                        raise OracleError("snapshot_changed")
                    _unchanged(source_file, reader, initial, source_parent)
                    if _digest(reader, initial.st_size) != before_digest:
                        raise OracleError("snapshot_changed")
                    _unchanged(source_file, reader, initial, source_parent)
                    if _database_contents(source_dir, allow_ancillary=frozen) != source_inventory:
                        raise OracleError("snapshot_changed")
                    _check_directory(source, source_dir)
                    if frozen:
                        os.fchmod(writer, 0o400)
                    written = os.fstat(writer)
                    _regular(written)
                    if written.st_size != initial.st_size:
                        raise OracleError("snapshot_changed")
                finally:
                    os.close(writer)
                # Read the actual destination, not just the stream sent to write().
                result = file_summary(destination / DATABASE_NAME)
                if result != _summary(initial.st_size, before_digest):
                    raise OracleError("snapshot_changed")
                actual = os.stat(DATABASE_NAME, dir_fd=dest_dir, follow_symlinks=False)
                if _signature(actual) != _signature(written):
                    raise OracleError("snapshot_changed")
                _database_contents(dest_dir, allow_ancillary=False)
                _check_directory(destination, dest_dir)
                if frozen:
                    os.fchmod(dest_dir, 0o500)
                budget_check(root)
                _unchanged(source_file, reader, initial, source_parent)
                if _database_contents(source_dir, allow_ancillary=frozen) != source_inventory:
                    raise OracleError("snapshot_changed")
                return result
            finally:
                os.close(dest_dir)


def freeze_database(source_dir: Path, dest_dir: Path, *,
                    quiescent: Callable[[], bool], capture_source_name: bool = False) -> dict:
    """Freeze a closed database; source and destination must be direct siblings.

    Their private parent is the live-byte budget root. ``quiescent`` must prove
    all owned native workers have exited, immediately before and after copy.
    A marker, unchanged mtime, or sleep is not an acceptable implementation.
    Optional basename diagnostics apply only to the first source inventory;
    they never authorize an otherwise rejected entry or inspect its content.
    """
    if type(capture_source_name) is not bool:
        raise OracleError("invalid_input")
    source, destination = _path(source_dir), _path(dest_dir)
    if source == destination or source.parent != destination.parent or not callable(quiescent):
        raise OracleError("invalid_input")
    try:
        return _copy_database(source, destination, source.parent, quiescent, frozen=True,
                              capture_source_name=capture_source_name)
    except OSError:
        raise OracleError("snapshot_changed") from None


def clone_database(frozen_dir: Path, dest_dir: Path, *, budget_root: Path) -> None:
    """Create a fresh writable native-use clone of an immutable frozen source."""
    source, destination, root = _path(frozen_dir), _path(dest_dir), _path(budget_root)
    if (source == destination or source == root or destination == root
            or root not in source.parents or root not in destination.parents
            or source in destination.parents or destination in source.parents):
        raise OracleError("invalid_input")
    try:
        _copy_database(source, destination, root, None, frozen=False, capture_source_name=False)
    except OSError:
        raise OracleError("snapshot_changed") from None


def _counters() -> dict:
    return dict(changed_bytes=0, unchanged_bytes=0, added_bytes=0,
                removed_bytes=0, size_delta=0, changed_windows=0)


def _count_bytes(before: bytes, after: bytes, counters: dict) -> bool:
    common = min(len(before), len(after))
    changed = sum(a != b for a, b in zip(before, after))
    counters["changed_bytes"] += changed
    counters["unchanged_bytes"] += common - changed
    counters["added_bytes"] += max(0, len(after) - len(before))
    counters["removed_bytes"] += max(0, len(before) - len(after))
    different = before != after
    counters["changed_windows"] += int(different)
    return different


def _windows(size: int) -> int:
    return (size + WINDOW_BYTES - 1) // WINDOW_BYTES


def compare_files(predecessor: Path, control: Path, treatment: Path) -> dict:
    """Compare stable files using bounded byte counters and sampled windows.

    Control and treatment each compare against the same predecessor. Overlap is
    descriptive only, never subtraction, row attribution, pages, or causation.
    """
    paths = [_path(path) for path in (predecessor, control, treatment)]
    try:
        with ExitStack() as stack:
            opened = [stack.enter_context(_file(path)) for path in paths]
            sizes = [initial.st_size for _, initial, _ in opened]
            if len({_identity(initial) for _, initial, _ in opened}) != 3:
                raise OracleError("invalid_input")
            control_count, treatment_count = _counters(), _counters()
            windows = {"window_bytes": WINDOW_BYTES, "count": _windows(max(sizes)),
                       "overlap_count": 0, "control_only_count": 0, "treatment_only_count": 0,
                       "overlap_sample": [], "control_only_sample": [], "treatment_only_sample": []}
            digests = [hashlib.sha256() for _ in paths]
            for index in range(windows["count"]):
                blocks = [os.read(descriptor, WINDOW_BYTES) for descriptor, _, _ in opened]
                for digest, block in zip(digests, blocks):
                    digest.update(block)
                control_changed = _count_bytes(blocks[0], blocks[1], control_count)
                treatment_changed = _count_bytes(blocks[0], blocks[2], treatment_count)
                category = ("overlap" if control_changed and treatment_changed else
                            "control_only" if control_changed else
                            "treatment_only" if treatment_changed else None)
                if category is not None:
                    windows[category + "_count"] += 1
                    if len(windows[category + "_sample"]) < MAX_SAMPLES:
                        windows[category + "_sample"].append(index)
            for path, (descriptor, initial, parent), digest in zip(paths, opened, digests):
                _unchanged(path, descriptor, initial, parent)
                if _digest(descriptor, initial.st_size) != digest.hexdigest():
                    raise OracleError("snapshot_changed")
                _unchanged(path, descriptor, initial, parent)
            control_count["size_delta"] = sizes[1] - sizes[0]
            treatment_count["size_delta"] = sizes[2] - sizes[0]
            result = dict(predecessor_bytes=sizes[0], control_bytes=sizes[1],
                          treatment_bytes=sizes[2], control=control_count,
                          treatment=treatment_count, byte_windows=windows,
                          interpretation="physical_byte_differences_not_causation")
            validate_comparison(result)
            return result
    except OSError:
        raise OracleError("snapshot_changed") from None


def validate_comparison(result: dict) -> None:
    """Reject unknown fields, bool-as-int, unbounded or inconsistent counters."""
    def require(condition: bool) -> None:
        if not condition:
            raise OracleError("invalid_input")

    def integer(value: object, maximum: int, minimum: int = 0) -> None:
        require(type(value) is int and minimum <= value <= maximum)

    require(type(result) is dict and set(result) == {
        "predecessor_bytes", "control_bytes", "treatment_bytes", "control",
        "treatment", "byte_windows", "interpretation"})
    require(result["interpretation"] == "physical_byte_differences_not_causation")
    for key in ("predecessor_bytes", "control_bytes", "treatment_bytes"):
        integer(result[key], MAX_FILE_BYTES)
    predecessor = result["predecessor_bytes"]
    counters_keys = set(_counters())
    branch_windows = {}
    for branch in ("control", "treatment"):
        counts, size = result[branch], result[branch + "_bytes"]
        require(type(counts) is dict and set(counts) == counters_keys)
        for key, value in counts.items():
            integer(value, MAX_FILE_BYTES, -MAX_FILE_BYTES if key == "size_delta" else 0)
        common = min(predecessor, size)
        require(counts["changed_bytes"] + counts["unchanged_bytes"] == common)
        require(counts["added_bytes"] == max(size - predecessor, 0))
        require(counts["removed_bytes"] == max(predecessor - size, 0))
        require(counts["size_delta"] == size - predecessor)
        changed = counts["changed_bytes"]
        branch_windows[branch] = _windows(max(predecessor, size))
        if predecessor != size:
            # Tail bytes necessarily touch this exact contiguous window range.
            # Only its first window can also contain common-prefix changes.
            tail_windows = branch_windows[branch] - common // WINDOW_BYTES
            overlap_capacity = common % WINDOW_BYTES
            minimum_windows = tail_windows + _windows(max(changed - overlap_capacity, 0))
            maximum_windows = tail_windows + min(changed, common // WINDOW_BYTES)
        else:
            minimum_windows = _windows(changed)
            maximum_windows = min(changed, branch_windows[branch])
        require(minimum_windows <= counts["changed_windows"] <= maximum_windows)
    windows = result["byte_windows"]
    require(type(windows) is dict and set(windows) == {
        "window_bytes", "count", "overlap_count", "control_only_count", "treatment_only_count",
        "overlap_sample", "control_only_sample", "treatment_only_sample"})
    integer(windows["window_bytes"], WINDOW_BYTES, WINDOW_BYTES)
    integer(windows["count"], _windows(MAX_FILE_BYTES))
    require(windows["count"] == _windows(max(result[key] for key in (
        "predecessor_bytes", "control_bytes", "treatment_bytes"))))
    seen = set()
    total = 0
    for category in ("overlap", "control_only", "treatment_only"):
        count, sample = windows[category + "_count"], windows[category + "_sample"]
        integer(count, windows["count"])
        total += count
        require(type(sample) is list and len(sample) == min(count, MAX_SAMPLES))
        limit = (min(branch_windows.values()) if category == "overlap" else
                 branch_windows[category.removesuffix("_only")])
        for index in sample:
            integer(index, limit - 1)
        require(sample == sorted(set(sample)) and not seen.intersection(sample))
        seen.update(sample)
    require(total <= windows["count"])
    require(windows["overlap_count"] + windows["control_only_count"] == result["control"]["changed_windows"])
    require(windows["overlap_count"] + windows["treatment_only_count"] == result["treatment"]["changed_windows"])


def compare_pair(predecessor: Path, treatment: Path) -> dict:
    """Bounded before/after observations without inventing a matched control.

    In particular, a supported native no-op is not assumed merely to populate
    comparison fields. These are physical observations, not causal attribution.
    """
    paths = [_path(path) for path in (predecessor, treatment)]
    try:
        with ExitStack() as stack:
            opened = [stack.enter_context(_file(path)) for path in paths]
            sizes = [initial.st_size for _, initial, _ in opened]
            if _identity(opened[0][1]) == _identity(opened[1][1]):
                raise OracleError("invalid_input")
            counters = _counters()
            windows = {"window_bytes": WINDOW_BYTES, "count": _windows(max(sizes)),
                       "changed_count": 0, "changed_sample": []}
            digests = [hashlib.sha256() for _ in paths]
            for index in range(windows["count"]):
                blocks = [os.read(descriptor, WINDOW_BYTES) for descriptor, _, _ in opened]
                for digest, block in zip(digests, blocks):
                    digest.update(block)
                if _count_bytes(blocks[0], blocks[1], counters):
                    windows["changed_count"] += 1
                    if len(windows["changed_sample"]) < MAX_SAMPLES:
                        windows["changed_sample"].append(index)
            for path, (descriptor, initial, parent), digest in zip(paths, opened, digests):
                _unchanged(path, descriptor, initial, parent)
                if _digest(descriptor, initial.st_size) != digest.hexdigest():
                    raise OracleError("snapshot_changed")
                _unchanged(path, descriptor, initial, parent)
            counters["size_delta"] = sizes[1] - sizes[0]
            result = {"predecessor_bytes": sizes[0], "treatment_bytes": sizes[1],
                      "treatment": counters, "byte_windows": windows,
                      "interpretation": "observational_before_after_not_causation"}
            validate_pair(result)
            return result
    except OSError:
        raise OracleError("snapshot_changed") from None


def validate_pair(result: dict) -> None:
    """Validate the exact observational schema with the shared counter algebra.

    A neutral comparison exists only inside this pure validator to reuse its
    size/window consistency checks. It is not measured or returned as evidence.
    """
    if (type(result) is not dict or set(result) != {
            "predecessor_bytes", "treatment_bytes", "treatment", "byte_windows",
            "interpretation"} or
            result["interpretation"] != "observational_before_after_not_causation"):
        raise OracleError("invalid_input")
    windows = result["byte_windows"]
    if type(windows) is not dict or set(windows) != {
            "window_bytes", "count", "changed_count", "changed_sample"}:
        raise OracleError("invalid_input")
    neutral = _counters()
    neutral["unchanged_bytes"] = result["predecessor_bytes"]
    validate_comparison({
        "predecessor_bytes": result["predecessor_bytes"],
        "control_bytes": result["predecessor_bytes"],
        "treatment_bytes": result["treatment_bytes"],
        "control": neutral,
        "treatment": result["treatment"],
        "byte_windows": {
            "window_bytes": windows["window_bytes"], "count": windows["count"],
            "overlap_count": 0, "control_only_count": 0,
            "treatment_only_count": windows["changed_count"],
            "overlap_sample": [], "control_only_sample": [],
            "treatment_only_sample": windows["changed_sample"],
        },
        "interpretation": "physical_byte_differences_not_causation",
    })
