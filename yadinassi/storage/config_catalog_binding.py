"""Private CONFIG/DBNames binding compiler for one measured owned table shape.

No descriptor, native projection or XML expectation enters this compiler.
Standard names/order/nullability/case are a frozen *owned-profile* observation
(run 40181431793, source 56e07ca0, report SHA256 abe1cee5d69a4721da82d4efa2f067c839ddda47d9c62956273b45f909d06651).
Lengths and numeric qualifiers are configuration values, not fixture constants.
Positive Description NVC placement was independently observed at configured
lengths 8 and 17 with Payload32 (native run 40971133699, source a318b990).
Other bounded lengths are structural generalization, not native range proof.
The zero-code opt-in is limited to four observed String/CodeLength0 shapes:
Description0/8, Payload32/64 and Amount9,2 (run 41181474017, source6e407b65).
These zero-code bounds are conservative measured-shape admission, not a range
generalization. Existing positive-code profiles keep their prior generalized
qualifier ranges. UUIDs, names and DBNames IDs are independently resolved inputs.
There is no physical _CODE declaration; no Code API value is synthesized.
Finite synthetic admission below is not native acceptance of other layouts.
"""
from dataclasses import dataclass, field
import re

from .config_catalog_name import CatalogIdentityPrefix
from .config_catalog_attributes import CatalogAttribute, CatalogAttributes
from .filedb_dbnames import DBNamesEntry, DBNamesIndex, DBNAMES_PROFILE_IDENTIFIER

PROFILE_IDENTIFIER = 'owned_catalog_string_code_two_attributes_v1'
ZERO_PROFILE_IDENTIFIER = 'owned_catalog_zero_string_code_two_attributes_v1'
NUMERIC_PROFILE_IDENTIFIER = 'owned_catalog_string_or_number_code_two_attributes_v1'
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
        if type(self.identifier) is not str or self.identifier not in (PROFILE_IDENTIFIER, NUMERIC_PROFILE_IDENTIFIER, ZERO_PROFILE_IDENTIFIER):
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
    description_length: int = 0
    code_type: int = field(default=1, kw_only=True)


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
    if (type(profile) is not CatalogBindingProfile
            or type(profile.identifier) is not str
            or profile.identifier not in (PROFILE_IDENTIFIER, NUMERIC_PROFILE_IDENTIFIER, ZERO_PROFILE_IDENTIFIER)):
        _fail('profile')
    if limits is not None and type(limits) is not CatalogBindingLimits:
        _fail('limits')
    limits = limits if limits is not None else CatalogBindingLimits()
    # Frozen dataclasses may still be forged through object.__setattr__.
    CatalogBindingLimits.__post_init__(limits)
    if (type(identity) is not CatalogIdentityPrefix or type(attributes) is not CatalogAttributes
            or type(dbnames) is not DBNamesIndex):
        _fail('input_type')
    if (type(dbnames.entries) is not tuple or len(dbnames.entries) > limits.max_dbnames_entries
            or type(dbnames.declared_count) is not int or dbnames.declared_count != len(dbnames.entries)
            or type(dbnames.profile) is not str or dbnames.profile != DBNAMES_PROFILE_IDENTIFIER):
        _fail('dbnames_shape')
    # At most three UUID targets, eight declarations and three bounded names.
    # Each entry's relevant text is bounded below (36+32); three linear joins
    # and collision scans fit this processing reservation. No full index copy.
    budget.charge('output_bytes', 8192)
    budget.charge('bytes_processed', 4096 + 1024 * len(dbnames.entries))
    budget.charge('tokens', 64 + 8 * len(dbnames.entries))
    if not _uuid(identity.metadata_uuid):
        _fail('identity')
    _name(identity.name)
    if (type(identity.code_type) is not int or identity.code_type not in (0, 1)
            or (identity.code_type == 0 and profile.identifier != NUMERIC_PROFILE_IDENTIFIER)
            or type(identity.description_length) is not int
            or not 0 <= identity.description_length <= limits.max_string_length
            or type(identity.code_length) is not int
            or not (0 if profile.identifier == ZERO_PROFILE_IDENTIFIER else 1) <= identity.code_length <= (limits.max_numeric_precision if identity.code_type == 0 else limits.max_string_length)):
        _fail('standard_profile')
    zero_code = profile.identifier == ZERO_PROFILE_IDENTIFIER
    if zero_code and (identity.code_type != 1 or identity.code_length != 0
                      or identity.description_length not in (0, 8)):
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
    if zero_code and (first.qualifiers not in ((32, 1), (64, 1))
                      or second.qualifiers != (9, 2, 0)):
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
        ('_CODE', 'N' if identity.code_type == 0 else 'NVC', 0, identity.code_length, 0, 'CS' if identity.code_type == 0 else 'CI'),
        (string_name, 'NVC', 0, first.qualifiers[0], 0, 'CI'),
        (number_name, 'N', 0, precision, scale, 'CS'))
    widths = (16, 16, 1, 16, (identity.code_length + 2) // 2 if identity.code_type == 0 else 2 + 2 * identity.code_length,
              2 + 2 * first.qualifiers[0], (precision + 2) // 2)
    standard_count = 5
    if zero_code:
        declarations = declarations[:4] + declarations[5:]
        widths = widths[:4] + widths[5:]
        standard_count = 4
    if identity.description_length:
        declarations = declarations[:standard_count] + (('_DESCRIPTION', 'NVC', 0,
            identity.description_length, 0, 'CI'),) + declarations[standard_count:]
        widths = widths[:standard_count] + (2 + 2 * identity.description_length,) + widths[standard_count:]
    record_size = 1 + sum(widths)
    if record_size > limits.max_record_bytes:
        _fail('record_bytes')
    offsets = [0] * len(widths)
    cursor = 1
    for index in (1, 0, *range(2, len(widths))):
        offsets[index] = cursor
        cursor += widths[index]
    placements = tuple(BoundFieldPlacement(declaration, offsets[i], widths[i])
                       for i, declaration in enumerate(declarations))
    bound = tuple(BoundCatalogAttribute(item.metadata_uuid, item.name, physical, item.type_token, item.qualifiers)
                  for item, physical in ((first, string_name), (second, number_name)))
    return CatalogBinding(identity.metadata_uuid, identity.name, table_name, declarations, bound, '0', 0, record_size, identity.code_length, placements, identity.description_length, code_type=identity.code_type)
