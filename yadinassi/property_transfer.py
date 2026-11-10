"""Bounded shallow FillPropertyValues adapters for built-in object/row endpoints.

The historical Structure-to-Structure path remains in structures.py. Ordinary
row selection follows the acquired Linux profile only in that explicit target.
Other endpoint/target combinations retain the bounded local host policy.
Only existing member setters mutate buffers; no persistence or handlers run here.
"""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from .catalog_backend import BackendError, CatalogSchema, FieldSchema, TabularSectionSchema
from .catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from .catalogs import BSLCatalogManager, BSLCatalogObject
from .document_backend import DocumentSchema
from .document_lines import BSLDocumentLine, BSLDocumentLines
from .documents import BSLDocumentManager, BSLDocumentObject
from .native_targets import LINUX_8_3_27_1508, current_native_target
from .structures import BSLFixedStructure, BSLStructure, _key
from .type_descriptions import BSLTypeDescription, _canonical, _query_nullable_description
from .type_qualifiers import (BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
                              BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers,
                              BSLStringQualifiers, _MAX_LENGTH_UNITS, _MAX_NUMBER_DIGITS)
from .values import BSLType
from .value_tables import (BSLCollectionIndex, BSLCollectionIndexes, BSLValueTable,
                           BSLValueTableColumn, BSLValueTableColumnCollection, BSLValueTableRow)
from .value_trees import (BSLValueTree, BSLValueTreeColumn, BSLValueTreeColumnCollection,
                          BSLValueTreeRow, BSLValueTreeRowCollection)

MAX_FIELDS = 4096
MAX_NAME_UNITS = 256
MAX_SCHEMA_UNITS = 1_000_000
MAX_LIST_UNITS = 65_536
MAX_LIST_NAMES = 4096
MAX_OWNER_ROWS = 100_000
MAX_INDEXES = 256
MAX_INDEX_COLUMNS = 4096

# Aliases are activated only by an endpoint that actually owns that standard
# property. Two ordinary user fields are otherwise compared by name alone.
_ALIASES = {
    'code': ('code', 'код'), 'description': ('description', 'наименование'),
    'number': ('number', 'номер'), 'date': ('date', 'дата'),
    'deletionmark': ('deletionmark', 'пометкаудаления'), 'ref': ('ref', 'ссылка'),
    'posted': ('posted', 'проведен', 'проведён'),
    'linenumber': ('linenumber', 'номерстроки'),
    'parent': ('parent', 'родитель'), 'rows': ('rows', 'строки'),
}
_CATALOG = ('code', 'description', 'deletionmark', 'ref')
_DOCUMENT = ('number', 'date', 'deletionmark', 'posted', 'ref')
_READONLY = frozenset(('ref', 'posted', 'linenumber', 'parent', 'rows'))


def _is_extended_endpoint(value):
    """Dispatch only admitted non-structure families, without host type hooks."""
    return any(type(value) is kind for kind in (
        BSLValueTableRow, BSLValueTreeRow, BSLCatalogObject, BSLDocumentObject,
        BSLCatalogSectionRow, BSLDocumentLine))


def _invalid(message):
    raise ValueError('ЗаполнитьЗначенияСвойств: ' + message)


def _get(value, name):
    return object.__getattribute__(value, name)


def _instance(value, expected):
    if type(value) is not expected:
        raise TypeError('ЗаполнитьЗначенияСвойств: неподдерживаемый тип объекта')
    state = _get(value, '__dict__')
    if type(state) is not dict or len(state) > 64:
        _invalid('недопустимое состояние объекта')
    # Existing class methods may call other methods on self. Reject instance
    # replacements before calling those trusted implementations.
    for name in state:
        if type(name) is not str:
            _invalid('недопустимое состояние объекта')
        for base in expected.__mro__:
            member = vars(base).get(name)
            if callable(member) or type(member) is property:
                _invalid('подмена метода объекта не поддерживается')


def _sequence(value, kind, maximum):
    if type(value) is not kind or len(value) > maximum:
        _invalid('недопустимый состав или превышен предел ресурсов')
    return value


class _Budget:
    def __init__(self):
        self.units = 0

    def name(self, name):
        if type(name) is not str or not name or len(name) > MAX_NAME_UNITS:
            _invalid('недопустимое имя свойства')
        units = len(name) + sum(ord(char) > 0xffff for char in name)
        self.units += units
        if units > MAX_NAME_UNITS or self.units > MAX_SCHEMA_UNITS:
            _invalid('превышен предел имен свойств')
        return _key(name)


