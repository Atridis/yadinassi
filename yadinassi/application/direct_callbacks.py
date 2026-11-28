"""Passive direct callback values. No dispatch, lookup, scheduler or reflection."""
from dataclasses import dataclass

@dataclass(frozen=True, slots=True, eq=False)
class CallbackDescription:
    procedure_name: object = None
    module: object = None
    additional_parameters: object = None


def construct(*arguments):
    if len(arguments)>5:
        raise TypeError('ОписаниеОповещения ожидает от 0 до 5 аргументов')
    name,target,extra,error_name,error_target=(*arguments, *((None,)*(5-len(arguments))))
    if name is not None and type(name) is not str:
        raise TypeError('ОписаниеОповещения: имя процедуры должно быть строкой')
    if error_name is not None or error_target is not None:
        raise ValueError('Обработчик ошибки ОписаниеОповещения пока не поддерживается')
    return CallbackDescription(name,target,extra)


def read(value,name):
    key=name.casefold()
    if key in ('procedurename','имяпроцедуры'):return value.procedure_name
    if key in ('module','модуль'):return value.module
    if key in ('additionalparameters','дополнительныепараметры'):return value.additional_parameters
    if key in ('errorhandlerprocedurename','имяпроцедурыобработкиошибки','errorhandlermodule','модульобработкиошибки'):return None
    raise ValueError('Поле объекта не обнаружено: '+name)
