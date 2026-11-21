"""Synchronous direct dispatch for passive callbacks of the current or an explicitly imported module."""

from yadinassi.application.callbacks import run_callback_marker
from yadinassi.application.direct_callbacks import CallbackDescription
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import Reference


def _arity():
    raise TypeError('ВыполнитьОбработкуОповещения ожидает от 1 до 2 аргументов')


def bind(context, key, service, *, argument_count):
    from yadinassi.runtime import Interpreter, _Module
    from .python_direct_services import builtin_binding

    vm = getattr(context, 'vm', None)
    if type(vm) is not Interpreter or vm._configuration_runtime is not None or vm.database_context is not None:
        raise ValueError('ВыполнитьОбработкуОповещения требует текущий модуль')
    def admit_context():
        if not vm._has_module_context:
            raise ValueError('ВыполнитьОбработкуОповещения недоступно в подпрограмме без контекста')
        if vm.execution_context != 'client' or getattr(context, '_server_side', False):
            raise ValueError('ВыполнитьОбработкуОповещения поддерживается только на клиенте')

    admit_context()
    if argument_count is not None and not 1 <= argument_count <= 2:
        _arity()

    snapshot = getattr(vm, '_builtin_functions', None)
    entry = None if snapshot is None else snapshot.get(key)

    def canonical():
        if (context.vm is not vm or context._services is not vm.functions or vm.functions.get(key) is not service
                or (snapshot is not None and not builtin_binding(service, entry))
                or service.function is not run_callback_marker or service.returns_value is not True
                or type(service.reference_parameters) is not frozenset or service.reference_parameters):
            raise BoundaryViolation('canonical RunCallback service changed')

    canonical()

    def invoke(description, result=None):
        context._before('call', key)
        context._check_effect()
        admit_context()
        canonical()
        if type(description) is not CallbackDescription:
            raise TypeError('ВыполнитьОбработкуОповещения: ожидается ОписаниеОповещения')
        name, target, extra = (description.procedure_name, description.module,
                               description.additional_parameters)
        if type(name) is not str or not name or target is None:
            raise ValueError('ОписаниеОповещения: не заданы имя процедуры и модуль')
        # Callbacks transfer values, never caller storage locations. Mutable
        # data keeps its identity, but a host Reference is not a BSL value.
        if type(result) is Reference or type(extra) is Reference:
            raise TypeError('ВыполнитьОбработкуОповещения: ожидается значение, не ссылка на переменную')
        # This is the same ready/owned/exported routine gateway as ThisObject.F.
        # A procedure is allowed: RunCallback itself returns Undefined.
        if type(target) is _Module and target is vm._self_module:
            call = context.resolve_public_module_call(target, name, require_value=False, argument_count=2)
        else:
            call = context.resolve_callback_target(target, name, require_value=False, argument_count=2)
        return call(result, extra)

    def omissions(bound, positions, count):
        if count != 2 or positions != (1,):
            from yadinassi.execution.codegen.experimental_naked_collections import _host_omission_error
            _host_omission_error()
        return bound, {1: None}

    invoke.requires_reference = lambda index: False
    invoke.prepare_omissions = omissions
    return invoke
