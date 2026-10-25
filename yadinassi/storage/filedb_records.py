"""Experimental bounded physical rows, independently implemented with stdlib.

Only explicit source-reviewed profiles are accepted. A successful call is not
native compatibility evidence. Raw rows/fields are private caller-local data;
fixture reporting must project only an independently reviewed finite verdict.
See docs/file-db-experimental-records.md for facts versus pinned hypotheses.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Callable

from .filedb_catalog import (CatalogLimits, CatalogReader, CatalogUsage,
                             InternalFileInfo, InvalidStructure, PhysicalField,
                             PhysicalTable, ResourceLimit, UnsupportedLayout)


Declaration = tuple[str, str, int, int, int, str]


def _identifier(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 128:
        return False
    return (value[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
            and all(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789"
                    for char in value))


@dataclass(frozen=True)
class RecordLimits:
    """Finite policy budgets, not statements of native format support.

    One active row is a fixture admission rule: its caller must pass 1 explicitly.
    Higher caller limits have independent finite ceilings, not native coverage.
    CatalogLimits also bounds total reads, processing, mapping and retained data.
    """

    max_slots: int = 4096
    max_active_records: int = 4096
    max_record_bytes: int = 4096
    max_fields: int = 16

    def __post_init__(self):
        ceilings = {"max_slots": 65_536, "max_active_records": 65_536,
                    "max_record_bytes": 65_536, "max_fields": 256}
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or not 1 <= value <= ceilings[item.name]:
                raise ValueError("invalid record limit")


@dataclass(frozen=True)
class FieldPlacement:
    declaration: Declaration
    offset: int
    width: int


def _width(declaration: Declaration) -> int:
    _, kind, nullable, length, precision, case = declaration
    if nullable != 0:
        raise ValueError("nullable fields are unsupported")
    if case not in ("CS", "CI"):
        raise ValueError("unsupported case token")
    # Declaration lengths and storage widths are deliberately separate.
    if (kind, length, precision) == ("RV", 0, 0):
        return 16
    if (kind, length, precision) == ("L", 0, 0):
        return 1
    if (kind, length, precision) == ("B", 16, 0):
        return 16
    if kind == "NVC" and length in (2, 32) and precision == 0:
        return 2 + 2 * length
    if (kind, length, precision) == ("N", 9, 2):
        return 5
    raise ValueError("unsupported primitive declaration")


@dataclass(frozen=True)
class RecordProfile:
    """Explicit experimental recipe, with no native-supported default.

    All four inputs are required. The exact-int-zero format admission is a
    predeclared restriction with unknown semantics, never learned from a table.
    RV-first ordering, status/framing and codecs are pinned by this implementation
    version. There is no alternate-layout search or logical metadata mapping.
    """

    table_name: str
    declarations: tuple[Declaration, ...]
    recordlock: str
    format_item: int
    placements: tuple[FieldPlacement, ...] = field(init=False)
    record_size: int = field(init=False)

    def __post_init__(self):
        if not _identifier(self.table_name):
            raise ValueError("invalid physical table name")
        if type(self.recordlock) is not str or self.recordlock != "0":
            raise ValueError("only explicit recordlock zero is supported")
        if type(self.format_item) is not int or self.format_item != 0:
            raise ValueError("only explicit integer-zero format is supported")
        if type(self.declarations) is not tuple or not 1 <= len(self.declarations) <= 16:
            raise ValueError("invalid declaration vector")
        widths = []
        names = set()
        for declaration in self.declarations:
            if type(declaration) is not tuple or len(declaration) != 6:
                raise ValueError("invalid declaration")
            if any(type(value) is not expected for value, expected in
                   zip(declaration, (str, str, int, int, int, str))):
                raise ValueError("invalid declaration primitive")
            name, kind, nullable, length, precision, case = declaration
            if not _identifier(name) or len(kind) > 8 or len(case) > 8:
                raise ValueError("invalid field token")
            if name.lower() in names:
                raise ValueError("duplicate physical field")
            names.add(name.lower())
            widths.append(_width(declaration))
        versions = [i for i, declaration in enumerate(self.declarations) if declaration[1] == "RV"]
        if len(versions) > 1:
            raise ValueError("multiple version fields are unsupported")
        order = versions + [i for i in range(len(widths)) if i not in versions]
        offsets = [0] * len(widths)
        cursor = 1
        for index in order:
            offsets[index] = cursor
            cursor += widths[index]
        object.__setattr__(self, "placements", tuple(
            FieldPlacement(declaration, offsets[i], widths[i])
            for i, declaration in enumerate(self.declarations)))
        object.__setattr__(self, "record_size", max(5, cursor))


def format_discriminator(value: object) -> str:
    """Finite shape/value class; never expose an unknown descriptor or AST."""
    if type(value) is int:
        return "integer_zero" if value == 0 else "integer_nonzero"
    if type(value) is str:
        return "string_zero" if value == "0" else "string_other"
    if type(value) is tuple:
        return "list"
    return "other"


@dataclass(frozen=True)
class PhysicalValue:
    declaration: PhysicalField
    offset: int
    width: int
    raw: bytes
    value: bytes | bool | str | Decimal


@dataclass(frozen=True)
class PhysicalRecord:
    slot: int
    raw: bytes
    fields: tuple[PhysicalValue, ...]


@dataclass(frozen=True)
class PhysicalRecords:
    table: PhysicalTable
    data_file: InternalFileInfo
    record_size: int
    slots: int
    framing: str
    rows: tuple[PhysicalRecord, ...]
    usage: CatalogUsage
    capability: str = field(default="experimental_physical_records", init=False)
    native_acceptance: str = field(default="pending", init=False)


def _decode(raw: bytes, declaration: Declaration):
    kind = declaration[1]
    if kind in ("B", "RV"):
        return raw
    if kind == "L":
        if raw not in (b"\x00", b"\x01"):
            raise UnsupportedLayout("boolean_encoding")
        return raw == b"\x01"
    if kind == "NVC":
        length = int.from_bytes(raw[:2], "little")
        if length > declaration[3]:
            raise InvalidStructure("string_length")
        try:
            return raw[2:2 + 2 * length].decode("utf-16-le", errors="strict")
        except UnicodeDecodeError:
            raise UnsupportedLayout("string_encoding") from None
    # Exactly N(9,2): one sign nibble and nine digits, no padding nibble.
    number = int.from_bytes(raw, "big")
    sign = number >> 36
    if sign not in (0, 1):
        raise UnsupportedLayout("decimal_sign")
    digits = tuple((number >> shift) & 15 for shift in range(32, -1, -4))
    if any(digit > 9 for digit in digits):
        raise UnsupportedLayout("decimal_digit")
    return Decimal((0 if sign == 1 else 1, digits, -2))


def read_records(read_at: Callable[[int, int], bytes], file_size: int, *,
                 profile: RecordProfile, limits: RecordLimits | None = None,
                 catalog_limits: CatalogLimits | None = None) -> PhysicalRecords:
    """Borrow a caller-owned consistent offline file, read exactly one table.

    Calls never close or write the source. Root/catalog and selected table data
    share cumulative budgets and no-sharing roles. Results are all-or-nothing.
    Only active slots are decoded; nonreserved freed slots are unsupported here.
    """
    if type(profile) is not RecordProfile:
        raise ValueError("profile must be RecordProfile")
    if limits is not None and type(limits) is not RecordLimits:
        raise ValueError("limits must be RecordLimits")
    limits = limits if limits is not None else RecordLimits()
    if len(profile.declarations) > limits.max_fields:
        raise ResourceLimit("record_fields")
    if profile.record_size > limits.max_record_bytes:
        raise ResourceLimit("record_bytes")
    reader = CatalogReader(read_at, file_size, limits=catalog_limits)
    catalog = reader.read_catalog()
    matches = tuple(table for table in catalog.tables if table.name == profile.table_name)
    if len(matches) != 1:
        raise UnsupportedLayout("selected_table_count")
    table = matches[0]
    discriminator = format_discriminator(table.format_item)
    if discriminator != "integer_zero":
        raise UnsupportedLayout("format_" + discriminator)
    if table.recordlock != profile.recordlock:
        raise UnsupportedLayout("recordlock_mismatch")
    if tuple(item.raw for item in table.fields) != profile.declarations:
        raise UnsupportedLayout("declaration_mismatch")
    data = reader._open_table_data(table)
    length = data.info.logical_length
    if length % profile.record_size:
        raise InvalidStructure("record_file_length")
    slots = length // profile.record_size
    if slots > limits.max_slots:
        raise ResourceLimit("record_slots")
    if not slots:
        return PhysicalRecords(table, data.info, profile.record_size, 0,
                               "empty_zero_length", (), reader.usage)
    if data._read_range(0, 1) != b"\x01":
        raise UnsupportedLayout("reserved_slot_marker")
    rows = []
    for slot in range(1, slots):
        raw = data._read_range(slot * profile.record_size, profile.record_size)
        if raw[0] != 0:
            raise UnsupportedLayout("nonreserved_free_slot")
        if len(rows) >= limits.max_active_records:
            raise ResourceLimit("active_records")
        # Conservatively charge duplicate retained row/field bytes and objects.
        reader._budget.charge("output_bytes", 2 * len(raw) + 128 + 128 * len(table.fields))
        reader._budget.charge("bytes_processed", 2 * len(raw))
        values = []
        for declaration, placement in zip(table.fields, profile.placements):
            field_raw = raw[placement.offset:placement.offset + placement.width]
            value = _decode(field_raw, placement.declaration)
            if type(value) is str:
                reader._budget.charge("output_bytes", len(value.encode("utf-8")))
            values.append(PhysicalValue(declaration, placement.offset, placement.width, field_raw, value))
        rows.append(PhysicalRecord(slot, raw, tuple(values)))
    return PhysicalRecords(table, data.info, profile.record_size, slots,
                           "empty_reserved" if slots == 1 else "reserved_and_active",
                           tuple(rows), reader.usage)