@dataclass(frozen=True)
class _Field:
    name: str
    key: str
    standard: bool = False
    readable: bool = True
    writable: bool = True


@dataclass(frozen=True)
class _Endpoint:
    value: object
    fields: tuple
    getter: object
    setter: object


def _field_names(fields, budget):
    _sequence(fields, tuple, MAX_FIELDS)
    result, seen = [], set()
    for field in fields:
        if type(field) is not FieldSchema:
            _invalid('недопустимая схема реквизита')
        key = budget.name(field.name)
        if key in seen:
            _invalid('повторное имя реквизита')
        seen.add(key)
        # These values reach the existing typed setter. Do not permit injected
        # hash, iteration or comparison hooks inside a metadata record.
        if (type(field.identity) is not UUID or type(field.kind) is not str
                or field.kind not in ('string', 'number', 'boolean', 'datetime', 'catalog_ref')
                or type(field.qualifiers) is not tuple or len(field.qualifiers) > 4
                or any(not (type(v) is int or type(v) is str) for v in field.qualifiers)
                or any(type(v) is str and len(v) > 256 for v in field.qualifiers)
                or any(type(v) is int and not 0 <= v <= 1_000_000 for v in field.qualifiers)
                or (field.target_catalog_id is not None and type(field.target_catalog_id) is not UUID)):
            _invalid('недопустимая схема реквизита')
        result.append(_Field(field.name, key))
    return result


def _mapping(values, keys):
    _sequence(values, dict, MAX_FIELDS + 16)
    if any(type(key) is not str for key in values) or set(values) != keys:
        _invalid('состав значений не соответствует схеме')


def _qualifier_count(value, maximum):
    # Qualifier constructors store canonical nonnegative integer Decimals.
    # This validates metadata only, not cell values or assignment coercions.
    if (type(value) is not Decimal or not value.is_finite()
            or Decimal.__sizeof__ is object.__sizeof__
            or Decimal.__sizeof__(value) > 256 or not 0 <= value <= maximum):
        _invalid('недопустимый числовой квалификатор')
    parts = value.as_tuple()
    if parts.sign or parts.exponent != 0:
        _invalid('неканонический числовой квалификатор')
    return int(value)


def _descriptor_state(description):
    _instance(description, BSLTypeDescription)
    kinds = _sequence(description.types, tuple, MAX_FIELDS)
    if any(type(kind) is not BSLType for kind in kinds):
        _invalid('недопустимое описание типов колонки')
    number, string, date, binary = (description.number_qualifiers, description.string_qualifiers,
                                    description.date_qualifiers, description.binary_data_qualifiers)
    for qualifier, cls in ((number, BSLNumberQualifiers), (string, BSLStringQualifiers),
                           (date, BSLDateQualifiers), (binary, BSLBinaryDataQualifiers)):
        _instance(qualifier, cls)
    digits = _qualifier_count(number.digits, _MAX_NUMBER_DIGITS)
    fraction = _qualifier_count(number.fraction_digits, digits)
    length = _qualifier_count(string.length, _MAX_LENGTH_UNITS)
    binary_length = _qualifier_count(binary.length, _MAX_LENGTH_UNITS)
    if (not (number.allowed_sign is BSLAllowedSign.ANY or number.allowed_sign is BSLAllowedSign.NONNEGATIVE)
            or not (string.allowed_length is BSLAllowedLength.VARIABLE or string.allowed_length is BSLAllowedLength.FIXED)
            or (not length and string.allowed_length is not BSLAllowedLength.VARIABLE)
            or not any(date.date_fractions is mode for mode in
                       (BSLDateFractions.DATE_TIME, BSLDateFractions.DATE, BSLDateFractions.TIME))
            or binary_length or binary.allowed_length is not BSLAllowedLength.VARIABLE):
        _invalid('недопустимый квалификатор колонки')
    if ((BSLType.NUMBER not in kinds and (digits or fraction or number.allowed_sign is not BSLAllowedSign.ANY))
            or (BSLType.STRING not in kinds and (length or string.allowed_length is not BSLAllowedLength.VARIABLE))
            or (BSLType.DATE not in kinds and date.date_fractions is not BSLDateFractions.DATE_TIME)):
        _invalid('квалификатор отсутствующего типа колонки')
    return (kinds, digits, fraction, number.allowed_sign, length,
            string.allowed_length, date.date_fractions)


def _descriptor(description):
    state = _descriptor_state(description)
    marker = description._query_scalar
    if marker is None:
        if _canonical(set(description.types)) != description.types:
            _invalid('неканоническое описание типов колонки')
    else:
        _instance(marker, BSLTypeDescription)
        if marker._query_scalar is not None:
            _invalid('недопустимое nullable описание колонки')
        _descriptor(marker)
        if _descriptor_state(_query_nullable_description(marker)) != state:
            _invalid('несогласованное nullable описание колонки')


