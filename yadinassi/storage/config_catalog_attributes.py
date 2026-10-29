"""Private, bounded Catalog attribute collection projection.

Only a single explicit String/Number type per attribute is admitted. This is a
partial CONFIG grammar, not an applied schema, DBNames binding or row decoder.
The independent byte walk retains no opaque AST and accepts no oracle inputs.
See docs/config-catalog-attributes.md for pinned positional facts and limits.
"""
from dataclasses import dataclass

from .config_catalog_name import (CatalogNameError, CatalogNameLimits, _Cursor,
                                  _IdentityCursor)

PROFILE_IDENTIFIER = 'config_catalog_attributes_single_primitive_v1'
COLLECTION_UUID = 'cf4abea7-37b2-11d4-940f-008048da11f9'
UUID_PATH = (0, 1, 1, 1, 1, 2)
NAME_PATH = (0, 1, 1, 1, 2)
TYPE_PATH = (0, 1, 1, 2)
OUTPUT_RESERVATION = 262144


class CatalogAttributeError(Exception):
    codes = CatalogNameError.codes | frozenset((
        'missing_collection', 'collection_uuid', 'collection_count',
        'attribute_limit', 'missing_field', 'uuid_syntax', 'uuid_zero',
        'duplicate_uuid', 'duplicate_name', 'integer_syntax', 'integer_bound',
        'type_pattern', 'type_shape', 'type_unsupported', 'qualifier_kind',
        'numeric_qualifiers'))

    def __init__(self, code):
        if type(code) is not str or code not in self.codes:
            raise ValueError('invalid catalog attribute diagnostic')
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CatalogAttributeLimits(CatalogNameLimits):
    max_attributes: int = 64
    max_qualifier: int = 2147483647

    def __post_init__(self):
        try:
            CatalogNameLimits.__post_init__(self)
        except CatalogNameError as error:
            raise CatalogAttributeError(error.code) from None
        for name, ceiling in (('max_attributes', 64), ('max_qualifier', 2147483647)):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= ceiling:
                raise CatalogAttributeError('limit')


@dataclass(frozen=True, slots=True)
class CatalogAttribute:
    metadata_uuid: str
    name: str
    type_token: str
    # S: (length, StringKind); N: (precision, scale, NumericKind).
    # Values are metadata, never fixed decoder widths or platform range claims.
    qualifiers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CatalogAttributes:
    attributes: tuple[CatalogAttribute, ...]


