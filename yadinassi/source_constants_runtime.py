"""Source-owned scalar constant managers, without catalog/profile grants."""
import weakref
from .values import BSLObject, HostFunction
from .safe_mode import require_external_access


class SourceConstants(BSLObject):
    def __init__(self, application):
        self._application = weakref.ref(application)

    def _store(self, caller):
        app = self._application()
        if app is None or caller is None:
            raise ValueError('constant manager belongs to a closed application')
        app.require_open()
        if (caller._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler
                or caller.execution_context != 'server'
                or caller._scheduler._active_task is not None):
            raise ValueError('constants require the owning synchronous server context')
        caller._require_family()
        if app.constant_store is None:
            raise ValueError('constants require an explicitly created source scratch database')
        require_external_access('source constants database')
        return app.constant_store

    def member(self, caller, name):
        store = self._store(caller)
        if not store.has(name):
            raise ValueError('unknown constant: ' + name)
        return SourceConstant(self, name)


class SourceConstant(BSLObject):
    def __init__(self, owner, name):
        self._owner, self._name = owner, name

    def get_member(self, name):
        if name.casefold() in ('get', 'получить'):
            return HostFunction(name, ConstantCall(self._owner, self._name, False))
        if name.casefold() in ('set', 'установить'):
            return HostFunction(name, ConstantCall(self._owner, self._name, True), returns_value=False)
        raise ValueError('unsupported constant manager member: ' + name)


class ConstantCall:
    """Host-call marker; authorization uses the actual invoking interpreter."""
    def __init__(self, owner, name, writing):
        self.owner, self.name, self.writing = owner, name, writing

    def __call__(self, *args):
        raise ValueError('constant methods require an interpreter invocation')

    def invoke(self, caller, values):
        store = self.owner._store(caller)
        expected = 1 if self.writing else 0
        if len(values) != expected:
            raise TypeError('invalid constant method argument count')
        if self.writing:
            return store.set(self.name, values[0])
        return store.get(self.name)
