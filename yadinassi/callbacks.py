"""In-process BSL callback descriptions, dispatched by the existing interpreter.

No scheduler, Python callable, dynamic source, or serialization lives here.
The module receiver remains an opaque runtime-owned capability.
"""
from .values import BSLObject


class BSLCallbackDescription(BSLObject):
    """Readonly description; mutable additional parameters retain their identity."""

    __slots__ = ('procedure_name', 'module', 'additional_parameters')

    def __init__(self, procedure_name=None, module=None, additional_parameters=None):
        self.procedure_name = procedure_name
        self.module = module
        self.additional_parameters = additional_parameters

    def get_member(self, name):
        key = name.casefold()
        if key in ('имяпроцедуры', 'procedurename'):
            return self.procedure_name
        if key in ('модуль', 'module'):
            return self.module
        if key in ('дополнительныепараметры', 'additionalparameters'):
            return self.additional_parameters
        if key in ('имяпроцедурыобработкиошибки', 'errorhandlerprocedurename',
                   'модульобработкиошибки', 'errorhandlermodule'):
            return None
        return super().get_member(name)

    def get_method(self, name):
        raise ValueError(f'Метод объекта не обнаружен: {name}')

    def __str__(self):
        return 'ОписаниеОповещения'


def callback_description_marker(*arguments):
    raise TypeError('ОписаниеОповещения требует контекст интерпретатора')


def run_callback_marker(*arguments):
    raise TypeError('ВыполнитьОбработкуОповещения требует контекст интерпретатора')
