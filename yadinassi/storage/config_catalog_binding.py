"""Private CONFIG/DBNames binding compiler for one measured owned table shape.

No descriptor, native projection or XML expectation enters this compiler.
Standard names/order/nullability/case are a frozen *owned-profile* observation
(run 40181431793, source 56e07ca0, report SHA256 abe1cee5d69a4721da82d4efa2f067c839ddda47d9c62956273b45f909d06651).
Lengths and numeric qualifiers are configuration values, not fixture constants.
Finite synthetic admission below is not native acceptance of other layouts.
"""
from dataclasses import dataclass
import re

from .config_catalog_name import CatalogIdentityPrefix
from .config_catalog_attributes import CatalogAttribute, CatalogAttributes
from .filedb_dbnames import DBNamesEntry, DBNamesIndex, DBNAMES_PROFILE_IDENTIFIER

PROFILE_IDENTIFIER = 'owned_catalog_string_code_two_attributes_v1'
_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z', re.ASCII)
_KIND = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,31}\Z', re.ASCII)
_ZERO = '00000000-0000-0000-0000-000000000000'


class CatalogBindingError(Exception):
    codes = frozenset(('profile', 'limits', 'input_type', 'identity', 'name',
                       'standard_profile', 'attribute_shape', 'attribute_identity',
                       'attribute_type', 'qualifiers', 'dbnames_shape', 'dbnames_entry',
                       'dbnames_missing', 'dbnames_ambiguous', 'dbnames_kind',
                       'dbnames_id', 'dbnames_collision', 'record_bytes'))

    def __init__(self, code):
        if type(code) is not str or code not in self.codes:
            raise ValueError('invalid catalog binding diagnostic')
        self.code = code
        super().__init__(code)


def _fail(code):
    raise CatalogBindingError(code)


@dataclass(frozen=True, slots=True)
class CatalogBindingProfile:
    identifier: str

    def __post_init__(self):
        if type(self.identifier) is not str or self.identifier != PROFILE_IDENTIFIER:
            _fail('profile')


