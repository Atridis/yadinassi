"""Bounded physical catalog inspection of consistent, offline 1CD copies.

This independent standard-library module supports only storage 8.3.8.0 with
8192-byte pages. It is not a row reader, allocation validator, metadata mapper,
repair tool, or evidence of native 1C compatibility. The caller supplies a stable
copy; read-only access and unchanged file metadata cannot establish consistency.

Offsets and address units are documented in docs/file-db-physical-catalog-design.md.
The implementation is independent of the source readers discussed there. BLOB
IDs are logical 256-byte block indices in the root internal file, whereas Files
entries are physical header-page numbers. No referred table files are opened.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import os
import stat
from typing import Callable, Union


PAGE_SIZE = 8192
BLOB_SIZE = 256
_HEADER_POINTERS = (PAGE_SIZE - 24) // 4
_FAT_POINTERS = PAGE_SIZE // 4
_VERSION = (8, 3, 8, 0)
_SPACE = b" \t\r\n\v\f"
DescriptorValue = Union[str, int, tuple["DescriptorValue", ...]]


class CatalogError(Exception):
    """A finite diagnostic code, never source contents, paths or OS error text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class InvalidStructure(CatalogError):
    """A mandatory signature, range, exact-read or structural check failed."""


class UnsupportedLayout(CatalogError):
    """The layout or descriptor variant is outside the implemented subset."""


class ResourceLimit(CatalogError):
    """A configured budget was exhausted; this does not establish corruption."""


class UnsupportedSharing(CatalogError):
    """Conservative no-sharing policy, not proof of universal format invalidity."""


class SourceIOError(CatalogError):
    """Reading the source failed."""


class ChangedDuringRead(CatalogError):
    """Observed file metadata changed during the path-based inspection."""


class NotRegularFile(CatalogError):
    """The path does not refer to a regular offline file."""


@dataclass(frozen=True)
class CatalogLimits:
    """Independent cumulative budgets, with deliberately finite hard ceilings.

    Bytes processed conservatively charge reads, pointer decoding, BLOB payload
    assembly and descriptor scanning. Output bytes charge retained raw bytes,
    UTF-8 string bytes, 32 bytes per AST node and 128 per table/field. This is a
    representation weight, not a promise about Python's exact heap overhead;
    node, mapping and traversal limits independently bound that overhead.
    Page reads count page touches per read call, including repeated touches.
    """

    max_page_reads: int = 100_000
    max_read_bytes: int = 64 * 1024 * 1024
    max_bytes_processed: int = 128 * 1024 * 1024
    max_blob_visits: int = 100_000
    max_catalog_bytes: int = 1024 * 1024
    max_description_bytes: int = 1024 * 1024
    max_total_blob_bytes: int = 16 * 1024 * 1024
    max_tables: int = 4096
    max_fields: int = 65_536
    max_tokens: int = 262_144
    max_tree_depth: int = 64
    max_string_bytes: int = 65_536
    max_integer_digits: int = 20
    max_mapping_pages: int = 262_144
    max_output_bytes: int = 32 * 1024 * 1024

    def __post_init__(self):
        ceilings = {
            "max_page_reads": 1_000_000, "max_read_bytes": 512 * 1024 * 1024,
            "max_bytes_processed": 1024 * 1024 * 1024,
            "max_blob_visits": 1_000_000, "max_catalog_bytes": 16 * 1024 * 1024,
            "max_description_bytes": 16 * 1024 * 1024,
            "max_total_blob_bytes": 128 * 1024 * 1024,
            "max_tables": 65_536, "max_fields": 1_000_000,
            "max_tokens": 2_000_000, "max_tree_depth": 128,
            "max_string_bytes": 1024 * 1024, "max_integer_digits": 128,
            "max_mapping_pages": 1_000_000, "max_output_bytes": 256 * 1024 * 1024,
        }
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or not 1 <= value <= ceilings[field.name]:
                raise ValueError(f"invalid limit: {field.name}")


