"""Bounded single-catalog Query over the logical read port, never SQL text.

!todo General regional string collation and other query profiles. Native
Query24 calibrates cursor boundaries, Code label and nullable scalar metadata.
Relational joins/aggregates use the separate backend-independent executor.
No data modification or implicit casts.
Dynamic-reference projections are available in cursors; Unload refuses them
until truthful dynamic column TypeDescription support exists.
"""
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN
from uuid import UUID
import sys

from . import query_parser as syntax
from .catalog_backend import (CatalogComparison, CatalogPredicate, CatalogOrder,
                              CatalogScanRequest, CatalogValuePage, CatalogValueRow,
                              CatalogKey, CatalogSectionPage, CatalogSectionRecord, TabularRow, BackendError)
from .catalog_qualifiers import bound_number, validate_string
from .catalog_types import BSLCatalogReference
from .document_types import BSLDocumentReference
from .dates import BSLDate
from .values import BSLObject, HostFunction
from .value_tables import BSLValueTable
from .type_descriptions import BSLTypeDescription, _query_nullable_description
from .type_qualifiers import (BSLStringQualifiers, BSLNumberQualifiers,
                              BSLDateQualifiers, BSLAllowedSign, BSLAllowedLength, BSLDateFractions)

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
    reference_identity: object = None


def _field(manager, field, source_alias, section=None):
    if len(field.parts) == 2 and field.parts[0].casefold() != source_alias.casefold():
        raise ValueError('Unknown query source qualifier')
    name = field.parts[-1].casefold()
    standard = _STANDARD.get(name)
    if section is not None and name in ('linenumber', 'номерстроки'):
        raise ValueError('Query section line numbers are unsupported')
    if section is not None and standard not in (None, 'ref'):
        raise ValueError('Query section does not inherit owner fields')
    if standard is not None:
        kind = {'ref':'catalog_ref', 'code':'string', 'description':'string',
                'deletion_mark':'boolean'}[standard]
        qualifiers = ((manager._schema.code_length,) if standard == 'code' else
                      (manager._schema.description_length,) if standard == 'description' else ())
        return _Column('', standard, kind, qualifiers)
    schema_fields = manager._schema.fields if section is None else section.fields
    fields = [item for item in schema_fields if item.name.casefold() == name]
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
    elif kind is not bool and kind is not BSLCatalogReference and kind is not BSLDocumentReference:
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


def _predicate(manager, node, alias, parameters, section=None):
    if node is None:
        return None
    if type(node) is syntax.Predicate:
        return CatalogPredicate(node.kind, tuple(_predicate(manager, term, alias, parameters, section)
                                                 for term in node.terms))
    column = _field(manager, node.field, alias, section)
    value = node.value
    if type(value) is syntax.Parameter:
        key = value.name.casefold()
        if key not in parameters:
            raise ValueError('Query parameter is not set')
        value = parameters[key]
    return CatalogComparison(column.field, node.operator, _stored(manager, column, value))


def _logical(manager, column, value):
    if column.custom is not None:
        return manager._logical(column.custom, value)
    if column.field == 'ref':
        if (type(value) is not CatalogKey
                or any(type(item) is not UUID for item in (value.database_id,value.catalog_id,value.record_id))
                or value.database_id != manager._key(UUID(int=0)).database_id
                or value.catalog_id != manager._schema.identity or type(value.record_id) is not UUID):
            raise BackendError('integrity')
        return manager._ref(value.record_id)
    if column.field in ('code', 'description'):
        if type(value) is not str or len(value) > column.qualifiers[0]: raise BackendError('integrity')
    elif type(value) is not bool: raise BackendError('integrity')
    return value


def _section_value(manager, field, value):
    """Validate the logical port independently of any particular backend."""
    try:
        if field.kind == 'string':
            validate_string(value, field.qualifiers[0])
        elif field.kind == 'number':
            bound_number(value)
            digits, scale, sign = field.qualifiers
            # A hostile ambient/default Decimal context cannot alter validation.
            context = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999,
                              Emax=999999, capitals=1, clamp=0, flags=[],
                              traps=[InvalidOperation])
            quantum = Decimal((0, (1,), -scale))
            ceiling = Decimal((0, (1,), digits - scale))
            if (context.quantize(value, quantum) != value
                    or value.copy_abs() >= ceiling
                    or (sign == 'Nonnegative' and value < 0)):
                raise BackendError('integrity')
        elif field.kind == 'catalog_ref':
            if (type(value) is not CatalogKey
                    or any(type(identity) is not UUID for identity in
                           (value.database_id, value.catalog_id, value.record_id))):
                raise BackendError('integrity')
        # This also enforces exact scalar/date types and database/target scope.
        return manager._logical(field, value)
    except (ValueError, TypeError, InvalidOperation):
        raise BackendError('integrity') from None


