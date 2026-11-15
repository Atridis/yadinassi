"""Read-only empty extension registry of an explicitly created scratch host.

This is not extension activation or access to another information base. Unknown
or populated registry state fails, rather than being presented as an empty list.
"""
import weakref
from enum import Enum
from .values import BSLObject, BSLArray, HostFunction
from .safe_mode import require_external_access


class ExtensionSource(Enum):
    DATABASE = 'Database'
    APPLIED = 'SessionApplied'
    DISABLED = 'SessionDisabled'


class SourceExtensionSources(BSLObject):
    def get_member(self, name):
        values = {'database': ExtensionSource.DATABASE, 'базаданных': ExtensionSource.DATABASE,
                  'sessionapplied': ExtensionSource.APPLIED, 'сеансактивные': ExtensionSource.APPLIED,
                  'sessiondisabled': ExtensionSource.DISABLED, 'сеансотключенные': ExtensionSource.DISABLED}
        if name.casefold() not in values:
            raise ValueError('unknown configuration extensions source: ' + name)
        return values[name.casefold()]


class SourceExtensions(BSLObject):
    def __init__(self, application):
        self._application = weakref.ref(application)

    def get_member(self, name):
        aliases = {'get':'get', 'получить':'get',
                   'getsessionapplicationissuesinformation':'issues',
                   'получитьинформациюопроблемахприменениявсеансе':'issues'}
        operation = aliases.get(name.casefold())
        if operation is None:
            raise ValueError('extension attachment and mutation are not supported: ' + name)
        return HostFunction(name, ExtensionCall(self, operation))

    def read(self, caller, operation, arguments):
        app = self._application()
        if app is None or caller is None:
            raise ValueError('extension registry belongs to a closed application')
        app.require_open()
        caller._require_family()
        if (caller._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler
                or caller.execution_context != 'server'
                or caller._scheduler._active_task is not None):
            raise ValueError('extension registry requires owning synchronous server context')
        if app.constant_store is None:
            raise ValueError('extension state requires an explicitly created source scratch database')
        if operation == 'get':
            if len(arguments) > 2:
                raise TypeError('ConfigurationExtensions.Get accepts at most two arguments')
            if arguments and arguments[0] is not None:
                raise ValueError('extension filter is not yet supported')
            if len(arguments) == 2 and arguments[1] is not None and type(arguments[1]) is not ExtensionSource:
                raise TypeError('ConfigurationExtensionsSource required')
        elif arguments:
            raise TypeError('extension issues query takes no arguments')
        require_external_access('source extension registry database')
        app.constant_store.require_empty_extension_registry()
        return BSLArray()


class ExtensionCall:
    def __init__(self, manager, operation):
        self.manager, self.operation = manager, operation

    def __call__(self, *args):
        raise ValueError('extension methods require an interpreter invocation')

    def invoke(self, caller, values):
        return self.manager.read(caller, self.operation, values)
