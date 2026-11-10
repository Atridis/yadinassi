"""Bounded relational execution over CatalogReadView, independent of SQL engines.

Joins, computed expressions, grouping and aggregates operate on one logical
transaction snapshot. Computed numeric scale and rounding are host rules.
Input/intermediate bounds fail explicitly, never return partial aggregate totals.
String equality/order uses the existing casefold_v1 host policy, not regional 1C
collation. Decimal aggregation uses an owned context, not the caller's context.
"""
from .database_transactions import query_view as _transaction_query_view

from dataclasses import dataclass, replace
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN
from uuid import UUID

from . import query_parser as syntax
from .catalog_backend import (BackendError, CatalogKey, CatalogScanRequest,
    CatalogValuePage, CatalogValueRow, CatalogSectionPage)
from .catalog_types import BSLCatalogReference
from .document_types import BSLDocumentReference
from .dates import BSLDate
from .values import NULL

MAX_JOIN_PAIRS = 1000000
MAX_INTERMEDIATE_ROWS = 10000
MAX_MEMBERSHIP_WORK = 1000000


@dataclass(frozen=True)
class _BoundField:
    source: int
    column: object


@dataclass(frozen=True)
class _BoundAggregate:
    function: str
    field: object | None
    distinct: bool


@dataclass(frozen=True)
class _ParameterList:
    values: tuple


@dataclass(frozen=True)
class _BoundMembership:
    field: object
    values: tuple
    plan: object = None
    constant: bool = False


@dataclass(frozen=True)
class _BoundHierarchy:
    field: object
    root: object
    manager: object


def snapshot_parameters(parameters):
    """Freeze admitted list buffers before any package source is opened."""
    from .values import BSLArray, BSLFixedArray
    from .queries import _parameter_value, _MAX_CELLS, _MAX_RESULT_TEXT
    result, cells, text = dict(parameters), 0, 0
    for name, value in parameters.items():
        if type(value) is not BSLArray and type(value) is not BSLFixedArray: continue
        items = value.items
        if (type(items) is not list and type(items) is not tuple) or len(items) > syntax.MAX_ROWS:
            raise ValueError('Query parameter list limit exceeded')
        frozen = tuple(items)
        cells += len(frozen)
        for item in frozen:
            if item is not NULL: _parameter_value(item)
            text += len(item) if type(item) is str else 0
        if cells > _MAX_CELLS or text > _MAX_RESULT_TEXT:
            raise ValueError('Query parameter list resource limit exceeded')
        result[name] = _ParameterList(frozen)
    return result


def required(query):
    def extended(node):
        if type(node) is syntax.Membership or type(node) is syntax.Hierarchy: return True
        if type(node) is syntax.Predicate:
            return node.kind == 'not' or any(extended(term) for term in node.terms)
        return (type(node) is syntax.Comparison and
                (node.operator in ('is_null', 'is_not_null') or type(node.field) is not syntax.Field or
                 type(node.value) in (syntax.Field, syntax.Aggregate, syntax.Expression, syntax.NullLiteral) or node.value is None))
    return (query.derived is not None or query.family in ('document', 'information_register') or query.joins or query.groups or query.having is not None or query.distinct
            or any(type(p.field) is not syntax.Field for p in query.projections)
            or any(type(o.field) is not syntax.Field for o in query.order)
            or extended(query.predicate))


def _key(value):
    if value is NULL: return ('null',)
    if type(value) is str: return ('string', value.casefold())
    if type(value) is bool: return ('boolean', value)
    if type(value) is Decimal: return ('number', value)
    if type(value) is BSLDate: return ('datetime', value.ticks)
    if type(value) is BSLCatalogReference or type(value) is BSLDocumentReference:
        return ('document_ref' if type(value) is BSLDocumentReference else 'catalog_ref', id(value.value_type.snapshot),
                value.value_type.metadata_uuid.int, value.reference_uuid.int)
    raise TypeError('Unsupported relational query value')


def _compare(left, right, operator):
    # SQL NULL comparisons are unknown, hence not selected by ON/WHERE/HAVING.
    if left is NULL or right is NULL: return None
    a, b = _key(left), _key(right)
    if a[0] != b[0]: raise TypeError('Query comparison requires exact field type')
    if a[0] in ('catalog_ref', 'document_ref') and a[1:3] != b[1:3]:
        raise TypeError('Query references require same database and catalog')
    if a[0] in ('catalog_ref', 'document_ref', 'boolean') and operator not in ('eq', 'ne'):
        raise ValueError('Query value does not support ordering comparison')
    if operator == 'eq': return a == b
    if operator == 'ne': return a != b
    if operator == 'lt': return a < b
    if operator == 'le': return a <= b
    if operator == 'gt': return a > b
    if operator == 'ge': return a >= b
    raise ValueError('Unsupported query comparison')


