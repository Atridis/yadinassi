"""Native storage for mutable Arrays; the emitter supplies BSL brackets.

Inherited Python list subscripting is intentionally different from BSL
brackets. The public BSL Get/Set operations normalize the index themselves.
"""
from decimal import Decimal
from yadinassi.types.direct_method_names import DirectMethodNames
from yadinassi.types.array_index import array_offset


class PlainArray(list, DirectMethodNames):
    __slots__=()
    def get(self,index):
        return list.__getitem__(self,array_offset(self,index,method=True))
    def set(self,index,value):
        list.__setitem__(self,array_offset(self,index,method=True),value)
    def __eq__(self,other):return self is other
    def __ne__(self,other):return self is not other
    add=list.append

    def _bsl_proc_add(self,value=None):
        self.append(value)

    def _bsl_proc_ubound(self):
        return len(self) - 1

    def _bsl_proc_insert(self,index,value=None):
        from yadinassi.execution.codegen.direct_resources import bounded_insert
        return bounded_insert(self,index,value)

    def _bsl_proc_delete(self,index):
        if type(index) is Decimal and (not index.is_finite() or index!=index.to_integral_value()):
            raise ValueError('Ожидается целое число')
        del self[array_offset(self,index)]

    def _bsl_proc_find(self,value):
        if type(value) in (int,Decimal):
            for index,item in enumerate(self):
                if type(item) in (int,Decimal) and item==value:
                    return index
            return None
        from yadinassi.execution.codegen.direct_scalar_semantics import typed_find
        return typed_find(self,value)

    _bsl_proc_count = _bsl_value_count = list.__len__
    _bsl_proc_clear = list.clear
    _bsl_proc_get = _bsl_value_get = get
    _bsl_proc_set = set
    _bsl_value_ubound = _bsl_proc_ubound
    _bsl_value_find = _bsl_proc_find


_DIRECT_PLAIN_ARRAY_TYPE = PlainArray
