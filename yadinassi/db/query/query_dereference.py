"""Typed, explicit one-hop query paths, not live BSL reference access."""
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from . import query_parser as syntax
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogKey
from yadinassi.db.catalog.catalog_qualifiers import validate_string
from yadinassi.db.document.document_backend import DocumentKey
from yadinassi.temporal.dates import _date_from_datetime
from yadinassi.types.values import NULL


@dataclass(frozen=True, slots=True)
class BoundPath:
    source: int
    origin: str | UUID
    family: str
    manager: object
    column: object


def require_shape(query):
    if (query.joins or query.derived is not None or query.temporary or query.external
            or query.into is not None or query.period_boundary is not None
            or query.virtual_condition is not None or query.groups or query.having is not None or query.distinct
            or any(type(item.field) is not syntax.Field for item in (*query.projections, *query.order))):
        raise ValueError('Query dereference requires a flat field-only SELECT')


def _target(plan, family, identity):
    if type(identity) is not UUID or not identity.int:
        raise ValueError('Query dereference requires a declared reference target')
    if plan.enum_scope is not None:
        plan.enum_scope.prepare_family(family)
    if family == 'catalog':
        plan.catalogs._metadata._snapshot(query_language=True)
        return plan.catalogs._manager_by_metadata_uuid(identity)
    documents = plan.documents
    if family != 'document' or documents is None:
        raise ValueError('Query dereference requires the declared document context')
    if documents._catalogs is not plan.catalogs or documents._context is not plan.catalogs._context:
        raise BackendError('schema_changed')
    matches = [item for item in documents._metadata._snapshot(query_language=True).values()
               if item._schema.identity == identity]
    if len(matches) != 1:
        raise ValueError('Query dereference document target is not present')
    return documents.get_index(matches[0]._name)


def bind(plan, field):
    parts = field.parts
    source = plan.sources[0]
    if len(parts) == 3 and parts[0].casefold() != source.alias.casefold():
        raise ValueError('Unknown query dereference source qualifier')
    base = plan.resolve_field(0, syntax.Field((parts[-2],)))
    if base.kind == 'catalog_ref':
        family = 'catalog'
    elif base.kind == 'document_ref':
        family = 'document'
    else:
        raise TypeError('Query dereference requires a declared reference field')
    from .relational_queries import _BoundField
    metadata, identity = plan.reference_identity(_BoundField(0, base))
    manager = _target(plan, family, identity)
    context = manager._catalogs._metadata if family == 'catalog' else manager._documents._metadata
    if metadata is not context:
        raise BackendError('schema_changed')
    tail = syntax.Field((parts[-1],))
    if family == 'catalog':
        from .queries import _field
        column = _field(manager, tail, source.alias)
        if column.kind == 'catalog_ref':
            target = manager._schema.identity if column.custom is None else column.custom.target_catalog_id
            column = replace(column, reference_identity=(context, target))
    else:
        from .document_queries import document_field
        column = document_field(manager, tail, source.alias)
    if column.kind == 'enum_ref':
        raise ValueError('Query dereference of an enum field is unsupported')
    return BoundPath(0, base.field, family, manager, column)


def _reference_converter(plan, expression):
    column = expression.column
    metadata, identity = plan.reference_identity(expression)
    family = column.kind.removesuffix('_ref')
    manager = _target(plan, family, identity)
    catalog = family == 'catalog'
    context = manager._catalogs._metadata if catalog else manager._documents._metadata
    if context is not metadata:
        raise BackendError('schema_changed')
    key_type = CatalogKey if catalog else DocumentKey

    def convert(value, database):
        if (type(value) is not key_type or type(value.database_id) is not UUID
                or value.database_id != database or type(value.record_id) is not UUID
                or (column.custom is None and column.field in ('ref','recorder')
                    and not value.record_id.int)):
            raise BackendError('integrity')
        entity = value.catalog_id if catalog else value.document_id
        if type(entity) is not UUID or entity != identity:
            raise BackendError('integrity')
        return manager._ref(value.record_id)
    return convert



def _where(plan):
    if plan.predicate is None: return None
    from .query_ordered_predicates import bind_scalar_predicate
    from yadinassi.db.catalog.catalog_types import BSLCatalogReference
    from yadinassi.db.document.document_types import BSLDocumentReference

    def key(field, value):
        catalog = field.column.kind == 'catalog_ref'
        expected = BSLCatalogReference if catalog else BSLDocumentReference
        if type(value) is not expected or type(value.reference_uuid) is not UUID:
            return None
        metadata, identity = plan.reference_identity(field)
        if value.value_type.snapshot is not metadata or value.value_type.metadata_uuid != identity:
            return None
        database = plan.catalogs._metadata._database_id
        physical_key = CatalogKey if catalog else DocumentKey
        return physical_key(database, identity, value.reference_uuid)

    result = bind_scalar_predicate(plan, (
        'ref', 'code', 'description', 'deletion_mark', 'parent', 'is_folder',
        'number', 'date', 'posted', 'line_number', 'recorder', 'period', 'active',
    ), allow_or=False, reference=key)
    if result is None:
        raise ValueError('Query dereference WHERE requires source-field comparisons combined by AND')
    return result