def _section_row(manager, section, record, columns, view, seen):
    if (type(record) is not CatalogSectionRecord or type(record.owner) is not CatalogKey
            or any(type(identity) is not UUID for identity in
                   (record.owner.database_id, record.owner.catalog_id, record.owner.record_id))
            or record.owner.database_id != view.database_id
            or record.owner.catalog_id != manager._schema.identity
            or not record.owner.record_id.int
            or type(record.section_id) is not UUID or record.section_id != section.identity
            or type(record.row) is not TabularRow
            or type(record.row.identity) is not UUID or not record.row.identity.int
            or type(record.row.values) is not tuple
            or len(record.row.values) != len(section.fields)):
        raise BackendError('integrity')
    identity = (record.owner, record.section_id, record.row.identity)
    if identity in seen:
        raise BackendError('integrity')
    seen.add(identity)
    # Unprojected values must be checked too: a narrow projection cannot hide
    # corrupt scalars, wrong reference scopes or malformed record identities.
    values = {field.identity: _section_value(manager, field, value)
              for field, value in zip(section.fields, record.row.values)}
    return tuple(manager._ref(record.owner.record_id) if column.field == 'ref'
                 else values[column.field] for column in columns)


def _description(column):
    if not column.explicit_alias and column.field in ('description', 'deletion_mark'):
        raise ValueError('Query unaliased standard column label is not yet supported by Unload')
    if column.kind == 'string':
        allowed = BSLAllowedLength.FIXED if column.qualifiers[1:] == ('Fixed',) else BSLAllowedLength.VARIABLE
        return BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(column.qualifiers[0]), allowed))
    if column.kind == 'number':
        digits, scale, sign = column.qualifiers
        allowed = BSLAllowedSign.NONNEGATIVE if sign == 'Nonnegative' else BSLAllowedSign.ANY
        return BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(digits), Decimal(scale), allowed))
    if column.kind == 'boolean':
        return BSLTypeDescription('Boolean')
    if column.kind == 'datetime':
        fraction = {'Date': BSLDateFractions.DATE, 'Time': BSLDateFractions.TIME,
                    'DateTime': BSLDateFractions.DATE_TIME}[column.qualifiers[0]]
        return BSLTypeDescription('Date', None, None, BSLDateQualifiers(fraction))
    raise ValueError('Query Unload dynamic reference column metadata is not supported')


