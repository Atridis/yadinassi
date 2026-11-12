"""Bounded raw, Balance and Turnovers sources on the document owner's view.

The measured subset has active movements, second-resolution dates, scalar
dimensions and numeric resources. Totals use exact scaled integer arithmetic
and the existing native-backed caseless UCA key. Ordinary relational WHERE,
ORDER BY and GROUP BY retain the query engine's separate host comparison policy.
No totals table, SQL aggregate, independent connection or transaction is added.
"""
from decimal import Decimal

from . import query_parser as syntax
from .accumulation_movements import AccumulationDirection, _sum_resource_vectors
from .catalog_backend import BackendError
from .dates import _from_parts
from .accumulation_periods import bind_dates, StatementReducer


def needs_accumulation(statements):
    return any(arm.family == 'accumulation_register' or any(
        join.source.family == 'accumulation_register' for join in arm.joins)
        for arm in syntax.selects(statements))


def _boundaries(source, parameters):
    if source.section is None:
        if source.period_boundary is not None:
            raise ValueError('Raw accumulation source has no period arguments')
        return ()
    count = {'balance': 1, 'turnovers': 2, 'balance_and_turnovers': 2}.get(source.section)
    if count is None:
        raise ValueError('Invalid accumulation virtual source')
    periodicity = _periodicity(source)
    arguments = source.period_boundary[:-1] if periodicity else source.period_boundary
    boundaries = bind_dates(arguments, parameters, count)
    if source.section == 'balance_and_turnovers' or periodicity:
        # Deliberate host admission, not an inferred native calendar cutoff.
        # The accepted boundary probe refuses year 9999. Wider endpoint parity
        # is deferred; legacy Balance/Turnovers and stored dates are unchanged.
        if any(not 1900 <= value.year <= 2099 for value in boundaries):
            raise ValueError('Stock period statements support query dates from 1900 through 2099')
    return boundaries


def _periodicity(source):
    args = source.period_boundary
    if type(args) is tuple and len(args) == 3:
        mode = args[2]
        if (source.section not in ('turnovers', 'balance_and_turnovers')
                or type(mode) is not syntax.Periodicity
                or type(mode.kind) is not str or mode.kind not in ('day', 'month')):
            raise ValueError('Unsupported accumulation periodicity')
        return mode.kind
    return None


class AccumulationQueryManager:
    def __init__(self, documents, schema):
        self.documents = documents
        self._schema = schema
        self._catalogs = documents._catalogs
        self._documents_by_id = {document.identity: documents.get_index(document.name)
            for document in documents._context.backend.accumulation_configuration.documents}

    def _logical(self, field, value):
        return self._documents_by_id[self._schema.recorder_documents[0]]._logical(field, value)


def manager(documents, source, parameters, *, condition_budget=None):
    from .configuration_accumulation import AccumulationConfiguration
    from .configuration_accumulation_references import InventoryConfiguration
    from .configuration_inventory_application import InventoryApplicationConfiguration
    from .configuration_inventory_enums import InventoryEnumConfiguration
    from .sqlite_catalog import SQLiteCatalogBackend
    if documents is None or documents._context is None:
        raise ValueError('Accumulation query requires document context')
    backend = documents._context.backend
    if type(backend) is not SQLiteCatalogBackend:
        raise ValueError('Accumulation query requires the accumulation profile')
    config = backend.accumulation_configuration
    if type(config) not in (AccumulationConfiguration, InventoryConfiguration, InventoryApplicationConfiguration, InventoryEnumConfiguration):
        raise ValueError('Accumulation query requires the accumulation profile')
    matches = [schema for schema in config.registers
               if schema.name.casefold() == source.catalog.casefold()]
    if len(matches) != 1:
        raise ValueError('Unknown accumulation-register source')
    _boundaries(source, parameters)  # Validate before opening a read lease.
    from .accumulation_query_conditions import bind_condition
    result = AccumulationQueryManager(documents, matches[0])
    result.condition = bind_condition(result, source, parameters,
        typed=type(config) is InventoryEnumConfiguration, budget=condition_budget)
    return result


