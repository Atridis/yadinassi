"""Structural order for the in-memory row buffers, not persisted row identity."""


def pop_row(rows, index):
    row = rows.pop(index)
    for position in range(index, len(rows)):
        rows[position]._position = position
    return row
