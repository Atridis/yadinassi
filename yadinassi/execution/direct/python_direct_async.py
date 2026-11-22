"""Standalone direct async entry; the scheduler owns all suspension and delivery."""
from threading import get_ident

from yadinassi.application.async_runtime import Promise, Scheduler
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_errors import convert_error
from yadinassi.syntax import ast


def entry_mode(vm, program):
    from .python_direct import _reject
    if type(program) not in (list, tuple):
        return False
    incoming = any(type(node) is ast.Routine and node.is_async is True for node in program)
    if not incoming and not any(module.async_names for module in
                                getattr(vm, '_direct_routine_modules', {}).values()):
        return False
    from yadinassi.runtime import Interpreter
    supported = (type(vm) is Interpreter and vm._family_owner is vm
                 and vm.database_context is None and not vm.imports
                 and not getattr(vm, '_direct_invocation_ports', None)
                 and not any(type(node) is ast.Import for node in program)
                 and type(vm._scheduler) is Scheduler)
    if not supported:
        if incoming:
            _reject('asynchronous routines require a standalone client module without imports')
        return False
    return True


def promise_opaque(value):
    if type(value) is Promise:
        raise ValueError('Обещание не имеет доступных полей или методов')


def inline_root(vm, plan, boundary):
    def run():
        if False:
            yield
        return plan.run(vm.variables, context=boundary)
    return vm._scheduler.run_inline(run())


def _activation_guard(vm, scheduler, generation, state, task, thread):
    if (get_ident() != thread or vm._family_owner is not vm or vm._scheduler is not scheduler
            or vm._family_generation != generation
            or vm.variables is not state or vm._family_closed
            or vm.imports or getattr(vm, '_direct_invocation_ports', None)
            or scheduler._active_task is not task):
        raise BoundaryViolation('direct async activation changed')


def root_guard(vm):
    scheduler, generation, state = vm._scheduler, vm._family_generation, vm.variables
    thread = get_ident()
    return lambda: _activation_guard(vm, scheduler, generation, state, None, thread)


def bind_context(context, vm):
    from .python_direct import make_boundary
    scheduler = vm._scheduler
    context._async_scheduler = scheduler

    def start(factory, constants, body_key, actuals, procedure):
        # The caller resolves and evaluates actuals before entering the task.
        # Bind code to a fresh activation, not to a root lease that is about
        # to end, and do not replay any initializers or source statements.
        context._check()
        generation, state, thread = vm._family_generation, vm.variables, get_ident()

        def run():
            task = scheduler._active_task
            def guard():
                _activation_guard(vm, scheduler, generation, state, task, thread)
            boundary = make_boundary(vm, _async_guard=guard)
            boundary._async_task = True
            boundary.enter()
            try:
                body = factory(state, constants, [], boundary, True)[body_key](*actuals)
                try:
                    value, error = None, None
                    while True:
                        boundary._check()
                        try:
                            request = body.send(value) if error is None else body.throw(error)
                        except StopIteration as stop:
                            boundary._check()
                            return stop.value
                        finally:
                            error = None
                        boundary._check()
                        try:
                            value = yield request
                        except GeneratorExit:
                            raise
                        except BaseException as delivered:
                            error = delivered
                            value = None
                finally:
                    body.close()
            except Exception as error:
                converted = convert_error(error, factory.__code__.co_filename,
                                          getattr(factory, '_direct_source_text', ''), _context=boundary)
                if converted is error:
                    raise
                raise converted from None
            finally:
                boundary._routine_exports.clear()
                boundary.leave()

        result = scheduler.start(run(), procedure=procedure)
        return None if procedure else result

    context.start_async = start
