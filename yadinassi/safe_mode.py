"""Boolean-only source execution restriction, not a security-profile manager.

The state belongs to a scheduler context and a BSL routine frame. External
capability guards consult it at their actual effect boundary, including handles
created before entry. This module does not grant OS permissions or a native host.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import weakref

_CURRENT = ContextVar('yadinassi_source_safe_mode', default=None)


class SourceSafeMode:
    def __init__(self, application):
        self._application = weakref.ref(application)
        self._key = object()

    def _app(self):
        app = self._application()
        if app is None:
            raise ValueError('safe-mode source application is closed')
        app.require_open()
        return app

    def _frames(self):
        app = self._app()
        return app.interpreter._scheduler.active_context.state.get(self._key, {}).get('frames', [])

    def active(self):
        return any(frame['count'] for frame in self._frames())

    def get(self):
        if _CURRENT.get() is not self:
            raise ValueError('safe mode requires the active source execution context')
        return self.active()

    def set(self, enabled):
        if type(enabled) is not bool:
            raise TypeError('source safe mode supports Boolean only; security profiles are unavailable')
        app = self._app()
        if _CURRENT.get() is not self or app.interpreter._scheduler._active_task is not None:
            raise ValueError('safe-mode changes require a synchronous source routine')
        frames = self._frames()
        if not frames:
            raise ValueError('safe-mode changes require a BSL routine frame')
        if enabled:
            frames[-1]['count'] += 1
        elif not frames[-1]['count']:
            raise ValueError('cannot disable safe mode owned by a caller or an inactive frame')
        else:
            frames[-1]['count'] -= 1

    @contextmanager
    def execution(self):
        self._app()
        previous = _CURRENT.get()
        if previous is not None and previous is not self and previous.active():
            raise ValueError('safe mode forbids transfer to another application')
        token = _CURRENT.set(self)
        try:
            yield
        finally:
            _CURRENT.reset(token)

    @contextmanager
    def routine(self, caller, owner):
        app = self._app()
        if (caller._family_owner is not app.interpreter
                or owner._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler):
            raise ValueError('safe-mode routine belongs to another source application')
        state = app.interpreter._scheduler.active_context.state
        frames = state.setdefault(self._key, {'frames': []})['frames']
        frame = {'count': 0}
        frames.append(frame)
        try:
            yield
        finally:
            frames.pop()
            if not frames:
                state.pop(self._key, None)


@contextmanager
def routine_frame(caller, owner):
    mode = _CURRENT.get()
    if mode is None:
        yield
    else:
        with mode.routine(caller, owner):
            yield


def require_external_access(operation='external operation'):
    mode = _CURRENT.get()
    if mode is not None and mode.active():
        raise ValueError('safe mode forbids external access: ' + operation)


def require_transfer(operation):
    mode = _CURRENT.get()
    if mode is not None and mode.active():
        raise ValueError('source safe mode does not support ' + operation)
