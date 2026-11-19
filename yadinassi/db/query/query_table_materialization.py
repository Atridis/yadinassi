"""Build detached query tables directly in the positional table representation."""
from yadinassi.collections.plain_value_table_runtime import BSLValueTable, BSLValueTableRow, _growth


def materialize(columns, descriptions, rows):
    # Preflight the whole result before allocating any row vectors. Keep the
    # table facade's existing capacity contract, independently of query limits.
    table = BSLValueTable()
    _growth(table, rows=len(rows), columns=len(columns))
    if len(descriptions) != len(columns) or any(len(values) != len(columns) for values in rows):
        raise TypeError('Invalid query result shape')
    for column, description in zip(columns, descriptions):
        table.columns.add(column.name, description)
    storage = table._storage
    for values in rows:
        storage.rows.append(BSLValueTableRow(table, storage.schema, list(values)))
        storage.epoch += 1
    return table