class _Walk(_Cursor):
    def __init__(self, data, budget, limits):
        super().__init__(data, budget, limits)
        self.count = None
        self.rows = []
        self.current = {}
        self.uuids = set()
        self.names = set()

    def integer(self, maximum):
        self.event()
        first = self.peek()
        value = digits = 0
        while self.peek() not in (44, 125):
            byte = self.peek()
            if byte is None or not 48 <= byte <= 57 or digits and first == 48:
                raise CatalogAttributeError('integer_syntax')
            if digits == 10:
                raise CatalogAttributeError('integer_bound')
            value = value * 10 + byte - 48
            if value > maximum:
                raise CatalogAttributeError('integer_bound')
            self.character()
            digits += 1
        if not digits:
            raise CatalogAttributeError('integer_syntax')
        return value

    def kind(self, path):
        """Classify only fixed routes; unknown subtrees are syntax-only."""
        if path == (6,):
            return 'object'
        if path == (6, 0):
            return 'collection_uuid'
        if path == (6, 1):
            return 'count'
        if len(path) < 2 or path[0] != 6 or path[1] < 2:
            return 'opaque'
        if self.count is None or path[1] >= self.count + 2:
            raise CatalogAttributeError('collection_count')
        relative = path[2:]
        if relative == UUID_PATH:
            return 'uuid'
        if relative == NAME_PATH:
            return 'name'
        if relative == TYPE_PATH + (0,):
            return 'pattern'
        if relative == TYPE_PATH + (1, 0):
            return 'token'
        if relative[:len(TYPE_PATH)] == TYPE_PATH and len(relative) > len(TYPE_PATH):
            tail = relative[len(TYPE_PATH):]
            if len(tail) == 1 and tail[0] == 1:
                return 'object'
            if len(tail) == 2 and tail[0] == 1 and tail[1] in (1, 2, 3):
                return 'qualifier'
            raise CatalogAttributeError('type_shape')
        if any(route[:len(relative)] == relative for route in (UUID_PATH, NAME_PATH, TYPE_PATH)):
            return 'object'
        return 'opaque'

    def value(self, path, kind):
        if kind in ('collection_uuid', 'uuid'):
            value = _IdentityCursor.uuid(self)
            if kind == 'collection_uuid':
                if value != COLLECTION_UUID:
                    raise CatalogAttributeError('collection_uuid')
            else:
                self.current['uuid'] = value
        elif kind in ('count', 'qualifier'):
            value = self.integer(2147483647 if kind == 'count' else self.limits.max_qualifier)
            if kind == 'count':
                if value > self.limits.max_attributes:
                    raise CatalogAttributeError('attribute_limit')
                self.count = value
            else:
                self.current.setdefault('qualifiers', []).append(value)
        elif kind == 'pattern':
            self.event()
            for byte in b'"Pattern"':
                if self.peek() != byte:
                    raise CatalogAttributeError('type_pattern')
                self.character()
            self.spaces()
            if self.peek() not in (44, 125):
                raise CatalogAttributeError('type_pattern')
        elif kind in ('name', 'token'):
            # These are strings in the admitted grammar, never bare guesses.
            if self.peek() != 34:
                raise CatalogAttributeError('expected_scalar')
            value = self.scalar(True)
            self.current[kind] = value
        else:
            self.scalar(False)

    def close(self, path, children):
        if path == (6,):
            if self.count is None or children != self.count + 2 or len(self.rows) != self.count:
                raise CatalogAttributeError('collection_count')
            return True
        if len(path) < 2 or path[0] != 6 or path[1] < 2:
            return False
        relative = path[2:]
        if relative == TYPE_PATH and children != 2:
            raise CatalogAttributeError('type_shape')
        if relative == TYPE_PATH + (1,):
            token = self.current.get('token')
            if token not in ('S', 'N'):
                raise CatalogAttributeError('type_unsupported')
            qualifiers = self.current.get('qualifiers', [])
            if children != (3 if token == 'S' else 4) or len(qualifiers) != children - 1:
                raise CatalogAttributeError('type_shape')
            if qualifiers[-1] not in (0, 1):
                raise CatalogAttributeError('qualifier_kind')
            if token == 'N' and (qualifiers[0] == 0 or qualifiers[1] > qualifiers[0]):
                raise CatalogAttributeError('numeric_qualifiers')
        if not relative:
            if set(self.current) != {'uuid', 'name', 'token', 'qualifiers'}:
                raise CatalogAttributeError('missing_field')
            uuid, name = self.current['uuid'], self.current['name']
            if uuid in self.uuids:
                raise CatalogAttributeError('duplicate_uuid')
            # Exact spelling only; no unsupported locale/case binding claim.
            if name in self.names:
                raise CatalogAttributeError('duplicate_name')
            self.uuids.add(uuid)
            self.names.add(name)
            self.rows.append(CatalogAttribute(uuid, name, self.current['token'],
                                              tuple(self.current['qualifiers'])))
            self.current = {}
        return False

    def run(self):
        if self.data.startswith(b'\xef\xbb\xbf'):
            self.position = 3
        self.spaces()
        if self.peek() != 123:
            raise CatalogAttributeError('syntax')
        self.event()
        self.character()
        # path, completed children, after-value. No opaque scalar/AST retention.
        stack = [[(), 0, False]]
        while stack:
            frame = stack[-1]
            self.spaces()
            if self.peek() == 125:
                # Empty objects are syntactically valid; a trailing comma is not.
                if frame[1] and not frame[2]:
                    raise CatalogAttributeError('syntax')
                self.event()
                self.character()
                if self.close(frame[0], frame[1]):
                    self.spaces()
                    if self.peek() not in (44, 125):
                        raise CatalogAttributeError('syntax')
                    return CatalogAttributes(tuple(self.rows))
                stack.pop()
                continue
            if frame[2]:
                if self.peek() != 44:
                    raise CatalogAttributeError('syntax')
                self.character()
                frame[2] = False
                continue
            path = frame[0] + (frame[1],)
            kind = self.kind(path)
            if self.peek() == 123:
                if kind not in ('object', 'opaque'):
                    raise CatalogAttributeError('expected_scalar')
                if len(stack) >= self.depth:
                    raise CatalogAttributeError('depth')
                self.event()
                self.character()
                frame[1] += 1
                frame[2] = True
                stack.append([path, 0, False])
            else:
                if kind == 'object':
                    raise CatalogAttributeError('expected_object')
                self.value(path, kind)
                frame[1] += 1
                frame[2] = True
        raise CatalogAttributeError('missing_collection')


def project_catalog_attributes(data, *, budget, limits=None):
    """Parse through the complete [6] collection; do not validate its suffix.

    Expected metadata, physical names and fixture values are deliberately not
    parameters. Every allocation is preceded by cumulative budget reservation;
    failure retains charges, and no per-attribute budget is created or reset.
    """
    if type(data) is not bytes:
        raise CatalogAttributeError('input_type')
    limits = CatalogAttributeLimits() if limits is None else limits
    if type(limits) is not CatalogAttributeLimits:
        raise CatalogAttributeError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise CatalogAttributeError('input_bytes')
    budget.charge('bytes_processed', 8 * len(data))
    budget.charge('output_bytes', OUTPUT_RESERVATION)
    try:
        return _Walk(data, budget, limits).run()
    except CatalogNameError as error:
        raise CatalogAttributeError(error.code) from None
