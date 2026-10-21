"""Source-bound, lossless Map-entry-order relation for collections output.

This is not a 1C deserializer and never changes either input. It accepts only a
small, explicitly typed stream grammar. Unknown object layouts, references,
identity-bearing object keys and native alternative string encodings fail
closed. Every token and separator is retained; only complete Map/FixedMap
key/value pairs may move. Ordered containers and scalar spellings stay exact.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re

PROFILE = "typed-map-order-v1"
SOURCE_SHA256 = "70dfefabf9466e1d8d3e00e844f931a7b8f005ed110d74049e07fbfed8fbbc72"
RECORD_COUNT = 758
MAX_FILE = 1_048_576
MAX_RECORD = 4096
MAX_DEPTH = 12
MAX_NODES = 256
MAX_SCALAR = 256

_BASES = ((283, "internal.map.typed-keys"),
          (287, "internal.map.typed-keys-again"),
          (291, "internal.map.reverse-insertion"),
          (303, "internal.array.nested"))
_ELIGIBLE = {ordinal + offset: base + suffix
             for ordinal, base in _BASES
             for offset, suffix in ((0, ".payload"), (3, ".roundtrip.payload"))}
ELIGIBLE_LABELS = tuple(_ELIGIBLE.values())
_CHECKS = {ordinal + offset: base + suffix
           for ordinal, base in _BASES
           for offset, suffix in ((1, ".roundtrip.type"), (2, ".roundtrip.count"))}
_CHECKS.update({307 + index: "internal.nested." + name for index, name in enumerate((
    "structure-type", "fixed-structure-type", "fixed-map-type", "record-value",
    "string-value", "map-value", "typed-keys"))})
REASONS = frozenset({"none", "source_mismatch", "input_limit", "invalid_framing",
                     "record_mismatch", "ineligible_difference", "unsupported_payload",
                     "payload_limit", "typed_difference", "roundtrip_failed"})

_MAP = b"3d48feae-a9c6-4c5a-a099-9eb6477630c6"
_FIXED_MAP = b"220455ea-6c85-4513-996f-bbe79ed07774"
_ARRAY = b"51e7a0d2-530b-11d4-b98a-008048da3034"
_ARRAYS = frozenset({_ARRAY, b"4500381b-db30-4a10-9db4-990038032acf"})
_STRUCTURES = frozenset({b"4238019d-7e49-4fc9-91db-b6b951d5cf8e",
                         b"3ee983d7-ace7-40f9-bb7e-2e916fcddd56"})
_MAPS = frozenset({_MAP, _FIXED_MAP})
_CONTAINERS = _ARRAYS | _STRUCTURES | _MAPS
_TYPE_IDS = _CONTAINERS | frozenset({
    b"af40a278-63bc-478e-91a8-19e0d16b10b5",  # Null
    b"ee8d3e7c-f930-4a76-8aad-4ff9083a6ea6",  # Undefined
    b"5d4125ad-f6e7-4313-be32-f71d0ab60915",  # Boolean
    b"b0be78f2-0ee6-4d31-a3bb-77dd32ba5bec",  # Number
    b"9b6abf8b-0173-48e5-b0a0-83b21fcf63c5",  # String
    b"aae38c48-a877-411c-a6d3-fbaa1f83c4bd",  # Date
    b"d47d59f8-73f0-481c-8b5e-f6384c0a4804",  # Type
})
_LABEL = re.compile(rb"[A-Za-z][A-Za-z0-9_.-]{0,127}: \[")
_UUID = re.compile(rb"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
_NUMBER = re.compile(rb"[+-]?[0-9]+(?:\.[0-9]+)?")
_COUNT = re.compile(rb"0|[1-9][0-9]{0,2}")
_WS = b" \t\r\n"


class _Reject(Exception):
    pass


class _Atom:
    __slots__ = ("raw", "quoted")

    def __init__(self, raw, quoted):
        self.raw, self.quoted = raw, quoted


class _Group:
    __slots__ = ("children", "gaps")

    def __init__(self, children, gaps):
        self.children, self.gaps = tuple(children), tuple(gaps)


def _records(data):
    """Consume frames, not apparent labels embedded in quoted payload strings."""
    if type(data) is not bytes or not 0 < len(data) <= MAX_FILE:
        raise _Reject("input_limit")
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeError:
        raise _Reject("invalid_framing") from None
    if b"\x00" in data:
        raise _Reject("invalid_framing")
    records, labels, cursor = [], set(), 0
    while cursor < len(data):
        start = cursor
        match = _LABEL.match(data, cursor)
        if match is None or len(records) >= RECORD_COUNT:
            raise _Reject("invalid_framing")
        label = data[start:match.end() - 3].decode("ascii")
        if label in labels:
            raise _Reject("record_mismatch")
        labels.add(label)
        cursor = payload_start = match.end()
        depth, quoted = 1, False
        while cursor < len(data):
            char = data[cursor]
            if char == 34:
                if quoted and data[cursor:cursor + 2] == b'""':
                    cursor += 2
                    continue
                quoted = not quoted
            elif not quoted:
                if char == 91:
                    depth += 1
                    if depth > MAX_NODES:
                        raise _Reject("invalid_framing")
                elif char == 93:
                    depth -= 1
                    if depth == 0:
                        break
            cursor += 1
        if quoted or depth or data[cursor:cursor + 2] != b"]\n":
            raise _Reject("invalid_framing")
        records.append((label, data[start:cursor + 2], data[payload_start:cursor]))
        cursor += 2
    if len(records) != RECORD_COUNT:
        raise _Reject("record_mismatch")
    return records


class _Parser:
    def __init__(self, data):
        self.data, self.cursor, self.nodes = data, 0, 0

    def whitespace(self):
        while self.cursor < len(self.data) and self.data[self.cursor] in _WS:
            self.cursor += 1

    def parse(self, depth=0):
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise _Reject("payload_limit")
        data, start = self.data, self.cursor
        if start >= len(data):
            raise _Reject("unsupported_payload")
        if data[start] == 123:
            self.cursor += 1
            self.whitespace()
            children, gaps = [], [data[start:self.cursor]]
            while True:
                children.append(self.parse(depth + 1))
                start = self.cursor
                self.whitespace()
                if self.cursor >= len(data):
                    raise _Reject("unsupported_payload")
                char = data[self.cursor]
                self.cursor += 1
                if char == 125:
                    gaps.append(data[start:self.cursor])
                    return _Group(children, gaps)
                if char != 44:
                    raise _Reject("unsupported_payload")
                self.whitespace()
                gaps.append(data[start:self.cursor])
        quoted = data[start] == 34
        if quoted:
            self.cursor += 1
            while self.cursor < len(data):
                if self.cursor - start > MAX_SCALAR:
                    raise _Reject("payload_limit")
                if data[self.cursor] == 34:
                    self.cursor += 1
                    if data[self.cursor:self.cursor + 1] != b'"':
                        break
                self.cursor += 1
            else:
                raise _Reject("unsupported_payload")
        else:
            while self.cursor < len(data) and data[self.cursor] not in b",{} \t\r\n":
                self.cursor += 1
                if self.cursor - start > MAX_SCALAR:
                    raise _Reject("payload_limit")
        raw = data[start:self.cursor]
        if not raw:
            raise _Reject("unsupported_payload")
        if len(raw) > MAX_SCALAR:
            raise _Reject("payload_limit")
        return _Atom(raw, quoted)


def _atom(node, *, quoted=False):
    if not isinstance(node, _Atom) or node.quoted != quoted:
        raise _Reject("unsupported_payload")
    return node.raw


def _group(node):
    if not isinstance(node, _Group):
        raise _Reject("unsupported_payload")
    return node.children


def _signature(node, children):
    # Homogeneous tuple components make sorting deterministic without repr,
    # hashing payloads or converting scalar tokens to application values.
    return (b"group", node.gaps, tuple(children))


def _scalar_key(node):
    """Reject duplicate scalar keys, without normalizing comparison signatures.

    Container keys have object identity that this restricted grammar cannot
    establish. Refusing them is safer than equating independently equal objects.
    """
    children = _group(node)
    tag = _atom(children[0], quoted=True)
    if tag == b'"#"':
        raise _Reject("unsupported_payload")
    raw = _atom(children[1], quoted=tag == b'"S"') if len(children) == 2 else b""
    if tag == b'"N"':
        return tag, Decimal(raw.decode("ascii"))
    if tag == b'"S"':
        return tag, raw[1:-1].replace(b'""', b'"')
    return tag, raw


def _value(node):
    children = _group(node)
    tag = _atom(children[0], quoted=True)
    if tag in (b'"U"', b'"L"') and len(children) == 1:
        pass
    elif tag in (b'"B"', b'"N"', b'"S"', b'"T"', b'"D"') and len(children) == 2:
        raw = _atom(children[1], quoted=tag == b'"S"')
        if tag == b'"B"' and raw not in (b"0", b"1"):
            raise _Reject("unsupported_payload")
        if tag == b'"N"' and _NUMBER.fullmatch(raw) is None:
            raise _Reject("unsupported_payload")
        if tag == b'"T"' and (_UUID.fullmatch(raw) is None or raw not in _TYPE_IDS):
            raise _Reject("unsupported_payload")
        if tag == b'"D"':
            if len(raw) != 14 or not raw.isdigit():
                raise _Reject("unsupported_payload")
            try:
                datetime(*(int(raw[a:b]) for a, b in ((0, 4), (4, 6), (6, 8),
                                                      (8, 10), (10, 12), (12, 14))))
            except ValueError:
                raise _Reject("unsupported_payload") from None
    elif tag == b'"#"' and len(children) == 3:
        identifier = _atom(children[1])
        if identifier not in _CONTAINERS:
            raise _Reject("unsupported_payload")
        body = children[2]
        items = _group(body)
        count = _atom(items[0])
        if _COUNT.fullmatch(count) is None or int(count) != len(items) - 1:
            raise _Reject("unsupported_payload")
        values = []
        if identifier in _ARRAYS:
            values = [_value(child) for child in items[1:]]
        else:
            keys = set()
            for pair in items[1:]:
                binding = _group(pair)
                if len(binding) != 2:
                    raise _Reject("unsupported_payload")
                values.append(_signature(pair, [_value(child) for child in binding]))
                key = _scalar_key(binding[0])
                if identifier in _STRUCTURES:
                    if key[0] != b'"S"':
                        raise _Reject("unsupported_payload")
                    name = key[1].decode("utf-8")
                    if (not name or not (name[0].isalpha() or name[0] == "_")
                            or not all(char.isalnum() or char == "_" for char in name)):
                        raise _Reject("unsupported_payload")
                    # Structure names are case-insensitive. Preserve the raw
                    # spelling for comparison, but reject duplicate aliases.
                    key = (key[0], name.casefold())
                if key in keys:
                    raise _Reject("unsupported_payload")
                keys.add(key)
            if identifier in _MAPS:
                values.sort()
        body_signature = _signature(body, [(b"atom", count), *values])
        return _signature(node, [(b"atom", tag), (b"atom", identifier), body_signature])
    else:
        raise _Reject("unsupported_payload")
    return _signature(node, [(b"atom", _atom(child, quoted=child.quoted))
                              for child in children])


def _payload(record, ordinal):
    if len(record[1]) > MAX_RECORD:
        raise _Reject("payload_limit")
    parser = _Parser(record[2])
    parser.whitespace()
    prefix = parser.data[:parser.cursor]
    root = parser.parse()
    end = parser.cursor
    parser.whitespace()
    if parser.cursor != len(parser.data):
        raise _Reject("unsupported_payload")
    children = _group(root)
    expected = _ARRAY if ordinal in (303, 306) else _MAP
    if (len(children) != 3 or _atom(children[0], quoted=True) != b'"#"'
            or _atom(children[1]) != expected):
        raise _Reject("unsupported_payload")
    return prefix, _value(root), parser.data[end:]


def compare_collections(native: bytes, interpreter: bytes, source_sha256: str) -> dict:
    """Return only fixed labels/codes and bounded counts, never payload data.

    The caller must separately verify the Linux target/build and the hash of
    the actual executed source. Passing a hash here is not proof of execution.
    Rejections intentionally disclose no partial record or parser diagnostics.
    """
    result = {"status": "rejected", "profile": PROFILE, "records": 0,
              "byte_equal_records": 0, "accepted_labels": [], "reason": "none"}
    try:
        if type(source_sha256) is not str or source_sha256 != SOURCE_SHA256:
            raise _Reject("source_mismatch")
        left, right = _records(native), _records(interpreter)
        trees = ({}, {})
        accepted, equal = [], 0
        for ordinal, (a, b) in enumerate(zip(left, right), 1):
            if a[0] != b[0]:
                raise _Reject("record_mismatch")
            expected = _ELIGIBLE.get(ordinal, _CHECKS.get(ordinal))
            if expected is not None and a[0] != expected:
                raise _Reject("record_mismatch")
            if ordinal in _CHECKS and (a[2] != b"true" or b[2] != b"true"):
                raise _Reject("roundtrip_failed")
            if ordinal in _ELIGIBLE:
                trees[0][ordinal], trees[1][ordinal] = _payload(a, ordinal), _payload(b, ordinal)
                if trees[0][ordinal] != trees[1][ordinal]:
                    raise _Reject("typed_difference")
                if a[1] != b[1]:
                    accepted.append(_ELIGIBLE[ordinal])
            elif a[1] != b[1]:
                raise _Reject("ineligible_difference")
            equal += a[1] == b[1]
        for side in trees:
            for ordinal, _ in _BASES:
                if side[ordinal] != side[ordinal + 3]:
                    raise _Reject("roundtrip_failed")
        result.update(status="equivalent", records=RECORD_COUNT,
                      byte_equal_records=equal, accepted_labels=accepted)
    except _Reject as exc:
        result["reason"] = exc.args[0]
    return result
