"""Single-threaded cooperative tasks for BSL async routines.

An await always suspends, even for scalars and settled promises. Only the host
execution boundary pumps the FIFO; calling a routine never pumps other tasks.
"""
import builtins
from collections import deque
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import localcontext
from typing import Any

from .errors import BSLRuntimeError
from .native_targets import target_context, validate_native_target


@dataclass
class ExecutionContext:
    locals: dict[object, dict | None] = field(default_factory=dict)
    context_stack: list[str] = field(default_factory=lambda: ['client'])
    module_context_stack: list[bool] = field(default_factory=lambda: [True])
    state: dict[object, dict] = field(default_factory=dict)
    host_failure: BaseException | None = None
    request_cache: dict | None = None


@dataclass(frozen=True)
class AwaitRequest:
    value: Any


@dataclass(frozen=True)
class _HostFault:
    """Traceback-free failure value. Every host/Await delivery gets a new error.

    Never store exception instances, arbitrary exception attributes or mutable
    argument payloads: these can own caller frames even after task cleanup.
    """
    kind: type
    args: tuple
    cause: object = None
    context: object = None
    suppress_context: bool = False
    notes: tuple = ()

    @classmethod
    def capture(cls, error, seen=()):
        if type(error) is cls:
            return error
        def argument(value, depth=0):
            if type(value) in (str, bytes, int, float, bool, type(None)):
                return value
            if type(value) is tuple and depth < 8:
                return tuple(argument(item, depth + 1) for item in value)
            # Do not invoke an arbitrary host object's repr/str on cleanup.
            return '<host argument: ' + type.__getattribute__(type(value), '__name__') + '>'
        seen = (*seen, id(error))
        def chain(item):
            return (None if item is None or id(item) in seen or len(seen) >= 8
                    else cls.capture(item, seen))
        # Direct base descriptors bypass subclass getattribute/property hooks.
        attributes = BaseException.__dict__['__dict__'].__get__(error)
        notes = attributes.get('__notes__', ())
        return cls(type(error), tuple(argument(arg) for arg in BaseException.args.__get__(error)),
                   chain(BaseException.__cause__.__get__(error)),
                   chain(BaseException.__context__.__get__(error)),
                   BaseException.__suppress_context__.__get__(error),
                   tuple(note for note in notes if type(note) is str)
                   if type(notes) in (tuple, list) else ())

    def deliver(self):
        # Bypass custom __init__/__new__/copy/reduce callbacks. Specialized
        # builtin exceptions (e.g. OSError) require their own C allocator.
        name = type.__getattribute__(self.kind, '__name__')
        if getattr(builtins, name, None) is self.kind:
            try:
                error = self.kind(*self.args)
            except (TypeError, ValueError):
                # Sanitized payloads may not satisfy a specialized allocator
                # (e.g. ExceptionGroup's list of child exception objects).
                error = RuntimeError(name, *self.args)
        else:
            try:
                error = BaseException.__new__(self.kind, *self.args)
            except TypeError:
                error = RuntimeError(name, *self.args)
        BaseException.args.__set__(error, self.args if type(error) is self.kind else (name, *self.args))
        BaseException.__cause__.__set__(error, None if self.cause is None else self.cause.deliver())
        BaseException.__context__.__set__(error, None if self.context is None else self.context.deliver())
        BaseException.__suppress_context__.__set__(error, self.suppress_context)
        if self.notes:
            BaseException.__dict__['__dict__'].__get__(error)['__notes__'] = list(self.notes)
        return error


class Promise:
    """Opaque BSL value; settlement is owned exclusively by its scheduler."""
    __slots__ = ('_scheduler', '_state', '_result', '_listeners', '_adopting', '_claimed')

    def __init__(self, scheduler: 'Scheduler'):
        self._scheduler = scheduler
        self._state = 'pending'
        self._result = None
        self._listeners = []
        self._adopting = None
        self._claimed = False

    def __str__(self):
        raise TypeError('Promise string presentation is not supported')

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def state(self):
        return self._state

    @property
    def result(self):
        return self._result.deliver() if self._state == 'failed' else self._result


@dataclass(eq=False)
class _Task:
    generator: Generator
    promise: Promise
    context: ExecutionContext


def _error(message):
    return BSLRuntimeError(message, '<async>', 1, 1)


class SchedulerLimitError(RuntimeError):
    """The host-selected cooperative scheduler budget was exhausted."""


