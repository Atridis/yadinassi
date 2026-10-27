"""Private partial Catalog declaration references in decoded CONFIG target bytes.

Only declared positions needed for navigation are observed. No complete target,
object identity, properties, or applied-state claim; no suffix lookahead. This
module performs no I/O and accepts no expected object identifier.
"""
from dataclasses import dataclass

PROFILE_IDENTIFIER = 'config_catalog_declared_references_v1'
CATALOG_TYPE = 'cf4abea6-37b2-11d4-940f-008048da11f9'
_GENERAL = '9cd510cd-abfc-11d4-9434-004095e12fc7'
_OPERATIONS = '9fcd25a0-4822-11d4-9414-008048da11f9'
_DIRECT = frozenset((_GENERAL, 'e3687481-0a87-462c-a166-9f34594f9bba',
                     '51f2d5d8-ea4d-4064-8892-82951750031e'))
OUTPUT_RESERVATION = 212992
RESOURCE_CODES = frozenset(('input_bytes', 'tokens', 'depth', 'components',
                            'collections', 'references'))


class CatalogReferenceError(Exception):
    codes = frozenset(('input_type', 'limits_type', 'limit', 'input_bytes',
                       'tokens', 'depth', 'components', 'collections', 'references',
                       'scalar', 'syntax', 'encoding', 'control', 'bom', 'count',
                       'guid', 'zero_guid', 'duplicate', 'component_duplicate',
                       'no_catalog', 'no_positive'))

    def __init__(self, code):
        if type(code) is not str or code not in self.codes:
            raise ValueError('invalid catalog reference diagnostic')
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CatalogReferenceLimits:
    max_input_bytes: int = 4194304
    max_tokens: int = 131072
    max_depth: int = 64
    max_components: int = 16
    max_collections: int = 64
    max_references: int = 256

    def __post_init__(self):
        for key, maximum in (('max_input_bytes',4194304), ('max_tokens',131072),
                ('max_depth',64), ('max_components',16), ('max_collections',64),
                ('max_references',256)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise CatalogReferenceError('limit')


@dataclass(frozen=True, slots=True)
class CatalogReferences:
    """Private keys only. Never serialize this object into a diagnostic/report."""
    collection_count: int
    references: tuple[str, ...]


class _Frame:
    __slots__ = ('role', 'index', 'after', 'kind', 'count')

    def __init__(self, role):
        self.role, self.index, self.after, self.kind, self.count = role, 0, False, None, None


class _Walk:
    __slots__ = ('data', 'pos', 'budget', 'limits', 'depth', 'tokens', 'stack',
                 'components_left', 'collections_left', 'collection_total',
                 'catalog_count', 'refs', 'seen', 'kinds', 'component', 'container')

    def __init__(self, data, budget, limits):
        self.data, self.pos, self.budget, self.limits = data, 0, budget, limits
        self.depth = min(limits.max_depth, budget.limits.max_tree_depth)
        self.tokens = self.collection_total = self.catalog_count = 0
        self.stack, self.refs, self.seen, self.kinds = [], [], set(), set()
        self.components_left = self.collections_left = None
        self.component = self.container = None

    def fail(self, code):
        raise CatalogReferenceError(code)

    def peek(self):
        return self.data[self.pos] if self.pos < len(self.data) else None

    def take(self):
        """Validate exactly one consumed UTF-8 character, with no read-ahead."""
        b = self.peek()
        if b is None:
            self.fail('syntax')
        if b < 128:
            if b == 127 or b < 32 and b not in (10, 13):
                self.fail('control')
            self.pos += 1
            return b
        if 194 <= b <= 223:
            n, code, minimum = 1, b & 31, 128
        elif 224 <= b <= 239:
            n, code, minimum = 2, b & 15, 2048
        elif 240 <= b <= 244:
            n, code, minimum = 3, b & 7, 65536
        else:
            self.fail('encoding')
        if self.pos + n >= len(self.data):
            self.fail('encoding')
        for offset in range(1, n+1):
            tail = self.data[self.pos+offset]
            if not 128 <= tail <= 191:
                self.fail('encoding')
            code = (code << 6) | (tail & 63)
        if code < minimum or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
            self.fail('encoding')
        if code == 0xFEFF:
            self.fail('bom')
        self.pos += n+1
        return code

    def spaces(self):
        while self.peek() in (32, 13, 10):
            self.take()

    def token(self):
        if self.tokens >= self.limits.max_tokens:
            self.fail('tokens')
        self.budget.charge('tokens', 1)
        self.tokens += 1

    def push(self, role):
        if len(self.stack) >= self.depth:
            self.fail('depth')
        self.token()  # before frame allocation/state growth
        frame = _Frame(role)
        self.stack.append(frame)
        if role == 'component':
            self.component = frame
        elif role == 'container':
            self.container = frame

    def wanted(self, frame):
        i, role = frame.index, frame.role
        return (role == 'root' and i == 2 or role == 'component' and i == 0
                or role == 'container' and i == 2 or role == 'collection')

    def object_role(self, frame):
        i, role = frame.index, frame.role
        if self.wanted(frame):
            self.fail('scalar')
        if role == 'root' and i >= 3:
            return 'component'
        if role == 'component' and i == 1:
            return 'wrapper' if frame.kind == _OPERATIONS else 'container'
        if role == 'wrapper' and i == 1:
            return 'container'
        if role == 'container' and i >= 3:
            return 'collection'
        return 'ignore'

    def scalar(self, interested):
        # Charge before allocating even the bounded scalar buffer. Opaque text
        # never enters a buffer, including arbitrarily long quoted values.
        self.token()
        chars = [] if interested else None
        def append(code):
            if interested:
                if code > 127 or len(chars) >= 36:
                    self.fail('scalar')
                chars.append(chr(code))
        first = self.peek()
        if first in (44, 125):
            return None
        if first == 34:
            self.take()
            while True:
                code = self.take()
                if code == 34:
                    if self.peek() == 34:
                        self.take()
                        append(34)
                    else:
                        break
                else:
                    append(code)
            self.spaces()
            if self.peek() not in (44, 125):
                self.fail('syntax')
        else:
            while self.peek() not in (44, 125):
                if self.peek() in (None, 34, 123):
                    self.fail('syntax')
                append(self.take())
        return ''.join(chars) if interested else None

    def integer(self, text, maximum, code):
        if text is None or not 1 <= len(text) <= 3 or (len(text)>1 and text[0]=='0'):
            self.fail('count')
        value = 0
        for char in text:
            if not '0' <= char <= '9':
                self.fail('count')
            digit = ord(char)-48
            if value > (maximum-digit)//10:
                self.fail(code)
            value = value*10+digit
        return value

    def guid(self, text):
        if text is None or len(text) != 36:
            self.fail('guid')
        for i, char in enumerate(text):
            if i in (8, 13, 18, 23):
                if char != '-':
                    self.fail('guid')
            elif not ('0' <= char <= '9' or 'a' <= char <= 'f' or 'A' <= char <= 'F'):
                self.fail('guid')
        return text.lower()

    def component_done(self):
        self.component.role = 'ignore'
        self.components_left -= 1
        if self.container is not None:
            self.container.role = 'ignore'
        # Operations has a wrapper ancestor that must no longer impose a route.
        for frame in self.stack:
            if frame.role == 'wrapper':
                frame.role = 'ignore'

    def collection_done(self, frame):
        frame.role = 'ignore'
        self.collections_left -= 1
        if self.collections_left == 0:
            self.component_done()

    def value(self, frame, text):
        role, i = frame.role, frame.index
        if role == 'root' and i == 2:
            self.components_left = self.integer(text, self.limits.max_components, 'components')
        elif role == 'component' and i == 0:
            kind = self.guid(text)
            frame.kind = kind
            if kind in _DIRECT or kind == _OPERATIONS:
                if kind in self.kinds:
                    self.fail('component_duplicate')
                self.kinds.add(kind)
            else:
                self.component_done()
        elif role == 'container' and i == 2:
            count = self.integer(text, self.limits.max_collections, 'collections')
            if self.collection_total + count > self.limits.max_collections:
                self.fail('collections')
            self.collection_total += count
            self.collections_left = count
            if count == 0:
                self.component_done()
        elif role == 'collection':
            if i == 0:
                frame.kind = self.guid(text)
                if frame.kind != CATALOG_TYPE:
                    self.collection_done(frame)
                else:
                    self.catalog_count += 1
            elif i == 1:
                frame.count = self.integer(text, self.limits.max_references, 'references')
                if len(self.refs) + frame.count > self.limits.max_references:
                    self.fail('references')
                if frame.count == 0:
                    self.collection_done(frame)
            else:
                key = self.guid(text)
                if key == '00000000-0000-0000-0000-000000000000':
                    self.fail('zero_guid')
                if key in self.seen:
                    self.fail('duplicate')
                if len(self.refs) >= self.limits.max_references:
                    self.fail('references')
                self.seen.add(key)
                self.refs.append(key)
                if i == frame.count + 1:
                    self.collection_done(frame)
        elif (role == 'root' and i >= 3 or role == 'component' and i == 1
              or role == 'wrapper' and i == 1 or role == 'container' and i >= 3):
            self.fail('syntax')

    def run(self):
        if self.data.startswith(b'\xef\xbb\xbf'):
            self.pos = 3
        self.spaces()
        if self.peek() != 123:
            self.fail('syntax')
        self.take()
        self.push('root')
        while self.stack:
            frame = self.stack[-1]
            self.spaces()
            if frame.after:
                boundary = self.peek()
                if boundary == 44:
                    self.take()
                    frame.index += 1
                    frame.after = False
                elif boundary == 125:
                    self.token()
                    self.take()
                    if frame.role != 'ignore':
                        self.fail('count')
                    self.stack.pop()
                else:
                    self.fail('syntax')
                continue
            if self.peek() == 123:
                role = self.object_role(frame)
                self.take()
                frame.after = True
                self.push(role)
            else:
                text = self.scalar(self.wanted(frame))
                self.value(frame, text)
                frame.after = True
                if self.components_left == 0:
                    if not self.catalog_count:
                        self.fail('no_catalog')
                    if not self.refs:
                        self.fail('no_positive')
                    return CatalogReferences(self.catalog_count, tuple(self.refs))
        self.fail('count')


def project_catalog_references(data, *, budget, limits=None):
    """Reserve against the caller's existing cumulative budget before parsing.

    The caller owns immutable decoded bytes; no budget reset/refund or reader is
    created. Every event also charges the same token counter before state growth.
    The fixed output weight bounds retained representation, not Python VM RSS.
    """
    if type(data) is not bytes:
        raise CatalogReferenceError('input_type')
    if limits is None:
        limits = CatalogReferenceLimits()
    if type(limits) is not CatalogReferenceLimits:
        raise CatalogReferenceError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise CatalogReferenceError('input_bytes')
    budget.charge('bytes_processed', 3*len(data))
    budget.charge('output_bytes', OUTPUT_RESERVATION)
    return _Walk(data, budget, limits).run()
