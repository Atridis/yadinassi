"""One bounded, expectation-free DBNames text hypothesis.

This original standard-library implementation accepts only the explicitly named
UTF-8-BOM counted-triples profile. It is not a general 1C configuration parser,
an identity resolver, or evidence of native compatibility. The header is parsed
and retained but deliberately has no invented semantic meaning. Unknown kinds,
zero UUIDs and duplicate entries are preserved, in source order.

No filesystem, catalog, native process, fixture, or expected identity is an input.
The caller can reserve the conservative work/output weights in its own shared
budget before parsing. Those weights are not an exact interpreter-heap guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass


DBNAMES_PROFILE_IDENTIFIER = "dbnames_utf8bom_counted_triples_v1"
_BOM = b"\xef\xbb\xbf"
_SPACE = b" \t\r\n"
_BARE_DELIMITERS = b' \t\r\n,{}"'
_INTEGER_MAX = 2_147_483_647
_UUID_HYPHENS = (8, 13, 18, 23)
_LIMIT_CEILINGS = (
    ("max_input_bytes", 8 * 1024 * 1024),
    ("max_entries", 4096),
    ("max_tokens", 65536),
    ("max_depth", 4),
    ("max_scalar_bytes", 128),
    ("max_integer_digits", 10),
    ("max_output_bytes", 16 * 1024 * 1024),
)


class DBNamesParseError(Exception):
    """Only a finite diagnostic code; never source values or exception text."""

    codes: frozenset[str] = frozenset()

    def __init__(self, code: str):
        if type(code) is not str or code not in self.codes:
            raise ValueError("invalid DBNames diagnostic code")
        self.code = code
        super().__init__(code)


class InvalidDBNames(DBNamesParseError):
    """An API primitive or a mandatory encoding/grammar/range check failed."""

    codes = frozenset((
        "dbnames_input_type", "dbnames_profile_type", "dbnames_limits_type",
        "dbnames_limit", "dbnames_utf8_bom", "dbnames_utf8",
        "dbnames_grammar", "dbnames_integer", "dbnames_integer_range",
        "dbnames_uuid", "dbnames_kind", "dbnames_count_mismatch",
        "dbnames_trailing",
    ))


class UnsupportedDBNamesProfile(DBNamesParseError):
    """No profile/codec/layout guessing or fallback is performed."""

    codes = frozenset(("dbnames_profile",))


class DBNamesParseResourceLimit(DBNamesParseError):
    """A policy limit was exceeded; this alone does not establish corruption."""

    codes = frozenset((
        "dbnames_input_bytes", "dbnames_entries", "dbnames_tokens",
        "dbnames_depth", "dbnames_scalar_bytes", "dbnames_integer_digits",
        "dbnames_output_bytes",
    ))


@dataclass(frozen=True, slots=True)
class DBNamesParseProfile:
    """Explicit selection of one frozen recipe, not configurable grammar."""

    identifier: str

    def __post_init__(self):
        if (type(self.identifier) is not str
                or self.identifier != DBNAMES_PROFILE_IDENTIFIER):
            raise UnsupportedDBNamesProfile("dbnames_profile")


@dataclass(frozen=True, slots=True)
class DBNamesParseLimits:
    """Defaults are hard ceilings in v1; exact integers may only lower them.

    A zero entry ceiling is useful for accepting only an empty counted list.
    Other ceilings must be positive. Scalar bytes include kind quote delimiters;
    tokens include scalar and punctuation tokens but exclude whitespace/BOM.
    Depth counts the root, list and entry braces (three for nonempty input).
    Output bytes are conservative cumulative representation weights, including
    bounded transient scalar copies, rather than a native Python heap bound.
    """

    max_input_bytes: int = 8 * 1024 * 1024
    max_entries: int = 4096
    max_tokens: int = 65536
    max_depth: int = 4
    max_scalar_bytes: int = 128
    max_integer_digits: int = 10
    max_output_bytes: int = 16 * 1024 * 1024

    def __post_init__(self):
        for name, ceiling in _LIMIT_CEILINGS:
            value = getattr(self, name)
            floor = 0 if name == "max_entries" else 1
            if type(value) is not int or not floor <= value <= ceiling:
                raise InvalidDBNames("dbnames_limit")


@dataclass(frozen=True, slots=True)
class DBNamesParseReservation:
    """Weights to charge, without refund, before invoking ``parse_dbnames``."""

    input_bytes: int
    entry_bound: int
    bytes_processed: int
    output_bytes: int


@dataclass(frozen=True, slots=True)
class DBNamesParseUsage:
    """Observed counts plus the same conservative reserved byte weights."""

    input_bytes: int
    bytes_processed: int
    tokens: int
    depth: int
    entries: int
    output_bytes: int


@dataclass(frozen=True, slots=True)
class DBNamesEntry:
    """An uninterpreted ordered triple; ``raw_kind`` includes both quotes."""

    uuid: str
    raw_uuid: str
    kind: str
    raw_kind: str
    id: int
    raw_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class DBNamesIndex:
    """Complete immutable parse; no dictionary or first-match selection."""

    profile: str
    header_value: int
    raw_header: str
    declared_count: int
    raw_count: str
    entries: tuple[DBNamesEntry, ...]
    usage: DBNamesParseUsage


def reserve_dbnames_parse(data: bytes, *, profile: DBNamesParseProfile,
                          limits: DBNamesParseLimits) -> DBNamesParseReservation:
    """Return an O(1), no-input-scan reservation for this exact immutable input.

    A minimum-size encoding has 10 bytes outside its entries, including the BOM.
    Each entry and its preceding comma need at least 45 bytes: a 36-byte UUID,
    a one-letter quoted kind, one decimal digit, three commas and two braces.
    Therefore ``len(data) >= 10 + 45 * N`` for every accepted encoding; extra
    header/count digits and whitespace only increase its length. No successful
    or partially retained parse can exceed ``entry_bound``.
    Malformed declarations above that bound are rejected before entry allocation.

    We reserve 1024 fixed representation bytes and 1024 per possible entry.
    An entry has at most 148 retained ASCII string bytes (raw/canonical UUID,
    quoted/unquoted kind and ID), 256 object bytes, 128 integer/ordinal bytes,
    32 list/tuple slot bytes, and 256 transient scalar/copy bytes: 820 total.
    The remaining 204 bytes per entry and the fixed weight cover bookkeeping,
    list over-allocation, header/count strings, result/usage and scanner state.
    UTF-8 validation is bytewise and does not allocate a decoded copy or chunks.
    Eight input passes plus these object weights conservatively cover the UTF-8
    scan, token scan, bounded scalar checks, spelling copies and collection work.
    These are cumulative representation weights, not exact VM allocations/time.

    The parser never retains its input. Its caller separately owns/charges the
    supplied bytes. No fixed 16 MiB reservation or expectation-dependent count
    is used. The same input/profile/limits must be supplied to the actual parse.
    """
    if type(data) is not bytes:
        raise InvalidDBNames("dbnames_input_type")
    if type(profile) is not DBNamesParseProfile:
        raise InvalidDBNames("dbnames_profile_type")
    if type(limits) is not DBNamesParseLimits:
        raise InvalidDBNames("dbnames_limits_type")
    # Recheck the immutable selections rather than silently accepting an altered
    # object constructed outside normal dataclass initialization.
    profile.__post_init__()
    limits.__post_init__()
    length = len(data)
    if length > limits.max_input_bytes:
        raise DBNamesParseResourceLimit("dbnames_input_bytes")
    entry_bound = min(limits.max_entries, max(0, (length - 10) // 45))
    output_bytes = 1024 * (entry_bound + 1)
    if output_bytes > limits.max_output_bytes:
        raise DBNamesParseResourceLimit("dbnames_output_bytes")
    return DBNamesParseReservation(
        length, entry_bound, 8 * length + output_bytes, output_bytes,
    )


def _validate_utf8(data: bytes) -> None:
    """Incremental scalar-valid UTF-8 recognition with constant integer state."""
    remaining, low, high = 0, 0x80, 0xBF
    for byte in data:
        if remaining:
            if not low <= byte <= high:
                raise InvalidDBNames("dbnames_utf8")
            remaining -= 1
            low, high = 0x80, 0xBF
        elif byte < 0x80:
            continue
        elif 0xC2 <= byte <= 0xDF:
            remaining = 1
        elif 0xE0 <= byte <= 0xEF:
            remaining = 2
            low = 0xA0 if byte == 0xE0 else 0x80
            high = 0x9F if byte == 0xED else 0xBF
        elif 0xF0 <= byte <= 0xF4:
            remaining = 3
            low = 0x90 if byte == 0xF0 else 0x80
            high = 0x8F if byte == 0xF4 else 0xBF
        else:
            raise InvalidDBNames("dbnames_utf8")
    if remaining:
        raise InvalidDBNames("dbnames_utf8")


class _Cursor:
    """Nonrecursive ASCII grammar cursor; no token vector or general AST."""

    __slots__ = ("data", "limits", "position", "tokens", "depth", "peak_depth")

    def __init__(self, data: bytes, limits: DBNamesParseLimits):
        self.data, self.limits = data, limits
        self.position, self.tokens, self.depth, self.peak_depth = 3, 0, 0, 0

    def peek(self) -> int | None:
        while self.position < len(self.data) and self.data[self.position] in _SPACE:
            self.position += 1
        return self.data[self.position] if self.position < len(self.data) else None

    def token(self) -> None:
        if self.tokens >= self.limits.max_tokens:
            raise DBNamesParseResourceLimit("dbnames_tokens")
        self.tokens += 1

    def punctuation(self, wanted: int) -> None:
        if self.peek() != wanted:
            raise InvalidDBNames("dbnames_grammar")
        self.token()
        if wanted == 123:  # {
            if self.depth >= self.limits.max_depth:
                raise DBNamesParseResourceLimit("dbnames_depth")
            self.depth += 1
            self.peak_depth = max(self.peak_depth, self.depth)
        elif wanted == 125:  # }
            if not self.depth:
                raise InvalidDBNames("dbnames_grammar")
            self.depth -= 1
        self.position += 1

    def bare_span(self) -> tuple[int, int]:
        self.peek()
        self.token()
        start = self.position
        while (self.position < len(self.data)
               and self.data[self.position] not in _BARE_DELIMITERS):
            if self.position - start >= self.limits.max_scalar_bytes:
                raise DBNamesParseResourceLimit("dbnames_scalar_bytes")
            self.position += 1
        if self.position == start:
            raise InvalidDBNames("dbnames_grammar")
        return start, self.position

    def unsigned(self, *, count: bool = False) -> tuple[int, str]:
        start, end = self.bare_span()
        if end - start > self.limits.max_integer_digits:
            raise DBNamesParseResourceLimit("dbnames_integer_digits")
        if end - start > 1 and self.data[start] == 48:
            raise InvalidDBNames("dbnames_integer")
        value = 0
        for position in range(start, end):
            byte = self.data[position]
            if not 48 <= byte <= 57:
                raise InvalidDBNames("dbnames_integer")
            value = value * 10 + byte - 48
        if count:
            if value > self.limits.max_entries:
                raise DBNamesParseResourceLimit("dbnames_entries")
        elif value > _INTEGER_MAX:
            raise InvalidDBNames("dbnames_integer_range")
        return value, self.data[start:end].decode("ascii")

    def uuid(self) -> tuple[str, str]:
        start, end = self.bare_span()
        if end - start != 36:
            raise InvalidDBNames("dbnames_uuid")
        for offset in range(36):
            byte = self.data[start + offset]
            if offset in _UUID_HYPHENS:
                if byte != 45:
                    raise InvalidDBNames("dbnames_uuid")
            elif not (48 <= byte <= 57 or 65 <= byte <= 70 or 97 <= byte <= 102):
                raise InvalidDBNames("dbnames_uuid")
        raw = self.data[start:end].decode("ascii")
        return raw.lower(), raw

    def kind(self) -> tuple[str, str]:
        if self.peek() != 34:
            raise InvalidDBNames("dbnames_kind")
        self.token()
        start = self.position
        self.position += 1
        letters = 0
        while self.position < len(self.data):
            byte = self.data[self.position]
            if self.position - start + 1 > self.limits.max_scalar_bytes:
                raise DBNamesParseResourceLimit("dbnames_scalar_bytes")
            if byte == 34:
                if not letters:
                    raise InvalidDBNames("dbnames_kind")
                self.position += 1
                raw = self.data[start:self.position].decode("ascii")
                return raw[1:-1], raw
            if letters >= 32 or not (
                65 <= byte <= 90 or 97 <= byte <= 122
                or (letters > 0 and (48 <= byte <= 57 or byte == 95))
            ):
                raise InvalidDBNames("dbnames_kind")
            letters += 1
            self.position += 1
        raise InvalidDBNames("dbnames_kind")


def parse_dbnames(data: bytes, *, profile: DBNamesParseProfile,
                  limits: DBNamesParseLimits) -> DBNamesIndex:
    """Parse exactly ``BOM {H,{N,{UUID,\"Kind\",ID},...}}`` through EOF.

    ``H`` and ``ID`` are canonical unsigned signed-32-bit-range decimal text.
    ``N`` is the complete entry count, not a format version or expected value.
    No input-derived string or entry is allocated before resource reservation.
    """
    reservation = reserve_dbnames_parse(data, profile=profile, limits=limits)
    if not data.startswith(_BOM):
        raise InvalidDBNames("dbnames_utf8_bom")
    _validate_utf8(data)
    cursor = _Cursor(data, limits)
    cursor.punctuation(123)
    header, raw_header = cursor.unsigned()
    cursor.punctuation(44)
    cursor.punctuation(123)
    declared, raw_count = cursor.unsigned(count=True)
    if declared > reservation.entry_bound:
        raise InvalidDBNames("dbnames_count_mismatch")
    entries: list[DBNamesEntry] = []
    while cursor.peek() != 125:
        cursor.punctuation(44)
        # Charge/reserve before retaining an entry. Declared count and the
        # independent input-length bound are both already checked.
        if len(entries) >= declared:
            raise InvalidDBNames("dbnames_count_mismatch")
        cursor.punctuation(123)
        canonical_uuid, raw_uuid = cursor.uuid()
        cursor.punctuation(44)
        kind, raw_kind = cursor.kind()
        cursor.punctuation(44)
        identifier, raw_id = cursor.unsigned()
        cursor.punctuation(125)
        entries.append(DBNamesEntry(
            canonical_uuid, raw_uuid, kind, raw_kind,
            identifier, raw_id, len(entries),
        ))
    if len(entries) != declared:
        raise InvalidDBNames("dbnames_count_mismatch")
    cursor.punctuation(125)
    cursor.punctuation(125)
    if cursor.peek() is not None:
        raise InvalidDBNames("dbnames_trailing")
    usage = DBNamesParseUsage(
        reservation.input_bytes, reservation.bytes_processed, cursor.tokens,
        cursor.peak_depth, len(entries), reservation.output_bytes,
    )
    return DBNamesIndex(
        profile.identifier, header, raw_header, declared, raw_count,
        tuple(entries), usage,
    )
