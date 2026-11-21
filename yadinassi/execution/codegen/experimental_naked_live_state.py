"""Trusted standalone namespace, NOT a configuration/VM scope adapter.

The caller retains the exact casefold-keyed dict. Normal emitted reads/writes
are native dict operations; these helpers only handle missing names, reserved
assignment failures, and reference binding. No VM dispatcher or scope lease.
"""
from yadinassi.types.values import Reference
from .experimental_naked_collections import _Reference

UNSET=object()


def validate_state(state):
    if type(state) is not dict:
        raise TypeError('live_module_state requires an exact caller dict')
    if any(type(key) is not str or key != key.casefold() for key in state):
        raise ValueError('live module state keys must be casefolded strings')
    return state


def missing(name):
    raise ValueError('Переменная или функция не определена: '+name)


def readonly(name):
    raise ValueError('Нельзя присвоить значение свойству только для чтения: '+name)


class _SlotReference(_Reference):
    def __init__(self,state,key):self.state,self.key=state,key
    @property
    def value(self):return self.state[self.key]
    @value.setter
    def value(self,value):self.state[self.key]=value


class _ForwardReference(_Reference):
    def __init__(self,reference):self.reference=reference
    @property
    def value(self):return self.reference.get()
    @value.setter
    def value(self,value):self.reference.set(value)


def source_reference(state,name,cached=None):
    # Cache only the address, never the value or the binding decision.
    if type(state) is not dict:
        from yadinassi.execution.direct.python_direct_execute import FragmentScope
        if type(state) is FragmentScope:return _ForwardReference(state.reference(name.casefold()))
    key=name.casefold() if cached is None else cached.key
    value=state.get(key,UNSET)
    if value is UNSET:missing(name)
    return _ForwardReference(value) if type(value) is Reference else (cached if cached is not None else _SlotReference(state,key))


def host_reference(state,name):
    if type(state) is not dict:
        from yadinassi.execution.direct.python_direct_execute import FragmentScope
        if type(state) is FragmentScope:return state.reference(name.casefold())
    key=name.casefold()
    value=state.get(key,UNSET)
    if value is UNSET:missing(name)
    if type(value) is Reference:return value
    ref=_SlotReference(state,key)
    result=Reference(ref.get,ref.set)
    result._direct_name_sink=True
    return result
