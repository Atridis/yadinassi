"""Atomic, bounded in-memory temporary tables for logical query packages.

These are explicit host semantics, not native temporary-table storage or measured
native statement-result parity. A package borrows one read-only connection,
or the existing transaction when present. No table rows escape as mutable buffers.
"""
from yadinassi.db.database_transactions import (open_query_read as _open_query_read,
    query_view as _transaction_query_view, pin_query_snapshot)
from yadinassi.db.catalog.catalog_backend import BackendError

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from . import query_parser as syntax
from yadinassi.types.values import BSLArray, BSLObject, HostFunction

MAX_TABLES = 16
MAX_ROWS = 10000
MAX_CELLS = 100000
MAX_TEXT = 8000000


@dataclass(frozen=True, slots=True)
class _Table:
    columns: tuple
    rows: tuple


def _cost(columns, rows):
    return len(columns) * len(rows), sum(len(v) for row in rows for v in row if type(v) is str)


def _check_tables(tables):
    if len(tables) > MAX_TABLES:
        raise ValueError('Temporary table count limit exceeded')
    cells = text = 0
    for table in tables.values():
        if len(table.rows) > MAX_ROWS:
            raise ValueError('Temporary table row limit exceeded')
        c, t = _cost(table.columns, table.rows)
        cells += c; text += t
        if cells > MAX_CELLS or text > MAX_TEXT:
            raise ValueError('Temporary table resource limit exceeded')


TEMP_TABLE_MANAGER_NAMES = ('temptablesmanager', 'менеджервременныхтаблиц')


class BSLTempTablesManager(BSLObject):
    """Explicitly owned table lifetime; a closed manager cannot be reopened."""
    def __init__(self, owner=None):
        self._tables = {}
        self._owner = owner
        self._closed = False
        self._lock = Lock()

    def __str__(self):
        return 'Менеджер временных таблиц'

    def get_member(self, name):
        if name.casefold() in ('close', 'закрыть'):
            return HostFunction(name, self.close, returns_value=False)
        return super().get_member(name)

    def close(self):
        if not self._lock.acquire(blocking=False):
            raise ValueError('Temporary table manager is busy')
        try:
            self._tables = {}
            self._closed = True
        finally:
            self._lock.release()


def _package_sources(statements, validate_node=None):
    """Collect all source requirements in the same pre-order as binding."""
    families, external = set(), {}
    stored_sources = 0
    reads_hierarchy = False
    for node in syntax.walk_nodes(statements):
        if validate_node is not None:
            validate_node(node)
        if type(node) is syntax.Hierarchy:
            reads_hierarchy = True
        if type(node) is syntax.Select:
            families.add(node.family)
            if node.external:
                external[node.catalog.casefold()] = None
            elif not node.temporary and node.derived is None:
                stored_sources += 1
            for join in node.joins:
                source = join.source
                families.add(source.family)
                if source.external:
                    external[source.catalog.casefold()] = None
                elif not source.temporary and source.derived is None:
                    stored_sources += 1
    return families, tuple(external), stored_sources > 1 or (stored_sources != 0 and reads_hierarchy)


def execute_owned_package(owner, statements, catalogs, parameters, manager, documents,
                          information_registers):
    """Execute one logical package under the configuration's owned read lease."""
    from yadinassi.configuration.demos.inventory_enum_runtime import read_snapshot
    from .query_enum_reporting import _EnumReportScope
    from .query_enum_tables import _preflight_parameters, validate_profile_node
    if type(statements) is not tuple or not statements:
        raise BackendError('invalid_input')
    sources = _package_sources(statements, validate_profile_node)
    parameters = _preflight_parameters(owner, catalogs, parameters)
    view, scope = _open_query_read(owner.backend), None
    try:
        if sources[2]: pin_query_snapshot(view)
        with read_snapshot(owner.metadata, view):
            if (view.database_id != view._view.database_id
                    or view.configuration_generation != view._view.configuration_generation):
                raise BackendError('schema_changed')
            scope = _EnumReportScope(catalogs, owner=owner, view=view)
            return execute_package(statements, catalogs, parameters, manager, documents,
                                   information_registers, _enum_scope=scope, _owned_view=view,
                                   _sources=sources)
    finally:
        try:
            if not view._view._closed:
                view.close()
        finally:
            if scope is not None: scope._retired = True