def _row_endpoint(row, budget, target, readable_rows=False):
    tree_row = type(row) is BSLValueTreeRow
    row_type = BSLValueTreeRow if tree_row else BSLValueTableRow
    _instance(row, row_type)
    if row._deleted is not False:
        _invalid('отсоединенная строка недоступна')
    owner = row.tree if tree_row else row.table
    _instance(owner, BSLValueTree if tree_row else BSLValueTable)
    columns = owner.columns
    _instance(columns, BSLValueTreeColumnCollection if tree_row else BSLValueTableColumnCollection)
    if columns.table is not owner:
        _invalid('неверный владелец колонок')
    items = _sequence(columns.items, list, MAX_FIELDS)
    if tree_row:
        collection = row.collection
        _instance(collection, BSLValueTreeRowCollection)
        _sequence(collection.items, list, MAX_OWNER_ROWS)
        _sequence(owner._all_rows, dict, MAX_OWNER_ROWS)
        if (collection.tree is not owner or collection.parent is not row.parent
                or not any(item is row for item in collection.items)
                or not any(item is row for item in owner._all_rows)):
            _invalid('неверный владелец строки дерева')
        if row.parent is not None:
            _instance(row.parent, BSLValueTreeRow)
            if row.parent.tree is not owner or row.parent._deleted is not False:
                _invalid('отсоединенный родитель строки дерева')
        _instance(row.rows, BSLValueTreeRowCollection)
        if row.rows.tree is not owner or row.rows.parent is not row:
            _invalid('неверный владелец дочерних строк')
    else:
        _sequence(owner.rows, list, MAX_OWNER_ROWS)
        if not any(item is row for item in owner.rows):
            _invalid('строка отсутствует в таблице')
        if type(owner._bounded_slice_read) is not bool:
            _invalid('недопустимое состояние таблицы')
        if target and owner._bounded_slice_read:
            _invalid('строка снимка доступна только для чтения')
    fields, ids, names = [], set(), set()
    for column in items:
        _instance(column, BSLValueTreeColumn if tree_row else BSLValueTableColumn)
        if column.table is not owner or column._deleted is not False or id(column) in ids:
            _invalid('неверный владелец колонки')
        ids.add(id(column))
        key = budget.name(column.name)
        if key in names or (tree_row and key in ('parent', 'родитель', 'rows', 'строки')):
            _invalid('повторное или зарезервированное имя колонки')
        names.add(key)
        if target:
            _descriptor(column.value_type)
        fields.append(_Field(column.name, key))
    cells = _sequence(row.cells, dict, MAX_FIELDS)
    if len(cells) != len(items) or any(type(c) is not (BSLValueTreeColumn if tree_row else BSLValueTableColumn)
                                    or id(c) not in ids for c in cells):
        _invalid('состав ячеек не соответствует колонкам')
    if tree_row:
        fields.extend(_Field(name, budget.name(name), True, name == 'parent' or readable_rows, False)
                      for name in ('parent', 'rows'))
    elif target:
        indexes = owner.indexes
        _instance(indexes, BSLCollectionIndexes)
        if indexes.table is not owner:
            _invalid('неверный владелец индексов')
        _sequence(indexes.items, list, MAX_INDEXES)
        positions = 0
        for index in indexes.items:
            _instance(index, BSLCollectionIndex)
            selected = _sequence(index.columns, list, MAX_INDEX_COLUMNS)
            positions += max(1, len(selected))
            if (positions > MAX_INDEX_COLUMNS or index.table is not owner
                    or index._deleted is not False or index._cleared is not False
                    or any(type(c) is not BSLValueTableColumn or id(c) not in ids for c in selected)
                    or type(index._keys) is not dict or type(index._buckets) is not dict
                    or type(index._units) is not int or index._units < 0):
                _invalid('недопустимое состояние индекса')
    return _Endpoint(row, tuple(fields), row_type.get_member, row_type.set_member)


