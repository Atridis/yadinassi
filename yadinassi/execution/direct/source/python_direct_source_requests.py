"""Synchronous direct-source request cache lifetime, without scheduler execution."""
from contextlib import contextmanager
from contextvars import ContextVar
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_ACTIVE=ContextVar('direct_source_requests',default=())


@contextmanager
def request_scope(owner):
    scheduler=owner._scheduler
    context=scheduler.active_context
    if scheduler._active_task is not None or scheduler.pending:
        raise BoundaryViolation('direct source request requires synchronous execution')
    active=_ACTIVE.get()
    shared=next((entry for entry in reversed(active) if entry[0] is scheduler),None)
    if shared is not None:
        _,expected_context,cache=shared
        if context is not expected_context or context.request_cache is not cache:
            raise BoundaryViolation('direct source request context changed')
        try:
            yield
        finally:
            changed=(scheduler.active_context is not context or context.request_cache is not cache
                     or owner._scheduler is not scheduler)
            context.request_cache=cache
            if changed:
                raise BoundaryViolation('direct source request context changed')
        return
    previous=context.request_cache
    if previous is not None and type(previous) is not dict:
        raise BoundaryViolation('direct source request cache is not canonical')
    cache={}
    context.request_cache=cache
    token=_ACTIVE.set((*active,(scheduler,context,cache)))
    try:
        yield
    finally:
        changed=(scheduler.active_context is not context or context.request_cache is not cache
                 or owner._scheduler is not scheduler)
        dict.clear(cache)
        context.request_cache=previous
        _ACTIVE.reset(token)
        if changed:
            raise BoundaryViolation('direct source request context changed')
