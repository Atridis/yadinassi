"""Atomic, bounded in-memory temporary tables for logical query packages.

These are explicit host semantics, not native temporary-table storage or measured
native statement-result parity. Persistent database access is read-only through
one CatalogReadView per package. No table rows escape as mutable buffers.
"""
from .database_transactions import query_view as _transaction_query_view

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from . import query_parser as syntax
from .values import BSLArray, BSLObject, HostFunction

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


def execute_package(statements, catalogs, parameters, manager=None, documents=None, information_registers=None, *, _enum_scope=None, _owned_view=None):
    from .queries import BSLQueryResult, _Column
    from .relational_queries import _Plan, snapshot_parameters
    from .query_sources import _UnionPlan, snapshot_sources
    if _enum_scope is not None:
        from .query_enum_reporting import _EnumReportScope
        from .sqlite_documents import DocumentView
        if (type(_enum_scope) is not _EnumReportScope or _enum_scope.catalogs is not catalogs
                or type(_owned_view) is not DocumentView):
            raise TypeError('Enum package requires the exact lexical report scope')
        _enum_scope.require_current()
    elif _owned_view is not None:
        raise TypeError('A borrowed package view requires an enum report scope')
    parameters = (_enum_scope.snapshot_parameters(parameters) if _enum_scope is not None
                  else snapshot_parameters(parameters))
    if manager is None: manager = BSLTempTablesManager()
    if type(manager) is not BSLTempTablesManager:
        raise TypeError('Query package requires TempTablesManager')
    if not manager._lock.acquire(blocking=False):
        raise ValueError('Temporary table manager is busy')
    view = _owned_view
    try:
        from .document_queries import needs_documents
        from .register_queries import needs_registers
        from .accumulation_queries import needs_accumulation
        documents_needed = needs_documents(statements)
        registers_needed = needs_registers(statements)
        accumulation_needed = needs_accumulation(statements)
        composite = documents_needed or registers_needed or accumulation_needed
        # Metadata initialization opens its own view. Finish it before the
        # single package transaction, including catalog-first packages. Do not
        # require document metadata for a register-only database.
        if documents_needed or accumulation_needed:
            if documents is None:
                raise ValueError('Document query sources require document context')
            documents._metadata._snapshot()
        if registers_needed:
            from .sqlite_catalog import SQLiteCatalogBackend
            from .configuration_posting import PostingConfiguration
            context = documents._context if documents is not None else None
            backend = context.backend if context is not None else None
            posting = backend.posting_configuration if type(backend) is SQLiteCatalogBackend else None
            if type(posting) is PostingConfiguration:
                documents._metadata._snapshot()
            else:
                if information_registers is None:
                    raise ValueError('Information-register query sources require register context')
                information_registers._metadata._snapshot()
        if composite: catalogs._metadata._snapshot()
        if manager._closed:
            raise ValueError('Temporary table manager is closed')
        owner = catalogs._metadata
        if manager._owner is not None and manager._owner is not owner:
            raise ValueError('Temporary table manager belongs to another metadata snapshot')
        external = snapshot_sources(statements, parameters, catalogs, documents)
        tables = dict(manager._tables)
        if _enum_scope is not None:
            from .query_enum_tables import prepare_tables
            external = prepare_tables(external, _enum_scope)
            tables = prepare_tables(tables, _enum_scope)
        from .query_reference_tables import input_bindings, validate_view
        bindings = input_bindings((*external.values(), *tables.values()), catalogs, documents)
        if bindings:
            composite = composite or any(b.kind == 'document_ref' for b in bindings)
            if view is None:
                view = (catalogs._context.backend.begin_query_read() if composite
                        else _transaction_query_view(bindings[0].issuer))
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
                if view is None and source_manager is not None:
                    view = (catalogs._context.backend.begin_query_read() if composite else _transaction_query_view(source_manager))
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
        manager._tables = tables
        manager._owner = owner
        return result
    finally:
        try:
            if view is not None: view.close()
        finally:
            manager._lock.release()
