"""Experimental, partial CONFIG/root reference-prefix projection.

This is not a document parser or evidence that a native file is valid. Only one
explicit conservative prefix profile is recognized. The remainder is neither
read nor UTF-8 validated, even when the prefix's final delimiter is ``}``.
No database, filesystem, expected reference, or native process is an input.
"""
from __future__ import annotations

from dataclasses import dataclass, field


PROFILE_IDENTIFIER = "config_root_bom_uint_bare_guid_prefix_v1"
_HYPHENS = (8, 13, 18, 23)


class RootProjectionError(Exception):
    """Finite diagnostic only; no source bytes or input-derived message."""

    codes = frozenset(("input_type", "profile_type", "profile", "limits_type",
                       "limit", "input_bytes", "prefix_bytes", "output_bytes",
                       "bom", "opening_brace", "header", "header_range",
                       "comma", "guid", "delimiter"))

    def __init__(self, code: str):
        if type(code) is not str or code not in self.codes:
            raise ValueError("invalid root projection diagnostic")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RootProjectionProfile:
    identifier: str

    def __post_init__(self):
        if type(self.identifier) is not str or self.identifier != PROFILE_IDENTIFIER:
            raise RootProjectionError("profile")


@dataclass(frozen=True, slots=True)
class RootProjectionLimits:
    """Lowerable local policy ceilings, not native format constraints."""

    max_input_bytes: int = 4 * 1024 * 1024
    max_prefix_bytes: int = 1024
    max_output_bytes: int = 2048

    def __post_init__(self):
        for name, ceiling in (("max_input_bytes", 4 * 1024 * 1024),
                              ("max_prefix_bytes", 1024),
                              ("max_output_bytes", 2048)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise RootProjectionError("limit")


@dataclass(frozen=True, slots=True)
class RootProjectionReservation:
    input_bytes: int
    prefix_byte_bound: int
    bytes_processed: int
    output_bytes: int


@dataclass(frozen=True, slots=True)
class RootReferencePrefixProjection:
    """A lexical prefix result, never a complete/accepted root document.

    Header is preserved without interpreting it as version, count, or validity.
    The GUID is an uninterpreted candidate reference, including the zero GUID.
    ``prefix_end`` is the first byte after the observed comma/closing brace.
    It is not a promise that another token or a complete object exists there.
    No input or suffix buffer is retained.
    """

    profile: str
    header_value: int
    raw_header: str
    reference: str
    raw_reference: str
    delimiter: str
    prefix_end: int
    input_bytes: int
    reservation: RootProjectionReservation
    capability: str = field(default="partial_root_reference_prefix", init=False)
    document_validation: str = field(default="not_performed", init=False)
    suffix_validation: str = field(default="not_performed", init=False)


def reserve_root_projection(data: bytes, *, profile: RootProjectionProfile,
                            limits: RootProjectionLimits) -> RootProjectionReservation:
    """O(1) reservation before any input-derived allocation or content scan.

    The caller owns the existing immutable input separately. Fixed 2048 output
    weight covers the result, reservation, cursor, bounded integers, 82 retained
    ASCII characters (two GUID spellings and header), and transient copies.
    Four prefix passes plus that weight conservatively cover byte recognition,
    spelling copies, normalization, and object construction. These are cumulative
    representation weights, not exact VM heap/time bounds. Shared-budget callers
    must charge them before parsing, without refund, for identical inputs.
    """
    if type(data) is not bytes:
        raise RootProjectionError("input_type")
    if type(profile) is not RootProjectionProfile:
        raise RootProjectionError("profile_type")
    if type(limits) is not RootProjectionLimits:
        raise RootProjectionError("limits_type")
    profile.__post_init__()
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise RootProjectionError("input_bytes")
    if limits.max_output_bytes < 2048:
        raise RootProjectionError("output_bytes")
    bound = min(len(data), limits.max_prefix_bytes)
    return RootProjectionReservation(len(data), bound, 4 * bound + 2048, 2048)


class _Cursor:
    __slots__ = ("data", "limit", "position")

    def __init__(self, data: bytes, limit: int):
        self.data, self.limit, self.position = data, limit, 0

    def peek(self):
        if self.position == len(self.data):
            return None
        if self.position >= self.limit:
            raise RootProjectionError("prefix_bytes")
        return self.data[self.position]

    def space(self):
        while self.peek() in (32, 9, 13, 10):
            self.position += 1

    def require(self, byte: int, code: str):
        if self.peek() != byte:
            raise RootProjectionError(code)
        self.position += 1


def project_root_reference_prefix(data: bytes, *, profile: RootProjectionProfile,
                                  limits: RootProjectionLimits) -> RootReferencePrefixProjection:
    """Recognize ``BOM WS { WS UINT WS , WS GUID WS (',' | '}')`` only.

    UINT is canonical unsigned decimal in signed-32-bit range; GUID has exactly
    the ordinary 8-4-4-4-12 bare hexadecimal spelling. Whitespace is ASCII space,
    tab, CR, or LF. No strings, escaped forms, nested values, alternate encodings,
    first-field semantics, suffix grammar, complete UTF-8, EOF, table lookup,
    native compatibility, or applied configuration state are established.
    """
    reservation = reserve_root_projection(data, profile=profile, limits=limits)
    cursor = _Cursor(data, limits.max_prefix_bytes)
    for byte in (0xEF, 0xBB, 0xBF):
        cursor.require(byte, "bom")
    cursor.space()
    cursor.require(123, "opening_brace")
    cursor.space()
    start = cursor.position
    value = 0
    while (byte := cursor.peek()) is not None and 48 <= byte <= 57:
        if cursor.position - start >= 10:
            raise RootProjectionError("header_range")
        value = value * 10 + byte - 48
        cursor.position += 1
    end = cursor.position
    if end == start or (end - start > 1 and data[start] == 48):
        raise RootProjectionError("header")
    if value > 2_147_483_647:
        raise RootProjectionError("header_range")
    cursor.space()
    cursor.require(44, "comma")
    cursor.space()
    guid_start = cursor.position
    for offset in range(36):
        byte = cursor.peek()
        if offset in _HYPHENS:
            valid = byte == 45
        else:
            valid = byte is not None and (48 <= byte <= 57 or 65 <= byte <= 70 or 97 <= byte <= 102)
        if not valid:
            raise RootProjectionError("guid")
        cursor.position += 1
    guid_end = cursor.position
    cursor.space()
    delimiter = cursor.peek()
    if delimiter not in (44, 125):
        raise RootProjectionError("delimiter")
    cursor.position += 1
    # All source-dependent allocations follow the fixed reservation and complete
    # prefix checks. Never inspect a byte after the delimiter, even for UTF-8.
    raw_guid = data[guid_start:guid_end].decode("ascii")
    return RootReferencePrefixProjection(
        profile.identifier, value, data[start:end].decode("ascii"),
        raw_guid.lower(), raw_guid, chr(delimiter), cursor.position, len(data),
        reservation,
    )
