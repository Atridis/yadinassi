"""Closed native data methods reached through imported public module fields."""
from functools import partial
from yadinassi.collections.plain_value_list import PlainValueList, _DIRECT_PLAIN_METHODS
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


_ADD,_INSERT,_GET,_COUNT=_DIRECT_PLAIN_METHODS
_METHODS={'add':(_ADD,0,4),'insert':(_INSERT,1,5),'get':(_GET,1,1),'count':(_COUNT,0,0)}
_NAMES={'добавить':'add','вставить':'insert','получить':'get','количество':'count','вграница':'ubound'}


def _check_list_method(key,method):
    if vars(PlainValueList).get(key) is not method:
        raise BoundaryViolation('native ValueList method changed')


def bind_optional_list(value,name,omitted,argument_count=None):
    key=_NAMES.get(name,name)
    method=_ADD if key=='add' else _INSERT if key=='insert' else None
    if method is None:raise TypeError('Пропуск аргумента метода списка значений не поддерживается')
    first=key=='insert'
    defaults=((None,) if first else ())+(None,'',False,None)
    if (any(not first<=index<len(defaults) for index in omitted)
            or argument_count is not None and not first<=argument_count<=len(defaults)):
        raise TypeError('Пропуск обязательного аргумента метода списка значений')
    def invoke(*actuals):
        _check_list_method(key,method)
        values=list(actuals)
        for index in omitted:values[index]=defaults[index]
        return method(value,*values)
    _check_list_method(key,method)
    return invoke


def bind(value,name,argument_count,omitted,require_value):
    if type(value) is PlainValueList:
        if omitted:return bind_optional_list(value,name,omitted,argument_count)
        key=_NAMES.get(name,name)
        selected=_METHODS.get(key)
        if selected is None:raise ValueError('Метод объекта не обнаружен: '+name)
        method,low,high=selected
        if not low<=argument_count<=high:raise TypeError('Неверное количество аргументов: '+name)
        _check_list_method(key,method)
        def invoke(*arguments):
            _check_list_method(key,method)
            return method(value,*arguments)
        return invoke
    if type(value) is not list:return None
    # Array methods already use these exact native operations in ordinary
    # codegen. Do not look up arbitrary Python attributes on export values.
    from yadinassi.execution.codegen.experimental_direct_ast import _list_get,_native_count,_native_ubound
    key=_NAMES.get(name,name)
    methods={'add':(0,1,list.append),'count':(0,0,_native_count),
             'get':(1,1,_list_get),'ubound':(0,0,_native_ubound)}
    entry=methods.get(key)
    if entry is None:raise ValueError('Метод объекта не обнаружен: '+name)
    low,high,method=entry
    if omitted or not low<=argument_count<=high:
        raise TypeError('Неверное количество аргументов: '+name)
    if require_value and key=='add':
        raise TypeError('Процедура не возвращает значение: '+name)
    if key=='add' and not argument_count:return partial(method,value,None)
    return partial(method,value)
