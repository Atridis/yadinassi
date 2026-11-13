"""Read-only Constants query snapshot using the existing closed relational engine.

No user text is SQL. Only explicitly referenced scalar constants are read; no
invented catalog/register tables or guessed defaults are supplied.
"""
from dataclasses import replace
from .queries import BSLQuery, _Column
from .values import HostFunction
from . import query_parser as syntax
from .source_constants_runtime import SourceConstants


class SourceConstantQuery(BSLQuery):
    def __init__(self, caller, application, text=''):
        super().__init__(caller._catalogs, text)
        self._source_owner = SourceConstants(application)

    def get_method(self, name):
        key = name.casefold()
        if key in ('execute', 'выполнить'):
            return HostFunction(name, SourceQueryCall(self))
        if key in ('executebatch', 'выполнитьпакет'):
            return HostFunction(name, SourceQueryCall(self, batch=True))
        return super().get_method(name)

    def execute(self):
        raise ValueError('source constant queries require actual interpreter caller')

    def execute_batch(self):
        raise ValueError('source constant query packages unsupported')

    def read(self, caller, *, batch=False):
        statements = syntax.parse_package(self._text)
        uses_constants = any(
            (node.temporary and node.catalog.casefold() in ('constants', 'константы'))
            for node in syntax.walk_nodes(statements) if type(node) in (syntax.Select, syntax.Source))
        if not uses_constants:
            # Preserve previously available in-memory/external-table Query behavior.
            # Its existing binder continues to reject unactivated DB sources.
            return BSLQuery.execute_batch(self) if batch else BSLQuery.execute(self)
        if batch:
            raise ValueError('source constant query packages unsupported')
        store = self._source_owner._store(caller)
        app = self._source_owner._application()
        if caller._scheduler.pending:
            raise ValueError('source constant queries require synchronous execution')
        if any(m.family == 'CommonAttribute' for m in app.source.metadata):
            raise ValueError('source constant query data separation unsupported')
        if self._temp_tables_manager is not None:
            raise ValueError('source constant query temporary tables unsupported')
        if len(statements) != 1 or type(statements[0]) is not syntax.Select:
            raise ValueError('source constant query requires one SELECT')
        query = statements[0]
        if (not query.temporary or query.external or query.catalog.casefold() not in ('constants', 'константы')
                or query.joins or query.into is not None or query.derived is not None or query.section is not None
                or sum(type(n) is syntax.Select for n in syntax.walk_nodes(query)) != 1):
            raise ValueError('only the source Constants table is supported')
        if syntax.extended_filters(query):
            raise ValueError('source constant query extended filters unsupported')
        aliases = {p.alias.casefold() for p in query.projections if p.explicit_alias}
        order_fields = {id(order.field) for order in query.order}
        names = {}
        for node in syntax.walk_nodes(query):
            if type(node) is not syntax.Field:
                continue
            if len(node.parts) not in (1, 2) or (len(node.parts) == 2 and node.parts[0].casefold() != query.source_alias.casefold()):
                raise ValueError('unknown source Constants query field qualifier')
            name = node.parts[-1]
            if id(node) in order_fields and len(node.parts) == 1 and name.casefold() in aliases:
                continue
            definition = store._definition(name)
            if definition.kind not in ('string', 'number', 'boolean', 'datetime'):
                raise ValueError('source constant query supports only scalar fields: ' + name)
            names[name.casefold()] = definition
        if len(names) > 128:
            raise ValueError('source constant query field bound')
        definitions = tuple(names.values())
        columns = tuple(_Column(d.name, None, d.kind, d.qualifiers, explicit_alias=True) for d in definitions)
        from .query_packages import _Table
        from .relational_queries import _Plan
        # Bind and type-check all expressions before reading values. The same
        # closed plan later consumes precisely one immutable constants snapshot.
        translated = replace(query, temporary=False, external=True)
        parameters = dict(self._parameters)
        tables = {query.catalog.casefold(): _Table(columns, ())}
        plan = _Plan(translated, self._catalogs, parameters, external_tables=tables)
        snapshot = store.get_many(tuple(d.name for d in definitions))
        tables[query.catalog.casefold()] = _Table(columns, (tuple(snapshot[d.name.casefold()] for d in definitions),))
        self._source_owner._store(caller)
        return plan.execute()


class SourceQueryCall:
    def __init__(self, query, batch=False):
        self.query, self.batch = query, batch

    def __call__(self, *values):
        raise ValueError('source query execution requires actual interpreter caller')

    def invoke(self, caller, values):
        if values:
            raise TypeError('Query.Execute takes no arguments')
        return self.query.read(caller, batch=self.batch)