def _converter(plan, expression, manager):
    from .queries import _section_value
    column = expression.column
    if column.kind in ('catalog_ref', 'document_ref'):
        convert = _reference_converter(plan, expression)
    elif column.kind == 'enum_ref':
        raise ValueError('Enum projection with query dereference is unsupported')
    elif column.custom is not None:
        def convert(value, database):
            return _section_value(manager, column.custom, value)
    else:
        def convert(value, database):
            try:
                if column.kind == 'string':
                    validate_string(value, column.qualifiers[0])
                    if column.field == 'number' and not value:
                        raise BackendError('integrity')
                elif column.kind == 'boolean':
                    if type(value) is not bool: raise BackendError('integrity')
                elif column.kind == 'datetime':
                    if type(value) is not datetime or value.tzinfo is not None or value.microsecond:
                        raise BackendError('integrity')
                    return _date_from_datetime(value)
                elif column.kind == 'number':
                    if type(value) is not Decimal or not value.is_finite() or not 1 <= value <= 10000:
                        raise BackendError('integrity')
                else:
                    raise BackendError('integrity')
                return value
            except (ValueError, TypeError):
                raise BackendError('integrity') from None
    if type(expression) is BoundPath:
        return lambda value, database: NULL if value is None else convert(value, database)
    return convert


class Dereference:
    def __init__(self, plan):
        from .recorder_queries import RecorderQueryManager
        from .relational_queries import _BoundField
        source = plan.sources[0]
        manager = plan.managers[0]
        section = plan.sections[0]
        family = 'recorder' if type(manager) is RecorderQueryManager else source.family
        self.source = (family, manager._schema.identity, None if section is None else section.identity)
        if manager._catalogs is not plan.catalogs:
            raise BackendError('schema_changed')
        collection = (manager._documents if family == 'document' else
                      manager.documents if family in ('recorder', 'accumulation_register') else
                      manager._registers if family == 'information_register' else plan.catalogs)
        if collection._context is not plan.catalogs._context:
            raise BackendError('schema_changed')
        schema = manager.recorder_schema if family == 'recorder' else manager._schema
        schemas = {(family, schema.identity): schema}
        paths, positions, converters = [], {}, []

        def put(expression):
            if type(expression) is BoundPath:
                target = expression.manager
                identity = target._schema.identity
                path = (expression.origin, expression.family, identity, expression.column.field)
                schemas[(expression.family, identity)] = target._schema
            elif type(expression) is _BoundField and expression.source == 0:
                target = manager
                path = (expression.column.field, None, None, None)
            else:
                raise ValueError('Unsupported query dereference projection')
            position = positions.get(path)
            if position is None:
                position = positions[path] = len(paths)
                paths.append(path)
                converters.append(_converter(plan, expression, target))
            return position

        self.projection = tuple(put(expression) for expression in plan.projections)
        self.order = tuple((put(expression), descending) for expression, descending in plan.orders)
        self.paths = tuple(paths)
        self.converters = tuple(converters)
        self.schemas = tuple(schemas.items())
        self.predicate = _where(plan)

    def _require_schemas(self, view):
        # All families use the same checked read view and open descriptors.
        # Do not transfer authority from a separately supplied manager.
        backend = view._view._backend
        for (family, identity), expected in self.schemas:
            if family == 'catalog':
                actual = view.catalog_schema(identity)
            elif family == 'document':
                actual = view.document_schema(identity)
            elif family == 'information_register':
                actual = view.register_schema(identity)
            else:
                config = (backend.posting_configuration if family == 'recorder'
                          else backend.accumulation_configuration)
                if config is None: raise BackendError('schema_changed')
                actual = next((schema for schema in config.registers if schema.identity == identity), None)
            if actual != expected:
                raise BackendError('schema_changed')

    def execute(self, plan, view, budget):
        from .queries import BSLQueryResult, _MAX_CELLS, _MAX_RESULT_TEXT
        from yadinassi.db.sqlite.sqlite_documents import DocumentView
        from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
        if type(view) is not DocumentView or type(plan.catalogs._context.backend) is not SQLiteCatalogBackend:
            raise ValueError('Query dereference requires the owned SQLite query port')
        # No residual per-row BSL reference access if a closed physical shape is refused.
        provider = getattr(DocumentView, 'query_dereference', None)
        if provider is None or view._view._backend is not plan.catalogs._context.backend:
            raise ValueError('Query dereference is unsupported for this source')
        metadata = plan.catalogs._metadata
        if (view.database_id != metadata._database_id
                or view.configuration_generation != metadata._generation):
            raise BackendError('schema_changed')
        self._require_schemas(view)
        count = plan.query.limit
        limit = count + (count == syntax.MAX_ROWS)
        if self.predicate is None:
            result = provider(view, self.source, self.paths, self.order, limit)
        else:
            result = provider(view, self.source, self.paths, self.order, limit,
                              predicate=self.predicate)
        if result is None:
            raise ValueError('Query dereference is unsupported for this source')
        if type(result) is not tuple or len(result) > limit:
            raise BackendError('integrity')
        if len(result) > count:
            raise ValueError('Query input row limit exceeded')
        rows, text = [], 0
        for raw in result:
            if type(raw) is not tuple or len(raw) != len(self.paths):
                raise BackendError('integrity')
            values = tuple(convert(value, view.database_id) for convert, value in zip(self.converters, raw))
            budget[0] += len(values)
            budget[1] += sum(len(value) for value in values if type(value) is str)
            row = tuple(values[i] for i in self.projection)
            text += sum(len(value) for value in row if type(value) is str)
            rows.append(row)
            if (budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT
                    or len(rows)*len(self.projection) > _MAX_CELLS or text > _MAX_RESULT_TEXT):
                raise ValueError('Query dereference resource limit exceeded')
        return BSLQueryResult(plan.columns, tuple(rows))