@dataclass(frozen=True, slots=True)
class CatalogBindingLimits:
    max_dbnames_entries: int = 4096
    max_record_bytes: int = 4096
    max_string_length: int = 2047
    max_numeric_precision: int = 38

    def __post_init__(self):
        for name, ceiling in (('max_dbnames_entries', 4096), ('max_record_bytes', 4096),
                              ('max_string_length', 2047), ('max_numeric_precision', 38)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                _fail('limits')


@dataclass(frozen=True, slots=True)
class BoundCatalogAttribute:
    metadata_uuid: str
    name: str
    physical_name: str
    type_token: str
    qualifiers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BoundFieldPlacement:
    declaration: tuple[str, str, int, int, int, str]
    offset: int
    width: int


@dataclass(frozen=True, slots=True)
class CatalogBinding:
    metadata_uuid: str
    name: str
    table_name: str
    declarations: tuple[tuple[str, str, int, int, int, str], ...]
    attributes: tuple[BoundCatalogAttribute, ...]
    recordlock: str
    format_item: int
    record_size: int
    code_length: int
    placements: tuple[BoundFieldPlacement, ...]


def _uuid(value, *, nonzero=True):
    return (type(value) is str and len(value) == 36 and _UUID.fullmatch(value) is not None
            and (not nonzero or value != _ZERO))


def _name(value):
    if type(value) is not str or not 1 <= len(value) <= 256:
        _fail('name')
    try:
        if len(value.encode('utf-8')) > 1024:
            _fail('name')
    except UnicodeEncodeError:
        _fail('name')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        _fail('name')


def compile_catalog_binding(identity, attributes, dbnames, *, profile, budget, limits=None):
    """Compile independently expected declarations; never inspect physical data.

    Caller supplies complete parsed CONFIG collections and DBNames on its single
    lifetime budget. This function does not establish their file provenance or
    CONFIG applied-state identity. Old APIs and decoder admissions are unchanged.
    Reservation precedes scans/retained construction and is never refunded.
    """
    if type(profile) is not CatalogBindingProfile:
        _fail('profile')
    if limits is not None and type(limits) is not CatalogBindingLimits:
        _fail('limits')
    limits = limits if limits is not None else CatalogBindingLimits()
    if (type(identity) is not CatalogIdentityPrefix or type(attributes) is not CatalogAttributes
            or type(dbnames) is not DBNamesIndex):
        _fail('input_type')
    if (type(dbnames.entries) is not tuple or len(dbnames.entries) > limits.max_dbnames_entries
            or type(dbnames.declared_count) is not int or dbnames.declared_count != len(dbnames.entries)
            or type(dbnames.profile) is not str or dbnames.profile != DBNAMES_PROFILE_IDENTIFIER):
        _fail('dbnames_shape')
    # At most three UUID targets, seven declarations and three bounded names.
    # Each entry's relevant text is bounded below (36+32); three linear joins
    # and collision scans fit this processing reservation. No full index copy.
    budget.charge('output_bytes', 8192)
    budget.charge('bytes_processed', 4096 + 1024 * len(dbnames.entries))
    budget.charge('tokens', 64 + 8 * len(dbnames.entries))
    if not _uuid(identity.metadata_uuid):
        _fail('identity')
    _name(identity.name)
    if (type(identity.code_type) is not int or identity.code_type != 1
            or type(identity.description_length) is not int or identity.description_length != 0
            or type(identity.code_length) is not int or not 1 <= identity.code_length <= limits.max_string_length):
        _fail('standard_profile')
    if type(attributes.attributes) is not tuple or len(attributes.attributes) != 2:
        _fail('attribute_shape')
    first, second = attributes.attributes
    if type(first) is not CatalogAttribute or type(second) is not CatalogAttribute:
        _fail('attribute_shape')
    for item in (first, second):
        if not _uuid(item.metadata_uuid):
            _fail('attribute_identity')
        _name(item.name)
        if (type(item.qualifiers) is not tuple or len(item.qualifiers) > 3
                or any(type(x) is not int for x in item.qualifiers)):
            _fail('qualifiers')
    targets = (identity.metadata_uuid, first.metadata_uuid, second.metadata_uuid)
    if len(set(targets)) != 3 or first.name == second.name:
        _fail('attribute_identity')
    if type(first.type_token) is not str or type(second.type_token) is not str or first.type_token != 'S' or second.type_token != 'N':
        _fail('attribute_type')
    if (len(first.qualifiers) != 2 or first.qualifiers[1] != 1
            or not 1 <= first.qualifiers[0] <= limits.max_string_length
            or len(second.qualifiers) != 3 or second.qualifiers[2] != 0
            or not 1 <= second.qualifiers[0] <= limits.max_numeric_precision
            or not 0 <= second.qualifiers[1] <= second.qualifiers[0]):
        _fail('qualifiers')
    selected = [None, None, None]
    for ordinal, entry in enumerate(dbnames.entries):
        if (type(entry) is not DBNamesEntry or not _uuid(entry.uuid, nonzero=False)
                or type(entry.kind) is not str or len(entry.kind) > 32 or _KIND.fullmatch(entry.kind) is None
                or type(entry.id) is not int or not 0 <= entry.id <= 2147483647
                or type(entry.ordinal) is not int or entry.ordinal != ordinal):
            _fail('dbnames_entry')
        for position, target in enumerate(targets):
            if entry.uuid == target:
                if selected[position] is not None:
                    _fail('dbnames_ambiguous')
                if entry.kind != ('Reference' if position == 0 else 'Fld'):
                    _fail('dbnames_kind')
                if entry.id == 0:
                    _fail('dbnames_id')
                selected[position] = entry
    if any(item is None for item in selected):
        _fail('dbnames_missing')
    if len({item.id for item in selected}) != 3:
        _fail('dbnames_collision')
    for entry in dbnames.entries:
        for chosen in selected:
            if entry is not chosen and entry.kind == chosen.kind and entry.id == chosen.id:
                _fail('dbnames_collision')
    table_name = '_Reference' + str(selected[0].id)
    string_name, number_name = ('_FLD' + str(selected[i].id) for i in (1, 2))
    precision, scale, _ = second.qualifiers
    declarations = (
        ('_IDRREF', 'B', 0, 16, 0, 'CS'),
        ('_VERSION', 'RV', 0, 0, 0, 'CS'),
        ('_MARKED', 'L', 0, 0, 0, 'CS'),
        ('_PREDEFINEDID', 'B', 0, 16, 0, 'CS'),
        ('_CODE', 'NVC', 0, identity.code_length, 0, 'CI'),
        (string_name, 'NVC', 0, first.qualifiers[0], 0, 'CI'),
        (number_name, 'N', 0, precision, scale, 'CS'))
    record_size = 1 + 16 + 16 + 1 + 16 + (2 + 2 * identity.code_length) + (2 + 2 * first.qualifiers[0]) + (precision + 2) // 2
    if record_size > limits.max_record_bytes:
        _fail('record_bytes')
    widths = (16, 16, 1, 16, 2 + 2 * identity.code_length,
              2 + 2 * first.qualifiers[0], (precision + 2) // 2)
    offsets = [0] * 7
    cursor = 1
    for index in (1, 0, 2, 3, 4, 5, 6):
        offsets[index] = cursor
        cursor += widths[index]
    placements = tuple(BoundFieldPlacement(declaration, offsets[i], widths[i])
                       for i, declaration in enumerate(declarations))
    bound = tuple(BoundCatalogAttribute(item.metadata_uuid, item.name, physical, item.type_token, item.qualifiers)
                  for item, physical in ((first, string_name), (second, number_name)))
    return CatalogBinding(identity.metadata_uuid, identity.name, table_name, declarations, bound, '0', 0, record_size, identity.code_length, placements)