def execute_package(statements, catalogs, parameters, manager=None, documents=None, information_registers=None, *, _enum_scope=None, _owned_view=None, _source_scope=None, _sources=None):
    from .queries import BSLQueryResult, _Column
    from .relational_queries import _Plan, snapshot_parameters
    from .query_sources import _UnionPlan, _snapshot_named_sources
    if _source_scope is not None:
        from .source_query_references import SourcePackageScope
        if type(_source_scope) is not SourcePackageScope or _enum_scope is not None or _owned_view is not None:
            raise TypeError('Invalid source package capability')
        _source_scope.require_context(statements, catalogs)
    if _enum_scope is not None:
        from .query_enum_reporting import _EnumReportScope
        from yadinassi.db.sqlite.sqlite_documents import DocumentView
        if (type(_enum_scope) is not _EnumReportScope or _enum_scope.catalogs is not catalogs
                or type(_owned_view) is not DocumentView):
            raise TypeError('Enum package requires the exact lexical report scope')
        _enum_scope.require_current()
    elif _owned_view is not None:
        raise TypeError('A borrowed package view requires an enum report scope')
    parameters = (_enum_scope.validate_frozen_parameters(parameters) if _enum_scope is not None
                  else snapshot_parameters(parameters))
    if manager is not None:
        if type(manager) is not BSLTempTablesManager:
            raise TypeError('Query package requires TempTablesManager')
        if not manager._lock.acquire(blocking=False):
            raise ValueError('Temporary table manager is busy')
    view = _owned_view
    try:
        families, external_names, shared_snapshot = (_package_sources(statements) if _sources is None else _sources)
        documents_needed = 'document' in families
        registers_needed = 'information_register' in families
        accumulation_needed = 'accumulation_register' in families
        composite = documents_needed or registers_needed or accumulation_needed
        # Prime required metadata from the open SQLite backend, not another
        # read transaction. Other backend protocols retain their own readers.
        if documents_needed or accumulation_needed:
            if documents is None:
                raise ValueError('Document query sources require document context')
            if _enum_scope is None: documents._metadata._snapshot(query_language=True)
        if registers_needed:
            from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
            from yadinassi.configuration.configuration_posting import PostingConfiguration
            context = documents._context if documents is not None else None
            backend = context.backend if context is not None else None
            posting = backend.posting_configuration if type(backend) is SQLiteCatalogBackend else None
            if type(posting) is PostingConfiguration:
                documents._metadata._snapshot(query_language=True)
            else:
                if information_registers is None:
                    raise ValueError('Information-register query sources require register context')
                information_registers._metadata._snapshot(query_language=True)
        if composite and _enum_scope is None: catalogs._metadata._snapshot(query_language=True)
        owner = catalogs._metadata
        if manager is not None:
            if manager._closed:
                raise ValueError('Temporary table manager is closed')
            source_owner = getattr(manager, '_source_owner', None)
            if source_owner is not None:
                from weakref import ReferenceType
                if type(source_owner) is not ReferenceType:
                    raise TypeError('Invalid source temporary manager owner')
                if _source_scope is None:
                    raise ValueError('Source temporary manager requires a source-owned snapshot')
                if source_owner() is not _source_scope.ownerapp():
                    raise TypeError('Source temporary manager belongs to another application')
            if manager._owner is not None and manager._owner is not owner:
                raise ValueError('Temporary table manager belongs to another metadata snapshot')
        external = (_snapshot_named_sources(external_names, parameters, catalogs, documents) if _source_scope is None
                    else _source_scope.external_tables(statements, parameters, catalogs, documents))
        tables = {} if manager is None else dict(manager._tables)
        if _enum_scope is not None and (external or tables):
            from .query_enum_tables import prepare_tables
            external = prepare_tables(external, _enum_scope)
            tables = prepare_tables(tables, _enum_scope)
        from .query_reference_tables import _Binding, input_bindings, validate_view
        bindings = input_bindings((*external.values(), *tables.values()), catalogs, documents)
        from .source_query_references import SourceBinding
        if _source_scope is None and any(type(binding) is SourceBinding for binding in bindings):
            raise ValueError("Source reference report re-query requires a source-owned snapshot; unsupported")
        if _source_scope is not None:
            if any(type(binding) is not SourceBinding for binding in bindings):
                raise TypeError('Source packages reject legacy reference bindings')
            validate_view(bindings, None)
        elif bindings:
            composite = composite or any(b.kind == 'document_ref' for b in bindings)
            if view is None:
                from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
                backend = catalogs._context.backend if composite else bindings[0].issuer._backend
                if type(backend) is SQLiteCatalogBackend and any(type(binding) is _Binding for binding in bindings):
                    # Typed reports retain a database generation; validate the live
                    # generation once on the package view, including empty reports.
                    view = backend.begin_query_read()
                else:
                    view = (_open_query_read(backend) if composite
                            else _transaction_query_view(bindings[0].issuer))
                if shared_snapshot: pin_query_snapshot(view)
            validate_view(bindings, view)
        result = BSLArray()
        budget = [0, 0, 0, 0] if _enum_scope is not None else [0, 0]
        condition_budget = [0, 0]
        result_cells = result_text = 0
        for statement in statements:
            if type(statement) is syntax.Destroy:
                key = statement.name.casefold()
                if key not in tables: raise ValueError('Unknown temporary table')
                del tables[key]
                output = BSLQueryResult((), ())
            else:
                if statement.into is not None and statement.into.casefold() in tables:
                    raise ValueError('Temporary table already exists')
                plan_type = _UnionPlan if type(statement) is syntax.Union else _Plan
                plan = plan_type(statement, catalogs, parameters, tables, external, documents=documents,
                                 information_registers=information_registers, enum_scope=_enum_scope, condition_budget=condition_budget)
                source_manager = next((m for m in plan.all_managers if m is not None), None)
                if _source_scope is not None and source_manager is not None:
                    raise ValueError('Source package cannot acquire legacy manager view')
                if view is None and source_manager is not None:
                    view = (_open_query_read(catalogs._context.backend) if composite else _transaction_query_view(source_manager))
                    if shared_snapshot: pin_query_snapshot(view)
                output = plan.execute(view=view, budget=budget)
                if statement.into is not None:
                    tables[statement.into.casefold()] = _Table(output._columns, output._rows)
                    _check_tables(tables)
                    # Explicit host statement result; not native parity evidence.
                    output = BSLQueryResult((_Column('Count', None, 'number', (38, 0, 'Any'), explicit_alias=True),),
                                            ((Decimal(len(output._rows)),),))
            cells, text = _cost(output._columns, output._rows)
            result_cells += cells; result_text += text
            if result_cells > MAX_CELLS or result_text > MAX_TEXT:
                raise ValueError('Query package result resource limit exceeded')
            if _enum_scope is not None:
                from .query_enum_tables import detach_columns
                output = BSLQueryResult(detach_columns(output._columns), output._rows)
            result.items.append(output)
        if _enum_scope is not None:
            _enum_scope.require_current()
            from .query_enum_tables import detach_columns
            tables = {name: _Table(detach_columns(t.columns), t.rows) for name, t in tables.items()}
        # Closing is part of success: a port close failure must not publish temps.
        if view is not None:
            closing, view = view, None
            closing.close()
        if _source_scope is not None:
            _source_scope.require_context(statements, catalogs)
        if manager is not None:
            if _source_scope is not None:
                manager._source_owner = _source_scope.ownerapp
            manager._tables = tables
            manager._owner = owner
        return result
    finally:
        try:
            if view is not None: view.close()
        finally:
            if manager is not None: manager._lock.release()
