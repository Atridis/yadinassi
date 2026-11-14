"""Source-owned synchronous constant value managers, not native parity."""
from contextvars import ContextVar
from .values import BSLObject, HostFunction, InterpreterCall
from .syntax import ast
from .configuration_source_runtime import _SourceInterpreter
from .source_constants_runtime import SourceConstants

_active_write = ContextVar('source_constant_write', default=False)
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

    def get_member(self, name):
        aliases = {'read': 'read', 'прочитать': 'read', 'write': 'write', 'записать': 'write',
                   'metadata': 'metadata', 'метаданные': 'metadata'}
        operation = aliases.get(name.casefold())
        if operation is None:
            raise ValueError('unsupported value-manager property or exported routine: ' + name)
        return HostFunction(name, ValueManagerCall(self, operation).descriptor(), returns_value=operation == 'metadata')

    def authorize(self, caller):
        # The DB integration extends this exact seam with initialization/closed
        # manager checks. Keep that richer method when merging its lifecycle.
        return self.owner._store(caller)

    def value_read(self, caller):
        self.owner._store(caller)
        if self.value is _UNSET:
            raise ValueError('uninitialized constant manager Value; explicit Read or assignment required')
        return self.value

    def value_write(self, caller, value):
        store = self.owner._store(caller)
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
        # Dedicated caller storage avoids leaking a Cancel variable into the user module.
        # call_routine accepts AST arguments; a private variable belongs to a fresh
        # synchronous source interpreter, never an alias into user variable storage.
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
        program = compile_module(app.files[path], path, 'server', common=False,
                                 compilation_profile=app.compilation_profile)
        if any(type(node) not in (ast.Routine, ast.Var) for node in program):
            raise ValueError('constant module initialization statements unsupported')
        reserved = {'value', 'значение', 'thisobject', 'этотобъект', '__constant_cancel'}
        if any((type(node) is ast.Var and any(n.casefold() in reserved for n in node.names))
               or (type(node) is ast.Routine and (node.name.casefold() in reserved
                    or any(p.name.casefold() in reserved for p in node.parameters))) for node in program):
            raise ValueError('constant module reserved name conflict')
        if any(type(node) is ast.Routine and node.name.casefold() in ('fillcheckprocessing', 'обработкапроверкизаполнения') for node in program):
            raise ValueError('constant FillCheckProcessing unsupported')
        vm = _ValueInterpreter(manager, app)
        manager.interpreter = vm
        try:
            yield from vm._execute_program(program)
        except BaseException:
            vm.close()
            raise
    return manager


def write_managers(caller, owner, managers):
    store = owner._store(caller)
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
    managers = []
    try:
        for name, value in values.items():
            manager = yield from create_manager(caller, owner, name)
            managers.append(manager)
            manager.value_write(caller, value)
        yield from write_managers(caller, owner, managers)
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

    def authorize(self, caller):
        if self.operation == 'create':
            from .source_constants_runtime import SourceConstant
            if type(self.receiver) is not SourceConstant:
                raise TypeError('value manager creation requires a constant')
            return self.receiver._owner._store(caller)
        if self.operation not in ('read', 'write', 'metadata'):
            raise ValueError('invalid value manager operation')
        if type(self.receiver) is not SourceConstantValueManager:
            raise TypeError('value manager operation requires a value manager')
        return self.receiver.authorize(caller)

    def descriptor(self):
        return InterpreterCall(0, 0, self.authorize, self.invoke)

    def invoke(self, caller, values):
        receiver = self.receiver
        owner = receiver._owner if self.operation == 'create' else receiver.owner
        store = self.authorize(caller)
        if values:
            raise TypeError('constant value manager method takes no arguments')
        if self.operation == 'create':
            return (yield from create_manager(caller, owner, receiver._name))
        if self.operation == 'read':
            receiver.value = store.get(receiver.name)
            return
        if self.operation == 'metadata':
            return owner._application().metadata.get_member('Constants').get_member(receiver.name)
        yield from write_managers(caller, owner, [receiver])
