"""Experimental single-part PARAMS/DBNames extraction, independently implemented.

One explicit, source-reviewed profile is a falsifiable layout hypothesis, not
native compatibility evidence. Only stdlib and the exact sibling catalog module
are imported. The borrowed source must be a caller-owned consistent offline copy.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import hashlib
import zlib

from .filedb_catalog import (BLOB_SIZE, CatalogLimits, CatalogReader, CatalogUsage,
                             InternalFile, InvalidStructure, PhysicalCatalog, ResourceLimit,
                             UnsupportedLayout, UnsupportedSharing,
                             _Budget)


@dataclass(frozen=True)
class _TransportLimits:
    """Finite policy ceilings, independent of shared cumulative catalog budgets."""

    max_packed_bytes: int = 1024 * 1024
    max_plain_bytes: int = 8 * 1024 * 1024
    max_blob_visits: int = 8192
    max_inflate_calls: int = 4096

    def __post_init__(self):
        ceilings = {"max_packed_bytes": 16 * 1024 * 1024,
                    "max_plain_bytes": 64 * 1024 * 1024,
                    "max_blob_visits": 131_072, "max_inflate_calls": 65_536}
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or not 1 <= value <= ceilings[item.name]:
                raise ValueError("invalid transport limit")


@dataclass(frozen=True)
class _TransportUsage:
    blob_bytes: int
    inflate_input_bytes: int
    plain_bytes: int
    blob_visits: int
    inflate_calls: int
    catalog: CatalogUsage


class _TransportBudget:
    def __init__(self, catalog: _Budget, limits: _TransportLimits | None = None):
        if type(catalog) is not _Budget:
            raise ValueError("transport requires the shared catalog budget")
        if limits is not None and type(limits) is not _TransportLimits:
            raise ValueError("limits must be transport limits")
        self.catalog = catalog
        self.limits = limits if limits is not None else _TransportLimits()
        self.counts = {"blob_bytes": 0, "inflate_input_bytes": 0, "plain_bytes": 0,
                       "blob_visits": 0, "inflate_calls": 0}

    def charge(self, name: str, amount: int):
        limit = "packed_bytes" if name in ("blob_bytes", "inflate_input_bytes") else name
        total = self.counts[name] + amount
        if total > getattr(self.limits, "max_" + limit):
            raise ResourceLimit("transport_" + name)
        self.counts[name] = total

    def usage(self) -> _TransportUsage:
        return _TransportUsage(**self.counts, catalog=self.catalog.usage())


class _TableBlobStore:
    """Exact-length chains in one selected table's own logical BLOB object.

    Logical owners are private to this store, not the root catalog store.
    Multiple logical blocks may legitimately share one mapped physical page.
    Failures consume budgets/ownership; callers must not retry this operation.
    """

    def __init__(self, blob: InternalFile, budget: _TransportBudget):
        from .filedb_catalog import _BindingFile
        if type(budget) is not _TransportBudget:
            raise ValueError("table BLOB and transport must share the catalog source")
        same_source = (blob._matches_blob_budget(budget.catalog) if type(blob) is _BindingFile else
                       type(blob) is InternalFile and blob._source.budget is budget.catalog
                       and blob._source.roles.get(blob.info.physical_header_page) == "table_blob_header")
        if not same_source:
            raise ValueError("table BLOB and transport must share the catalog source")
        if blob.info.logical_length % BLOB_SIZE:
            raise InvalidStructure("unaligned_blob_store")
        self.blob, self.budget = blob, budget
        self.block_count = blob.info.logical_length // BLOB_SIZE
        self.owners: set[int] = set()

    def chain(self, first: int, length: int) -> bytes:
        if type(first) is not int or type(length) is not int:
            raise ValueError("BLOB reference must contain exact integers")
        if not 1 <= first < self.block_count:
            raise InvalidStructure("blob_start_reference")
        if length <= 0:
            raise InvalidStructure("blob_declared_length")
        budget = self.budget
        budget.charge("blob_bytes", length)
        # Reserve assembly and its final immutable copy before either allocation.
        budget.catalog.charge("output_bytes", 2 * length)
        budget.catalog.charge("total_blob_bytes", length)
        budget.catalog.charge("bytes_processed", 2 * length)
        output = bytearray(length)
        current, written = first, 0
        visited: set[int] = set()
        while current:
            budget.charge("blob_visits", 1)
            budget.catalog.charge("blob_visits", 1)
            if not 1 <= current < self.block_count:
                raise InvalidStructure("blob_block_reference")
            if current in visited:
                raise InvalidStructure("blob_chain_cycle")
            if current in self.owners:
                raise UnsupportedSharing("logical_blob_chain_overlap")
            visited.add(current)
            self.owners.add(current)
            # _read_range has callback bytes, a bytearray and final bytes. The
            # two integer slices add six bytes. The payload copy is charged below.
            budget.catalog.charge("output_bytes", 3 * BLOB_SIZE + 6)
            block = self.blob._read_range(current * BLOB_SIZE, BLOB_SIZE)
            following = int.from_bytes(block[:4], "little")
            used = int.from_bytes(block[4:6], "little")
            if used > 250:
                raise InvalidStructure("blob_payload_length")
            if following and not 1 <= following < self.block_count:
                raise InvalidStructure("blob_next_reference")
            if used > length - written:
                raise InvalidStructure("blob_declared_length")
            budget.catalog.charge("output_bytes", used)
            budget.catalog.charge("bytes_processed", used)
            output[written:written + used] = block[6:6 + used]
            written += used
            if written == length and following:
                raise InvalidStructure("blob_declared_length")
            current = following
        if written != length:
            raise InvalidStructure("blob_declared_length")
        return bytes(output)


def _inflate_raw(packed: bytes, budget: _TransportBudget) -> bytes:
    """Decode exactly one raw DEFLATE stream with bounded calls and buffers.

    No flush, dictionary, wrapper fallback, concatenation, or recursive decode.
    Reservations are cumulative representation weights, not an exact native-zlib
    heap/time guarantee. The caller's isolated deadline remains the outer bound.
    """
    if type(packed) is not bytes or type(budget) is not _TransportBudget:
        raise ValueError("inflate requires exact bytes and the transport budget")
    if not packed:
        raise InvalidStructure("deflate_truncated")
    budget.charge("inflate_input_bytes", len(packed))
    decoder = zlib.decompressobj(wbits=-15)
    output = bytearray()
    cursor = 0
    pending = b""
    while True:
        budget.charge("inflate_calls", 1)
        if not pending and cursor < len(packed):
            amount = min(32768, len(packed) - cursor)
            budget.catalog.charge("output_bytes", amount)
            pending = packed[cursor:cursor + amount]
            cursor += amount
        remaining = budget.limits.max_plain_bytes - budget.counts["plain_bytes"]
        ceiling = min(65536, remaining + 1)
        # Reserve returned output, assembly copy, unconsumed_tail and unused_data
        # before zlib can allocate them. The one-byte overflow probe is included.
        budget.catalog.charge("output_bytes", 2 * ceiling + 2 * len(pending))
        budget.catalog.charge("bytes_processed", len(pending) + ceiling)
        try:
            chunk = decoder.decompress(pending, max_length=ceiling)
        except zlib.error:
            raise InvalidStructure("deflate_invalid") from None
        if len(chunk) > remaining:
            raise ResourceLimit("transport_plain_bytes")
        budget.charge("plain_bytes", len(chunk))
        output.extend(chunk)
        tail = decoder.unconsumed_tail
        if decoder.eof:
            if decoder.unused_data or tail or cursor != len(packed):
                raise InvalidStructure("deflate_trailing")
            budget.catalog.charge("output_bytes", len(output))
            budget.catalog.charge("bytes_processed", len(output))
            return bytes(output)
        if not chunk and len(tail) == len(pending):
            if not pending and cursor == len(packed):
                raise InvalidStructure("deflate_truncated")
            raise InvalidStructure("deflate_nonprogress")
        pending = tail


DBNAMES_DECLARATIONS = (
    ("FILENAME", "NVC", 0, 128, 0, "CI"),
    ("CREATION", "DT", 0, 0, 0, "CS"),
    ("MODIFIED", "DT", 0, 0, 0, "CS"),
    ("ATTRIBUTES", "N", 0, 5, 0, "CS"),
    ("DATASIZE", "N", 0, 20, 0, "CS"),
    ("BINARYDATA", "I", 0, 0, 0, "CS"),
    ("PARTNO", "N", 0, 10, 0, "CS"),
)


@dataclass(frozen=True)
class DBNamesProfile:
    """One explicitly admitted recipe; no inferred or native-supported default.

    All constructor inputs are required. Exact spelling and primitive types are
    significant. Status-first, declaration-order and no hidden version are the
    named hypothesis, not information measured from the table's row contents.
    """

    declarations: tuple[tuple[str, str, int, int, int, str], ...]
    recordlock: str
    format_item: int
    identifier: str = field(default="params_dbnames_8380_8192_v1", init=False)
    framing: str = field(default="status_then_declared_no_version_v1", init=False)
    record_size: int = field(init=False)
    placements: tuple[tuple[int, int], ...] = field(init=False)

    def __post_init__(self):
        if type(self.recordlock) is not str or self.recordlock != "0":
            raise ValueError("DBNames requires explicit recordlock zero")
        if type(self.format_item) is not int or self.format_item != 0:
            raise ValueError("DBNames requires explicit integer-zero format")
        if type(self.declarations) is not tuple or len(self.declarations) != 7:
            raise ValueError("invalid DBNames declaration vector")
        for declaration in self.declarations:
            if (type(declaration) is not tuple or len(declaration) != 6
                    or any(type(value) is not kind for value, kind in
                           zip(declaration, (str, str, int, int, int, str)))):
                raise ValueError("invalid DBNames declaration primitive")
        if self.declarations != DBNAMES_DECLARATIONS:
            raise ValueError("unsupported DBNames declarations")
        # Independently derived widths for this exact reviewed vector only.
        widths = (2 + 2 * 128, 7, 7, (5 + 2) // 2, (20 + 2) // 2, 8, (10 + 2) // 2)
        cursor, placements = 1, []
        for width in widths:
            placements.append((cursor, width))
            cursor += width
        object.__setattr__(self, "placements", tuple(placements))
        object.__setattr__(self, "record_size", cursor)


@dataclass(frozen=True)
class NamedFileLimits:
    """Finite extraction policy, also bounded by cumulative CatalogLimits."""

    max_slots: int = 4096
    max_record_bytes: int = 4096
    max_packed_bytes: int = 1024 * 1024
    max_plain_bytes: int = 8 * 1024 * 1024
    max_blob_visits: int = 8192
    max_inflate_calls: int = 4096

    def __post_init__(self):
        for name in ("max_slots", "max_record_bytes"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 65_536:
                raise ValueError("invalid named-file limit")
        self._transport_limits()

    def _transport_limits(self):
        return _TransportLimits(**{item.name: getattr(self, item.name)
                                   for item in fields(_TransportLimits)})


@dataclass(frozen=True)
class NamedFileUsage:
    slots: int
    blob_bytes: int
    inflate_input_bytes: int
    plain_bytes: int
    blob_visits: int
    inflate_calls: int
    catalog: CatalogUsage


@dataclass(frozen=True)
class NamedFileBytes:
    target: str
    profile_id: str
    data: bytes
    packed_bytes: int
    packed_sha256: str
    usage: NamedFileUsage
    capability: str = field(default="experimental_named_file_bytes", init=False)
    native_acceptance: str = field(default="pending", init=False)


def _ascii_equal(value: str, uppercase: str) -> bool:
    """Only fixed ASCII case equivalence; no Unicode/name normalization."""
    return len(value) == len(uppercase) and all(
        ord(actual) == ord(expected) or (97 <= ord(actual) <= 122 and ord(actual) - 32 == ord(expected))
        for actual, expected in zip(value, uppercase))


def _scalar(data: InternalFile, offset: int, length: int) -> bytes:
    data._validate_range(offset, length)
    # Callback bytes, logical bytearray and immutable copy, before allocation.
    data._source.budget.charge("output_bytes", 3 * length)
    data._source.budget.charge("bytes_processed", length)
    return data._read_range(offset, length)


def _filename(data: InternalFile, offset: int) -> str:
    units = int.from_bytes(_scalar(data, offset, 2), "little")
    if units > 128:
        raise InvalidStructure("dbnames_filename_length")
    data._source.budget.charge("output_bytes", 4 * units)
    raw = _scalar(data, offset + 2, 2 * units)
    try:
        return raw.decode("utf-16-le", errors="strict")
    except UnicodeDecodeError:
        raise UnsupportedLayout("dbnames_filename_encoding") from None


def _unsigned_decimal(raw: bytes, digits: int) -> int:
    # Only caller-selected N(20,0) and N(10,0): sign, digits, zero low padding.
    if raw[0] >> 4 != 1:
        raise UnsupportedLayout("dbnames_numeric_sign")
    if raw[-1] & 15:
        raise UnsupportedLayout("dbnames_numeric_padding")
    value = 0
    for position in range(1, digits + 1):
        byte = raw[position // 2]
        digit = (byte >> 4) if position % 2 == 0 else (byte & 15)
        if digit > 9:
            raise UnsupportedLayout("dbnames_numeric_digit")
        value = 10 * value + digit
    return value


def read_dbnames(read_at, file_size: int, *, profile: DBNamesProfile,
                 limits: NamedFileLimits | None = None,
                 catalog_limits: CatalogLimits | None = None) -> NamedFileBytes:
    """Extract exactly PARAMS/DBNames through one shared read-only budget graph.

    No callbacks are closed or written. No filename/layout fallback, metadata
    mapping, native execution, or consistency guarantee is supplied. Failures
    are all-or-nothing and contain only finite codes, never source values.
    """
    if type(profile) is not DBNamesProfile:
        raise ValueError("profile must be DBNamesProfile")
    if limits is not None and type(limits) is not NamedFileLimits:
        raise ValueError("limits must be NamedFileLimits")
    limits = limits if limits is not None else NamedFileLimits()
    if profile.record_size > limits.max_record_bytes:
        raise ResourceLimit("dbnames_record_bytes")
    reader = CatalogReader(read_at, file_size, limits=catalog_limits)
    catalog = reader.read_catalog()
    return _read_dbnames_from_catalog(reader, catalog, profile=profile, limits=limits)


def _read_dbnames_from_catalog(reader: CatalogReader, catalog: PhysicalCatalog, *,
                             profile: DBNamesProfile,
                             limits: NamedFileLimits | None = None,
                             _binding_handle=None) -> NamedFileBytes:
    if _binding_handle is None:
        return _read_dbnames_from_catalog_inner(reader, catalog, profile=profile, limits=limits)
    try:
        return _read_dbnames_from_catalog_inner(reader, catalog, profile=profile,
            limits=limits, _binding_handle=_binding_handle)
    except BaseException:
        from .filedb_catalog import _CatalogBindingGraph
        graph = getattr(reader, '_binding_graph', None) if type(reader) is CatalogReader else None
        if type(graph) is _CatalogBindingGraph:
            graph.failed = True
        raise


def _read_dbnames_from_catalog_inner(reader: CatalogReader, catalog: PhysicalCatalog, *,
                             profile: DBNamesProfile,
                             limits: NamedFileLimits | None = None,
                             _binding_handle=None) -> NamedFileBytes:
    """Private same-reader seam; one attempt consumes its extraction state.

    Only the identical completed catalog is admitted. All mapping, BLOB ownership
    and cumulative accounting stay on its originating reader. No caller values
    can replace a table, choose a filename or reset a failed reader's state.
    """
    if (type(reader) is not CatalogReader or type(catalog) is not PhysicalCatalog
            or reader._catalog is not catalog or not reader._used):
        raise ValueError("extraction requires the identical completed catalog")
    if _binding_handle is not None:
        from .filedb_catalog import _BindingHandle
        if (type(_binding_handle) is not _BindingHandle
                or _binding_handle._graph.reader is not reader
                or _binding_handle._graph.catalog is not catalog
                or _binding_handle.role != "params"):
            raise ValueError("DBNames requires its identical PARAMS binding handle")
        _binding_handle._check()
    if (getattr(reader, "_dbnames_attempted", False) or
            (_binding_handle is None and (reader._table_opened or reader._table_blob_opened))):
        raise ValueError("DBNames extraction is single-use")
    reader._dbnames_attempted = True
    if type(profile) is not DBNamesProfile:
        raise ValueError("profile must be DBNamesProfile")
    if limits is not None and type(limits) is not NamedFileLimits:
        raise ValueError("limits must be NamedFileLimits")
    limits = limits if limits is not None else NamedFileLimits()
    if profile.record_size > limits.max_record_bytes:
        raise ResourceLimit("dbnames_record_bytes")
    selected = None
    for table in catalog.tables:
        if _ascii_equal(table.name, "PARAMS"):
            if selected is not None:
                raise UnsupportedLayout("dbnames_table_ambiguous")
            selected = table
    if selected is None:
        raise UnsupportedLayout("dbnames_table_missing")
    if (type(selected.format_item) is not int or selected.format_item != profile.format_item
            or selected.recordlock != profile.recordlock
            or len(selected.fields) != len(profile.declarations)
            or any(item.raw != expected for item, expected in zip(selected.fields, profile.declarations))):
        raise UnsupportedLayout("dbnames_profile_mismatch")
    opener = reader if _binding_handle is None else _binding_handle
    data = opener._open_table_data(selected)
    if data.info.logical_length % profile.record_size:
        raise InvalidStructure("dbnames_record_length")
    slots = data.info.logical_length // profile.record_size
    if slots > limits.max_slots:
        raise ResourceLimit("dbnames_slots")
    selected_slot = None
    for slot in range(slots):
        base = slot * profile.record_size
        marker = _scalar(data, base, 1)
        if slot == 0:
            if marker != b"\x01":
                raise UnsupportedLayout("dbnames_reserved_slot")
            continue
        if marker != b"\x00":
            raise UnsupportedLayout("dbnames_nonreserved_slot")
        name = _filename(data, base + profile.placements[0][0])
        if _ascii_equal(name, "DBNAMES"):
            if selected_slot is not None:
                raise InvalidStructure("dbnames_duplicate")
            selected_slot = base
    if selected_slot is None:
        raise InvalidStructure("dbnames_not_found")
    # Decode transport fields only after the complete filename/framing scan.
    size_offset, size_width = profile.placements[4]
    size = _unsigned_decimal(_scalar(data, selected_slot + size_offset, size_width), 20)
    part_offset, part_width = profile.placements[6]
    part = _unsigned_decimal(_scalar(data, selected_slot + part_offset, part_width), 10)
    if part != 0:
        raise UnsupportedLayout("dbnames_part")
    if size == 0:
        raise InvalidStructure("dbnames_size")
    pointer_offset, pointer_width = profile.placements[5]
    reference = _scalar(data, selected_slot + pointer_offset, pointer_width)
    reader._budget.charge("output_bytes", 8)
    first = int.from_bytes(reference[:4], "little")
    length = int.from_bytes(reference[4:], "little")
    if not first or not length:
        raise InvalidStructure("dbnames_reference")
    if size != length:
        raise InvalidStructure("dbnames_size_mismatch")
    if length > limits.max_packed_bytes:
        raise ResourceLimit("transport_blob_bytes")
    blob = opener._open_table_blob(selected)
    budget = _TransportBudget(reader._budget, limits._transport_limits())
    packed = _TableBlobStore(blob, budget).chain(first, length)
    # Hashing reads the existing bytes; reserve its digest representation first.
    reader._budget.charge("bytes_processed", len(packed))
    reader._budget.charge("output_bytes", 96)
    packed_sha256 = hashlib.sha256(packed).hexdigest()
    plain = _inflate_raw(packed, budget)
    # Fixed identifiers and immutable result/usage representation weights.
    reader._budget.charge("output_bytes", 512)
    usage = NamedFileUsage(slots=slots, **budget.counts, catalog=reader.usage)
    return NamedFileBytes("PARAMS/DBNames", profile.identifier, plain, len(packed), packed_sha256, usage)
