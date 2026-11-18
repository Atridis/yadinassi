"""Minimal native table, reconstructed independently, not a 1C parity layer.

Storage is positional mutable rows and one shared name-to-index dictionary.
Column views are transient. Native errors, ordering and integer indices apply.
Removed rows remain ordinary lists; stale column/row references have no guards.
Names supplied to get_member/set_member are canonical (casefolded by compiler).
"""


class BareRow(list):
    __slots__ = ('table',)
    get = list.__getitem__
    set = list.__setitem__
    get_index = list.__getitem__
    set_index = list.__setitem__

    def get_member(self, name):
        return self[self.table.schema[name]]

    def set_member(self, name, value):
        self[self.table.schema[name]] = value


class BareColumn:
    __slots__ = ('table', 'name')

    def __init__(self, table, name):
        self.table = table
        self.name = name

    def get_member(self, name):
        if name == 'name':
            return self.name
        raise AttributeError(name)

    def set_member(self, name, value):
        if name != 'name':
            raise AttributeError(name)
        value = value.casefold()
        if value != self.name and value in self.table.schema:
            raise ValueError('duplicate column')
        index = self.table.schema.pop(self.name)
        self.table.schema[value] = index
        self.name = value


class BareColumns:
    __slots__ = ('table',)

    def __init__(self, table):
        self.table = table

    def add(self, name):
        self.table.add_column(name)
        return BareColumn(self.table, name.casefold())

    def get(self, index):
        # Schema insertion order can change on rename; position is authoritative.
        name = next(name for name, offset in self.table.schema.items() if offset == index)
        return BareColumn(self.table, name)

    def find(self, name):
        name = name.casefold()
        return BareColumn(self.table, name) if name in self.table.schema else None

    def count(self):
        return len(self.table.schema)

    def __len__(self):
        return len(self.table.schema)

    def __iter__(self):
        for name, _ in sorted(self.table.schema.items(), key=lambda item: item[1]):
            yield BareColumn(self.table, name)


class BareTable:
    __slots__ = ('rows', 'schema')

    def __init__(self):
        self.rows = []
        self.schema = {}

    @property
    def columns(self):
        return BareColumns(self)

    def get_member(self, name):
        if name == 'columns':
            return BareColumns(self)
        raise AttributeError(name)

    def add_column(self, name):
        name = name.casefold()
        if name in self.schema:
            raise ValueError('duplicate column')
        self.schema[name] = len(self.schema)
        for row in self.rows:
            row.append(None)

    def add(self):
        row = BareRow([None] * len(self.schema))
        row.table = self
        self.rows.append(row)
        return row

    def insert(self, index):
        row = BareRow([None] * len(self.schema))
        row.table = self
        self.rows.insert(index, row)
        return row

    def get(self, index):
        return self.rows[index]

    def set(self, row, column, value):
        self.rows[row][column] = value

    def delete(self, index):
        del self.rows[index]

    def clear(self):
        self.rows.clear()

    def count(self):
        return len(self.rows)

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, index):
        return self.rows[index]

    def find(self, value, column):
        index = self.schema[column.casefold()]
        for row in self.rows:
            if row[index] == value:
                return row
        return None

    def sort(self, column, reverse=False):
        index = self.schema[column.casefold()]
        self.rows.sort(key=lambda row: row[index], reverse=reverse)

    def copy_columns(self):
        result = BareTable()
        result.schema = self.schema.copy()
        return result

    def copy(self):
        result = self.copy_columns()
        for source in self.rows:
            row = BareRow(source)
            row.table = result
            result.rows.append(row)
        return result

    def total(self, column):
        index = self.schema[column.casefold()]
        return sum(row[index] for row in self.rows)


BareValueTable = BareTable
