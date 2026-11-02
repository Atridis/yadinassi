"""Bounded single-catalog Query over the logical read port, never SQL text.

!todo General regional string collation and other query profiles. Native
Query24 calibrates cursor boundaries, Code label and nullable scalar metadata. No joins, aggregates, data modification or implicit casts.
Dynamic-reference projections are available in cursors; Unload refuses them
until truthful dynamic column TypeDescription support exists.
"""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
import sys

from . import query_parser as syntax
from .catalog_backend import (CatalogComparison, CatalogPredicate, CatalogOrder,
                              CatalogScanRequest, CatalogPage, CatalogCard,
                              CatalogKey, BackendError)
from .catalog_types import BSLCatalogReference
from .dates import BSLDate
from .values import BSLObject, HostFunction
from .value_tables import BSLValueTable
from .type_descriptions import BSLTypeDescription, _query_nullable_description
from .type_qualifiers import (BSLStringQualifiers, BSLNumberQualifiers,
                              BSLDateQualifiers, BSLAllowedSign)

_MAX_PARAMETERS = 128
_MAX_CELLS = 100000
_MAX_RESULT_TEXT = 8000000
_STANDARD = {'ref':'ref', 'ссылка':'ref', 'code':'code', 'код':'code',
             'description':'description', 'наименование':'description',
             'deletionmark':'deletion_mark', 'пометкаудаления':'deletion_mark'}


@dataclass(frozen=True, slots=True)
class _Column:
    name: str
    field: str | UUID
    kind: str
    qualifiers: tuple
    custom: object = None
    explicit_alias: bool = False


def _field(manager, field, source_alias):
    if len(field.parts) == 2 and field.parts[0].casefold() != source_alias.casefold():
        raise ValueError('Unknown query source qualifier')
    name = field.parts[-1].casefold()
    standard = _STANDARD.get(name)
    if standard is not None:
        kind = {'ref':'catalog_ref', 'code':'string', 'description':'string',
                'deletion_mark':'boolean'}[standard]
        qualifiers = ((manager._schema.code_length,) if standard == 'code' else
                      (manager._schema.description_length,) if standard == 'description' else ())
        return _Column('', standard, kind, qualifiers)
    fields = [item for item in manager._schema.fields if item.name.casefold() == name]
    if len(fields) != 1:
        raise ValueError('Unknown query field')
    item = fields[0]
    return _Column('', item.identity, item.kind, item.qualifiers, item)


def _parameter_value(value):
    kind = type(value)
    if kind is str:
        if len(value) > 4096:
            raise ValueError('Query parameter string limit exceeded')
    elif kind is Decimal:
        if sys.implementation.name != 'cpython' or Decimal.__sizeof__ is object.__sizeof__:
            raise ValueError('Query numeric implementation is unsupported')
        if (not value.is_finite() or value.__sizeof__() > 2048
                or len(value.as_tuple().digits) > 38 or abs(value.adjusted()) > 38):
            raise ValueError('Query parameter number limit exceeded')
    elif kind is BSLDate:
        value.require_known()
    elif kind is not bool and kind is not BSLCatalogReference:
        raise TypeError('Unsupported query parameter type')
    return value


def _stored(manager, column, value):
    _parameter_value(value)
    if column.custom is not None:
        return manager._stored(column.custom, value)
    if column.field == 'ref':
        if (type(value) is not BSLCatalogReference
                or value.value_type.snapshot is not manager._catalogs._metadata
                or value.value_type.metadata_uuid != manager._schema.identity):
            raise TypeError('Query reference requires same database and catalog')
        return manager._key(value.reference_uuid)
    expected = bool if column.field == 'deletion_mark' else str
    if type(value) is not expected:
        raise TypeError('Query comparison requires exact field type')
    return value


