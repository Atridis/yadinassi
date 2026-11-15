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
        from .source_document_runtime import _active_write as document_write, _constructing as document_construction
        if (document_write.get() or document_construction.get()) and not app.constant_store.transaction_active:
            raise ValueError('document lifecycle transaction aborted; constants access refused')
        return app.constant_store

    def get_member(self, name):
        if name.casefold() in ('createset', 'создатьнабор'):
            return HostFunction(name, ConstantSetCall(self, 'create'))
        raise ValueError('constant manager property requires interpreter access')

    def members(self, caller):
        store = self._store(caller)
        return tuple(SourceConstant(self, name) for name in store.names)

    def member(self, caller, name):
        store = self._store(caller)
        if type(name) is not str:
            raise TypeError('constant name requires String')
        if name.casefold() in ('createset', 'создатьнабор'):
            if store.has(name):
                raise ValueError('constant name conflicts with CreateSet; unsupported')
            return self.get_member(name)
        if not store.has(name):
            raise ValueError('unknown constant: ' + name)
        return SourceConstant(self, name)


class SourceConstant(BSLObject):
    def __init__(self, owner, name):
        self._owner, self._name = owner, name

    def get_member(self, name):
        if name.casefold() in ('createvaluemanager', 'создатьменеджерзначения'):
            from .source_constant_managers import ValueManagerCall
            return HostFunction(name, ValueManagerCall(self, 'create'))
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


class SourceConstantSet(BSLObject):
    """Explicitly assigned scalar buffer, no guessed defaults or handler bypass."""
    def __init__(self, owner, names):
        self.owner, self.names, self.values = owner, tuple(names), {}
        self.keys = {name.casefold(): name for name in self.names}

    def get_member(self, name):
        aliases = {'read': 'read', 'прочитать': 'read', 'write': 'write', 'записать': 'write'}
        operation = aliases.get(name.casefold())
        if operation is None:
            raise ValueError('constant set property requires interpreter access')
        return HostFunction(name, ConstantSetCall(self, operation), returns_value=False)

    def read_property(self, caller, name):
        self.owner._store(caller)
        key = name.casefold()
        if key not in self.keys:
            raise ValueError('constant is not selected: ' + name)
        if key not in self.values:
            raise ValueError('uninitialized constant set field: ' + name)
        return self.values[key]

    def write_property(self, caller, name, value):
        store = self.owner._store(caller)
        key = name.casefold()
        if key not in self.keys:
            raise ValueError('constant is not selected: ' + name)
        from .source_constant_store import _encode
        _encode(value, store._definition(self.keys[key]))
        self.values[key] = value


class ConstantSetCall:
    def __init__(self, receiver, operation):
        self.receiver, self.operation = receiver, operation

    def __call__(self, *args):
        raise ValueError('constant set methods require an interpreter invocation')

    def invoke(self, caller, values):
        receiver = self.receiver
        owner = receiver if type(receiver) is SourceConstants else receiver.owner
        store = owner._store(caller)
        if self.operation == 'create':
            if any(name.casefold() in ('createset', 'создатьнабор') for name in store.names):
                raise ValueError('constant name conflicts with CreateSet; unsupported')
            if len(values) > 1 or (values and type(values[0]) is not str):
                raise TypeError('CreateSet expects an optional explicit String list')
            if values:
                if len(values[0]) > 132096:
                    raise ValueError('constant set name list bound')
                names = tuple(item.strip() for item in values[0].split(','))
            else:
                names = store.names
            if not names or len(names) > 1024 or len({name.casefold() for name in names}) != len(names):
                raise ValueError('empty or duplicate constant selection unsupported')
            reserved = {'read', 'прочитать', 'write', 'записать'}
            for name in names:
                store._definition(name)
                if name.casefold() in reserved:
                    raise ValueError('constant set method/name conflict unsupported')
            return SourceConstantSet(owner, names)
        if values:
            raise TypeError('constant set Read/Write take no arguments')
        if self.operation == 'read':
            replacement = store.get_many(receiver.names)
            receiver.values = replacement
            return
        if len(receiver.values) != len(receiver.keys):
            raise ValueError('all selected constant fields must be assigned or read before Write')
        store.set_many({name: receiver.values[name.casefold()] for name in receiver.names})
