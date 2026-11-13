"""Read-only Constants query snapshot using the existing closed relational engine.

No user text is SQL. Only explicitly referenced scalar constants are read; no
invented catalog/register tables or guessed defaults are supplied.
"""
from dataclasses import replace, fields, is_dataclass
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
        if len(statements) != 1 or type(statements[0]) not in (syntax.Select, syntax.Union):
            raise ValueError('source constant query requires one SELECT or UNION')
        query = statements[0]
        source_names = set()
        names = {}
        for arm in syntax.selects((query,)):
            if arm.into is not None:
                raise ValueError('source constant query temporary tables unsupported')
            sources = (syntax.Source(arm.catalog, arm.source_alias, arm.section, arm.temporary,
                                      arm.external, arm.family, arm.period_boundary, arm.derived),
                       *(join.source for join in arm.joins))
            direct_aliases = set()
            for source in sources:
                if source.derived is not None:
                    continue
                if (not source.temporary or source.external or source.section is not None
                        or source.catalog.casefold() not in ('constants', 'константы')):
                    raise ValueError('only the source Constants table is supported')
                source_names.add(source.catalog.casefold())
                direct_aliases.add(source.alias.casefold())
            aliases = {p.alias.casefold() for p in arm.projections if p.explicit_alias}
            order_fields = {id(order.field) for order in arm.order}
            for node in _local_nodes(arm):
                if type(node) is not syntax.Field:
                    continue
                if len(node.parts) not in (1, 2):
                    raise ValueError('unknown source Constants query field qualifier')
                name = node.parts[-1]
                if len(node.parts) == 2 and node.parts[0].casefold() not in direct_aliases:
                    continue  # Derived names and invalid aliases are checked by the binder.
                if len(node.parts) == 1:
                    if (not direct_aliases or not store.has(name)
                            or (id(node) in order_fields and name.casefold() in aliases)):
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
        from .relational_queries import _Plan, snapshot_parameters
        from .query_sources import _UnionPlan
        # Bind and type-check all expressions before reading values. The same
        # closed plan later consumes precisely one immutable constants snapshot.
        translated = _translate(query)
        parameters = snapshot_parameters(dict(self._parameters))
        tables = {name: _Table(columns, ()) for name in source_names}
        plan_type = _UnionPlan if type(query) is syntax.Union else _Plan
        plan = plan_type(translated, self._catalogs, parameters, external_tables=tables)
        snapshot = store.get_many(tuple(d.name for d in definitions))
        frozen = _Table(columns, (tuple(snapshot[d.name.casefold()] for d in definitions),))
        for name in source_names:
            tables[name] = frozen
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


def _local_nodes(arm):
    """Walk one lexical SELECT, not fields belonging to its nested SELECTs."""
    def walk(node):
        if type(node) in (syntax.Select, syntax.Union):
            return
        if type(node) is tuple:
            for child in node:
                yield from walk(child)
        elif is_dataclass(node):
            yield node
            for item in fields(node):
                yield from walk(getattr(node, item.name))
    for item in fields(arm):
        yield from walk(getattr(arm, item.name))


def _translate(node):
    if type(node) is tuple:
        return tuple(_translate(item) for item in node)
    if not is_dataclass(node):
        return node
    changes = {item.name:_translate(getattr(node,item.name)) for item in fields(node)}
    if type(node) in (syntax.Select, syntax.Source) and node.derived is None:
        changes.update(temporary=False, external=True)
    return replace(node, **changes)
