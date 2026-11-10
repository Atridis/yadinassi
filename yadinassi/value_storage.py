"""Bounded ValueStorage snapshot; not a platform codec or interchange format.

Shared children are copied per occurrence within local budgets; cycles fail
closed. Only two shared-array shapes were measured on 8.3.27.1508. No database
support is implied. Optional Deflation compresses bounded string/binary leaves
without introducing a platform format or weakening logical snapshot budgets.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import sys

try:
    from _decimal import Decimal as _CDecimal
except ImportError:
    _CDecimal = None

from .dates import BSLDate
from .data_compression import compression_degree, compress_payload, expand_payload
from .file_io import BSLBinaryData
from .maps import BSLFixedMap, BSLMap, _key as map_key
from .structures import BSLFixedStructure, BSLStructure, _key as structure_key
from .unique_identifiers import BSLUUID
from .value_tables import BSLValueTable
from .value_storage_table import TableSnapshotError, restore_table, take_table
from .values import BSLArray, BSLFixedArray, BSLObject, HostFunction, NULL

# Local defensive budgets, not platform limits. Nodes count occurrences,
# including scalars and map keys; text/binary/digit totals count occurrences.
MAX_DEPTH = 64
MAX_NODES = 10_000
MAX_TEXT_UNITS = 1_000_000
MAX_BINARY_BYTES = 16 * 1024 * 1024
MAX_NUMBER_DIGITS = 4096
MAX_TOTAL_NUMBER_DIGITS = 16_384
# Bound allocation in Decimal.as_tuple() before inspecting its coefficient.
MAX_DECIMAL_OBJECT_BYTES = 8192
# Conservative aggregate framing/deflate overhead on top of admitted payloads.
MAX_COMPRESSED_BYTES = MAX_BINARY_BYTES + 3 * MAX_TEXT_UNITS + 64 * MAX_NODES


class SnapshotError(ValueError):
    """Unsupported type, graph, source state, or local resource limit."""


def _required_field(value, name):
    # Used only after exact-type admission. Bypass per-instance hooks and
    # normalize only a genuinely missing field, not unrelated exceptions.
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        raise SnapshotError("missing internal snapshot field") from None


def _bounded_decimal(value):
    if (sys.implementation.name != "cpython" or Decimal is not _CDecimal
            or Decimal.__sizeof__ is object.__sizeof__
            or not value.is_finite()
            or Decimal.__sizeof__(value) > MAX_DECIMAL_OBJECT_BYTES):
        raise SnapshotError("unsupported number")
    digits = len(value.as_tuple().digits)
    if digits > MAX_NUMBER_DIGITS:
        raise SnapshotError("snapshot number budget exceeded")
    return digits


@dataclass(frozen=True, slots=True, repr=False)
class Snapshot:
    # The payload consists only of immutable builtin primitives and tuples.
    # This is a private, trusted in-process value, not an external format.
    _root: tuple = field(repr=False)


class _Capture:
    def __init__(self, root, degree=0):
        self.nodes = 0
        self.text_units = 0
        self.binary_bytes = 0
        self.digits = 0
        self.degree = degree
        self.compressed_bytes = 0
        # Active recursion path detects cycles; sibling aliases are copied.
        self.active = set()

    def reserve(self, count):
        # Metadata nodes share the same budget as every nested value.
        if type(count) is not int or count < 0 or count > MAX_NODES - self.nodes:
            raise SnapshotError("snapshot node budget exceeded")
        self.nodes += count

    def charge_text(self, text):
        if type(text) is not str:
            raise SnapshotError("snapshot expects exact strings")
        if len(text) > MAX_TEXT_UNITS - self.text_units:
            raise SnapshotError("snapshot text budget exceeded")
        units = len(text) + sum(ord(char) > 0xFFFF for char in text)
        self.text_units += units
        if self.text_units > MAX_TEXT_UNITS:
            raise SnapshotError("snapshot text budget exceeded")
        return text

    def remember(self, value, depth):
        identity = id(value)
        if identity in self.active:
            raise SnapshotError("cyclic values are not supported")
        self.active.add(identity)

    def compressed(self, tag, data):
        packed = compress_payload(data, self.degree)
        self.charge_compressed(packed)
        return (tag, packed, len(data))

    def charge_compressed(self, data):
        if type(data) is not bytes or len(data) > MAX_COMPRESSED_BYTES - self.compressed_bytes:
            raise SnapshotError('compressed snapshot byte budget exceeded')
        self.compressed_bytes += len(data)

    def take(self, value, depth=0):
        kind = type(value)
        identity_bearing = (kind is BSLArray or kind is BSLFixedArray
                            or kind is BSLStructure or kind is BSLFixedStructure
                            or kind is BSLMap or kind is BSLFixedMap
                            or kind is BSLBinaryData or kind is BSLValueStorage
                            or kind is BSLValueTable)
        if identity_bearing:
            self.remember(value, depth)
        try:
            return self._take(value, depth)
        finally:
            if identity_bearing:
                self.active.remove(id(value))

    def _take(self, value, depth=0):
        self.nodes += 1
        if self.nodes > MAX_NODES or depth > MAX_DEPTH:
            raise SnapshotError("snapshot node or depth budget exceeded")
        kind = type(value)
        if value is None:
            return ("undefined",)
        if value is NULL:
            return ("null",)
        if kind is bool:
            return ("boolean", value)
        if kind is Decimal:
            digits = _bounded_decimal(value)
            self.digits += digits
            if self.digits > MAX_TOTAL_NUMBER_DIGITS:
                raise SnapshotError("snapshot number budget exceeded")
            return ("number", value)
        if kind is str:
            text = self.charge_text(value)
            return (self.compressed('string_zlib', text.encode('utf-8', errors='surrogatepass'))
                    if self.degree else ('string', text))
        if kind is BSLDate:
            ticks = _required_field(value, "ticks")
            boundary = _required_field(value, "boundary")
            if type(ticks) is not int or type(boundary) is not bool:
                raise SnapshotError("invalid date state")
            # Check internal consistency before publishing the snapshot.
            BSLDate(ticks, boundary)
            return ("date", ticks, boundary)
        if kind is BSLUUID:
            text = self.charge_text(_required_field(value, "text"))
            if BSLUUID(text).text != text:
                raise SnapshotError("invalid UUID state")
            return ("uuid", text)
        if kind is BSLBinaryData:
            data = _required_field(value, "_data")
            if type(data) is not bytes:
                raise SnapshotError("invalid binary data state")
            self.binary_bytes += len(data)
            if self.binary_bytes > MAX_BINARY_BYTES:
                raise SnapshotError("snapshot binary budget exceeded")
            return self.compressed('binary_zlib', data) if self.degree else ('binary', data)
        if kind is BSLValueStorage:
            # Count the nested payload in this capture's existing budgets.
            return ("storage", self.take(BSLValueStorage.get(value), depth + 1))
        if kind is BSLValueTable:
            try:
                return take_table(value, encode=lambda item: self.take(item, depth + 1),
                                  charge_text=self.charge_text, reserve=self.reserve)
            except TableSnapshotError:
                raise SnapshotError("unsupported or invalid table snapshot") from None
        if kind is BSLArray or kind is BSLFixedArray:
            items = _required_field(value, "items")
            expected = list if kind is BSLArray else tuple
            if type(items) is not expected or len(items) > MAX_NODES - self.nodes:
                raise SnapshotError("invalid or oversized array")
            tag = "array" if kind is BSLArray else "fixed_array"
            return (tag, tuple(self.take(item, depth + 1) for item in items))
        if kind is BSLStructure or kind is BSLFixedStructure:
            entries = _required_field(value, "_items")
            if type(entries) is not dict or len(entries) > MAX_NODES - self.nodes:
                raise SnapshotError("invalid or oversized structure")
            captured = []
            for key, pair in entries.items():
                if type(key) is not str or type(pair) is not tuple or len(pair) != 2:
                    raise SnapshotError("invalid structure entry")
                name, item = pair
                self.charge_text(name)
                if key != structure_key(name):
                    raise SnapshotError("inconsistent structure key")
                captured.append((name, self.take(item, depth + 1)))
            tag = "structure" if kind is BSLStructure else "fixed_structure"
            return (tag, tuple(captured))
        if kind is BSLMap or kind is BSLFixedMap:
            entries = _required_field(value, "_items")
            if type(entries) is not dict or len(entries) > (MAX_NODES - self.nodes) // 2:
                raise SnapshotError("invalid or oversized map")
            captured = []
            for token, pair in entries.items():
                if (type(token) is not tuple or len(token) != 2
                        or type(pair) is not tuple or len(pair) != 2):
                    raise SnapshotError("invalid map entry")
                key, item = pair
                # Admission happens before map_key so no extension object hooks
                # or arbitrary host objects can influence reconstruction.
                encoded_key = self.take(key, depth + 1)
                encoded_item = self.take(item, depth + 1)
                expected = map_key(key)
                if (token[0] is not expected[0]
                        or type(token[1]) is not type(expected[1])):
                    raise SnapshotError("inconsistent map key")
                if type(token[1]) is Decimal:
                    _bounded_decimal(token[1])
                if token[1] != expected[1]:
                    raise SnapshotError("inconsistent map key")
                captured.append((encoded_key, encoded_item))
            tag = "map" if kind is BSLMap else "fixed_map"
            return (tag, tuple(captured))
        raise SnapshotError("unsupported snapshot type")


def capture(value, *, compression=None):
    """Build a bounded immutable snapshot, or fail without publishing one."""
    return Snapshot(_Capture(value, compression_degree(compression)).take(value))


class _Restore:
    """Validate every private snapshot node, including budgets, before use."""
    def __init__(self):
        self.budget = _Capture(None)

    def take(self, node, depth=0):
        budget = self.budget
        budget.nodes += 1
        if budget.nodes > MAX_NODES or depth > MAX_DEPTH:
            raise SnapshotError("snapshot node or depth budget exceeded")
        if type(node) is not tuple or not node or type(node[0]) is not str:
            raise SnapshotError("invalid internal snapshot")
        tag = node[0]
        if tag == "undefined" and len(node) == 1:
            return None
        if tag == "null" and len(node) == 1:
            return NULL
        if tag == "boolean" and len(node) == 2 and type(node[1]) is bool:
            return node[1]
        if tag == "number" and len(node) == 2 and type(node[1]) is Decimal:
            budget.digits += _bounded_decimal(node[1])
            if budget.digits > MAX_TOTAL_NUMBER_DIGITS:
                raise SnapshotError("snapshot number budget exceeded")
            return node[1]
        if tag == "string" and len(node) == 2:
            return budget.charge_text(node[1])
        if tag in ('string_zlib', 'binary_zlib') and len(node) == 3:
            budget.charge_compressed(node[1])
            limit = (3 * (MAX_TEXT_UNITS - budget.text_units) if tag == 'string_zlib'
                     else MAX_BINARY_BYTES - budget.binary_bytes)
            try:
                data = expand_payload(node[1], node[2], limit)
                if tag == 'string_zlib':
                    return budget.charge_text(data.decode('utf-8', errors='surrogatepass'))
            except (ValueError, UnicodeError):
                raise SnapshotError('invalid compressed snapshot payload') from None
            budget.binary_bytes += len(data)
            return BSLBinaryData.from_bytes(data)
        if tag == "date" and len(node) == 3:
            return BSLDate(node[1], node[2])
        if tag == "uuid" and len(node) == 2:
            text = budget.charge_text(node[1])
            result = BSLUUID(text)
            if result.text != text:
                raise SnapshotError("invalid UUID state")
            return result
        if tag == "binary" and len(node) == 2 and type(node[1]) is bytes:
            budget.binary_bytes += len(node[1])
            if budget.binary_bytes > MAX_BINARY_BYTES:
                raise SnapshotError("snapshot binary budget exceeded")
            return BSLBinaryData.from_bytes(node[1])
        if tag == "value_table":
            try:
                return restore_table(node, decode=lambda item: self.take(item, depth + 1),
                                     charge_text=budget.charge_text, reserve=budget.reserve)
            except TableSnapshotError:
                raise SnapshotError("unsupported or invalid table snapshot") from None
        if tag == "storage" and len(node) == 2:
            # Validate the complete immutable child tree within this budget.
            self.take(node[1], depth + 1)
            return BSLValueStorage._from_snapshot(Snapshot(node[1]))
        if (tag in ("array", "fixed_array", "structure", "fixed_structure", "map", "fixed_map")
                and len(node) == 2 and type(node[1]) is tuple):
            body = node[1]
            width = 2 if tag in ("map", "fixed_map") else 1
            if len(body) > (MAX_NODES - budget.nodes) // width:
                raise SnapshotError("snapshot node budget exceeded")
            if tag in ("array", "fixed_array"):
                items = [self.take(item, depth + 1) for item in body]
                if tag == "array":
                    result = BSLArray()
                    result.items = items
                else:
                    result = object.__new__(BSLFixedArray)
                    result.items = tuple(items)
                return result
            if tag in ("structure", "fixed_structure"):
                result = BSLStructure()
                for pair in body:
                    if type(pair) is not tuple or len(pair) != 2:
                        raise SnapshotError("invalid structure snapshot")
                    name = budget.charge_text(pair[0])
                    normalized = structure_key(name)
                    if normalized in result._items:
                        raise SnapshotError("duplicate structure key")
                    result.insert(name, self.take(pair[1], depth + 1))
                return result if tag == "structure" else BSLFixedStructure(result)
            result = BSLMap()
            for pair in body:
                if type(pair) is not tuple or len(pair) != 2:
                    raise SnapshotError("invalid map snapshot")
                key = self.take(pair[0], depth + 1)
                item = self.take(pair[1], depth + 1)
                old_count = len(result._items)
                result.insert(key, item)
                if len(result._items) != old_count + 1:
                    raise SnapshotError("duplicate map key")
            return result if tag == "map" else BSLFixedMap(result)
        raise SnapshotError("invalid internal snapshot")


def restore(snapshot):
    """Validate and restore a bounded snapshot, including nested storage."""
    if type(snapshot) is not Snapshot:
        raise SnapshotError("expected an internal snapshot")
    return _Restore().take(_required_field(snapshot, "_root"))


class BSLValueStorage(BSLObject):
    """Immutable private snapshot, optionally compressing leaf payloads."""
    __slots__ = ("_snapshot",)

    def __init__(self, value, compression=None):
        self._snapshot = capture(value, compression=compression)

    @classmethod
    def _from_snapshot(cls, snapshot):
        result = object.__new__(cls)
        result._snapshot = snapshot
        return result

    def get(self):
        if type(self) is not BSLValueStorage:
            raise SnapshotError("expected exact ValueStorage")
        return restore(_required_field(self, "_snapshot"))

    def get_method(self, name):
        if name.casefold() in {"получить", "get"}:
            return HostFunction(name, lambda: BSLValueStorage.get(self))
        return super().get_method(name)

    def __str__(self):
        raise ValueError("ХранилищеЗначения: строковое представление не измерено")
