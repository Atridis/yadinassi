"""Read-only catalog managers over the bounded offline CONFIG/row profile.

Native41214218572 establishes the bounded multi-row scenario and cursor cycle.
No live session or writes exist; advanced ordering/collation remain restricted.
"""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from .dates import BSLDate
from .catalog_types import BSLCatalogReference, BSLCatalogType
from .unique_identifiers import BSLUUID
from .values import BSLObject, HostFunction

_OMITTED = object()
_ZERO = UUID(int=0)


@dataclass(frozen=True, slots=True)
class CatalogCardField:
    """Logical adapter seam, NOT a CONFIG token or physical declaration.

    !todo Bind these descriptors only after mixed-field native evidence proves
    CONFIG type/target mapping and exact physical decoding. The current storage
    compiler never creates this type, so public file admission stays unchanged.
    """
    name: str
    physical_name: str
    kind: str
    target_metadata_uuid: UUID | None = None

    def __post_init__(self):
        if (type(self.name) is not str or not 1 <= len(self.name) <= 256
                or type(self.physical_name) is not str or not 1 <= len(self.physical_name) <= 64):
            raise ValueError('catalog card field requires bounded names')
        if type(self.kind) is not str or self.kind not in ('string', 'number', 'boolean', 'datetime', 'catalog_ref'):
            raise ValueError('unsupported catalog card field kind')
        if self.kind == 'catalog_ref':
            if type(self.target_metadata_uuid) is not UUID or self.target_metadata_uuid.int == 0:
                raise ValueError('catalog reference field requires target metadata UUID')
        elif self.target_metadata_uuid is not None:
            raise ValueError('scalar field cannot have a reference target')

    def project(self, value, catalogs):
        expected = {'string': str, 'number': Decimal, 'boolean': bool,
                    'datetime': BSLDate, 'catalog_ref': UUID}[self.kind]
        if type(value) is not expected:
            # No bytes/strings guessed into references, dates or booleans.
            raise TypeError('catalog card logical field type mismatch')
        if self.kind == 'number' and not value.is_finite():
            raise ValueError('catalog card number must be finite')
        if self.kind == 'datetime':
            return value.require_known()
        if self.kind == 'catalog_ref':
            return catalogs._manager_by_metadata_uuid(self.target_metadata_uuid)._ref(value)
        return value

    def default(self, catalogs):
        if self.kind == 'catalog_ref':
            return catalogs._manager_by_metadata_uuid(self.target_metadata_uuid).empty_ref()
        return {'string': '', 'number': Decimal(0), 'boolean': False,
                'datetime': BSLDate(0)}[self.kind]


class BSLCatalogs(BSLObject):
    def __init__(self, metadata, context):
        self._metadata = metadata
        self._context = context
        self._managers = {}

    def get_member(self, name):
        return self.get_index(name)

    def get_index(self, name):
        if type(name) is not str:
            raise TypeError('catalog name requires String')
        item = self._metadata._snapshot().get(name.casefold())
        if item is None:
            raise ValueError('catalog name not found')
        key = item._name.casefold()
        if key not in self._managers:
            self._managers[key] = BSLCatalogManager(self, item)
        return self._managers[key]

    def _manager_by_metadata_uuid(self, metadata_uuid):
        # The target is catalog metadata identity, never a native Ref TypeId.
        matches = [item for item in self._metadata._snapshot().values()
                   if item._metadata_uuid is not None and UUID(item._metadata_uuid) == metadata_uuid]
        if len(matches) != 1:
            raise ValueError('catalog target metadata identity not found or ambiguous')
        return self.get_index(matches[0]._name)

    def set_index(self, name, value):
        raise ValueError('catalog managers are read-only')

    def type_by_name(self, name):
        from .type_values import type_by_name
        if type(name) is str:
            prefix, separator, catalog = name.partition('.')
            families = {'справочникссылка': '_value_type', 'catalogref': '_value_type',
                        'справочникменеджер': '_manager_type', 'catalogmanager': '_manager_type',
                        'справочниквыборка': '_selection_type', 'catalogselection': '_selection_type'}
            if separator and prefix.casefold() in families:
                return getattr(self.get_index(catalog), families[prefix.casefold()])
        return type_by_name(name)

    def __str__(self):
        raise ValueError('catalog manager presentation is unsupported')


