"""Bounded, read-only header inspection of caller-provided offline .1CD copies.

A matching header/layout is not validation of the database or a live-read safety
check. The caller must supply a consistent snapshot; metadata equality cannot
establish snapshot consistency. This module never reads tables or repairs files.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import stat


_UINT32_MAX = (1 << 32) - 1
_PAGE_SIZES = frozenset((4096, 8192, 16384, 32768, 65536))
_MAX_FILE_BYTES = _UINT32_MAX * 65536


class InspectionStatus(str, Enum):
    HEADER_LAYOUT_MATCH = "header_layout_match"
    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_LAYOUT = "invalid_layout"
    POLICY_LIMIT = "policy_limit"
    CHANGED_DURING_READ = "changed_during_read"
    NOT_REGULAR_FILE = "not_regular_file"
    IO_ERROR = "io_error"


class InspectionReason(str, Enum):
    TRUNCATED_HEADER = "truncated_header"
    BAD_MAGIC = "bad_magic"
    UNKNOWN_VERSION = "unknown_version"
    INVALID_PAGE_SIZE = "invalid_page_size"
    UNALIGNED_FILE = "unaligned_file"
    PAGE_COUNT_MISMATCH = "page_count_mismatch"
    MINIMUM_PAGES = "minimum_pages"
    MAXIMUM_PAGES = "maximum_pages"
    MAXIMUM_FILE_BYTES = "maximum_file_bytes"


@dataclass(frozen=True)
class FileDBHeader:
    """Supported header facts, not a database validity certificate."""

    version: tuple[int, int, int, int]
    page_size: int
    page_count: int
    file_size: int


@dataclass(frozen=True)
class HeaderInspection:
    """Finite diagnostics: no path, raw header, reserved bytes or OS exception."""

    status: InspectionStatus
    reason: InspectionReason | None = None
    header: FileDBHeader | None = None


def _metadata(info: os.stat_result) -> tuple[int, ...]:
    # Access time is intentionally excluded: our own read may update it.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _limit(value: int, name: str, ceiling: int) -> None:
    if type(value) is not int or not 1 <= value <= ceiling:
        raise ValueError(f"{name} must be an exact integer from 1 to {ceiling}")


def inspect_header(
    path: str | bytes | os.PathLike,
    *,
    max_pages: int = _UINT32_MAX,
    max_file_bytes: int = _MAX_FILE_BYTES,
) -> HeaderInspection:
    """Inspect one regular, consistent offline copy using at most 24 read bytes.

    Limits are exact integers (not bool) and bound accepted facts, not allocation:
    no memory or reads scale with page count. Invalid limits raise ValueError
    before opening. Filesystem failures return IO_ERROR without exception text.
    Paths are followed normally; callers must choose a trusted offline snapshot.
    Nonblocking open avoids waiting on FIFOs where the OS supports O_NONBLOCK.
    No lock, snapshot creation, writes, CLI or Interpreter integration is provided.
    """
    _limit(max_pages, "max_pages", _UINT32_MAX)
    _limit(max_file_bytes, "max_file_bytes", _MAX_FILE_BYTES)
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                return HeaderInspection(InspectionStatus.NOT_REGULAR_FILE)
            raw = b""
            while len(raw) < 24:
                chunk = os.read(fd, 24 - len(raw))
                if not chunk:
                    break
                raw += chunk
            after = os.fstat(fd)
        finally:
            os.close(fd)
    except OSError:
        return HeaderInspection(InspectionStatus.IO_ERROR)
    if _metadata(before) != _metadata(after):
        return HeaderInspection(InspectionStatus.CHANGED_DURING_READ)
    return decode_header(raw, after.st_size, max_pages=max_pages,
                         max_file_bytes=max_file_bytes)


def decode_header(
    raw: bytes,
    size: int,
    *,
    max_pages: int = _UINT32_MAX,
    max_file_bytes: int = _MAX_FILE_BYTES,
) -> HeaderInspection:
    """Decode at most 24 supplied bytes and a verified physical size, without I/O.

    Acquisition, identity and consistency remain the caller's responsibility.
    Exact bytes and a nonnegative exact integer size are required; invalid
    arguments raise ValueError. A matching geometry is not database validity.
    """
    _limit(max_pages, "max_pages", _UINT32_MAX)
    _limit(max_file_bytes, "max_file_bytes", _MAX_FILE_BYTES)
    if type(raw) is not bytes or len(raw) > 24:
        raise ValueError("raw must be exact bytes of length at most 24")
    if type(size) is not int or size < 0:
        raise ValueError("size must be a nonnegative exact integer")
    invalid = InspectionStatus.INVALID_LAYOUT
    policy = InspectionStatus.POLICY_LIMIT
    if len(raw) < 8:
        return HeaderInspection(invalid, InspectionReason.TRUNCATED_HEADER)
    if raw[:8] != b"1CDBMSV8":
        return HeaderInspection(invalid, InspectionReason.BAD_MAGIC)
    if len(raw) < 12:
        return HeaderInspection(invalid, InspectionReason.TRUNCATED_HEADER)
    version = tuple(raw[8:12])
    # Dispatch before interpreting any version-dependent fields or policy limits.
    if version not in ((8, 2, 14, 0), (8, 3, 8, 0)):
        return HeaderInspection(InspectionStatus.UNSUPPORTED_FORMAT,
                                InspectionReason.UNKNOWN_VERSION)
    minimum = 20 if version == (8, 2, 14, 0) else 24
    if len(raw) < minimum:
        return HeaderInspection(invalid, InspectionReason.TRUNCATED_HEADER)
    page_size = 4096 if minimum == 20 else int.from_bytes(raw[20:24], "little")
    if page_size not in _PAGE_SIZES:
        return HeaderInspection(invalid, InspectionReason.INVALID_PAGE_SIZE)
    count = int.from_bytes(raw[12:16], "little")
    if size % page_size:
        return HeaderInspection(invalid, InspectionReason.UNALIGNED_FILE)
    if count * page_size != size:
        return HeaderInspection(invalid, InspectionReason.PAGE_COUNT_MISMATCH)
    # Minimum three pages is a conservative acceptance policy, not a format proof.
    if count < 3:
        return HeaderInspection(policy, InspectionReason.MINIMUM_PAGES)
    if count > max_pages:
        return HeaderInspection(policy, InspectionReason.MAXIMUM_PAGES)
    if size > max_file_bytes:
        return HeaderInspection(policy, InspectionReason.MAXIMUM_FILE_BYTES)
    return HeaderInspection(InspectionStatus.HEADER_LAYOUT_MATCH,
                            header=FileDBHeader(version, page_size, count, size))
