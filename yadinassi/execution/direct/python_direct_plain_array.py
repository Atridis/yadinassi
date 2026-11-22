"""Research native list surface: no BSLArray proxy or per-read dispatcher.

Explicit get/set Decimal indices truncate; inherited list indexing uses Python semantics. These
are explicit compatibility tradeoffs, not native-1C parity claims. Foreign index
objects/subclasses do not gain __index__/__int__ callback authority.
"""
from decimal import Decimal

class PlainArray(list):
    __slots__=()
    def get(self,index):
        if type(index) is not int and type(index) is not Decimal:
            raise TypeError('Ожидается число')
        return list.__getitem__(self,int(index))
    def set(self,index,value):
        if type(index) is not int and type(index) is not Decimal:
            raise TypeError('Ожидается число')
        list.__setitem__(self,int(index),value)
    def __eq__(self,other):return self is other
    def __ne__(self,other):return self is not other
    add=list.append


_DIRECT_PLAIN_ARRAY_TYPE = PlainArray