@dataclass(frozen=True)
class CatalogUsage:
    page_reads: int
    read_bytes: int
    bytes_processed: int
    blob_visits: int
    total_blob_bytes: int
    tables: int
    fields: int
    tokens: int
    output_bytes: int


@dataclass(frozen=True)
class CatalogHeader:
    version: tuple[int, int, int, int]
    page_size: int
    page_count: int
    file_size: int
    opaque_word: bytes


@dataclass(frozen=True)
class InternalFileInfo:
    physical_header_page: int
    fat_level: int
    version_words: tuple[int, int, int]
    logical_length: int
    data_page_count: int
    unused_header_pointers: bytes
    unused_fat_pointers: tuple[tuple[int, bytes], ...]


@dataclass(frozen=True)
class PhysicalField:
    name: str
    type_name: str
    null_marker: int
    declared_length: int
    precision: int
    case_marker: str
    raw: tuple[DescriptorValue, ...]


@dataclass(frozen=True)
class PhysicalTable:
    description_blob_id: int
    name: str
    format_item: DescriptorValue
    fields: tuple[PhysicalField, ...]
    raw_indexes: tuple[DescriptorValue, ...]
    recordlock: str
    files: tuple[int, int, int]
    descriptor: tuple[DescriptorValue, ...]
    raw_descriptor: bytes
    trailing_descriptor_bytes: bytes


@dataclass(frozen=True)
class PhysicalCatalog:
    header: CatalogHeader
    root: InternalFileInfo
    locale: str
    locale_bytes: bytes
    tables: tuple[PhysicalTable, ...]
    trailing_catalog_bytes: bytes
    usage: CatalogUsage
    capability: str = "physical_schema_read_only"


class _Budget:
    def __init__(self, limits: CatalogLimits):
        self.limits = limits
        self.counts = {field.name: 0 for field in fields(CatalogUsage)}

    def charge(self, name: str, amount: int):
        total = self.counts[name] + amount
        if total > getattr(self.limits, "max_" + name):
            raise ResourceLimit(name)
        self.counts[name] = total

    def usage(self) -> CatalogUsage:
        return CatalogUsage(**self.counts)


def _u32(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset:offset + 4], "little")


class _Source:
    def __init__(self, read_at: Callable[[int, int], bytes], size: int, budget: _Budget):
        self.callback, self.size, self.budget = read_at, size, budget
        self.page_count = 0
        self.mapping_pages = 0
        self.roles = {0: "file_header", 1: "free_header", 2: "root_header"}

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset > self.size or length > self.size - offset:
            raise InvalidStructure("physical_read_range")
        if not length:
            return b""
        touches = (offset % PAGE_SIZE + length + PAGE_SIZE - 1) // PAGE_SIZE
        self.budget.charge("page_reads", touches)
        self.budget.charge("read_bytes", length)
        self.budget.charge("bytes_processed", length)
        try:
            result = self.callback(offset, length)
        except OSError:
            raise SourceIOError("read_failed") from None
        if type(result) is not bytes:
            raise SourceIOError("read_result_type")
        if len(result) != length:
            raise InvalidStructure("inexact_read")
        return result

    def claim(self, page: int, role: str):
        if not 0 < page < self.page_count:
            raise InvalidStructure("physical_page_reference")
        if page in self.roles:
            raise UnsupportedSharing("physical_page_role_overlap")
        self.roles[page] = role


