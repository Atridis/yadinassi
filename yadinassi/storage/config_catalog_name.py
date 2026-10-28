"""Partial positional Catalog prefixes, never whole-document validation.

The original Name/standard contracts do not interpret the embedded UUID. The
separate opt-in identity contract parses it but does not verify external binding.

Independently written bounded walk. Only the visited prefix is validated. The
caller supplies immutable decoded bytes and its existing cumulative budget.
"""
from dataclasses import dataclass

PROFILE_IDENTIFIER = 'config_catalog_name_prefix_v1'
NAME_PATH = (1, 9, 1, 2)
OUTPUT_RESERVATION = 65536


class CatalogNameError(Exception):
    codes = frozenset(('input_type', 'limits_type', 'limit', 'input_bytes',
                       'tokens', 'depth', 'syntax', 'encoding', 'control',
                       'bom', 'missing_name', 'expected_object',
                       'expected_scalar', 'empty_name', 'name_bytes', 'name_chars'))

    def __init__(self, code):
        if type(code) is not str or code not in self.codes:
            raise ValueError('invalid catalog name diagnostic')
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CatalogNameLimits:
    max_input_bytes: int = 4194304
    max_tokens: int = 131072
    max_depth: int = 64
    max_name_bytes: int = 1024
    max_name_chars: int = 256

    def __post_init__(self):
        for key, ceiling in (('max_input_bytes', 4194304), ('max_tokens', 131072),
                             ('max_depth', 64), ('max_name_bytes', 1024),
                             ('max_name_chars', 256)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise CatalogNameError('limit')


@dataclass(frozen=True, slots=True)
class CatalogNamePrefix:
    """Private candidate name, not a public diagnostic or verified identity."""
    name: str


class _Cursor:
    def __init__(self, data, budget, limits):
        self.data, self.budget, self.limits = data, budget, limits
        self.position = self.tokens = 0
        self.depth = min(limits.max_depth, budget.limits.max_tree_depth)

    def peek(self):
        return self.data[self.position] if self.position < len(self.data) else None

    def character(self):
        """Decode exactly the consumed character, never a suffix buffer."""
        first = self.peek()
        if first is None:
            raise CatalogNameError('syntax')
        if first < 128:
            if first == 127 or first < 32 and first not in (10, 13):
                raise CatalogNameError('control')
            self.position += 1
            return first
        if 194 <= first <= 223:
            width, minimum, value = 2, 128, first & 31
        elif 224 <= first <= 239:
            width, minimum, value = 3, 2048, first & 15
        elif 240 <= first <= 244:
            width, minimum, value = 4, 65536, first & 7
        else:
            raise CatalogNameError('encoding')
        if self.position + width > len(self.data):
            raise CatalogNameError('encoding')
        for offset in range(1, width):
            byte = self.data[self.position + offset]
            if not 128 <= byte <= 191:
                raise CatalogNameError('encoding')
            value = (value << 6) | (byte & 63)
        if value < minimum or 0xD800 <= value <= 0xDFFF or value > 0x10FFFF:
            raise CatalogNameError('encoding')
        if value == 0xFEFF:
            raise CatalogNameError('bom')
        self.position += width
        return value

    def spaces(self):
        while self.peek() in (32, 10, 13):
            self.character()

    def event(self):
        if self.tokens >= self.limits.max_tokens:
            raise CatalogNameError('tokens')
        self.budget.charge('tokens', 1)
        self.tokens += 1

    def scalar(self, wanted):
        self.event()
        characters = [] if wanted else None
        encoded = 0

        def retain(value):
            nonlocal encoded
            if not wanted:
                return
            if value < 32 or value == 127:
                raise CatalogNameError('control')
            size = 1 if value < 128 else 2 if value < 2048 else 3 if value < 65536 else 4
            if encoded + size > self.limits.max_name_bytes:
                raise CatalogNameError('name_bytes')
            if len(characters) >= self.limits.max_name_chars:
                raise CatalogNameError('name_chars')
            encoded += size
            characters.append(chr(value))

        if self.peek() == 34:
            self.character()
            while True:
                value = self.character()
                if value != 34:
                    retain(value)
                elif self.peek() == 34:
                    self.character()
                    retain(34)
                else:
                    break
            self.spaces()
            if self.peek() not in (44, 125):
                raise CatalogNameError('syntax')
        else:
            while self.peek() not in (44, 125):
                if self.peek() in (None, 34, 123):
                    raise CatalogNameError('syntax')
                retain(self.character())
        if wanted:
            if not characters:
                raise CatalogNameError('empty_name')
            return ''.join(characters)
        return None

    def run(self):
        if self.data.startswith(b'\xef\xbb\xbf'):
            self.position = 3
        self.spaces()
        if self.peek() != 123:
            raise CatalogNameError('syntax')
        self.event()
        self.character()
        # Frames: child index, matched route length (None for opaque), after-value.
        # No per-token path allocation or retained opaque scalars.
        stack = [[0, 0, False]]
        while stack:
            frame = stack[-1]
            self.spaces()
            if frame[2]:
                if self.peek() == 44:
                    self.character()
                    frame[0] += 1
                    frame[2] = False
                elif self.peek() == 125:
                    self.event()
                    self.character()
                    if frame[1] is not None:
                        raise CatalogNameError('missing_name')
                    stack.pop()
                else:
                    raise CatalogNameError('syntax')
                continue
            route = frame[1]
            on_path = route is not None and frame[0] == NAME_PATH[route]
            wanted = on_path and route == len(NAME_PATH) - 1
            if self.peek() == 123:
                if wanted:
                    raise CatalogNameError('expected_scalar')
                if len(stack) >= self.depth:
                    raise CatalogNameError('depth')
                self.event()
                self.character()
                frame[2] = True
                stack.append([0, route + 1 if on_path else None, False])
            else:
                if on_path and not wanted:
                    raise CatalogNameError('expected_object')
                value = self.scalar(wanted)
                if wanted:
                    # scalar() has verified a real comma/close boundary, without
                    # consuming it or inspecting any following byte.
                    return CatalogNamePrefix(value)
                frame[2] = True
        raise CatalogNameError('missing_name')


def project_catalog_name_prefix(data, *, budget, limits=None):
    """Project a name only; expected UUID/name and declaration keys are not inputs.

    Reserve before cursor/stack/name allocations. Processing and representation
    weights are conservative admission accounting, not exact Python VM RSS.
    Failure retains every charge, and the supplied budget is never replaced.
    """
    if type(data) is not bytes:
        raise CatalogNameError('input_type')
    if limits is None:
        limits = CatalogNameLimits()
    if type(limits) is not CatalogNameLimits:
        raise CatalogNameError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise CatalogNameError('input_bytes')
    budget.charge('bytes_processed', 4 * len(data))
    budget.charge('output_bytes', OUTPUT_RESERVATION)
    return _Cursor(data, budget, limits).run()


STANDARD_PROFILE_IDENTIFIER = 'config_catalog_standard_prefix_v1'
STANDARD_PATHS = (NAME_PATH, (1, 17), (1, 18), (1, 19))
STANDARD_OUTPUT_RESERVATION = 131072


class CatalogStandardError(CatalogNameError):
    codes = CatalogNameError.codes | frozenset((
        'missing_field', 'integer_syntax', 'integer_bound', 'code_type'))


@dataclass(frozen=True, slots=True)
class CatalogStandardLimits(CatalogNameLimits):
    # Admission bound, not a claim about the platform's valid field lengths.
    max_length: int = 2147483647

    def __post_init__(self):
        try:
            CatalogNameLimits.__post_init__(self)
        except CatalogNameError as error:
            raise CatalogStandardError(error.code) from None
        if type(self.max_length) is not int or not 0 <= self.max_length <= 2147483647:
            raise CatalogStandardError('limit')


@dataclass(frozen=True, slots=True)
class CatalogStandardPrefix:
    """Private partial metadata; code_type is 0 (Number) or 1 (String)."""
    name: str
    code_length: int
    code_type: int
    description_length: int


class _StandardCursor(_Cursor):
    def integer(self, *, code_type):
        self.event()
        value = digits = 0
        first = self.peek()
        while self.peek() not in (44, 125):
            byte = self.peek()
            # Selected integers deliberately admit only canonical bare ASCII.
            if byte is None or not 48 <= byte <= 57 or digits and first == 48:
                raise CatalogStandardError('integer_syntax')
            if digits >= 10:
                raise CatalogStandardError('integer_bound')
            value = value * 10 + byte - 48
            digits += 1
            self.character()
            if value > self.limits.max_length and not code_type:
                raise CatalogStandardError('integer_bound')
            if value > 2147483647:
                raise CatalogStandardError('integer_bound')
        if not digits:
            raise CatalogStandardError('integer_syntax')
        if code_type and value not in (0, 1):
            raise CatalogStandardError('code_type')
        return value

    def run(self):
        if self.data.startswith(b'\xef\xbb\xbf'):
            self.position = 3
        self.spaces()
        if self.peek() != 123:
            raise CatalogStandardError('syntax')
        self.event()
        self.character()
        # Fixed target routes only: retain no paths inside opaque subtrees.
        # Frames: child index, shared route prefix or None, after-value.
        stack = [[0, (), False]]
        values = []
        while stack:
            frame = stack[-1]
            self.spaces()
            if frame[2]:
                if self.peek() == 44:
                    self.character()
                    frame[0] += 1
                    frame[2] = False
                elif self.peek() == 125:
                    self.event()
                    self.character()
                    route = frame[1]
                    if route is not None and any(
                            path[:len(route)] == route for path in STANDARD_PATHS[len(values):]):
                        raise CatalogStandardError('missing_field')
                    stack.pop()
                else:
                    raise CatalogStandardError('syntax')
                continue
            route = None if frame[1] is None else frame[1] + (frame[0],)
            target = STANDARD_PATHS[len(values)]
            wanted = route == target
            on_path = route is not None and any(
                path[:len(route)] == route for path in STANDARD_PATHS[len(values):])
            if self.peek() == 123:
                if wanted:
                    raise CatalogStandardError('expected_scalar')
                if len(stack) >= self.depth:
                    raise CatalogStandardError('depth')
                self.event()
                self.character()
                frame[2] = True
                stack.append([0, route if on_path else None, False])
            else:
                if on_path and not wanted:
                    raise CatalogStandardError('expected_object')
                if wanted:
                    value = (self.scalar(True) if not values else
                             self.integer(code_type=len(values) == 2))
                    values.append(value)
                    if len(values) == len(STANDARD_PATHS):
                        # Last scalar established a delimiter; leave suffix alone.
                        return CatalogStandardPrefix(*values)
                else:
                    self.scalar(False)
                frame[2] = True
        raise CatalogStandardError('missing_field')


def project_catalog_standard_prefix(data, *, budget, limits=None):
    """Read Name and three standard scalars, without expected values or I/O.

    Only the visited prefix is checked. Numeric limits describe this admission
    subset, not the platform's complete semantic range. Charges are retained on
    failure; there is one traversal and no call to the Name-only entrypoint.
    """
    if type(data) is not bytes:
        raise CatalogStandardError('input_type')
    if limits is None:
        limits = CatalogStandardLimits()
    if type(limits) is not CatalogStandardLimits:
        raise CatalogStandardError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise CatalogStandardError('input_bytes')
    budget.charge('bytes_processed', 4 * len(data))
    budget.charge('output_bytes', STANDARD_OUTPUT_RESERVATION)
    try:
        return _StandardCursor(data, budget, limits).run()
    except CatalogNameError as error:
        raise CatalogStandardError(error.code) from None


# Separate opt-in contract: earlier Name/standard prefixes ignore this identity.
IDENTITY_PROFILE_IDENTIFIER = 'config_catalog_identity_prefix_v1'
UUID_PATH = (1, 9, 1, 1, 2)
IDENTITY_PATHS = (UUID_PATH,) + STANDARD_PATHS
IDENTITY_OUTPUT_RESERVATION = 131072


class CatalogIdentityError(CatalogStandardError):
    codes = CatalogStandardError.codes | frozenset(('uuid_syntax', 'uuid_zero'))


@dataclass(frozen=True, slots=True)
class CatalogIdentityLimits(CatalogStandardLimits):
    def __post_init__(self):
        try:
            CatalogStandardLimits.__post_init__(self)
        except CatalogStandardError as error:
            raise CatalogIdentityError(error.code) from None


@dataclass(frozen=True, slots=True)
class CatalogIdentityPrefix:
    """Private parsed fields, not verified identity or a public diagnostic."""
    metadata_uuid: str
    name: str
    code_length: int
    code_type: int
    description_length: int


class _IdentityCursor(_StandardCursor):
    def uuid(self):
        self.event()
        start = self.position
        nonzero = False
        # This fixed-width admission grammar is narrower than general UUID text.
        # Inspect at most 36 ASCII bytes and a real delimiter before allocating.
        for offset in range(36):
            byte = self.peek()
            if offset in (8, 13, 18, 23):
                valid = byte == 45
            else:
                valid = byte is not None and (48 <= byte <= 57 or
                                              65 <= byte <= 70 or 97 <= byte <= 102)
                nonzero = nonzero or valid and byte != 48
            if not valid:
                raise CatalogIdentityError('uuid_syntax')
            self.character()
        if self.peek() not in (44, 125):
            raise CatalogIdentityError('uuid_syntax')
        if not nonzero:
            raise CatalogIdentityError('uuid_zero')
        return self.data[start:self.position].decode('ascii').lower()

    def run(self):
        if self.data.startswith(b'\xef\xbb\xbf'):
            self.position = 3
        self.spaces()
        if self.peek() != 123:
            raise CatalogIdentityError('syntax')
        self.event()
        self.character()
        # Fixed target routes only: retain no paths inside opaque subtrees.
        # Frames: child index, shared route prefix or None, after-value.
        stack = [[0, (), False]]
        values = []
        while stack:
            frame = stack[-1]
            self.spaces()
            if frame[2]:
                if self.peek() == 44:
                    self.character()
                    frame[0] += 1
                    frame[2] = False
                elif self.peek() == 125:
                    self.event()
                    self.character()
                    route = frame[1]
                    if route is not None and any(
                            path[:len(route)] == route for path in IDENTITY_PATHS[len(values):]):
                        raise CatalogIdentityError('missing_field')
                    stack.pop()
                else:
                    raise CatalogIdentityError('syntax')
                continue
            route = None if frame[1] is None else frame[1] + (frame[0],)
            target = IDENTITY_PATHS[len(values)]
            wanted = route == target
            on_path = route is not None and any(
                path[:len(route)] == route for path in IDENTITY_PATHS[len(values):])
            if self.peek() == 123:
                if wanted:
                    raise CatalogIdentityError('expected_scalar')
                if len(stack) >= self.depth:
                    raise CatalogIdentityError('depth')
                self.event()
                self.character()
                frame[2] = True
                stack.append([0, route if on_path else None, False])
            else:
                if on_path and not wanted:
                    raise CatalogIdentityError('expected_object')
                if wanted:
                    value = (self.uuid() if not values else self.scalar(True) if len(values) == 1
                             else self.integer(code_type=len(values) == 3))
                    values.append(value)
                    if len(values) == len(IDENTITY_PATHS):
                        # Last scalar established a delimiter; leave suffix alone.
                        return CatalogIdentityPrefix(*values)
                else:
                    self.scalar(False)
                frame[2] = True
        raise CatalogIdentityError('missing_field')



def project_catalog_identity_prefix(data, *, budget, limits=None):
    """Read private UUID/Name/standard fields once, with no expected values or I/O.

    Nonzero canonical-width bare UUID is a local admission policy, not a claim
    about every platform representation. Only the visited prefix is validated.
    Existing Name and standard entrypoints retain their independent contracts.
    """
    if type(data) is not bytes:
        raise CatalogIdentityError('input_type')
    if limits is None:
        limits = CatalogIdentityLimits()
    if type(limits) is not CatalogIdentityLimits:
        raise CatalogIdentityError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise CatalogIdentityError('input_bytes')
    budget.charge('bytes_processed', 4 * len(data))
    budget.charge('output_bytes', IDENTITY_OUTPUT_RESERVATION)
    try:
        return _IdentityCursor(data, budget, limits).run()
    except CatalogNameError as error:
        raise CatalogIdentityError(error.code) from None
