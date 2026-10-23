"""Single-threaded cooperative tasks for BSL async routines.

An await always suspends, even for scalars and settled promises. Only the host
execution boundary pumps the FIFO; calling a routine never pumps other tasks.
"""
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
    state: dict[object, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class AwaitRequest:
    value: Any


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
        return self._result


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
            self._listen(value, lambda source: self._settle(promise, source.state, source.result))
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
        context = ExecutionContext(context_stack=list(self.active_context.context_stack))
        task = _Task(generator, promise, context)
        self._tasks.add(task)
        if procedure:
            self._listen(promise, self._record_procedure_error)
        self._resume(task)
        return promise

    def _record_procedure_error(self, promise):
        if promise.state == 'rejected':
            self.procedure_errors.append(promise.result)

    def _resume(self, task, value=None, error=None):
        if task not in self._tasks:
            return
        with self._scope(task):
            try:
                if error is not None:
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
        if not isinstance(request, AwaitRequest):
            raise RuntimeError('Async task yielded an unsupported request')
        awaited = request.value
        if isinstance(awaited, Promise):
            if awaited.scheduler is not self:
                self._ready.append((task, None, _error('Promise belongs to another scheduler')))
            elif awaited is task.promise:
                self._ready.append((task, None, _error('A task cannot await itself')))
            else:
                self._listen(awaited, lambda source: self._ready.append(
                    (task, source.result if source.state == 'fulfilled' else None,
                     source.result if source.state == 'rejected' else None)))
        else:
            self._ready.append((task, awaited, None))

    def run_inline(self, generator):
        """Execute a synchronous root without pumping or switching task context."""
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
