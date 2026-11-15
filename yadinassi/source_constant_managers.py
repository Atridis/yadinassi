"""Source-owned synchronous constant value managers, not native parity."""
from contextvars import ContextVar
from .values import BSLObject, HostFunction
from .syntax import ast
from .configuration_source_runtime import _SourceInterpreter
from .source_constants_runtime import SourceConstants

_active_write = ContextVar('source_constant_write', default=False)
_constructing = ContextVar('source_constant_construction', default=())
_STANDARD_METHODS = {'read', 'прочитать', 'write', 'записать', 'metadata', 'метаданные'}
_UNSET = object()
_MODULE_BLOCKER = 'constant module execution is not supported'


class _ValueInterpreter(_SourceInterpreter):
    def __init__(self, manager, application):
        super().__init__(application, family_owner=application.interpreter,
                         compilation_profile=application.compilation_profile)
        self.manager = manager
        self._logical_side = 'server'

    def visit_Name(self, node):
        if node.name.casefold() in ('value', 'значение'):
            return self.manager.value_read(self)
        if node.name.casefold() in ('thisobject', 'этотобъект'):
            return self.manager
        return super().visit_Name(node)

    def argument(self, node):
        node = self.ungroup(node)
        if type(node) is ast.Name and node.name.casefold() == '__constant_cancel':
            from .runtime import _Reference
            return _Reference(lambda: self.variables['__constant_cancel'],
                              lambda value: self.variables.__setitem__('__constant_cancel', value))
        if type(node) is ast.Name and node.name.casefold() in ('value', 'значение'):
            from .runtime import _Reference
            self.manager.value_read(self)
            return _Reference(lambda: self.manager.value_read(self),
                              lambda value: self.manager.value_write(self, value))
        return (yield from super().argument(node))

    def set_variable(self, name, value):
        if name.casefold() in ('value', 'значение'):
            self.manager.value_write(self, value)
            return
        if name.casefold() in ('thisobject', 'этотобъект'):
            raise ValueError('ThisObject is read-only')
        super().set_variable(name, value)


class SourceConstantValueManager(BSLObject):
    def __init__(self, owner, name):
        self.owner, self.name = owner, name
        self.value = _UNSET
        self.interpreter = None
        self._ready = True
        self._closed = False

    def get_member(self, name):
        aliases = {'read': 'read', 'прочитать': 'read', 'write': 'write', 'записать': 'write',
                   'metadata': 'metadata', 'метаданные': 'metadata'}
        operation = aliases.get(name.casefold())
        if operation is None:
            raise ValueError('unsupported value-manager property or exported routine: ' + name)
        return HostFunction(name, ValueManagerCall(self, operation), returns_value=operation == 'metadata')

    def authorize(self, caller):
        store = self.owner._store(caller)
        if self._closed or (not self._ready and caller is not self.interpreter):
            raise ValueError('constant manager initialization is incomplete or failed')
        if self.interpreter is not None:
            self.interpreter._require_family()
        return store

    def property_read(self, caller, name):
        self.authorize(caller)
        if name.casefold() in ('value', 'значение'):
            return self.value_read(caller)
        if name.casefold() in _STANDARD_METHODS:
            return self.get_member(name)
        if self.interpreter is None:
            raise ValueError('constant manager exported field unavailable: ' + name)
        return self.interpreter._self_module.get_member(name)

    def property_write(self, caller, name, value):
        self.authorize(caller)
        if name.casefold() in ('value', 'значение'):
            return self.value_write(caller, value)
        if self.interpreter is None or name.casefold() in _STANDARD_METHODS:
            raise ValueError('constant manager exported field unavailable: ' + name)
        self.interpreter._self_module.set_member(name, value)

    def exported_routine(self, caller, name):
        self.authorize(caller)
        if caller._scheduler.pending:
            raise ValueError('constant manager exports require synchronous execution')
        if self.interpreter is None:
            raise ValueError('constant manager exported routine unavailable: ' + name)
        return self.interpreter._self_module.routine(name)

    def value_read(self, caller):
        self.authorize(caller)
        if self.value is _UNSET:
            raise ValueError('uninitialized constant manager Value; explicit Read or assignment required')
        return self.value

    def value_write(self, caller, value):
        store = self.authorize(caller)
        from .source_constant_store import _encode
        _encode(value, store._definition(self.name))
        self.value = value

    def event(self, caller, names):
        vm = self.interpreter
        if vm is None:
            return
        routines = [vm.server_routines[name] for name in names if name in vm.server_routines]
        if not routines:
            return
        if len(routines) != 1:
            raise ValueError('ambiguous constant event')
        routine = routines[0]
        if (routine.is_function or routine.is_async or len(routine.parameters) != 1
                or routine.parameters[0].by_value or routine.parameters[0].default is not None):
            raise ValueError('unsupported constant event signature')
        # Reserved internal storage remains reachable when Write is called from
        # an exported routine with an active local frame. It never aliases user locals.
        vm.variables['__constant_cancel'] = False
        argument = ast.Name(routine.token, '__constant_cancel')
        yield from vm.call_routine(routine, [argument], vm, require_value=False)
        cancelled = vm.variables.pop('__constant_cancel')
        if type(cancelled) is not bool:
            raise TypeError('constant event Cancel requires Boolean')
        if cancelled:
            raise ValueError('constant write cancelled by handler')