def _object_schema(value, budget, target):
    document = type(value) is BSLDocumentObject
    cls = BSLDocumentObject if document else BSLCatalogObject
    _instance(value, cls)
    manager = value._manager
    _instance(manager, BSLDocumentManager if document else BSLCatalogManager)
    schema = manager._schema
    if type(schema) is not (DocumentSchema if document else CatalogSchema):
        _invalid('недопустимая схема объекта')
    if target and (value._pending_write is not None
                   or (not document and value._pending_preparation is not None)):
        raise BackendError('uncertain_commit')
    fields = [_Field(name, budget.name(name), True, True, name not in _READONLY)
              for name in (_DOCUMENT if document else _CATALOG)]
    fields.extend(_field_names(schema.fields, budget))
    _mapping(value._values, {field.key for field in fields})
    sections = _sequence(schema.tabular_sections, tuple, MAX_FIELDS)
    _sequence(value._sections, dict, MAX_FIELDS)
    section_keys = set()
    for section in sections:
        if type(section) is not TabularSectionSchema:
            _invalid('недопустимая схема табличной части')
        key = budget.name(section.name)
        if key in section_keys:
            _invalid('повторное имя табличной части')
        section_keys.add(key)
        # Sections are visible only for explicit exclusion/presence checks.
        # Never call their getters or copy an entire collection by reference.
        fields.append(_Field(section.name, key, False, False, False))
    if any(type(key) is not str for key in value._sections) or set(value._sections) != section_keys:
        _invalid('состав табличных частей не соответствует схеме')
    for section in value._sections.values():
        _instance(section, BSLDocumentLines if document else BSLCatalogSection)
        if (section._owner is not value or type(section._bytes) is not int
                or not 0 <= section._bytes <= 4 * 1024 * 1024):
            _invalid('неверный владелец или размер табличной части')
    return _Endpoint(value, tuple(fields), cls.get_member, cls.set_member)


def _section_endpoint(row, budget, target):
    document = type(row) is BSLDocumentLine
    cls = BSLDocumentLine if document else BSLCatalogSectionRow
    _instance(row, cls)
    section = row._section
    _instance(section, BSLDocumentLines if document else BSLCatalogSection)
    owner = section._owner
    if type(owner) is not (BSLDocumentObject if document else BSLCatalogObject):
        _invalid('неверный владелец табличной части')
    _object_schema(owner, budget, target)
    if row._attached is not True or type(row._identity) is not UUID:
        _invalid('отсоединенная строка табличной части')
    _sequence(section._rows, list, MAX_OWNER_ROWS)
    # LineNumber uses the existing list.index implementation. Keep foreign or
    # subclass equality hooks out of that read, and validate mutable counters.
    if (any(type(item) is not cls for item in section._rows)
            or any(item._section is not section or item._attached is not True for item in section._rows)
            or type(row._bytes) is not int or not 0 <= row._bytes <= 4 * 1024 * 1024):
        _invalid('недопустимое состояние строки табличной части')
    if not any(item is row for item in section._rows):
        _invalid('строка отсутствует в табличной части')
    schema = section._schema
    if type(schema) is not TabularSectionSchema:
        _invalid('недопустимая схема табличной части')
    key = budget.name(schema.name)
    if owner._sections.get(key) is not section or not any(item is schema for item in owner._manager._schema.tabular_sections):
        _invalid('табличная часть не принадлежит объекту')
    fields = _field_names(schema.fields, budget)
    _mapping(row._values, {field.key for field in fields})
    _mapping(section._fields, {field.key for field in fields})
    for descriptor in schema.fields:
        if section._fields[descriptor.name.casefold()] is not descriptor:
            _invalid('неверная схема поля табличной части')
    fields.append(_Field('LineNumber', budget.name('LineNumber'), True, True, False))
    return _Endpoint(row, tuple(fields), cls.get_member, cls.set_member)


def _endpoint(value, budget, target=False, readable_rows=False):
    kind = type(value)
    if kind is BSLStructure or kind is BSLFixedStructure:
        _instance(value, kind)
        if target and kind is BSLFixedStructure:
            _invalid('фиксированный приемник нового профиля недоступен для записи')
        _sequence(value._items, dict, MAX_FIELDS)
        fields = []
        for key, pair in value._items.items():
            if type(key) is not str or type(pair) is not tuple or len(pair) != 2:
                _invalid('недопустимое свойство структуры')
            folded = budget.name(pair[0])
            if key != folded:
                _invalid('имя свойства не соответствует ключу')
            fields.append(_Field(pair[0], key))
        return _Endpoint(value, tuple(fields), kind.get_member, kind.set_member)
    if kind is BSLValueTableRow or kind is BSLValueTreeRow:
        return _row_endpoint(value, budget, target, readable_rows)
    if kind is BSLCatalogObject or kind is BSLDocumentObject:
        return _object_schema(value, budget, target)
    if kind is BSLCatalogSectionRow or kind is BSLDocumentLine:
        return _section_endpoint(value, budget, target)
    raise TypeError('ЗаполнитьЗначенияСвойств: неподдерживаемый тип объекта')


