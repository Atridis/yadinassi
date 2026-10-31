"""Optional, immutable file-database location, not a database session.

Construction only normalizes path spelling. Every executed database-dependent
call performs a bounded, read-only inspection. Metadata reads require a caller-
owned consistent offline copy; unchanged file metadata cannot prove live-read
safety. A recognized header does not establish database validity or authentication.
"""

from dataclasses import dataclass, field
import ntpath
import os
import posixpath
import stat

from .storage.filedb import InspectionStatus, inspect_header


def _unsupported_directory(directory: str) -> bool:
    return (directory.startswith(("\\\\", "//")) or
            any(character in '\";' or ord(character) < 32 or
                127 <= ord(character) <= 159 or 0xD800 <= ord(character) <= 0xDFFF
                for character in directory))


def _normalize_directory(directory: str, cwd: str, *, windows: bool) -> tuple[str, bool]:
    """Pure native-host spelling rules; ntpath can be tested on any test host."""
    drive, tail = ntpath.splitdrive(directory)
    windows_absolute = bool(drive) and tail.startswith(("\\", "/"))
    unsupported = (_unsupported_directory(directory) or
                   (windows and bool(drive) and not windows_absolute) or
                   (not windows and windows_absolute))
    path = ntpath if windows else posixpath
    normalized = path.normpath(path.join(cwd, directory))
    return normalized, unsupported or _unsupported_directory(normalized)


def require_database_context() -> str:
    """Use the normal host-call error wrapper, including BSL Try/Except."""
    raise ValueError("db required for further code execution")


@dataclass(frozen=True, slots=True)
class FileDBContext:
    """Lexically absolute directory anchored to the construction-time cwd.

    Native host paths are supported, including drive-absolute paths on Windows.
    Windows drive-relative paths and execution of Windows absolute paths on a
    POSIX host are unsupported, rather than consulting another drive or opening
    an accidentally relative filename containing backslashes.
    No existence check, symlink resolution, descriptor, user or session is kept.
    Unsupported spelling is rejected lazily, only by an executed database operation.
    """

    directory: str | os.PathLike[str]
    _unsupported: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        raw = os.fspath(self.directory)
        if not isinstance(raw, str):
            raise TypeError("file database directory must be a string path")
        windows = os.name == "nt"
        absolute = os.path.isabs(raw) and (not windows or bool(ntpath.splitdrive(raw)[0]))
        directory, unsupported = _normalize_directory(raw, "" if absolute else os.getcwd(),
                                                       windows=windows)
        object.__setattr__(self, "directory", directory)
        object.__setattr__(self, "_unsupported", unsupported)

    def connection_string(self) -> str:
        """Inspect 1Cv8.1CD now, then describe its directory using File syntax.

        The trailing semicolon matches the captured Linux zero-argument result.
        Windows path serialization uses documented connection-string syntax,
        not a claim of separately measured Windows return-value parity.
        """
        if self._unsupported:
            raise ValueError("unsupported file database directory")
        result = inspect_header(os.path.join(self.directory, "1Cv8.1CD"))
        if result.status is not InspectionStatus.HEADER_LAYOUT_MATCH:
            detail = result.status.value
            if result.reason is not None:
                detail += ": " + result.reason.value
            raise ValueError("file database header inspection failed: " + detail)
        return f'File="{self.directory}";'

    def catalog_metadata(self):
        """Read Catalog identities from one bounded offline CONFIG descriptor.

        This creates no native session, lock or snapshot. The caller must supply
        a consistent offline copy. Before/after descriptor metadata checks catch
        some concurrent changes, not all; the descriptor is closed on every path.
        """
        from .storage.catalog_metadata import read_catalog_metadata
        from .storage.filedb_catalog import CatalogError, ChangedDuringRead, NotRegularFile, _metadata
        if self._unsupported:
            raise ValueError("unsupported file database directory")
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(os.path.join(self.directory, "1Cv8.1CD"), flags)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode):
                    raise NotRegularFile("not_regular_file")

                def read_at(offset, length):
                    # The coordinator's source wrapper validates and budgets all
                    # ranges. This private descriptor has no shared seek cursor.
                    if hasattr(os, "pread"):
                        return os.pread(fd, length, offset)
                    os.lseek(fd, offset, os.SEEK_SET)
                    return os.read(fd, length)

                try:
                    result = read_catalog_metadata(read_at, before.st_size)
                finally:
                    if _metadata(before) != _metadata(os.fstat(fd)):
                        raise ChangedDuringRead("source_changed")
            finally:
                os.close(fd)
        except CatalogError as error:
            raise ValueError("file database metadata inspection failed: " + error.code) from None
        except OSError:
            raise ValueError("file database metadata inspection failed: file_io_failed") from None
        return result