class _Plan:
    def __init__(self, query, catalogs, parameters, temporary_tables=None, external_tables=None, *, allow_null=False, documents=None, information_registers=None):
        # Import here to keep the existing result/cursor API in one module.
        from .queries import _Column, _field
        self.query, self.parameters = query, parameters
        self.catalogs, self.documents = catalogs, documents
        self.information_registers = information_registers
        self._descriptors = {}
        self.memberships = []
        self.hierarchies = []
        self.hierarchy_maps = {}
        self._membership_sets = {}
        self.temporary_tables = temporary_tables or {}
        self.external_tables = external_tables or {}
        self.sources = (syntax.Source(query.catalog, query.source_alias, query.section, query.temporary, query.external, query.family, query.period_boundary, query.derived),
                        *(join.source for join in query.joins))
        self.derived_plans = {}
        self.managers, self.sections, self.fields = [], [], [[] for _ in self.sources]
        for index, source in enumerate(self.sources):
            if source.derived is not None:
                from .query_sources import _UnionPlan
                if type(source.derived) is not syntax.Select and type(source.derived) is not syntax.Union:
                    raise TypeError('Invalid derived query source')
                if source.derived.into is not None:
                    raise ValueError('Derived source cannot create a temporary table')
                plan_type = _UnionPlan if type(source.derived) is syntax.Union else _Plan
                self.derived_plans[index] = plan_type(source.derived, catalogs, parameters,
                    self.temporary_tables, self.external_tables, documents=documents,
                    information_registers=information_registers)
                self.managers.append(None); self.sections.append(None)
                continue
            if source.temporary or source.external:
                tables = self.external_tables if source.external else self.temporary_tables
                if source.catalog.casefold() not in tables:
                    raise ValueError('Unknown temporary query source')
                self.managers.append(None)
                self.sections.append(None)
                continue
            if source.family == 'document':
                if documents is None: raise ValueError('Document query sources require document context')
                manager = documents.get_index(source.catalog)
            elif source.family == 'information_register':
                if information_registers is None:
                    raise ValueError('Information-register query sources require register context')
                manager = information_registers.get_index(source.catalog)
            else:
                manager = catalogs.get_index(source.catalog)
            self.managers.append(manager)
            section = None
            if source.section is not None:
                if source.family == 'information_register':
                    if not manager._schema.periodic or source.section not in ('first','last') or type(source.period_boundary) is not syntax.Parameter:
                        raise ValueError('Invalid periodic register virtual source')
                    from .periodic_information_registers import moment
                    key=source.period_boundary.name.casefold()
                    if key not in self.parameters: raise ValueError('Missing period parameter')
                    moment(self.parameters[key])
                    self.sections.append(None)
                    continue
                matches = [item for item in manager._schema.tabular_sections
                           if item.name.casefold() == source.section.casefold()]
                if len(matches) != 1: raise ValueError('Unknown query tabular section')
                section = matches[0]
            self.sections.append(section)
        self.projections = tuple(self.bind(p.field) for p in query.projections)
        self.groups = tuple(self.bind(f, aggregates=False) for f in query.groups)
        if len(set(self.groups)) != len(self.groups): raise ValueError('Duplicate grouping field')
        self.joins = tuple(self.condition(join.predicate, aggregates=False, source_limit=i + 2)
                           for i, join in enumerate(query.joins))
        self.predicate = self.condition(query.predicate, aggregates=False)
        self.having = self.condition(query.having)
        aliases = {p.alias.casefold(): expression for p, expression in zip(query.projections, self.projections)}
        self.orders = []
        for order in query.order:
            if type(order.field) is syntax.Field and len(order.field.parts) == 1 and order.field.parts[0].casefold() in aliases:
                expression = aliases[order.field.parts[0].casefold()]
            else: expression = self.bind(order.field)
            self.orders.append((expression, order.descending))
        expressions = (*self.projections, *(e for e, _ in self.orders), *self.condition_expressions(self.having))
        self.grouped = bool(self.groups or any(self.has_aggregate(e) for e in expressions))
        if query.having is not None and not self.grouped: raise ValueError('HAVING requires grouping or aggregates')
        if self.grouped:
            for expression in expressions:
                self.check_grouped(expression)
        if query.distinct and any(e not in self.projections for e, _ in self.orders):
            raise ValueError('DISTINCT ordering must use projected expressions')
        columns = []
        for projection, expression in zip(query.projections, self.projections):
            if type(expression) is _BoundField:
                column = expression.column
                name = ('Код' if not projection.explicit_alias and column.field == 'code' else projection.alias)
                column = _Column(name, column.field, column.kind, column.qualifiers,
                                 column.custom, projection.explicit_alias)
            else:
                descriptor = self.describe(expression)
                if descriptor.kind == 'null' and not allow_null:
                    raise TypeError('A NULL-only projection requires a typed expression')
                column = _Column(projection.alias, None, descriptor.kind, descriptor.qualifiers,
                                 descriptor.custom, True)
            if column.kind in ('catalog_ref', 'document_ref'):
                column = replace(column, reference_identity=self.reference_identity(expression))
            columns.append(column)
        if len({c.name.casefold() for c in columns}) != len(columns): raise ValueError('Duplicate localized query output column')
        self.columns = tuple(columns)
        # COUNT(*) still binds a source field so rows and identity are validated.
        for i, fields in enumerate(self.fields):
            if not fields and not (self.sources[i].temporary or self.sources[i].external or self.sources[i].derived is not None):
                name = (self.managers[i]._schema.dimensions[0].name
                        if self.sources[i].family == 'information_register' else 'Ref')
                fields.append(self.resolve_field(i, syntax.Field((name,))))

        self.all_managers = tuple(self.managers) + tuple(
            manager for plan in self.derived_plans.values() for manager in plan.all_managers) + tuple(
            manager for member in self.memberships if member.plan is not None
            for manager in member.plan.all_managers) + tuple(node.manager for node in self.hierarchies)

    def resolve_field(self, index, expression):
        from .queries import _field
        source = self.sources[index]
        if source.derived is not None:
            if len(expression.parts) == 2 and expression.parts[0].casefold() != source.alias.casefold():
                raise ValueError('Unknown derived source qualifier')
            matches = [(i, column) for i, column in enumerate(self.derived_plans[index].columns)
                       if column.name.casefold() == expression.parts[-1].casefold()]
            if len(matches) != 1: raise ValueError('Unknown derived table column')
            i, column = matches[0]
            return replace(column, field=i, custom=None, explicit_alias=True)
        if source.family == 'information_register' and not (source.temporary or source.external):
            from .register_queries import register_field
            return register_field(self.managers[index], expression, source.alias)
        if source.family == 'document' and not (source.temporary or source.external):
            from .document_queries import document_field
            return document_field(self.managers[index], expression, source.alias, self.sections[index])
        if not (source.temporary or source.external):
            return _field(self.managers[index], expression, source.alias, self.sections[index])
        if len(expression.parts) == 2 and expression.parts[0].casefold() != source.alias.casefold():
            raise ValueError('Unknown temporary source qualifier')
        tables = self.external_tables if source.external else self.temporary_tables
        table = tables[source.catalog.casefold()]
        matches = [(i, column) for i, column in enumerate(table.columns)
                   if column.name.casefold() == expression.parts[-1].casefold()]
        if len(matches) != 1: raise ValueError('Unknown temporary table column')
        i, column = matches[0]
        return replace(column, field=i, explicit_alias=True)

    def bind(self, expression, *, aggregates=True, source_limit=None):
        from .queries import _field
        if expression is None or type(expression) is syntax.NullLiteral: return NULL
        if type(expression) is syntax.Parameter:
            if expression.name.casefold() not in self.parameters: raise ValueError('Query parameter is not set')
            return self.parameters[expression.name.casefold()]
        if type(expression) is syntax.Expression:
            if expression.operator == 'case':
                branches, otherwise = expression.arguments
                result = syntax.Expression('case', (tuple((self.condition(condition, aggregates=aggregates, source_limit=source_limit),
                    self.bind(value, aggregates=aggregates, source_limit=source_limit)) for condition, value in branches),
                    self.bind(otherwise, aggregates=aggregates, source_limit=source_limit)))
            else:
                result = syntax.Expression(expression.operator, tuple(self.bind(arg, aggregates=aggregates,
                    source_limit=source_limit) for arg in expression.arguments))
            self.describe(result)  # Validate all branches before opening a read view.
            return result
        if type(expression) is syntax.Aggregate:
            if not aggregates: raise ValueError('Aggregates are not allowed in ON/WHERE/GROUP BY')
            field = None if expression.field is None else self.bind(expression.field, aggregates=False, source_limit=source_limit)
            if field is not None:
                if expression.function in ('sum','avg') and self.describe(field).kind not in ('number', 'null'):
                    raise TypeError('SUM/AVG require a Number field')
                if expression.function in ('min','max') and self.describe(field).kind in ('boolean','catalog_ref','document_ref'):
                    raise TypeError('MIN/MAX require String, Number or Date')
            return _BoundAggregate(expression.function, field, expression.distinct)
        if type(expression) is not syntax.Field: return expression
        matches = []
        for i, source in enumerate(self.sources[:source_limit]):
            if len(expression.parts) == 2 and expression.parts[0].casefold() != source.alias.casefold(): continue
            try: column = self.resolve_field(i, expression)
            except ValueError: continue
            matches.append(_BoundField(i, column))
        if len(matches) != 1: raise ValueError('Unknown or ambiguous query field')
        result = matches[0]
        if result.column not in self.fields[result.source]: self.fields[result.source].append(result.column)
        return result

    def condition(self, node, *, aggregates=True, source_limit=None):
        if node is None: return None
        if type(node) is syntax.Predicate:
            return syntax.Predicate(node.kind, tuple(self.condition(t, aggregates=aggregates, source_limit=source_limit) for t in node.terms))
        if type(node) is syntax.Hierarchy:
            left=self.bind(node.field,aggregates=aggregates,source_limit=source_limit)
            right=self.bind(node.root,aggregates=aggregates,source_limit=source_limit)
            if self.describe(left).kind!='catalog_ref' or self.describe(right).kind!='catalog_ref':
                raise TypeError('IN HIERARCHY requires catalog references')
            a,b=self.reference_identity(left),self.reference_identity(right)
            if a[0] is not b[0] or a[1]!=b[1]: raise TypeError('IN HIERARCHY requires the same catalog')
            manager=self.catalogs._manager_by_metadata_uuid(a[1])
            if manager._schema.hierarchy!='groups_v1': raise ValueError('IN HIERARCHY requires hierarchical catalog')
            result=_BoundHierarchy(left,right,manager);self.hierarchies.append(result)
            return result
        if type(node) is syntax.Membership:
            return self.membership(node, aggregates=aggregates, source_limit=source_limit)
        left = self.bind(node.field, aggregates=aggregates, source_limit=source_limit)
        right = self.bind(node.value, aggregates=aggregates, source_limit=source_limit)
        if type(right) is syntax.Parameter:
            if right.name.casefold() not in self.parameters: raise ValueError('Query parameter is not set')
            right = self.parameters[right.name.casefold()]
        # Validate comparison types before reading, even for an empty source.
        def kind(e):
            return self.describe(e).kind
        if node.operator in ('is_null', 'is_not_null'):
            return syntax.Comparison(left, node.operator, None)
        if kind(left) != kind(right) and 'null' not in (kind(left), kind(right)): raise TypeError('Query comparison requires exact field type')
        if kind(left) in ('boolean','catalog_ref','document_ref') and node.operator not in ('eq','ne'):
            raise ValueError('Query value does not support ordering comparison')
        if kind(left) == kind(right) and kind(left) in ('catalog_ref', 'document_ref'):
            a, b = self.reference_identity(left), self.reference_identity(right)
            if a[0] is not b[0] or a[1] != b[1]:
                raise TypeError('Query references require same database and catalog')
        return syntax.Comparison(left, node.operator, right)

    def membership(self, node, *, aggregates, source_limit):
        from .query_sources import _UnionPlan
        left = self.bind(node.field, aggregates=aggregates, source_limit=source_limit)
        plan, constant = None, False
        if type(node.values) is syntax.Select or type(node.values) is syntax.Union:
            plan_type = _UnionPlan if type(node.values) is syntax.Union else _Plan
            options = {'allow_null': True} if plan_type is _Plan else {}
            plan = plan_type(node.values, self.catalogs, self.parameters, self.temporary_tables,
                             self.external_tables, documents=self.documents,
                             information_registers=self.information_registers, **options)
            if len(plan.columns) != 1: raise ValueError('IN subquery requires exactly one column')
            values = ()
            right = plan.columns[0]
            self.check_membership_type(self.describe(left), right,
                self.reference_identity(left) if self.describe(left).kind in ('catalog_ref', 'document_ref') else None,
                right.reference_identity)
            constant = True
        elif type(node.values) is syntax.Parameter:
            value = self.bind(node.values)
            if type(value) is not _ParameterList:
                raise TypeError('IN parameter requires Array or FixedArray')
            values, constant = value.values, True
        else:
            values = tuple(self.bind(e, aggregates=aggregates, source_limit=source_limit) for e in node.values)
            constant = all(type(e) is not _BoundField and type(e) is not _BoundAggregate
                           and type(e) is not syntax.Expression for e in values)
        first_typed = next((value for value in values if self.describe(value).kind != 'null'), None)
        for value in values:
            a, b = self.describe(left), self.describe(value)
            if first_typed is not None:
                first = self.describe(first_typed)
                self.check_membership_type(first, b,
                    self.reference_identity(first_typed) if first.kind in ('catalog_ref','document_ref') else None,
                    self.reference_identity(value) if b.kind in ('catalog_ref','document_ref') else None)
            self.check_membership_type(a, b,
                self.reference_identity(left) if a.kind in ('catalog_ref','document_ref') else None,
                self.reference_identity(value) if b.kind in ('catalog_ref','document_ref') else None)
        bound = _BoundMembership(left, values, plan, constant)
        self.memberships.append(bound)
        return bound

    @staticmethod
    def check_membership_type(left, right, left_identity, right_identity):
        if left.kind != right.kind and 'null' not in (left.kind, right.kind):
            raise TypeError('IN requires exact operand types')
        if left.kind == right.kind and left.kind in ('catalog_ref','document_ref'):
            if left_identity[0] is not right_identity[0] or left_identity[1] != right_identity[1]:
                raise TypeError('IN references require the same metadata snapshot and target')

    def prepare_memberships(self, view, budget):
        self._membership_sets = {}
        for member in self.memberships:
            if member.plan is not None:
                values = tuple(row[0] for row in member.plan.execute(view=view, budget=budget)._rows)
            elif member.constant:
                values = member.values
            else: continue
            from .queries import _MAX_CELLS, _MAX_RESULT_TEXT
            budget[0] += len(values)
            budget[1] += sum(len(v) for v in values if type(v) is str)
            if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                raise ValueError('Query membership resource limit exceeded')
            self._membership_sets[id(member)] = (frozenset(_key(v) for v in values if v is not NULL),
                                                any(v is NULL for v in values), bool(values))

    def condition_expressions(self, node):
        if node is None: return ()
        if type(node) is syntax.Predicate:
            return tuple(e for term in node.terms for e in self.condition_expressions(term))
        if type(node) is _BoundHierarchy: return (node.field,node.root)
        if type(node) is _BoundMembership: return (node.field, *node.values)
        return (node.field, node.value)

    def children(self, expression):
        if type(expression) is syntax.Expression:
            if expression.operator == 'case':
                branches, otherwise = expression.arguments
                return tuple(e for condition, value in branches
                             for e in (*self.condition_expressions(condition), value)) + (otherwise,)
            return expression.arguments
        return ()

    def has_aggregate(self, expression):
        return type(expression) is _BoundAggregate or any(self.has_aggregate(e) for e in self.children(expression))

    def check_grouped(self, expression):
        if expression in self.groups or type(expression) is _BoundAggregate: return
        if type(expression) is _BoundField:
            raise ValueError('Nonaggregate query field must appear in GROUP BY')
        for child in self.children(expression): self.check_grouped(child)

    def reference_identity(self, expression):
        if type(expression) is _BoundField:
            if expression.column.reference_identity is not None:
                return expression.column.reference_identity
            manager = self.managers[expression.source]
            target = (manager._schema.identity if expression.column.field in ('ref','parent')
                      else expression.column.custom.target_catalog_id)
            return manager._catalogs._metadata, target
        if type(expression) is syntax.Expression:
            if expression.operator == 'case':
                branches, otherwise = expression.arguments
                candidates = [value for _, value in branches] + [otherwise]
            else: candidates = expression.arguments
            return next(self.reference_identity(e) for e in candidates if self.describe(e).kind in ('catalog_ref', 'document_ref'))
        return expression.value_type.snapshot, expression.value_type.metadata_uuid

    def describe(self, expression):
        # Bound nodes are immutable and retained with their cached descriptor.
        # Avoid repeated recursive inference for deeply nested conditional arms.
        cached = self._descriptors.get(id(expression))
        if cached is not None: return cached[1]
        result = self._describe(expression)
        self._descriptors[id(expression)] = (expression, result)
        return result

    def _describe(self, expression):
        from .queries import _Column
        def column(kind, qualifiers=(), custom=None):
            return _Column('', None, kind, qualifiers, custom)
        if type(expression) is _BoundField: return expression.column
        if type(expression) is _BoundAggregate:
            original = None if expression.field is None else self.describe(expression.field)
            if expression.function in ('count', 'sum', 'avg'):
                scale = (0 if expression.function == 'count' else 10 if expression.function == 'avg'
                         else original.qualifiers[1] if original.kind == 'number' else 0)
                return column('number', (38, scale, 'Any'))
            return original
        if type(expression) is syntax.Expression:
            op, args = expression.operator, expression.arguments
            if op in ('case', 'coalesce'):
                if op == 'case':
                    branches, otherwise = args
                    candidates = [value for _, value in branches] + [otherwise]
                else: candidates = args
                typed = [(e, self.describe(e)) for e in candidates if self.describe(e).kind != 'null']
                if not typed: return column('null')
                kinds = {c.kind for _, c in typed}
                if len(kinds) != 1: raise TypeError('Query conditional branches require the same type')
                kind = typed[0][1].kind
                if kind == 'number':
                    scale = max(c.qualifiers[1] for _, c in typed)
                    return column(kind, (38, scale, 'Any'))
                if kind == 'string':
                    lengths = [c.qualifiers[0] for _, c in typed]
                    return column(kind, (0 if 0 in lengths else max(lengths),))
                if kind == 'datetime': return column(kind, ('DateTime',))
                if kind in ('catalog_ref', 'document_ref'):
                    identities = [self.reference_identity(e) for e, _ in typed]
                    if any(a[0] is not identities[0][0] or a[1] != identities[0][1] for a in identities):
                        raise TypeError('Query references require same database and catalog')
                return typed[0][1]
            descriptions = [self.describe(e) for e in args]
            if any(c.kind not in ('number', 'null') for c in descriptions):
                raise TypeError('Query arithmetic requires Number operands')
            scales = [c.qualifiers[1] if c.kind == 'number' else 0 for c in descriptions]
            scale = 10 if op == '/' else sum(scales) if op == '*' else max(scales)
            if scale > 38: raise ValueError('Query expression Number scale exceeded')
            return column('number', (38, scale, 'Any'))
        if expression is NULL: return column('null')
        kind = _key(expression)[0]
        if kind == 'number':
            scale = max(0, -expression.as_tuple().exponent)
            if scale > 38: raise ValueError('Query expression Number scale exceeded')
            return column(kind, (38, scale, 'Any'))
        if kind == 'string': return column(kind, (max(1, len(expression)),))
        if kind == 'datetime': return column(kind, ('DateTime',))
        return column(kind)

    def checked_number(self, result, scale):
        if not result.is_finite() or result.copy_abs() >= Decimal((0, (1,), 38 - scale)):
            raise ValueError('Query expression Number range exceeded')
        return result

    def value(self, expression, row, group=None):
        if type(expression) is _BoundField:
            source = row[expression.source]
            return NULL if source is None else source[self.fields[expression.source].index(expression.column)]
        if type(expression) is syntax.Expression:
            op, args = expression.operator, expression.arguments
            if op in ('case', 'coalesce'):
                def branch_value(branch):
                    value = self.value(branch, row, group)
                    if type(value) is Decimal:
                        self.checked_number(value, self.describe(expression).qualifiers[1])
                    return value
                if op == 'case':
                    branches, otherwise = args
                    for condition, branch in branches:
                        if self.test(condition, row, group) is True: return branch_value(branch)
                    return branch_value(otherwise)
                first = branch_value(args[0])
                return branch_value(args[1]) if first is NULL else first
            left = self.value(args[0], row, group)
            if left is NULL: return NULL
            context = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                              capitals=1, clamp=0, flags=[], traps=[InvalidOperation])
            if op in ('unary+', 'unary-'):
                result = left if op == 'unary+' else left.copy_negate()
            else:
                right = self.value(args[1], row, group)
                if right is NULL: return NULL
                if op == '/' and right.is_zero(): raise ValueError('Query division by zero')
                result = {'+': context.add, '-': context.subtract, '*': context.multiply,
                          '/': context.divide}[op](left, right)
                if op == '/': result = context.quantize(result, Decimal('0.0000000001'))
            return self.checked_number(result, self.describe(expression).qualifiers[1])
        if type(expression) is not _BoundAggregate:
            if type(expression) is Decimal:
                self.checked_number(expression, self.describe(expression).qualifiers[1])
            return expression
        if group is None: raise ValueError('Aggregate outside grouped execution')
        values = ([Decimal(1)] * len(group) if expression.field is None else
                  [self.value(expression.field, item) for item in group])
        values = [v for v in values if v is not NULL]
        if expression.distinct:
            unique = {}; [unique.setdefault(_key(v), v) for v in values]; values = list(unique.values())
        if expression.function == 'count': return Decimal(len(values))
        if not values: return NULL
        if expression.function in ('min','max'):
            return (min if expression.function == 'min' else max)(values, key=_key)
        context = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                          capitals=1, clamp=0, flags=[], traps=[InvalidOperation])
        result = Decimal(0)
        for value in values: result = context.add(result, value)
        descriptor = self.describe(expression.field)
        scale = descriptor.qualifiers[1] if descriptor.kind == 'number' else 0
        if expression.function == 'avg':
            scale = 10
            result = context.divide(result, Decimal(len(values)))
            result = context.quantize(result, Decimal('0.0000000001'))
        if not result.is_finite() or result.copy_abs() >= Decimal((0,(1,),38-scale)):
            raise ValueError('Query aggregate Number range exceeded')
        return result

    def test(self, node, row, group=None):
        if node is None: return True
        if type(node) is syntax.Predicate:
            if node.kind == 'not':
                value = self.test(node.terms[0], row, group)
                return None if value is None else not value
            unknown = False
            for term in node.terms:
                value = self.test(term, row, group)
                if node.kind == 'and' and value is False: return False
                if node.kind == 'or' and value is True: return True
                unknown |= value is None
            return None if unknown else node.kind == 'and'
        if type(node) is _BoundMembership:
            left = self.value(node.field, row, group)
            cached = self._membership_sets.get(id(node))
            if cached is not None:
                self._budget[2] += 1
                if self._budget[2] > MAX_MEMBERSHIP_WORK: raise ValueError('Query membership work limit exceeded')
                keys, null, nonempty = cached
                if not nonempty: return False
                if left is NULL: return None
                if _key(left) in keys: return True
                return None if null else False
            unknown = False
            for expression in node.values:
                self._budget[2] += 1
                if self._budget[2] > MAX_MEMBERSHIP_WORK: raise ValueError('Query membership work limit exceeded')
                result = _compare(left, self.value(expression, row, group), 'eq')
                if result is True: return True
                unknown |= result is None
            return None if unknown else False
        if type(node) is _BoundHierarchy:
            value,root=self.value(node.field,row,group),self.value(node.root,row,group)
            if value is NULL or root is NULL: return None
            current=value.reference_uuid;target=root.reference_uuid
            parents=self.hierarchy_maps[node.manager._schema.identity]
            if not current.int: return False
            if current not in parents: return False
            seen=set()
            for _ in range(33):
                if current==target or not target.int: return True
                if not current.int: return False
                if current in seen or current not in parents: raise BackendError('integrity')
                seen.add(current);current=parents[current]
            raise BackendError('integrity')
        if node.operator in ('is_null', 'is_not_null'):
            result = self.value(node.field, row, group) is NULL
            return not result if node.operator == 'is_not_null' else result
        return _compare(self.value(node.field, row, group), self.value(node.value, row, group), node.operator)

    def prepare_hierarchies(self,view,budget):
        from .queries import _MAX_CELLS,_MAX_RESULT_TEXT
        from .catalog_backend import CatalogScanRequest, CatalogValuePage, CatalogValueRow, CatalogKey
        from uuid import UUID
        self.hierarchy_maps={}
        for node in self.hierarchies:
            identity=node.manager._schema.identity
            if identity in self.hierarchy_maps: continue
            parents={};continuation=None;tokens=set()
            while True:
                page=view.scan_catalog_values(identity,CatalogScanRequest(page_size=256,continuation=continuation),('ref','parent'))
                if type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows)>256: raise BackendError('integrity')
                for row in page.rows:
                    if type(row) is not CatalogValueRow or type(row.values) is not tuple or len(row.values)!=2: raise BackendError('integrity')
                    ref,parent=row.values
                    if (type(ref) is not CatalogKey or type(parent) is not CatalogKey or ref!=row.key
                            or type(ref.record_id) is not UUID or not ref.record_id.int or type(parent.record_id) is not UUID
                            or ref.database_id!=view.database_id or parent.database_id!=view.database_id
                            or ref.catalog_id!=identity or parent.catalog_id!=identity or ref.record_id in parents): raise BackendError('integrity')
                    parents[ref.record_id]=parent.record_id
                    budget[0]+=2;budget[1]+=72
                    if len(parents)>syntax.MAX_ROWS or budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT: raise ValueError('Query hierarchy resource limit exceeded')
                if page.continuation is None: break
                if type(page.continuation) is not str or page.continuation in tokens or not page.rows: raise BackendError('integrity')
                tokens.add(page.continuation);continuation=page.continuation
            self.hierarchy_maps[identity]=parents

    def load(self, index, view, budget):
        from .queries import _logical, _section_row, _section_value, _MAX_CELLS, _MAX_RESULT_TEXT
        manager, section, columns = self.managers[index], self.sections[index], self.fields[index]
        if self.sources[index].derived is not None:
            output = self.derived_plans[index].execute(view=view, budget=budget)
            # Charge all materialized columns, not just those referenced outside.
            budget[0] += len(output._rows) * len(output._columns)
            budget[1] += sum(len(v) for row in output._rows for v in row if type(v) is str)
            if len(output._rows) > syntax.MAX_ROWS or budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                raise ValueError('Query derived source resource limit exceeded')
            return [tuple(row[column.field] for column in columns) for row in output._rows]
        if self.sources[index].temporary or self.sources[index].external:
            tables = self.external_tables if self.sources[index].external else self.temporary_tables
            table = tables[self.sources[index].catalog.casefold()]
            rows = [tuple(row[column.field] for column in columns) for row in table.rows]
            budget[0] += len(rows) * len(columns)
            budget[1] += sum(len(v) for row in rows for v in row if type(v) is str)
            if len(rows) > syntax.MAX_ROWS or budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                raise ValueError('Query input resource limit exceeded')
            return rows
        if self.sources[index].family == 'information_register':
            from .register_queries import load_register
            return load_register(manager, columns, view, budget, source=self.sources[index], parameters=self.parameters)
        if self.sources[index].family == 'document':
            from .document_queries import load_documents
            return load_documents(manager, section, columns, view, budget)
        metadata = manager._catalogs._metadata
        if ((view.database_id, view.configuration_generation) != (metadata._database_id, metadata._generation)
                or view.catalog_schema(manager._schema.identity) != manager._schema):
            raise BackendError('schema_changed')
        rows, seen, cursors = [], set(), set()
        continuation = None
        while True:
            request = CatalogScanRequest(page_size=1000, continuation=continuation, string_comparison='casefold_v1')
            if section is None:
                page = view.scan_catalog_values(manager._schema.identity, request, tuple(c.field for c in columns))
                if type(page) is not CatalogValuePage: raise BackendError('integrity')
            else:
                page = view.scan_catalog_section(manager._schema.identity, section.identity, request)
                if type(page) is not CatalogSectionPage: raise BackendError('integrity')
            if (type(page.rows) is not tuple or len(page.rows) > 1000 or
                (page.continuation is not None and (type(page.continuation) is not str or
                 len(page.continuation) != 32 or page.continuation in cursors))): raise BackendError('integrity')
            for record in page.rows:
                if section is not None:
                    row = _section_row(manager, section, record, columns, view, seen)
                else:
                    if (type(record) is not CatalogValueRow or type(record.key) is not CatalogKey or
                        any(type(v) is not UUID for v in (record.key.database_id, record.key.catalog_id, record.key.record_id)) or
                        record.key.database_id != view.database_id or record.key.catalog_id != manager._schema.identity or
                        not record.key.record_id.int or record.key.record_id in seen or
                        type(record.values) is not tuple or len(record.values) != len(columns)): raise BackendError('integrity')
                    seen.add(record.key.record_id)
                    values = []
                    for column, value in zip(columns, record.values):
                        if column.field == 'ref' and value != record.key: raise BackendError('integrity')
                        values.append(_section_value(manager, column.custom, value) if column.custom is not None else _logical(manager, column, value))
                    row = tuple(values)
                rows.append(row)
                budget[0] += len(columns)
                budget[1] += sum(len(v) for v in row if type(v) is str)
                if len(rows) > syntax.MAX_ROWS or budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                    raise ValueError('Query input resource limit exceeded')
            if page.continuation is None: return rows
            if not page.rows: raise BackendError('integrity')
            continuation = page.continuation; cursors.add(continuation)

    def join(self, rows, right, index, condition, kind):
        # Equality across the boundary uses a hash index, with residual ON
        # predicates checked normally. Other joins have an explicit pair budget.
        def equality(node):
            if type(node) is syntax.Predicate:
                if node.kind == 'and':
                    for term in node.terms:
                        found = equality(term)
                        if found: return found
                return None
            if (type(node) is syntax.Comparison and node.operator == 'eq' and type(node.field) is _BoundField and type(node.value) is _BoundField):
                a, b = node.field, node.value
                if a.source < index and b.source == index: return a, b
                if b.source < index and a.source == index: return b, a
            return None
        pair = equality(condition)
        lookup = {}
        if pair:
            for position, item in enumerate(right):
                key = _key(self.value(pair[1], (None,) * index + (item,)))
                lookup.setdefault(key, []).append((position, item))
        result, matched = [], set()
        for left in rows:
            candidates = lookup.get(_key(self.value(pair[0], left)), ()) if pair else enumerate(right)
            found = False
            for position, item in candidates:
                self._budget[3] += 1
                if self._budget[3] > MAX_JOIN_PAIRS: raise ValueError('Query join work limit exceeded')
                row = left + (item,)
                if self.test(condition, row) is True:
                    result.append(row); found = True; matched.add(position)
                    if len(result) > MAX_INTERMEDIATE_ROWS: raise ValueError('Query intermediate row limit exceeded')
            if not found and kind in ('left', 'full'): result.append(left + (None,))
            if len(result) > MAX_INTERMEDIATE_ROWS: raise ValueError('Query intermediate row limit exceeded')
        if kind in ('right', 'full'):
            for position, item in enumerate(right):
                if position not in matched:
                    result.append((None,) * index + (item,))
                    if len(result) > MAX_INTERMEDIATE_ROWS:
                        raise ValueError('Query intermediate row limit exceeded')
        return result

    def execute(self, view=None, budget=None):
        from .queries import BSLQueryResult, _MAX_CELLS, _MAX_RESULT_TEXT
        owner = False
        if view is None:
            manager = next((m for m in self.all_managers if m is not None), None)
            if manager is not None:
                if any(arm.family in ('document', 'information_register') or any(j.source.family in ('document', 'information_register') for j in arm.joins) for arm in syntax.selects((self.query,))):
                    view = self.catalogs._context.backend.begin_query_read()
                else:
                    view = _transaction_query_view(manager)
                owner = True
        try:
            if budget is None: budget = [0, 0]
            while len(budget) < 4: budget.append(0)
            self._budget = budget
            self.prepare_memberships(view, budget)
            self.prepare_hierarchies(view, budget)
            sources = [self.load(i, view, budget) for i in range(len(self.sources))]
        finally:
            if owner: view.close()
        rows = [(row,) for row in sources[0]]
        for index, join in enumerate(self.query.joins, 1):
            rows = self.join(rows, sources[index], index, self.joins[index - 1], join.kind)
        rows = [row for row in rows if self.test(self.predicate, row) is True]
        if self.grouped:
            groups = {}
            for row in rows:
                key = tuple(_key(self.value(field, row)) for field in self.groups)
                groups.setdefault(key, []).append(row)
            if not self.groups and not groups: groups[()] = []
            batches = [(items[0] if items else (), items) for items in groups.values()]
        else: batches = [(row, None) for row in rows]
        projected, unique, text_units = [], set(), 0
        for row, group in batches:
            if self.test(self.having, row, group) is not True: continue
            values = tuple(self.value(expression, row, group) for expression in self.projections)
            if self.query.distinct:
                key = tuple(_key(v) for v in values)
                if key in unique: continue
                unique.add(key)
            order = tuple(self.value(expression, row, group) for expression, _ in self.orders)
            projected.append((values, order))
            text_units += sum(len(v) for v in values if type(v) is str)
            if len(projected) * len(self.columns) > _MAX_CELLS or text_units > _MAX_RESULT_TEXT:
                raise ValueError('Query result resource limit exceeded')
        for i in range(len(self.orders) - 1, -1, -1):
            # NULL sorts before non-NULL in ascending order.
            projected.sort(key=lambda item: (item[1][i] is not NULL, _key(item[1][i])), reverse=self.orders[i][1])
        return BSLQueryResult(self.columns, tuple(values for values, _ in projected[:self.query.limit]))


def execute(query, catalogs, parameters, documents=None, information_registers=None):
    return _Plan(query, catalogs, parameters, documents=documents,
                 information_registers=information_registers).execute()