def _names(value, budget, empty_include=False):
    if type(value) is not str:
        raise TypeError('ЗаполнитьЗначенияСвойств: список свойств должен быть строкой')
    if (len(value) > MAX_LIST_UNITS or value.count(',') + 1 > MAX_LIST_NAMES
            or len(value) + sum(ord(c) > 0xffff for c in value) > MAX_LIST_UNITS):
        _invalid('превышен предел списка свойств')
    if empty_include and value == '':
        return []
    # !todo Measure row-list empty tokens, quoted names and Unicode whitespace.
    # No empty tokens, quoted names, tabs or Unicode trimming is inferred from
    # the simple comma-separated contract. Repeated valid names retain order.
    return [budget.name(name.strip(' ')) for name in value.split(',')]


def _mapped(endpoint, aliases):
    result = {}
    for field in endpoint.fields:
        key = aliases.get(field.key, field.key)
        if key in result:
            _invalid('неоднозначные имена или синонимы свойств')
        result[key] = field
    return result


def _ordinary_linux_transfer(target, source):
    # !todo Acquire Windows row and catalog/document/tabular-row ordering before
    # extending these measurements beyond ordinary Linux row combinations.
    kinds = (BSLStructure, BSLFixedStructure, BSLValueTableRow, BSLValueTreeRow)
    return (current_native_target() == LINUX_8_3_27_1508
            and all(any(type(value) is kind for kind in kinds) for value in (target, source)))


def fill_property_values(target, source, properties=None, exclude=None):
    """Copy with existing setters; Linux ordinary rows retain measured errors.

    Schema, alias and bounded list syntax checks always precede assignments.
    Linux ordinary-row INCLUDE checks presence/readonly lazily, right to left.
    Other endpoint/target combinations retain the original preflight policy.
    """
    linux_rows = _ordinary_linux_transfer(target, source)
    budget = _Budget()
    try:
        destination = _endpoint(target, budget, True)
        origin = _endpoint(source, budget, readable_rows=linux_rows)
    except (AttributeError, KeyError):
        _invalid('неполное внутреннее состояние объекта')
    if linux_rows:
        # Include overrides a valid Exclude list, not its argument type.
        for value in (properties, exclude):
            if value is not None and type(value) is not str:
                raise TypeError('ЗаполнитьЗначенияСвойств: список свойств должен быть строкой')
    standards = {field.key for endpoint in (destination, origin) for field in endpoint.fields if field.standard}
    aliases = {name: key for key in standards for name in _ALIASES[key]}
    targets, sources = _mapped(destination, aliases), _mapped(origin, aliases)

    def check_selected(key):
        if key not in targets or key not in sources:
            _invalid('включенное свойство отсутствует в одном из объектов')
        if not targets[key].writable or not sources[key].readable:
            _invalid('включенное свойство доступно только для чтения или является коллекцией')

    def assign(key):
        value = origin.getter(origin.value, sources[key].name)
        destination.setter(destination.value, targets[key].name, value)

    if properties is not None:
        selected = [aliases.get(name, name) for name in
                    _names(properties, budget, empty_include=linux_rows)]
        if linux_rows:
            for key in reversed(selected):
                check_selected(key)
                assign(key)
            return
        for key in selected:
            check_selected(key)
    else:
        excluded, deferred = set(), None
        if exclude is not None:
            for name in _names(exclude, budget):
                key = aliases.get(name, name)
                if key not in sources:
                    _invalid('исключаемое свойство отсутствует в одном из объектов')
                if key not in targets:
                    # PV-21/31: one mutable Structure source-only field errors
                    # when reached in source order, after preceding assignments.
                    # !todo Measure multiple/mixed missing exclusions and other
                    # source kinds; do not extrapolate the partial-write rule.
                    if not linux_rows or type(source) is not BSLStructure or deferred is not None:
                        _invalid('исключаемое свойство отсутствует в одном из объектов')
                    deferred = key
                excluded.add(key)
        if deferred is not None:
            if sources.keys() - targets.keys() != {deferred}:
                _invalid('исключаемое свойство отсутствует в одном из объектов')
            for key in sources:
                if key == deferred:
                    _invalid('исключаемое свойство отсутствует в одном из объектов')
                if (key in targets and key not in excluded
                        and targets[key].writable and sources[key].readable):
                    assign(key)
            return
        selected = [key for key, field in targets.items()
                    if key in sources and key not in excluded
                    and field.writable and sources[key].readable]
    for key in selected:
        assign(key)