class InternalFile:
    """Validated internal-file range reader; retains no borrowed-source ownership.

    Constructed by CatalogReader. Public read_range calls consume the same
    cumulative budgets as catalog parsing, including their returned byte size.
    Logical page padding beyond logical_length is never exposed.
    """

    def __init__(self, source: _Source):
        self._initialize(source, 2, "root")

    @classmethod
    def _table_data(cls, source: _Source, header_page: int):
        if source.roles.get(header_page) != "table_data_header":
            raise InvalidStructure("table_data_header_role")
        result = cls.__new__(cls)
        result._initialize(source, header_page, "table_data")
        return result

    def _initialize(self, source: _Source, header_page: int, role: str):
        self._source = source
        budget = source.budget
        raw = source.read(header_page * PAGE_SIZE, PAGE_SIZE)
        if raw[:2] == b"\x1c\xff":
            raise UnsupportedLayout("free_object_header")
        if raw[:2] != b"\x1c\xfd":
            raise InvalidStructure("object_signature")
        level = int.from_bytes(raw[2:4], "little", signed=True)
        if level not in (0, 1):
            raise UnsupportedLayout("fat_level")
        length = int.from_bytes(raw[16:24], "little")
        count = (length + PAGE_SIZE - 1) // PAGE_SIZE
        capacity = _HEADER_POINTERS * (_FAT_POINTERS if level else 1)
        if count > capacity:
            raise InvalidStructure("internal_file_addressing_capacity")
        if source.mapping_pages + count > budget.limits.max_mapping_pages:
            raise ResourceLimit("mapping_pages")
        source.mapping_pages += count
        required = (count + _FAT_POINTERS - 1) // _FAT_POINTERS if level else count
        budget.charge("output_bytes", PAGE_SIZE - required * 4)
        unused_header = raw[24 + required * 4:]
        data_pages = []
        fat_padding = []
        # Claim every FAT role before data roles, including references in later
        # FAT pages. Required pointer arrays are counted, never sentinel-scanned.
        heads = []
        for index in range(required):
            budget.charge("bytes_processed", 4)
            page = _u32(raw, 24 + index * 4)
            source.claim(page, role + "_fat" if level else role + "_data")
            heads.append(page)
        if not level:
            data_pages = heads
        else:
            for page in heads:
                pointers = source.read(page * PAGE_SIZE, PAGE_SIZE)
                needed = min(_FAT_POINTERS, count - len(data_pages))
                for index in range(needed):
                    budget.charge("bytes_processed", 4)
                    target = _u32(pointers, index * 4)
                    source.claim(target, role + "_data")
                    data_pages.append(target)
                if needed < _FAT_POINTERS:
                    budget.charge("output_bytes", PAGE_SIZE - needed * 4 + 8)
                    fat_padding.append((page, pointers[needed * 4:]))
        self._pages = tuple(data_pages)
        self.info = InternalFileInfo(header_page, level, tuple(_u32(raw, n) for n in (4, 8, 12)),
                                     length, count, unused_header, tuple(fat_padding))

    def read_range(self, offset: int, length: int) -> bytes:
        """Read exactly a logical range, bounded before allocation or callback."""
        self._validate_range(offset, length)
        self._source.budget.charge("output_bytes", length)
        return self._read_range(offset, length)

    def _validate_range(self, offset: int, length: int):
        if type(offset) is not int or type(length) is not int:
            raise ValueError("logical offset and length must be exact integers")
        if offset < 0 or length < 0 or offset > self.info.logical_length or length > self.info.logical_length - offset:
            raise InvalidStructure("logical_read_range")

    def _read_range(self, offset: int, length: int) -> bytes:
        self._validate_range(offset, length)
        result = bytearray()
        while length:
            index, within = divmod(offset, PAGE_SIZE)
            amount = min(length, PAGE_SIZE - within)
            page = self._pages[index]
            result.extend(self._source.read(page * PAGE_SIZE + within, amount))
            offset += amount
            length -= amount
        return bytes(result)


