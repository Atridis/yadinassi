"""Standalone direct async entry; the scheduler owns all suspension and delivery."""
from threading import get_ident

from yadinassi.application.async_runtime import Promise, Scheduler
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.codegen.direct_errors import convert_error
from yadinassi.syntax import ast


def entry_mode(vm, program):
    from .python_direct import _reject
    if type(program) not in (list, tuple):
        return False
    incoming = any(type(node) is ast.Routine and node.is_async is True for node in program)
    if (not incoming and not getattr(vm, '_direct_import_async', False)
            and not any(module.async_names for module in
                        getattr(vm, '_direct_routine_modules', {}).values())):
        return False
    from yadinassi.runtime import Interpreter
    from .python_direct_imports import owned_child
    root = vm._family_owner
    supported = (type(vm) is Interpreter and (root is vm or owned_child(vm))
                 and vm.database_context is None and root.database_context is None
                 and not getattr(vm, '_direct_invocation_ports', None)
                 and not getattr(root, '_direct_invocation_ports', None)
                 and type(vm._scheduler) is Scheduler and vm._scheduler is root._scheduler)
    if not supported:
        if incoming:
            _reject('asynchronous routines require a standalone client module')
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


def _activation_guard(vm, root, scheduler, generation, state, task, thread):
    if (get_ident() != thread or vm._family_owner is not root
            or vm._scheduler is not scheduler or root._scheduler is not scheduler
            or vm._family_generation != generation or root._family_generation != generation
            or vm.variables is not state or vm._family_closed or root._family_closed
            or vm.database_context is not None or root.database_context is not None
            or getattr(vm, '_direct_invocation_ports', None)
            or getattr(root, '_direct_invocation_ports', None)
            or scheduler._active_task is not task):
        raise BoundaryViolation('direct async activation changed')
    if vm is not root:
        from .python_direct_imports import check_async_owner
        check_async_owner(vm,root,published=task is not None)


def root_guard(vm):
    scheduler, generation, state = vm._scheduler, vm._family_generation, vm.variables
    root, thread = vm._family_owner, get_ident()
    return lambda: _activation_guard(vm, root, scheduler, generation, state, None, thread)


def import_guard(parent, child):
    root = parent.vm._family_owner
    scheduler = parent._async_scheduler
    generation, state = child._family_generation, child.variables
    task, thread = scheduler._active_task, get_ident()
    return lambda: _activation_guard(child, root, scheduler, generation, state, task, thread)


def bind_context(context, vm):
    from .python_direct import make_boundary
    scheduler = vm._scheduler
    context._async_scheduler = scheduler

    def start(factory, constants, body_key, actuals, procedure):
        # The caller resolves and evaluates actuals before entering the task.
        # Bind code to a fresh activation, not to a root lease that is about
        # to end, and do not replay any initializers or source statements.
        context._check()
        root = vm._family_owner
        if vm is not root:
            from .python_direct_imports import check_async_owner
            check_async_owner(vm,root,published=True)
        generation, state, thread = vm._family_generation, vm.variables, get_ident()

        def run():
            task = scheduler._active_task
            def guard():
                _activation_guard(vm, root, scheduler, generation, state, task, thread)
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