def _predicate(manager, node, alias, parameters):
    if node is None:
        return None
    if type(node) is syntax.Predicate:
        return CatalogPredicate(node.kind, tuple(_predicate(manager, term, alias, parameters)
                                                 for term in node.terms))
    column = _field(manager, node.field, alias)
    value = node.value
    if type(value) is syntax.Parameter:
        key = value.name.casefold()
        if key not in parameters:
            raise ValueError('Query parameter is not set')
        value = parameters[key]
    return CatalogComparison(column.field, node.operator, _stored(manager, column, value))


def _logical(manager, column, card):
    if column.custom is not None:
        index = manager._schema.fields.index(column.custom)
        return manager._logical(column.custom, card.values[index])
    if column.field == 'ref':
        return manager._ref(card.key.record_id)
    return {'code':card.code, 'description':card.description,
            'deletion_mark':card.deletion_mark}[column.field]


def _description(column):
    if not column.explicit_alias and column.field in ('description', 'deletion_mark'):
        raise ValueError('Query unaliased standard column label is not yet supported by Unload')
    if column.kind == 'string':
        return BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(column.qualifiers[0])))
    if column.kind == 'number':
        digits, scale, sign = column.qualifiers
        allowed = BSLAllowedSign.NONNEGATIVE if sign == 'Nonnegative' else BSLAllowedSign.ANY
        return BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(digits), Decimal(scale), allowed))
    if column.kind == 'boolean':
        return BSLTypeDescription('Boolean')
    if column.kind == 'datetime':
        return BSLTypeDescription('Date', None, None, BSLDateQualifiers())
    raise ValueError('Query Unload dynamic reference column metadata is not supported')


class BSLQuery(BSLObject):
    def __init__(self, catalogs, text=''):
        self._catalogs = catalogs
        self._parameters = {}
        self.set_member('Text', text)

    def __str__(self):
        return 'Запрос'

    def get_member(self, name):
        if name.casefold() in ('text', 'текст'):
            return self._text
        return self.get_method(name)

    def set_member(self, name, value):
        if name.casefold() not in ('text', 'текст'):
            return super().set_member(name, value)
        if type(value) is not str:
            raise TypeError('Query.Text requires String')
        if len(value) > syntax.MAX_TEXT:
            raise ValueError('Query text limit exceeded')
        self._text = value

    def get_method(self, name):
        key = name.casefold()
        if key in ('setparameter', 'установитьпараметр'):
            return HostFunction(name, self.set_parameter, returns_value=False)
        if key in ('execute', 'выполнить'):
            return HostFunction(name, self.execute)
        return super().get_member(name)

    def set_parameter(self, name, value):
        if not syntax.identifier(name):
            raise ValueError('Invalid query parameter name')
        key = name.casefold()
        if key not in self._parameters and len(self._parameters) >= _MAX_PARAMETERS:
            raise ValueError('Query parameter count limit exceeded')
        self._parameters[key] = _parameter_value(value)

    def execute(self):
        query = syntax.parse_query(self._text)
        manager = self._catalogs.get_index(query.catalog)
        columns = []
        for projection in query.projections:
            column = _field(manager, projection.field, query.source_alias)
            name = ('Код' if not projection.explicit_alias and column.field == 'code'
                    else projection.alias)
            columns.append(_Column(name, column.field, column.kind,
                                   column.qualifiers, column.custom, projection.explicit_alias))
        if len({column.name.casefold() for column in columns}) != len(columns):
            raise ValueError('Duplicate localized query output column')
        predicate = _predicate(manager, query.predicate, query.source_alias, dict(self._parameters))
        order = tuple(CatalogOrder(_field(manager, item.field, query.source_alias).field, item.descending)
                      for item in query.order)
        rows = []
        text_units = 0
        continuation = None
        seen = set()
        size = min(1000, query.limit)
        view = manager._view()
        try:
            while len(rows) < query.limit:
                page = view.scan_catalog(manager._schema.identity,
                                         CatalogScanRequest(predicate, order, size, continuation, string_comparison='casefold_v1'))
                if (type(page) is not CatalogPage or type(page.cards) is not tuple or len(page.cards) > size
                        or (page.continuation is not None and
                            (type(page.continuation) is not str or len(page.continuation) != 32))):
                    raise BackendError('integrity')
                for card in page.cards[:query.limit - len(rows)]:
                    if (type(card) is not CatalogCard or type(card.key) is not CatalogKey
                            or card.key.database_id != view.database_id
                            or card.key.catalog_id != manager._schema.identity
                            or type(card.key.record_id) is not UUID or card.key.record_id.int == 0
                            or type(card.code) is not str or type(card.description) is not str
                            or len(card.code) > manager._schema.code_length
                            or len(card.description) > manager._schema.description_length
                            or type(card.deletion_mark) is not bool or type(card.values) is not tuple
                            or len(card.values) != len(manager._schema.fields)
                            or card.key.record_id in seen):
                        raise BackendError('integrity')
                    seen.add(card.key.record_id)
                    row = tuple(_logical(manager, column, card) for column in columns)
                    text_units += sum(len(value) for value in row if type(value) is str)
                    rows.append(row)
                    if len(rows) * len(columns) > _MAX_CELLS or text_units > _MAX_RESULT_TEXT:
                        raise ValueError('Query result resource limit exceeded')
                if page.continuation is None:
                    break
                if not page.cards or page.continuation == continuation:
                    raise BackendError('integrity')
                continuation = page.continuation
        finally:
            view.close()
        return BSLQueryResult(tuple(columns), tuple(rows))