class Scheduler:
    def __init__(self, native_target: str):
        self.native_target = validate_native_target(native_target)
        self.active_context = ExecutionContext()
        self._active_task = None
        self._tasks = set()
        self._pending = set()
        self._ready = deque()
        self._notifications = deque()
        self._notifying = False
        self._pumping = False
        self._inline_depth = 0
        self.procedure_errors: list[BSLRuntimeError] = []

    @property
    def is_active(self):
        return self._active_task is not None or self._inline_depth > 0

    @property
    def pending(self):
        """Pending promises, including suspended tasks and host-owned signals."""
        return tuple(self._pending)

    def new_pending(self):
        promise = Promise(self)
        self._pending.add(promise)
        return promise

    def _check_owner(self, promise):
        if not isinstance(promise, Promise) or promise.scheduler is not self:
            raise _error('Promise belongs to another scheduler')

    def _listen(self, promise, listener):
        if promise.state == 'pending':
            promise._listeners.append(listener)
        else:
            listener(promise)

    def _settle(self, promise, state, value):
        if promise.state != 'pending':
            return
        if state == 'failed':
            value = _HostFault.capture(value)
        if state == 'rejected':
            # BSL source diagnostics live in the error/info snapshot, not in
            # Python frames. Reusing a rejection must not retain prior tasks.
            value.__traceback__ = None
            value.__context__ = None
            value.__cause__ = None
        promise._state, promise._result = state, value
        promise._adopting = None
        self._pending.discard(promise)
        listeners, promise._listeners = promise._listeners, []
        self._notifications.extend((listener, promise) for listener in listeners)
        if self._notifying:
            return
        self._notifying = True
        try:
            while self._notifications:
                listener, source = self._notifications.popleft()
                listener(source)
        finally:
            self._notifying = False

    def resolve(self, promise, value=None):
        self._check_owner(promise)
        if promise._claimed:
            return
        promise._claimed = True
        if isinstance(value, Promise):
            if value.scheduler is not self:
                self._settle(promise, 'rejected', _error('Promise belongs to another scheduler'))
                return
            cursor = value
            while cursor is not None:
                if cursor is promise:
                    self._settle(promise, 'rejected', _error('Cyclic promise resolution'))
                    return
                cursor = cursor._adopting
            promise._adopting = value
            self._listen(value, lambda source: self._settle(promise, source.state, source._result))
        else:
            self._settle(promise, 'fulfilled', value)

    def reject(self, promise, error):
        self._check_owner(promise)
        if not isinstance(error, BSLRuntimeError):
            raise TypeError('A promise rejection must be a BSLRuntimeError')
        if not promise._claimed:
            promise._claimed = True
            self._settle(promise, 'rejected', error)

    @contextmanager
    def _scope(self, task=None):
        previous_context, previous_task = self.active_context, self._active_task
        if task is not None:
            self.active_context, self._active_task = task.context, task
        try:
            with target_context(self.native_target), localcontext() as context:
                context.prec = 38
                yield
        finally:
            self.active_context, self._active_task = previous_context, previous_task

    def start(self, generator, *, procedure=False):
        promise = self.new_pending()
        context = ExecutionContext(context_stack=list(self.active_context.context_stack),
                                   module_context_stack=list(self.active_context.module_context_stack))
        task = _Task(generator, promise, context)
        self._tasks.add(task)
        if procedure:
            self._listen(promise, self._record_procedure_error)
        self._resume(task)
        return promise

    def _record_procedure_error(self, promise):
        if promise.state == 'rejected':
            self.procedure_errors.append(promise.result)

    def take_procedure_error(self):
        """Consume a host-boundary batch, reporting its first failure only.

        The scheduler is not an exception history. Return a detached exception:
        the original can also belong to a rejected promise that BSL may await
        again, and raising it in host code would retain that host's frames.
        """
        if not self.procedure_errors:
            return None
        first = self.procedure_errors[0]
        self.procedure_errors.clear()
        return BSLRuntimeError(first.message, first.source, first.line, first.column,
                               info=first.info, source_line=first.source_line)

    def _resume(self, task, value=None, error=None):
        if task not in self._tasks:
            return
        with self._scope(task):
            try:
                if issubclass(type(error), BSLRuntimeError):
                    # A promise can be awaited repeatedly. Python appends a
                    # new delivery traceback to the same exception otherwise.
                    error.__traceback__ = None
                    error.__context__ = None
                    error.__cause__ = None
                    try:
                        request = task.generator.throw(error)
                    finally:
                        # A handled rejection can leave this consumer's frames
                        # on the shared error even when the task fulfills.
                        error.__traceback__ = None
                        error.__context__ = None
                        error.__cause__ = None
                elif error is not None:
                    # Distinguish an already-terminal host fault from ordinary
                    # ValueError/TypeError raised by a BSL builtin. The VM must
                    # not convert this delivery into a catchable BSL rejection.
                    previous = task.context.host_failure
                    task.context.host_failure = error
                    try:
                        request = task.generator.throw(error)
                    finally:
                        task.context.host_failure = previous
                else:
                    request = task.generator.send(value)
            except StopIteration as stop:
                self._tasks.discard(task)
                self.resolve(task.promise, stop.value)
                return
            except BSLRuntimeError as failure:
                self._tasks.discard(task)
                self.reject(task.promise, failure)
                return
            except BaseException as failure:
                # A generator that escaped is closed, not suspended. Retain a
                # terminal outcome for awaiters without disguising host faults
                # as catchable BSL rejections or losing the original exception.
                self._fail_task(task, failure)
                raise
        if not isinstance(request, AwaitRequest):
            failure = RuntimeError('Async task yielded an unsupported request')
            try:
                with self._scope(task):
                    task.generator.close()
            except BaseException as close_failure:
                self._fail_task(task, close_failure)
                raise
            self._fail_task(task, failure)
            raise failure
        awaited = request.value
        if isinstance(awaited, Promise):
            if awaited.scheduler is not self:
                self._ready.append((task, None, _error('Promise belongs to another scheduler')))
            elif awaited is task.promise:
                self._ready.append((task, None, _error('A task cannot await itself')))
            else:
                self._listen(awaited, lambda source: self._ready.append(
                    (task, source.result if source.state == 'fulfilled' else None,
                     source.result if source.state in ('rejected', 'failed') else None)))
        else:
            self._ready.append((task, awaited, None))

    def _fail_task(self, task, failure):
        self._tasks.discard(task)
        task.promise._claimed = True
        self._settle(task.promise, 'failed', failure)

    def run_inline(self, generator):
        """Execute a synchronous root without pumping or switching task context."""
        root_request = self._inline_depth == 0 and self._active_task is None
        context = self.active_context
        previous_request = context.request_cache
        if root_request:
            context.request_cache = {}
        self._inline_depth += 1
        try:
            with self._scope():
                try:
                    next(generator)
                except StopIteration as stop:
                    return stop.value
                finally:
                    generator.close()
            raise RuntimeError('Synchronous execution cannot suspend')
        finally:
            self._inline_depth -= 1
            if root_request:
                context.request_cache.clear()
                context.request_cache = previous_request

    def run_until_idle(self, *, max_steps=100_000):
        """Drain ready work, with a host safety budget of 100,000 resumptions.

        Exhaustion raises instead of claiming completion. Queued and pending
        work remains intact for host inspection, another pump, or reset. This
        budget does not preempt a routine that never reaches an await.
        """
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError('max_steps must be a positive integer')
        if self._pumping or self.is_active:
            raise RuntimeError('Nested scheduler pumping is not supported')
        self._pumping = True
        steps = 0
        try:
            while self._ready:
                if steps >= max_steps:
                    raise SchedulerLimitError('Async scheduler step budget exhausted')
                self._resume(*self._ready.popleft())
                steps += 1
        finally:
            self._pumping = False

    def reset(self):
        """Close suspended frames in their own context and discard all work."""
        if self._pumping or self.is_active:
            raise RuntimeError('Cannot reset an active scheduler')
        failure = None
        try:
            for task in tuple(self._tasks):
                try:
                    with self._scope(task):
                        task.generator.close()
                except BaseException as error:
                    # Still release other tasks; never turn host failures into BSL errors.
                    if failure is None:
                        failure = error
        finally:
            self._tasks.clear()
            self._ready.clear()
            self._notifications.clear()
            # Cancellation must not resume discarded tasks or report procedure errors.
            for promise in self._pending:
                promise._listeners.clear()
                promise._adopting = None
                promise._claimed = True
                promise._state = 'rejected'
                promise._result = _error('Scheduler was reset')
            self._pending.clear()
            self.procedure_errors.clear()
            self.active_context = ExecutionContext()
        if failure is not None:
            raise failure