def create_manager(caller, owner, name):
    store = owner._store(caller)
    if _constructing.get() and not store.transaction_active:
        raise ValueError('constant initialization transaction aborted')
    if caller._scheduler.pending:
        raise ValueError('constant value managers require no pending asynchronous tasks')
    definition = store._definition(name)
    app = owner._application()
    if any(item.family == 'EventSubscription' for item in app.source.metadata):
        raise ValueError('constant event subscriptions unsupported')
    prefix = 'Constants/' + definition.name + '/'
    path = prefix + 'Ext/ValueManagerModule.bsl'
    module_files = [p for p, raw in app.files.items() if p.startswith(prefix) and p.lower().endswith('.bsl') and raw.strip()]
    if any(p != path for p in module_files):
        raise ValueError('unsupported constant module location')
    manager = SourceConstantValueManager(owner, definition.name)
    if module_files:
        from .configuration_modules import compile_module
        program = compile_module(app.files[path], path, 'server', common=False)
        reserved = {'value', 'значение', 'thisobject', 'этотобъект', '__constant_cancel'} | _STANDARD_METHODS
        if any((type(node) is ast.Var and any(n.casefold() in reserved for n in node.names))
               or (type(node) is ast.Routine and (node.name.casefold() in reserved
                    or any(p.name.casefold() in reserved for p in node.parameters))) for node in program):
            raise ValueError('constant module reserved name conflict')
        if any(type(node) is ast.Routine and node.name.casefold() in ('fillcheckprocessing', 'обработкапроверкизаполнения') for node in program):
            raise ValueError('constant FillCheckProcessing unsupported')
        stack = _constructing.get()
        key = (id(app), definition.identity)
        if key in stack or len(stack) >= 32:
            raise ValueError('recursive or excessive constant manager construction')
        vm = _ValueInterpreter(manager, app)
        manager.interpreter, manager._ready = vm, False
        token = _constructing.set((*stack, key))
        owned = not store.transaction_active
        from .database_transactions import admission
        from .safe_mode import routine_frame
        try:
            if owned:
                store.begin_transaction()
            # Declarations register before statements. Self-access is allowed;
            # other callers cannot use a manager whose initialization is pending.
            vm._self_module.ready = True
            with admission(False), routine_frame(caller, vm):
                yield from vm._execute_program(program)
            if not store.transaction_active:
                raise ValueError('constant initialization transaction aborted')
            owner._store(caller)
            if owned:
                store.commit_transaction()
            manager._ready = True
        except BaseException:
            manager._closed = True
            if store.transaction_active:
                store.rollback_transaction()
            vm.close()
            raise
        finally:
            _constructing.reset(token)
    return manager


def write_managers(caller, owner, managers):
    store = owner._store(caller)
    if _constructing.get() and not store.transaction_active:
        raise ValueError('constant initialization transaction aborted')
    if caller._scheduler.pending:
        raise ValueError('constant writes require no pending asynchronous tasks')
    if _active_write.get():
        raise ValueError('recursive constant handler writes unsupported')
    owned = not store.transaction_active
    token = _active_write.set(True)
    from .database_transactions import admission
    try:
        if owned:
            store.begin_transaction()
        # Event code must not commit/rollback a transaction owned by this write.
        with admission(False):
            for manager in managers:
                if manager.owner._application() is not owner._application():
                    raise ValueError('foreign constant value manager')
                definition = store._definition(manager.name)
                blockers = tuple(item for item in definition.write_blockers if item != _MODULE_BLOCKER)
                if blockers:
                    raise ValueError('unsupported constant write: ' + '; '.join(blockers))
                manager.value_read(caller)
                yield from manager.event(caller, ('beforewrite', 'передзаписью'))
                if not store.transaction_active:
                    raise ValueError('constant write transaction aborted by handler')
                store._set_after_handlers(manager.name, manager.value_read(caller))
                yield from manager.event(caller, ('onwrite', 'призаписи'))
                if not store.transaction_active:
                    raise ValueError('constant write transaction aborted by handler')
                owner._store(caller)  # Recheck if a handler changed safe mode/ownership.
        if owned:
            store.commit_transaction()
    except BaseException:
        if store.transaction_active:
            store.rollback_transaction()
        raise
    finally:
        _active_write.reset(token)


def write_values(caller, owner, values):
    store = owner._store(caller)
    if _constructing.get() and not store.transaction_active:
        raise ValueError('constant initialization transaction aborted')
    if caller._scheduler.pending or _active_write.get():
        raise ValueError('recursive or asynchronous constant writes unsupported')
    owned = not store.transaction_active
    managers = []
    try:
        if owned:
            store.begin_transaction()
        for name, value in values.items():
            manager = yield from create_manager(caller, owner, name)
            managers.append(manager)
            manager.value_write(caller, value)
        yield from write_managers(caller, owner, managers)
        if owned:
            store.commit_transaction()
    except BaseException:
        store = owner._application().constant_store
        if store is not None and store.transaction_active:
            store.rollback_transaction()
        raise
    finally:
        for manager in managers:
            if manager.interpreter is not None:
                manager.interpreter.close()


class ValueManagerCall:
    def __init__(self, receiver, operation):
        self.receiver, self.operation = receiver, operation

    def __call__(self, *args):
        raise ValueError('value manager requires interpreter invocation')

    def invoke(self, caller, values):
        receiver = self.receiver
        owner = receiver._owner if self.operation == 'create' else receiver.owner
        store = owner._store(caller)
        if values:
            raise TypeError('constant value manager method takes no arguments')
        if self.operation == 'create':
            return (yield from create_manager(caller, owner, receiver._name))
        receiver.authorize(caller)
        if self.operation == 'read':
            receiver.value = store.get(receiver.name)
            return
        if self.operation == 'metadata':
            return owner._application().metadata.get_member('Constants').get_member(receiver.name)
        yield from write_managers(caller, owner, [receiver])
