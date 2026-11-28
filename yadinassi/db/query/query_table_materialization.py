"""Build detached query tables directly in the positional table representation."""
from yadinassi.collections.plain_value_table_runtime import BSLValueTable, BSLValueTableRow, BSLValueTableColumn
from yadinassi.types.type_descriptions import BSLTypeDescription


def materialize(columns, descriptions, rows):
    if len(descriptions) != len(columns) or any(len(values) != len(columns) for values in rows):
        raise TypeError('Invalid query result shape')
    table = BSLValueTable()
    for column, description in zip(columns, descriptions):
        # Actual query descriptors are nullable or source-owned reference
        # metadata. Copy the supplied cells below without asking for a default.
        if type(column.name) is not str or type(description) is not BSLTypeDescription:
            raise TypeError("Invalid query column metadata")
        table.columns._append_materialized(BSLValueTableColumn(table, column.name, description))
    storage = table._storage
    for values in rows:
        storage.rows.append(BSLValueTableRow(table, storage.schema, list(values)))
        storage.epoch += 1
    return table