class BSLCatalogManager(BSLObject):
    def __init__(self, catalogs, metadata):
        self._catalogs = catalogs
        self._metadata = metadata
        if type(metadata._metadata_uuid) is not str:
            raise ValueError('catalog metadata identity is required')
        self._value_type = BSLCatalogType(UUID(metadata._metadata_uuid), metadata._name,
                                        catalogs._metadata)
        self._manager_type = BSLCatalogType(UUID(metadata._metadata_uuid), metadata._name,
                                           catalogs._metadata, 'manager')
        self._selection_type = BSLCatalogType(UUID(metadata._metadata_uuid), metadata._name,
                                             catalogs._metadata, 'selection')

    def _ref(self, uuid):
        return BSLCatalogReference(self._value_type, uuid, self._metadata, self._read_member)

    def empty_ref(self):
        return self._ref(_ZERO)

    def get_ref(self, uuid=_OMITTED):
        if uuid is _OMITTED or uuid is None:
            uuid = BSLUUID()
        if type(uuid) is not BSLUUID:
            raise TypeError('GetRef requires UUID')
        return self._ref(UUID(uuid.text))

    def _rows(self):
        result = self._catalogs._context.catalog_rows(self._metadata._name)
        if (result.identity.name != self._metadata._name
                or UUID(result.identity.metadata_uuid) != self._value_type.metadata_uuid):
            raise ValueError('catalog metadata identity changed')
        return result

    def _attributes(self, result):
        attributes = result.binding.attributes
        if type(attributes) is not tuple or len(attributes) > 64:
            raise ValueError('catalog attribute collection exceeds bounded profile')
        return attributes

    def _fields(self, result, row):
        fields = {field.declaration.name: field.value for field in row.physical_record.fields}
        logical = {'code': fields.get('_CODE', ''),
                   'description': fields.get('_DESCRIPTION', ''),
                   'ref': self._ref(row.reference_uuid),
                   'deletionmark': fields['_MARKED']}
        for attribute in self._attributes(result):
            key = attribute.name.casefold()
            if key in logical or key in ('код', 'наименование', 'ссылка', 'пометкаудаления'):
                raise ValueError('ambiguous catalog field name')
            value = fields[attribute.physical_name]
            logical[key] = (attribute.project(value, self._catalogs)
                            if type(attribute) is CatalogCardField else value)
        return logical

    def _read_member(self, ref, name):
        result = self._rows()
        for row in result.rows:
            if row.reference_uuid == ref.reference_uuid:
                return _field(self._fields(result, row), name)
        return _field(self._default_fields(result, ref), name)

    def _default_fields(self, result, ref=None):
        # Native absent reference values are scalar defaults, not a physical row.
        logical = {'code': Decimal(0) if result.binding.code_type == 0 else '',
                   'description': '', 'ref': ref, 'deletionmark': False}
        for attribute in self._attributes(result):
            key = attribute.name.casefold()
            if key in logical or key in ('код', 'наименование', 'ссылка', 'пометкаудаления'):
                raise ValueError('ambiguous catalog field name')
            logical[key] = (attribute.default(self._catalogs) if type(attribute) is CatalogCardField
                            else '' if attribute.type_token == 'S' else Decimal(0))
        return logical

    # !todo Add hierarchy/filter/order options after native batch verification.
    def select(self):
        result = self._rows()
        # Keep identity/decoded data together; do not expose a Python iterable as
        # native selection. Cursor protocol is explicit and separately measured.
        return BSLCatalogSelection(self, result)

    def find_by_code(self, code):
        if type(code) not in (str, Decimal):
            raise TypeError('catalog code requires String or Number')
        return self._find('code', code)

    def find_by_description(self, description, exact=_OMITTED):
        if type(description) is not str:
            raise TypeError('catalog description requires String')
        if exact is not True:
            raise ValueError('only explicit exact description lookup is supported')
        return self._find('description', description)

    # !todo Verify native collation, padding and duplicate lookup ordering;
    # currently this bounded path only compares exactly equal scalar values.
    def _find(self, field, value):
        result = self._rows()
        matches = [row for row in result.rows if self._fields(result, row)[field] == value]
        if len(matches) > 1:
            raise ValueError('ambiguous catalog lookup ordering is unsupported')
        return self._ref(matches[0].reference_uuid) if matches else self.empty_ref()

    def get_member(self, name):
        methods = {'пустаяссылка': self.empty_ref, 'emptyref': self.empty_ref,
                   'получитьссылку': self.get_ref, 'getref': self.get_ref,
                   'выбрать': self.select, 'select': self.select,
                   'найтипокоду': self.find_by_code, 'findbycode': self.find_by_code,
                   'найтипонаименованию': self.find_by_description,
                   'findbydescription': self.find_by_description}
        method = methods.get(name.casefold())
        return HostFunction(name, method) if method else super().get_member(name)

    def __str__(self):
        raise ValueError('catalog manager presentation is unsupported')


def _field(fields, name):
    key = name.casefold()
    key = {'код': 'code', 'наименование': 'description', 'ссылка': 'ref',
           'пометкаудаления': 'deletionmark'}.get(key, key)
    if key not in fields:
        raise ValueError('catalog field not found: ' + name)
    return fields[key]


class BSLCatalogSelection(BSLObject):
    """Native cursor: exhaustion retains fields; the next call restarts."""
    def __init__(self, manager, result):
        self._manager, self._result = manager, result
        self._selection_type = manager._selection_type
        rows = tuple(result.rows)
        if len(rows) > 1:
            keys = [manager._fields(result, row)['code'] for row in rows]
            # !todo Measure arbitrary string collation, ties and zero-code order.
            # The batch established ascending fixed-width digit String codes.
            if (not all(type(key) is str and key.isascii() and key.isdigit() for key in keys)
                    or len({len(key) for key in keys}) != 1 or len(set(keys)) != len(keys)):
                raise ValueError('multi-row catalog code ordering is unsupported')
            rows = tuple(row for _, row in sorted(zip(keys, rows), key=lambda item: item[0]))
        self._rows = rows
        self._position = -1
        self._next_position = 0

    def next(self):
        if self._next_position >= len(self._rows):
            self._next_position = 0
            return False
        self._position = self._next_position
        self._next_position += 1
        return True

    def get_method(self, name):
        if name.casefold() in ('next', 'следующий'):
            return HostFunction(name, self.next)
        # Native Reset/Сбросить is unavailable. Never invent a cursor method.
        return super().get_method(name)

    def get_member(self, name):
        if self._position < 0:
            # Empty/not-yet-positioned fields are Undefined, including Ref.
            defaults = self._manager._default_fields(self._result)
            _field(defaults, name)  # Validate the field name before returning.
            return None
        return _field(self._manager._fields(self._result, self._rows[self._position]), name)

    def __str__(self):
        raise ValueError('catalog selection presentation is unsupported')