class _BlobStore:
    def __init__(self, root: InternalFile):
        self.root = root
        self.budget = root._source.budget
        if root.info.logical_length % BLOB_SIZE:
            raise InvalidStructure("unaligned_blob_store")
        self.block_count = root.info.logical_length // BLOB_SIZE
        self.owners: dict[int, int] = {}

    def chain(self, first: int, limit: int) -> bytes:
        current = first
        visited: set[int] = set()
        output = bytearray()
        while current:
            self.budget.charge("blob_visits", 1)
            if not 1 <= current < self.block_count:
                raise InvalidStructure("blob_block_reference")
            if current in visited:
                raise InvalidStructure("blob_chain_cycle")
            if current in self.owners:
                raise UnsupportedSharing("logical_blob_chain_overlap")
            visited.add(current)
            self.owners[current] = first
            block = self.root._read_range(current * BLOB_SIZE, BLOB_SIZE)
            following = _u32(block, 0)
            used = int.from_bytes(block[4:6], "little")
            if used > 250:
                raise InvalidStructure("blob_payload_length")
            if following and not 1 <= following < self.block_count:
                raise InvalidStructure("blob_next_reference")
            if len(output) + used > limit:
                raise ResourceLimit("blob_chain_bytes")
            self.budget.charge("total_blob_bytes", used)
            self.budget.charge("bytes_processed", used)
            self.budget.charge("output_bytes", used)
            output.extend(block[6:6 + used])
            current = following
        if not first:
            raise InvalidStructure("blob_start_reference")
        return bytes(output)


class _Parser:
    """Finite braced-list subset with integers and UTF-8 quoted strings.

    Doubled quotes represent a quote; other backslashes are literal bytes.
    Ambiguous backslash-quote forms and C-style escapes are not supported.
    No broader platform serialization grammar is claimed.
    The suffix following the one complete root list is retained, not interpreted.
    """

    def __init__(self, raw: bytes, budget: _Budget):
        self.raw, self.budget, self.at = raw, budget, 0
        budget.charge("bytes_processed", 2 * len(raw))

    def _space(self):
        while self.at < len(self.raw) and self.raw[self.at] in _SPACE:
            self.at += 1

    def _token(self):
        self.budget.charge("tokens", 1)

    def value(self, depth: int = 0) -> DescriptorValue:
        self._space()
        if self.at == len(self.raw):
            raise InvalidStructure("descriptor_unexpected_end")
        self._token()
        self.budget.charge("output_bytes", 32)
        char = self.raw[self.at]
        if char == ord("{"):
            if depth >= self.budget.limits.max_tree_depth:
                raise ResourceLimit("tree_depth")
            self.at += 1
            values = []
            self._space()
            if self.at < len(self.raw) and self.raw[self.at] == ord("}"):
                self.at += 1
                self._token()
                return ()
            while True:
                values.append(self.value(depth + 1))
                self._space()
                if self.at == len(self.raw):
                    raise InvalidStructure("descriptor_unclosed_list")
                delimiter = self.raw[self.at]
                self.at += 1
                self._token()
                if delimiter == ord("}"):
                    return tuple(values)
                if delimiter != ord(","):
                    raise InvalidStructure("descriptor_delimiter")
        if char == ord('"'):
            self.at += 1
            value = bytearray()
            while self.at < len(self.raw):
                char = self.raw[self.at]
                self.at += 1
                if char == ord("\\") and self.at < len(self.raw) and self.raw[self.at] == ord('"'):
                    raise UnsupportedLayout("backslash_quote_escape")
                if char == ord('"'):
                    if self.at < len(self.raw) and self.raw[self.at] == ord('"'):
                        self.at += 1
                    else:
                        self.budget.charge("output_bytes", len(value))
                        try:
                            return value.decode("utf-8")
                        except UnicodeDecodeError:
                            raise InvalidStructure("descriptor_utf8") from None
                if len(value) >= self.budget.limits.max_string_bytes:
                    raise ResourceLimit("string_bytes")
                value.append(char)
            raise InvalidStructure("descriptor_unclosed_string")
        start = self.at
        if char in (ord("-"), ord("+")):
            self.at += 1
        digits = self.at
        while self.at < len(self.raw) and ord("0") <= self.raw[self.at] <= ord("9"):
            self.at += 1
            if self.at - digits > self.budget.limits.max_integer_digits:
                raise ResourceLimit("integer_digits")
        if self.at == digits:
            if char in b"},+-":
                raise InvalidStructure("descriptor_expected_value")
            raise UnsupportedLayout("descriptor_token")
        return int(self.raw[start:self.at])


