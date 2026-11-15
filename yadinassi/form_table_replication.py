"""Closed tabular state/delta codec for trusted replicated form hosts.

Rows are form-owned identities, never catalog references or ordinary invocation
values. Client deltas can edit existing cells and selection, not schema/order.
Table Dates use exact bounded ticks, including defaults/fractions; this private
state codec does not widen Invocation argument/result admission.
"""
from decimal import Decimal

from .form_tables import (FormTableColumn, FormTableSchema, BSLFormDataCollection,
    MAX_TABLES, MAX_TABLE_COLUMNS as MAX_COLUMNS, MAX_TABLE_ROWS as MAX_ROWS,
    MAX_TABLE_ALLOCATED as MAX_ROW_IDENTITIES, validate_table_data)
from .form_model import BSLFormTable, name, text, scalar
from .ui.protocol import encode_value, decode_value
from .form_references import is_reference, adjust, encode, decode
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
    BSLDateQualifiers, BSLAllowedSign, BSLAllowedLength, BSLDateFractions)


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected.split()):
        raise ValueError('invalid table packet')


def _integer(value, minimum=1, maximum=MAX_ROW_IDENTITIES):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('invalid table identity')
    return value


def _list(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise ValueError('invalid table inventory')
    return value


def _row(value, size):
    if type(value) is not list or len(value) != size:
        raise ValueError('invalid table record')
    return value


def _column(column):
    kind = column.value_type
    if is_reference(kind):
        return [column.name, kind.scope.wire_type(kind.target), [kind.target], column.title, column.read_only]
    return [column.name, kind.types[0].value,
        [int(kind.number_qualifiers.digits), int(kind.number_qualifiers.fraction_digits),
         kind.number_qualifiers.allowed_sign.value, int(kind.string_qualifiers.length),
         kind.string_qualifiers.allowed_length.value, kind.date_qualifiers.date_fractions.value],
        column.title, column.read_only]


def _decode_column(row, session):
    column_name, kind, qualifiers, title, readonly = _row(row, 5)
    if kind in ('FormCatalogRef','FormEnumRef'):
        if session.reference_scope is None or session.reference_scope.server or type(readonly) is not bool:
            raise ValueError('explicit client reference column required')
        target, = _row(qualifiers, 1)
        _integer(target, 1, 128)
        if session.reference_scope.wire_type(target)!=kind:raise ValueError('form reference family mismatch')
        return FormTableColumn(column_name, session.reference_scope.descriptor(target), title, readonly)
    q = _row(qualifiers, 6)
    for value, maximum in zip(q, (128, 128, 1, 65536, 1, 3)):
        _integer(value, 0, maximum)
    if type(readonly) is not bool:
        raise ValueError('invalid table column flags')
    kind = BSLTypeDescription(kind,
        BSLNumberQualifiers(Decimal(q[0]), Decimal(q[1]), BSLAllowedSign(q[2])),
        BSLStringQualifiers(Decimal(q[3]), BSLAllowedLength(q[4])),
        BSLDateQualifiers(BSLDateFractions(q[5])))
    return FormTableColumn(column_name, kind, title, readonly)


def pack_tables(form):
    validate_table_data(form)
    result = []
    for table in form._tables.values():
        snapshot = table._snapshot()
        result.append({'id': table._identity, 'name': table.schema.name,
            'title': table.schema.title, 'columns': [_column(c) for c in table.schema.columns],
            'allocated': snapshot.allocated,
            'rows': [[identity, [encode(c.value_type, value, encode_value) for c,value in zip(table.schema.columns,values)]]
                     for identity, values in snapshot.rows]})
    return result


def _schema(packet):
    return {key: packet[key] for key in ('id', 'name', 'title', 'columns')}


def unpack_tables(packet, candidate, session):
    """Decode and validate detached tables; never mutate existing row handles."""
    existing = {row['name'].casefold(): row for row in pack_tables(session.form)}
    values = {}
    for index, record in enumerate(_list(packet, MAX_TABLES), 1):
        _keys(record, 'id name title columns allocated rows')
        if _integer(record['id'], 1, MAX_TABLES) != index:
            raise ValueError('invalid table identity order')
        key = name(record['name']).casefold()
        if key in values or key in candidate._attributes or key in session.reserved_names:
            raise ValueError('duplicate or reserved table name')
        columns = tuple(_decode_column(column, session) for column in _list(record['columns'], MAX_COLUMNS))
        schema = FormTableSchema(record['name'], columns, text(record['title'], 1024))
        allocated = _integer(record['allocated'], 0)
        previous = existing.get(key)
        if previous is not None and (_schema(previous) != _schema(record) or allocated < previous['allocated']):
            raise ValueError('table schema or allocation changed')
        previous_ids = set() if previous is None else {row[0] for row in previous['rows']}
        seen = set(); rows = []
        for row in _list(record['rows'], MAX_ROWS):
            identity, encoded = _row(row, 2)
            _integer(identity)
            if identity in seen or identity > allocated:
                raise ValueError('duplicate or unallocated row')
            if previous is not None and identity not in previous_ids and identity <= previous['allocated']:
                raise ValueError('removed row identity reused')
            seen.add(identity)
            _row(encoded, len(columns))
            decoded = tuple(decode(c.value_type, value, decode_value) for c,value in zip(columns,encoded))
            for column, value, raw in zip(columns, decoded, encoded):
                if encode(column.value_type, adjust(column.value_type,value), encode_value) != raw:
                    raise ValueError('table value outside schema')
            rows.append((identity, decoded))
        table = BSLFormDataCollection(candidate, schema, record['id'])
        table._replace_rows(tuple(rows), allocated)
        values[key] = table
    if session._baseline is not None and list(existing) != list(values):
        raise ValueError('table schema inventory changed')
    candidate._tables = values
    validate_table_data(candidate)


def install_tables(form, candidate):
    """Install a previously validated whole candidate, preserving live rows."""
    values = {}
    for key, table in candidate._tables.items():
        old = form._tables.get(key)
        if old is not None and old._identity == table._identity:
            old._replace_rows(table._snapshot().rows, table._allocated)
            values[key] = old
        else:
            table._form = form
            for row in table._rows:
                row._form = form
            values[key] = table
    # Schemas are fixed after bootstrap. Defensive invalidation keeps any stale
    # host-held rows unusable even if a future trusted caller replaces a schema.
    for key, table in form._tables.items():
        if values.get(key) is not table:
            for row in table._rows:
                row._removed = True
    form._tables = values


def capture_tables(form):
    return {packet['name'].casefold(): packet for packet in pack_tables(form)}


def capture_selections(form):
    return {key: [item._replica_id, form._tables[item.data_path.casefold()]._identity, item.current_row]
            for key, item in form.items._values.items() if type(item) is BSLFormTable and item.data_path}


def table_delta(current, baseline):
    if list(current) != list(baseline):
        raise ValueError('client cannot change table schema')
    result = []
    for key, table in current.items():
        before = baseline[key]
        if (_schema(table) != _schema(before) or table['allocated'] != before['allocated']
                or [r[0] for r in table['rows']] != [r[0] for r in before['rows']]):
            raise ValueError('client cannot change table structure')
        for row, old in zip(table['rows'], before['rows']):
            for index, (value, previous) in enumerate(zip(row[1], old[1])):
                if value != previous:
                    result.append([table['id'], row[0], index, value])
    return result


def selection_delta(current, baseline):
    if set(current) != set(baseline):
        raise ValueError('client cannot change table controls')
    result = []
    for key, selection in current.items():
        if selection[:2] != baseline[key][:2]:
            raise ValueError('client cannot change table binding')
        if selection[2] != baseline[key][2]:
            result.append(selection)
    return result


def admit_table_delta(form, cells, selections, scalar_data):
    """Whole delta admission before scalars, cells, or selection are changed."""
    tables = {table._identity: table for table in form._tables.values()}
    replacements = {}; seen = set()
    for cell in _list(cells, 256):
        table_id, row_id, column_index, encoded = _row(cell, 4)
        _integer(table_id, 1, MAX_TABLES); _integer(row_id)
        table = tables.get(table_id)
        if table is None:
            raise ValueError('unknown table')
        _integer(column_index, 0, len(table.schema.columns) - 1)
        identity = (table_id, row_id, column_index)
        if identity in seen or row_id not in table._by_id:
            raise ValueError('duplicate or removed table cell')
        seen.add(identity)
        column = table.schema.columns[column_index]
        if is_reference(column.value_type):
            raise ValueError("reference cell deltas require server-owned choice")
        value = scalar(decode_value(encoded))
        if encode_value(column.value_type.adjust_value(value)) != encoded:
            raise ValueError('table delta outside schema')
        key = table.schema.name.casefold()
        if key not in replacements:
            replacements[key] = [[r, list(v)] for r, v in table._snapshot().rows]
        for row in replacements[key]:
            if row[0] == row_id:
                row[1][column_index] = value
                break
    replacements = {key: tuple((identity, tuple(values)) for identity, values in rows)
                    for key, rows in replacements.items()}
    validate_table_data(form, replacements=replacements, scalar_data=scalar_data)
    controls = {item._replica_id: item for item in form.items._values.values() if type(item) is BSLFormTable}
    admitted = []; seen = set()
    for selection in _list(selections, MAX_TABLES):
        control_id, table_id, row_id = _row(selection, 3)
        _integer(control_id, 1, 1024); _integer(table_id, 1, MAX_TABLES)
        item = controls.get(control_id)
        if item is None or control_id in seen or not item.data_path:
            raise ValueError('unknown or repeated table selection')
        seen.add(control_id)
        table = form._tables[item.data_path.casefold()]
        if table._identity != table_id:
            raise ValueError('table selection binding changed')
        if row_id is not None and (_integer(row_id) not in table._by_id):
            raise ValueError('removed table selection')
        admitted.append((item, row_id))
    return replacements, admitted


def apply_table_delta(form, admitted):
    replacements, selections = admitted
    for key, rows in replacements.items():
        table = form._tables[key]
        table._replace_rows(rows, table._allocated)
    for item, row_id in selections:
        item.current_row = row_id