class BSLQuery(BSLObject):
    def __init__(self, catalogs, text='', documents=None):
        if documents is not None and documents._catalogs is not catalogs:
            raise ValueError('Query sources require one interpreter metadata snapshot')
        self._catalogs = catalogs
        self._documents = documents
        self._parameters = {}
        self._temp_tables_manager = None
        self.set_member('Text', text)

    def __str__(self):
        return 'Запрос'

    def get_member(self, name):
        if name.casefold() in ('temptablesmanager', 'менеджервременныхтаблиц'):
            return self._temp_tables_manager
        if name.casefold() in ('text', 'текст'):
            return self._text
        return self.get_method(name)

    def set_member(self, name, value):
        if name.casefold() in ('temptablesmanager', 'менеджервременныхтаблиц'):
            from .query_packages import BSLTempTablesManager
            if value is not None and type(value) is not BSLTempTablesManager:
                raise TypeError('Query.TempTablesManager requires TempTablesManager or Undefined')
            self._temp_tables_manager = value
            return
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
        if key in ('executebatch', 'выполнитьпакет'):
            return HostFunction(name, self.execute_batch)
        if key in ('execute', 'выполнить'):
            return HostFunction(name, self.execute)
        return super().get_member(name)

    def set_parameter(self, name, value):
        if not syntax.identifier(name):
            raise ValueError('Invalid query parameter name')
        key = name.casefold()
        if key not in self._parameters and len(self._parameters) >= _MAX_PARAMETERS:
            raise ValueError('Query parameter count limit exceeded')
        self._parameters[key] = value if type(value) is BSLValueTable else _parameter_value(value)

    def execute_batch(self):
        from .query_packages import execute_package
        return execute_package(syntax.parse_package(self._text), self._catalogs,
                               dict(self._parameters), self._temp_tables_manager, self._documents)

    def execute(self):
        statements = syntax.parse_package(self._text)
        query = statements[0]
        if (len(statements) != 1 or type(query) is not syntax.Select or query.into is not None
                or query.temporary or query.external
                or any(join.source.temporary or join.source.external for join in query.joins)
                or self._temp_tables_manager is not None):
            from .query_packages import execute_package
            return execute_package(statements, self._catalogs, dict(self._parameters),
                                   self._temp_tables_manager, self._documents).items[-1]
        from . import relational_queries
        if relational_queries.required(query):
            return relational_queries.execute(query, self._catalogs, dict(self._parameters), self._documents)
        manager = self._catalogs.get_index(query.catalog)
        section = None
        if query.section is not None:
            matches = [item for item in manager._schema.tabular_sections
                       if item.name.casefold() == query.section.casefold()]
            if len(matches) != 1:
                raise ValueError('Unknown query tabular section')
            section = matches[0]
        columns = []
        for projection in query.projections:
            column = _field(manager, projection.field, query.source_alias, section)
            name = ('Код' if not projection.explicit_alias and column.field == 'code'
                    else projection.alias)
            columns.append(_Column(name, column.field, column.kind,
                                   column.qualifiers, column.custom, projection.explicit_alias))
        if len({column.name.casefold() for column in columns}) != len(columns):
            raise ValueError('Duplicate localized query output column')
        predicate = _predicate(manager, query.predicate, query.source_alias, dict(self._parameters), section)
        order = tuple(CatalogOrder(_field(manager, item.field, query.source_alias, section).field, item.descending)
                      for item in query.order)
        rows = []
        text_units = 0
        continuation = None
        seen = set()
        seen_continuations = set()
        size = min(1000, query.limit)
        view = manager._view()
        try:
            while len(rows) < query.limit:
                request = CatalogScanRequest(predicate, order, size, continuation,
                                             string_comparison='casefold_v1')
                if section is None:
                    page = view.scan_catalog_values(manager._schema.identity, request,
                        tuple(column.field for column in columns))
                    if type(page) is not CatalogValuePage:
                        raise BackendError('integrity')
                    records = page.rows
                else:
                    page = view.scan_catalog_section(manager._schema.identity, section.identity, request)
                    if type(page) is not CatalogSectionPage:
                        raise BackendError('integrity')
                    records = page.rows
                if (type(records) is not tuple or len(records) > size
                        or (page.continuation is not None and
                            (type(page.continuation) is not str or len(page.continuation) != 32
                             or page.continuation in seen_continuations))):
                    raise BackendError('integrity')
                # Validate the full supplied page, including any tail beyond TOP.
                for projected in records:
                    if section is not None:
                        row = _section_row(manager, section, projected, columns, view, seen)
                    else:
                        if (type(projected) is not CatalogValueRow or type(projected.key) is not CatalogKey
                                or any(type(item) is not UUID for item in (projected.key.database_id,projected.key.catalog_id,projected.key.record_id))
                                or projected.key.database_id != view.database_id
                                or projected.key.catalog_id != manager._schema.identity
                                or type(projected.key.record_id) is not UUID or projected.key.record_id.int == 0
                                or type(projected.values) is not tuple or len(projected.values) != len(columns)
                                or projected.key.record_id in seen):
                            raise BackendError('integrity')
                        for column, value in zip(columns,projected.values):
                            if column.field == 'ref' and (type(value) is not CatalogKey
                                    or any(type(item) is not UUID for item in (value.database_id,value.catalog_id,value.record_id))
                                    or value != projected.key):
                                raise BackendError('integrity')
                        seen.add(projected.key.record_id)
                        row = tuple(_logical(manager, column, value) for column,value in zip(columns,projected.values))
                    if len(rows) >= query.limit:
                        continue
                    text_units += sum(len(value) for value in row if type(value) is str)
                    rows.append(row)
                    if len(rows) * len(columns) > _MAX_CELLS or text_units > _MAX_RESULT_TEXT:
                        raise ValueError('Query result resource limit exceeded')
                if page.continuation is None:
                    break
                if not records:
                    raise BackendError('integrity')
                seen_continuations.add(page.continuation)
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