def _tag(value: DescriptorValue, name: str) -> tuple[DescriptorValue, ...]:
    if not isinstance(value, tuple) or not value or value[0] != name:
        raise UnsupportedLayout("descriptor_section")
    return value


def _table(blob_id: int, raw: bytes, source: _Source) -> PhysicalTable:
    budget = source.budget
    parser = _Parser(raw, budget)
    tree = parser.value()
    if not isinstance(tree, tuple) or len(tree) != 6 or not isinstance(tree[0], str):
        raise UnsupportedLayout("descriptor_shape")
    declarations = _tag(tree[2], "Fields")
    indexes = _tag(tree[3], "Indexes")
    recordlock = _tag(tree[4], "Recordlock")
    files = _tag(tree[5], "Files")
    if len(recordlock) != 2 or not isinstance(recordlock[1], str):
        raise UnsupportedLayout("recordlock_shape")
    if len(files) != 4 or any(type(value) is not int for value in files[1:]):
        raise UnsupportedLayout("files_shape")
    for page, role in zip(files[1:], ("table_data_header", "table_blob_header", "table_index_header")):
        if page:
            source.claim(page, role)
    physical_fields = []
    for field in declarations[1:]:
        budget.charge("fields", 1)
        if not isinstance(field, tuple) or len(field) != 6:
            raise UnsupportedLayout("field_shape")
        expected = (str, str, int, int, int, str)
        if any(type(value) is not kind for value, kind in zip(field, expected)):
            raise UnsupportedLayout("field_attributes")
        budget.charge("output_bytes", 128)
        physical_fields.append(PhysicalField(*field, raw=field))
    budget.charge("output_bytes", 128 + len(raw) - parser.at)
    return PhysicalTable(blob_id, tree[0], tree[1], tuple(physical_fields), indexes,
                         recordlock[1], tuple(files[1:]), tree, raw, raw[parser.at:])