def field(manager, expression, source):
    from .queries import _Column
    if len(expression.parts) == 2 and expression.parts[0].casefold() != source.alias.casefold():
        raise ValueError('Unknown query source qualifier')
    name = expression.parts[-1].casefold()
    schema = manager._schema
    if source.section is None:
        standard = {'period': 'period', 'период': 'period', 'active': 'active',
            'активность': 'active', 'recorder': 'recorder', 'регистратор': 'recorder',
            'linenumber': 'line_number', 'номерстроки': 'line_number'}.get(name)
        if standard == 'period':
            return _Column('', standard, 'datetime', ('DateTime',))
        if standard == 'active':
            return _Column('', standard, 'boolean', ())
        if standard == 'line_number':
            return _Column('', standard, 'number', (10, 0, 'Nonnegative'))
        if standard == 'recorder':
            if len(schema.recorder_documents) != 1:
                raise ValueError('Recorder projection requires one declared document type')
            return _Column('', standard, 'document_ref', (),
                reference_identity=(manager.documents._metadata, schema.recorder_documents[0]))
        fields = schema.fields
    else:
        if name in ('period', 'период') and _periodicity(source):
            return _Column('', 'period', 'datetime', ('DateTime',))
        fields = schema.dimensions
    matches = [_Column('', f.identity, f.kind, f.qualifiers, f,
               reference_identity=(manager._catalogs._metadata, f.target_catalog_id)
                   if f.kind == 'catalog_ref' else None)
               for f in fields if f.name.casefold() == name]
    if source.section is not None:
        suffixes = (('balance', 'остаток'),) if source.section == 'balance' else (
            ('turnover', 'оборот'), ('receipt', 'приход'), ('expense', 'расход'))
        if source.section == 'balance_and_turnovers':
            suffixes += (('openingbalance', 'начальныйостаток'),
                         ('closingbalance', 'конечныйостаток'))
        for resource in schema.resources:
            for english, russian in suffixes:
                if name in (resource.name.casefold() + english, resource.name.casefold() + russian):
                    matches.append(_Column('', (resource.identity, english), 'number',
                                           (38, resource.qualifiers[1], 'Any')))
    if len(matches) != 1:
        # RecordType projection/enum parameters and virtual attributes are not
        # silently converted into numbers or strings by the shared query algebra.
        raise ValueError('Unknown or unsupported accumulation query field')
    return matches[0]


def fallback_field(manager, source):
    name = ('Period' if source.section is None else manager._schema.resources[0].name +
            ('Balance' if source.section == 'balance' else 'Turnover'))
    return field(manager, syntax.Field((name,)), source)


def _dimension_key(value):
    if type(value) is str:
        from .collation import caseless_string_key
        return ('string', caseless_string_key(value))
    from .relational_queries import _key
    return _key(value)


