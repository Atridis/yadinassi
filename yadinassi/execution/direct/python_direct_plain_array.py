"""Native storage for mutable Arrays; the emitter supplies BSL brackets.

Inherited Python list subscripting is intentionally different from BSL
brackets. The public BSL Get/Set operations normalize the index themselves.
"""
from yadinassi.types.array_index import array_offset


class PlainArray(list):
    __slots__=()
    def get(self,index):
        return list.__getitem__(self,array_offset(self,index,method=True))
    def set(self,index,value):
        list.__setitem__(self,array_offset(self,index,method=True),value)
    def __eq__(self,other):return self is other
    def __ne__(self,other):return self is not other
    add=list.append


_DIRECT_PLAIN_ARRAY_TYPE = PlainArray