class BSLQueryResult(BSLObject):
    def __init__(self, columns, rows):
        self._columns, self._rows = columns, rows

    def __str__(self):
        return 'Результат запроса'

    def get_member(self, name):
        return self.get_method(name)

    def get_method(self, name):
        methods = {'select':self.select, 'выбрать':self.select,
                   'unload':self.unload, 'выгрузить':self.unload,
                   'isempty':lambda:not self._rows, 'пустой':lambda:not self._rows}
        method = methods.get(name.casefold())
        if method is None:
            return super().get_member(name)
        return HostFunction(name, method)

    def select(self):
        return BSLQueryResultSelection(self)

    def unload(self):
        # Refuse the whole operation before creating an incorrectly untyped
        # dynamic column. Scalar descriptions derive from the admitted schema.
        descriptions = tuple(_description(column) for column in self._columns)
        table = BSLValueTable()
        for column, description in zip(self._columns, descriptions):
            table.columns.add(column.name, description)
        for values in self._rows:
            row = table.add()
            for column, value in zip(table.columns.items, values):
                row.cells[column] = value
        # Build data using known scalar defaults first. Only then expose the
        # measured nullable metadata. New-row defaults/coercions remain refused.
        for column, description in zip(table.columns.items, descriptions):
            column.value_type = _query_nullable_description(description)
        return table


class BSLQueryResultSelection(BSLObject):
    def __init__(self, result):
        self._result = result
        self._position = -1
        self._exhausted = False

    def __str__(self):
        return 'Выборка из результата запроса'

    def next(self):
        if self._exhausted:
            return False
        if self._position + 1 >= len(self._result._rows):
            self._exhausted = True
            return False
        self._position += 1
        return True

    def get_member(self, name):
        for index, column in enumerate(self._result._columns):
            if (column.name.casefold() == name.casefold() or
                    (not column.explicit_alias and column.field == 'code'
                     and name.casefold() in ('code', 'код'))):
                # Native Query24: Undefined before positioning, retained last
                # row after exhaustion (including another false Next call).
                if self._position < 0:
                    return None
                return self._result._rows[self._position][index]
        return self.get_method(name)

    def get_method(self, name):
        if name.casefold() in ('next', 'следующий'):
            return HostFunction(name, self.next)
        return super().get_member(name)
