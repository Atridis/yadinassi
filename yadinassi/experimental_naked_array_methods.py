"""Canonical bound method values, allocated only on Array member extraction.

Direct calls do not use this factory. The emitter supplies its selected index,
insert/find/delete semantics; no hidden VM adapter or capability registry exists.
"""
from decimal import Decimal
from .values import HostFunction

_ALIASES={'количество':'count','вграница':'ubound','добавить':'add','очистить':'clear',
          'получить':'get','установить':'set','вставить':'insert','удалить':'delete','найти':'find'}


def array_method_value(receiver,name,*,index=None,insert=None,find=None,delete=None):
    if type(receiver) is not list:raise TypeError('Ожидается массив')
    method=_ALIASES.get(name.casefold(),name.casefold())
    index_function=index
    if method=='count':
        def call():return Decimal(len(receiver))
        qualname='_ArrayBase.get_member.<locals>.<lambda>'
    elif method=='ubound':
        def call():return Decimal(len(receiver)-1)
        qualname='_ArrayBase.get_member.<locals>.<lambda>'
    elif method=='add':
        def call(self,value=None):receiver.append(value)
        qualname='BSLArray.add'
    elif method=='clear':
        # Builtin bound clear preserves ordinary arity diagnostics.
        return HostFunction(name,receiver.clear)
    elif method=='get' and index is not None:
        def call(self,index):return receiver[index_function(receiver,index)]
        qualname='_ArrayBase.get'
    elif method=='set' and index is not None:
        def call(self,index,value):receiver[index_function(receiver,index)]=value
        qualname='BSLArray.set'
    elif method=='insert' and insert is not None:
        def call(self,index,value=None):return insert(receiver,index,value)
        qualname='BSLArray.insert'
    elif method=='delete' and delete is not None:
        def call(self,index):return delete(receiver,index)
        qualname='BSLArray.delete'
    elif method=='find' and find is not None:
        def call(self,value):return find(receiver,value)
        qualname='_ArrayBase.find'
    elif method in ('get','set','insert','delete','find'):
        raise ValueError('Array method extraction requires selected semantics: '+method)
    else:raise ValueError('Метод или свойство не найдено: '+name)
    call.__qualname__=qualname
    if method not in ('count','ubound'):call=call.__get__(receiver,list)
    return HostFunction(name,call)
