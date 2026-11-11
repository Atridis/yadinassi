"""In-process BSL callback descriptions, dispatched by the existing interpreter.

No scheduler, Python callable, dynamic source, or serialization lives here.
The module receiver remains an opaque runtime-owned capability.
"""
from dataclasses import dataclass
from .values import BSLObject


@dataclass(frozen=True, slots=True)
class _FormCallbackTarget:
    """Host-enrolled self-form capability, never a public module substitute."""
    receiver: object
    interpreter: object
    family: object
    generation: int
    enrollment: object

    def require(self, caller):
        owner = self.interpreter
        session = owner._form_session
        if (caller._family_owner is not self.family or owner._family_owner is not self.family
                or self.family._family_closed or self.family._family_generation != self.generation
                or owner._family_released or session.closed
                or session.form is not self.receiver
                or getattr(session, '_owned_form_enrollment', None) is not self.enrollment):
            raise ValueError('retired or foreign form callback')
        return owner


class BSLCallbackDescription(BSLObject):
    """Readonly description; mutable additional parameters retain their identity."""

    __slots__ = ('procedure_name', 'module', 'additional_parameters', '_form_target')

    def __init__(self, procedure_name=None, module=None, additional_parameters=None, *, _form_target=None):
        self.procedure_name = procedure_name
        self.module = module
        self.additional_parameters = additional_parameters
        self._form_target = _form_target

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