class CatalogReader:
    """One bounded inspection with a borrowed positioned read_at callback.

    read_at(offset, length) must return exact bytes of exactly length. It is
    never closed or given a seek/close request; any cursor changes are solely
    the callback's responsibility. A callback must not mutate the source or
    re-enter this reader. The source size must be verified by the caller.
    InternalFile.read_range may be used before the single read_catalog call;
    all work shares cumulative limits. Partial results are never returned.
    """

    def __init__(self, read_at: Callable[[int, int], bytes], file_size: int,
                 *, limits: CatalogLimits | None = None):
        if not callable(read_at):
            raise ValueError("read_at must be callable")
        if type(file_size) is not int or file_size < 0:
            raise ValueError("file_size must be a nonnegative exact integer")
        if limits is not None and type(limits) is not CatalogLimits:
            raise ValueError("limits must be CatalogLimits")
        self._budget = _Budget(limits if limits is not None else CatalogLimits())
        self._source = _Source(read_at, file_size, self._budget)
        raw = self._source.read(0, 24)
        if raw[:8] != b"1CDBMSV8":
            raise InvalidStructure("file_signature")
        version = tuple(raw[8:12])
        if version != _VERSION:
            raise UnsupportedLayout("storage_version")
        if _u32(raw, 20) != PAGE_SIZE:
            raise UnsupportedLayout("page_size")
        count = _u32(raw, 12)
        if file_size % PAGE_SIZE or count * PAGE_SIZE != file_size:
            raise InvalidStructure("file_geometry")
        if count < 3:
            raise InvalidStructure("missing_root_page")
        self._source.page_count = count
        self._budget.charge("output_bytes", 24)
        self.header = CatalogHeader(version, PAGE_SIZE, count, file_size, raw[16:20])
        self.root = InternalFile(self._source)
        self._used = False
        self._catalog = None
        self._table_opened = False

    @property
    def usage(self) -> CatalogUsage:
        return self._budget.usage()

    def read_catalog(self) -> PhysicalCatalog:
        """Return an immutable ordered physical schema, never rows or B-trees."""
        if self._used:
            raise ValueError("read_catalog is single-use")
        self._used = True
        store = _BlobStore(self.root)
        raw = store.chain(1, self._budget.limits.max_catalog_bytes)
        if len(raw) < 36:
            raise InvalidStructure("catalog_header_length")
        locale_end = raw.find(b"\0", 0, 32)
        if locale_end < 0:
            raise InvalidStructure("locale_terminator")
        try:
            locale = raw[:locale_end].decode("utf-8")
        except UnicodeDecodeError:
            raise InvalidStructure("locale_utf8") from None
        count = int.from_bytes(raw[32:36], "little", signed=True)
        if count < 0:
            raise InvalidStructure("negative_table_count")
        if count > (len(raw) - 36) // 4:
            raise InvalidStructure("catalog_table_array")
        self._budget.charge("tables", count)
        self._budget.charge("bytes_processed", 4 * count)
        self._budget.charge("output_bytes", len(raw) + locale_end)
        ids = tuple(_u32(raw, 36 + index * 4) for index in range(count))
        for blob_id in ids:
            if not 1 <= blob_id < store.block_count:
                raise InvalidStructure("description_blob_reference")
        if len(set(ids)) != len(ids):
            raise UnsupportedSharing("duplicate_description_id")
        tables = []
        for blob_id in ids:
            descriptor = store.chain(blob_id, self._budget.limits.max_description_bytes)
            tables.append(_table(blob_id, descriptor, self._source))
        result = PhysicalCatalog(self.header, self.root.info, locale, raw[:32], tuple(tables),
                                 raw[36 + count * 4:], self.usage)
        self._catalog = result
        return result

    def _open_table_data(self, table: PhysicalTable) -> InternalFile:
        """One identity-bound data header from this completed catalog only."""
        if self._catalog is None or not any(table is item for item in self._catalog.tables):
            raise ValueError("table must belong to this completed catalog")
        if self._table_opened:
            raise ValueError("table data opening is single-use")
        self._table_opened = True
        if not table.files[0]:
            raise UnsupportedLayout("missing_table_data_header")
        return InternalFile._table_data(self._source, table.files[0])


def read_catalog(read_at: Callable[[int, int], bytes], file_size: int,
                 *, limits: CatalogLimits | None = None) -> PhysicalCatalog:
    """Inspect a borrowed positioned source without importing runtime modules."""
    return CatalogReader(read_at, file_size, limits=limits).read_catalog()


def _metadata(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def inspect_catalog(path: str | bytes | os.PathLike, *, limits: CatalogLimits | None = None) -> PhysicalCatalog:
    """Own and close one rb descriptor for a trusted, consistent offline copy.

    Opens nonblocking where supported, rejects non-regular files, and checks
    metadata before returning. This detects some changes, not all concurrent
    writes. No native platform, lock, snapshot promise or write is involved.
    """
    if limits is not None and type(limits) is not CatalogLimits:
        raise ValueError("limits must be CatalogLimits")
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise NotRegularFile("not_regular_file")

            def positioned(offset: int, length: int) -> bytes:
                # This descriptor is private, so seek/read is safe on platforms
                # without pread. One exact read is required, not unbounded retries.
                if hasattr(os, "pread"):
                    return os.pread(fd, length, offset)
                os.lseek(fd, offset, os.SEEK_SET)
                return os.read(fd, length)

            try:
                result = read_catalog(positioned, before.st_size, limits=limits)
            finally:
                after = os.fstat(fd)
                if _metadata(before) != _metadata(after):
                    raise ChangedDuringRead("source_changed")
        finally:
            os.close(fd)
    except OSError:
        raise SourceIOError("file_io_failed") from None
    return result
