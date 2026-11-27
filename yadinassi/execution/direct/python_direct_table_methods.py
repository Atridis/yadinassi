"""Direct methods on an owned ValueTable row store."""
from decimal import Decimal

from yadinassi.collections.plain_table_storage import _DIRECT_CLASSES
from yadinassi.types.direct_method_names import DirectMethodNames
from .python_direct_table_iteration import state
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


_KERNEL, _, _members = _DIRECT_CLASSES[-1]
_slots = dict(_members)
_OWNER = _slots['owner']
_ROWS = _slots['rows']


class TableMethods(DirectMethodNames):
    __slots__ = ('table','rows')

    def __init__(self, table):
        fields = state(table)
        kernel = fields.get('_storage')
        rows = fields.get('rows')
        if (type(kernel) is not _KERNEL or type(rows) is not list
                or _OWNER.__get__(kernel, _KERNEL) is not table
                or _ROWS.__get__(kernel, _KERNEL) is not rows):
            raise BoundaryViolation('noncanonical value table row storage')
        self.table = table
        self.rows = rows

    def _bsl_value_count(self):
        return Decimal(list.__len__(self.rows))

    _bsl_proc_count = _bsl_value_count

    def _bsl_value_add(self):
        from .python_direct_plain_tables import validate
        from yadinassi.collections.plain_value_table_runtime import BSLValueTable

        _, _, _, columns, _ = validate(self.table, iteration=True)
        if type(state(columns).get('_query_columns')) is not int:
            raise BoundaryViolation('noncanonical query column count')
        return BSLValueTable.add(self.table)

    _bsl_proc_add = _bsl_value_add


class ColumnMethods(DirectMethodNames):
    __slots__ = ('columns',)

    def __init__(self, columns):
        self.columns = columns

    def _bsl_value_add(self, *args):
        from .python_direct_plain_tables import validate
        from yadinassi.collections.plain_value_table_runtime import BSLValueTableColumnCollection

        _, _, _, columns, _ = validate(self.columns, iteration=True)
        if columns is not self.columns:
            raise BoundaryViolation('noncanonical value table column storage')
        return BSLValueTableColumnCollection.add(columns, *args)

    _bsl_proc_add = _bsl_value_add