def load(manager, columns, view, budget, source, parameters):
    from .sqlite_documents import DocumentView
    from .sqlite_transactions import _accumulation_port
    from .queries import _section_value, _MAX_CELLS, _MAX_RESULT_TEXT
    from .query_sources import _check_number
    if type(view) is not DocumentView:
        raise BackendError('unsupported')
    owner = view._view
    owner._require()
    config = owner._backend.accumulation_configuration
    schema = manager._schema
    if (config is None or schema not in config.registers or
            manager.documents._context.backend is not owner._backend):
        raise BackendError('schema_changed')
    from .accumulation_query_conditions import TypedDimensionCondition
    if type(manager.condition) is TypedDimensionCondition:
        manager.condition.require_live()
    boundaries = _boundaries(source, parameters)
    rows, groups = [], {}
    periodicity = _periodicity(source)
    # The explicit source-condition surface has measured dependency-sensitive
    # grouping. Columns include every bound SELECT/WHERE/ON/GROUP/HAVING/ORDER
    # dependency, not just the final projection. Condition-only dimensions do
    # not request output groups. Keep older unconditioned sources unchanged.
    dimensions = (tuple(f for f in schema.dimensions
                        if any(column.field == f.identity for column in columns))
                  if source.virtual_condition is not None else schema.dimensions)
    scalar_balance = (source.virtual_condition is not None and not dimensions
                      and not periodicity
                      and source.section in ('balance', 'balance_and_turnovers'))
    reducer = (StatementReducer(schema, boundaries[0], boundaries[1], periodicity,
                                combined=source.section == 'balance_and_turnovers',
                                enum_domain=owner._backend._enum_domain)
               if source.section == 'balance_and_turnovers' or periodicity else None)
    count = 0
    for key, partition in _accumulation_port(owner).scan(schema.identity):
        for row in partition.rows:
            count += 1
            if count > syntax.MAX_ROWS:
                raise ValueError('Query input row limit exceeded')
            if row.active is not True:
                raise BackendError('unsupported')
            values = {f.identity: _section_value(manager, f, value)
                for f, value in zip(schema.fields, row.dimensions + row.resources + row.attributes)}
            # Charge every source cell, even a row excluded by the period bound
            # or a field absent from projection. Reduction cannot bypass budgets.
            budget[0] += len(values) + 5
            budget[1] += sum(len(value) for value in values.values() if type(value) is str)
            if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                raise ValueError('Query input resource limit exceeded')
            if source.section is None:
                period = row.period
                values.update(period=_from_parts((period.year, period.month, period.day,
                    period.hour, period.minute, period.second)), active=row.active,
                    line_number=Decimal(row.line_number))
                if any(column.field == 'recorder' for column in columns):
                    values['recorder'] = manager._documents_by_id[key.document_id]._ref(key.record_id)
                rows.append(tuple(values[column.field] for column in columns))
                continue
            # Explicit source conditions are applied only after every source
            # row's complete validation/charge, before any grouping/reduction.
            if not manager.condition.matches(values):
                continue
            if reducer is not None:
                dims = tuple(values[f.identity] for f in dimensions)
                reducer.add(dims, tuple(_dimension_key(value) for value in dims), row)
                continue
            if source.section == 'balance':
                if row.period >= boundaries[0]:
                    continue
            elif not boundaries[0] <= row.period <= boundaries[1]:
                continue
            dims = tuple(values[f.identity] for f in dimensions)
            group_key = tuple(_dimension_key(value) for value in dims)
            group = groups.setdefault(group_key, (dims, [], []))
            group[1].append(row.resources)
            group[2].append(1 if row.direction is AccumulationDirection.RECEIPT else -1)
    if reducer is not None:
        for dims, period, totals in reducer.rows(syntax.MAX_ROWS):
            values = dict(zip((f.identity for f in dimensions), dims))
            if period is not None:
                values['period'] = _from_parts((period.year, period.month, period.day,
                    period.hour, period.minute, period.second))
            for name, vector in totals.items():
                for resource, value in zip(schema.resources, vector):
                    _check_number(value, (38, resource.qualifiers[1], 'Any'))
                    values[(resource.identity, name)] = value
            # Sparse boundary rows can outnumber movements. Charge before
            # materialization, irrespective of projection, WHERE or TOP.
            budget[0] += len(values)
            budget[1] += sum(len(value) for value in values.values() if type(value) is str)
            if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
                raise ValueError('Query period result resource limit exceeded')
            rows.append(tuple(values[column.field] for column in columns))
        if not rows and scalar_balance:
            rows.append(_zero_balance_row(schema, columns, source, budget,
                enum_domain=owner._backend._enum_domain))
        return rows
    for dims, vectors, weights in groups.values():
        vectors, weights = tuple(vectors), tuple(weights)
        net = _sum_resource_vectors(schema, vectors, weights, enum_domain=owner._backend._enum_domain)
        if source.section == 'balance' and all(value == 0 for value in net):
            continue
        values = dict(zip((f.identity for f in dimensions), dims))
        suffix = 'balance' if source.section == 'balance' else 'turnover'
        totals = {suffix: net}
        if source.section == 'turnovers':
            for name, weight in (('receipt', 1), ('expense', -1)):
                chosen = tuple(vector for vector, sign in zip(vectors, weights) if sign == weight)
                totals[name] = _sum_resource_vectors(schema, chosen, (1,) * len(chosen), enum_domain=owner._backend._enum_domain)
            if all(value == 0 for vector in totals.values() for value in vector):
                raise ValueError('All-zero turnover group is outside the measured profile')
        for name, vector in totals.items():
            for resource, value in zip(schema.resources, vector):
                _check_number(value, (38, resource.qualifiers[1], 'Any'))
                values[(resource.identity, name)] = value
        rows.append(tuple(values[column.field] for column in columns))
    if not rows and scalar_balance:
        rows.append(_zero_balance_row(schema, columns, source, budget,
            enum_domain=owner._backend._enum_domain))
    return rows


def _zero_balance_row(schema, columns, source, budget, *, enum_domain=None):
    """Native filter12 case9: dimensionless Balance/B&T has a zero aggregate.

    Called only after the full physical/logical scan and charge succeeded. It
    does not invent a reference, period bucket, or a Turnovers occurrence.
    """
    from .queries import _MAX_CELLS
    from .query_sources import _check_number
    vector = _sum_resource_vectors(schema, (), (), enum_domain=enum_domain)
    suffixes = (('balance',) if source.section == 'balance' else
                ('openingbalance', 'receipt', 'expense', 'turnover', 'closingbalance'))
    values = {}
    for resource, value in zip(schema.resources, vector):
        _check_number(value, (38, resource.qualifiers[1], 'Any'))
        for suffix in suffixes:
            values[(resource.identity, suffix)] = value
    budget[0] += len(values)
    if budget[0] > _MAX_CELLS:
        raise ValueError('Query result resource limit exceeded')
    return tuple(values[column.field] for column in columns)
