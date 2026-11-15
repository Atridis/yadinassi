"""Identity of this explicit synchronous scratch-host startup, not a native login."""
import weakref
from .values import BSLObject, HostFunction


class SourceHostSession(BSLObject):
    def __init__(self, application):
        self._application = weakref.ref(application)
        # SourceApplication starts synchronously, never through a background job.
        self._background_job = None

    def authorize(self, caller):
        app = self._application()
        if app is None:
            raise ValueError('source host session is closed')
        app.require_open()
        caller._require_family()
        if (caller._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler
                or caller.execution_context != 'server'
                or caller._scheduler._active_task is not None):
            raise ValueError('source host session requires owning synchronous server context')
        if app.constant_store is None:
            raise ValueError('information base session requires explicit source scratch database')
        # No disk read or platform authority is granted by this session identity.
        return app

    def get_member(self, name):
        if name.casefold() in ('getbackgroundjob', 'получитьфоновоезадание'):
            return HostFunction(name, SourceSessionCall(self, False))
        raise ValueError('source host session member is not supported: ' + name)


class SourceSessionCall:
    def __init__(self, session, current):
        self.session, self.current = session, current

    def __call__(self, *args):
        raise ValueError('session methods require an interpreter invocation')

    def invoke(self, caller, values):
        if values:
            raise TypeError('source session query takes no arguments')
        app = self.session.authorize(caller)
        if self.current == 'connection':
            # Explicit host identity, not native File/Srvr syntax or DB grants.
            return 'SQLite=' + app.constant_store.path
        return self.session if self.current else self.session._background_job
