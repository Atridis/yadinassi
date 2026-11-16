"""Small direct managed-form event bridge; no AST execution fallback."""
from contextlib import contextmanager
from . import safe_mode, source_transactions, database_transactions, form_runtime
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .python_direct import REPAIRS, _snapshot
from .python_direct_handlers import prepare_handlers
from .syntax import ast
from .python_direct_configuration import ConfigurationBoundary, check_owner
from .database_context import SQLiteDBContext

CALLBACK_CONSTRUCTORS=('callbackdescription','описаниеоповещения')

SYSTEM_NAMES = ('thisobject','этотобъект','items','элементы','commands','команды',
                'parameters','параметры','formfieldtype','видполяформы',
                'questiondialogmode','режимдиалогавопрос','dialogreturncode','кодвозвратадиалога')

class FormBoundary(ConfigurationBoundary):
    def __init__(self, session, routine):
        BoundaryContext.__init__(self)
        self.session = session
        self.routine = routine
        self.owner = session.interpreter
        self.app = self.owner._configuration_runtime
        self.database = self.owner.database_context
        self._services = session.interpreter.functions
        self.generation = session.interpreter._family_owner._family_generation

    def _check(self):
        BoundaryContext._check(self)
        if (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
                or database_transactions._execution.get() is not None):
            raise BoundaryViolation("direct restricted form execution is not connected")
        vm = self.session.interpreter
        if vm.database_context is not self.database:
            raise BoundaryViolation("form database owner changed")
        if vm._configuration_runtime is not self.app:
            raise BoundaryViolation("form configuration owner changed")
        registry=vm.server_routines if self.routine.execution_context=='server' else vm.routines
        if registry.get(self.routine.name.casefold()) is not self.routine:
            raise BoundaryViolation("form handler binding changed")
        if self.app is not None:
            check_form_owner(self.app,vm)
            self.app.check_call(self.routine,vm)
        if (vm._family_owner._family_closed or vm._family_released
                or vm._family_owner._family_generation != self.generation):
            raise BoundaryViolation("form interpreter authority closed")
        self.session.form._check()

    def checkpoint(self):
        self._check()
        self.session._steps += 1
        if self.session._steps > form_runtime.MAX_STEPS:
            raise form_runtime.FormLimitError('Форма: превышен предел исполнения события')

    def external_get(self, name):
        self._check()
        form = self.session.form
        if name in ('thisobject','этотобъект'): return form
        if name in ('items','элементы'): return form.items
        if name in ('commands','команды'): return form.commands
        if name in ('parameters','параметры'): return self.session._parameters
        if name in ('questiondialogmode','режимдиалогавопрос'):
            from .form_dialogs import QUESTION_DIALOG_MODES
            return QUESTION_DIALOG_MODES
        if name in ('dialogreturncode','кодвозвратадиалога'):
            from .form_dialogs import DIALOG_RETURN_CODES
            return DIALOG_RETURN_CODES
        if name in ('formfieldtype','видполяформы'):
            from .form_model import FORM_FIELD_VIEWS
            return FORM_FIELD_VIEWS
        if self.app is not None and name in self.app._definitions:
            return ConfigurationBoundary.external_get(self,name)
        return form.get_member(name)

    def external_set(self, name, value):
        self._check()
        if name in SYSTEM_NAMES or self.app is not None and name in self.app._definitions: raise ValueError('Форма: поле только для чтения')
        self.session.form.set_member(name, value)

    def resolve_service(self,*args,**kwargs):
        if args and args[0] in tuple('new:'+name for name in CALLBACK_CONSTRUCTORS):
            self._check()
            if self.owner.execution_context!='client' or self.session._owned_form_enrollment is None:
                raise BoundaryViolation('callback constructor requires an enrolled client form')
            def create(*values):
                self._check()
                if len(values)<2 or values[1] is not self.session.form:
                    raise ValueError('direct callback requires the owning self-form')
                result=self.owner._new_callback(values)
                self._check()
                return result
            return create
        if args and args[0].casefold() in ('getattributes','получитьреквизиты'):
            bound=(ConfigurationBoundary.resolve_service(self,*args,**kwargs) if self.app is not None
                   else BoundaryContext.resolve_service(self,*args,**kwargs))
            def attributes(*values):
                from .values import BSLArray
                result=bound(*values)
                if type(result) is not BSLArray:raise BoundaryViolation('form attribute service result')
                return result.items
            if hasattr(bound,'requires_reference'):attributes.requires_reference=bound.requires_reference
            return attributes
        if self.app is not None:return ConfigurationBoundary.resolve_service(self,*args,**kwargs)
        return BoundaryContext.resolve_service(self,*args,**kwargs)

    def get_member(self,value,name):
        from . import python_direct_form_objects as objects
        if objects.recognized(value):return objects.get(self,value,name)
        from .form_dialogs import QUESTION_DIALOG_MODES,DIALOG_RETURN_CODES
        if value is QUESTION_DIALOG_MODES or value is DIALOG_RETURN_CODES:
            self._check()
            return value.get_member(name)
        from .direct_form_parameters import is_parameters,get_parameter
        if is_parameters(self.session,value):
            self._check()
            return get_parameter(self.session,value,name)
        if value is self.session.form and name.casefold() in ('close','закрыть'):
            from .values import HostFunction
            return HostFunction(name,self.resolve_member(value,name),returns_value=False)
        return BoundaryContext.get_member(self,value,name)

    def resolve_member(self,value,name):
        from . import python_direct_form_objects as objects
        if objects.recognized(value):return objects.method(self,value,name)
        from .direct_form_parameters import is_parameters,bind_parameter_method
        if is_parameters(self.session,value):
            self._check()
            method=bind_parameter_method(self.session,value,name)
            def invoke(*args):
                self._check()
                try:return method(*args)
                finally:self._check()
            return invoke
        if value is self.session.form and name.casefold() in ('close','закрыть'):
            self._check()
            def close(result=None):
                self._check()
                try:return self.session.request_close(result)
                finally:self._check()
            return close
        if self.app is not None:return ConfigurationBoundary.resolve_member(self,value,name)
        return BoundaryContext.resolve_member(self,value,name)

    def resolve_set_member(self,value,name):
        from . import python_direct_form_objects as objects
        if objects.recognized(value):return objects.setter(self,value,name)
        from .direct_form_parameters import is_parameters,bind_parameter_write
        if is_parameters(self.session,value):
            self._check()
            write=bind_parameter_write(self.session,value,name)
            def invoke(new_value):
                self._check()
                try:return write(new_value)
                finally:self._check()
            return invoke
        return BoundaryContext.resolve_set_member(self,value,name)


def check_form_owner(app,owner):
    # Only form events use host-enrolled object bindings. This does not expose
    # Catalogs/Query to general configuration modules or bypass the host writer.
    if owner.database_context is not None and type(owner.database_context) is not SQLiteDBContext:
        raise BoundaryViolation('form database requires host-selected SQLite context')
    check_owner(app,owner,allow_database=True)


def prepare_form(session, program, source, attributes, tables, *, install_metadata=True):
    from .form_runtime import _FormInterpreter
    if type(session.interpreter) is not _FormInterpreter:
        raise BoundaryViolation('direct specialized source-form runtime is not connected')
    from . import safe_mode, source_transactions, database_transactions
    if (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
            or database_transactions._execution.get() is not None):
        raise BoundaryViolation("direct restricted form execution is not connected")
    app=session.interpreter._configuration_runtime
    if app is not None:check_form_owner(app,session.interpreter)
    if not hasattr(session,'_direct_form_source'):
        session._direct_form_source=(_snapshot(program),source)
    session._direct_form_schema=frozenset(a.name.casefold() for a in attributes)|frozenset(t.name.casefold() for t in tables)
    # These AST tables are signature metadata only; execution never reads bodies.
    for node in program:
        if install_metadata and type(node) is ast.Routine:
            registry = session.interpreter.server_routines if node.execution_context == 'server' else session.interpreter.routines
            registry[node.name.casefold()] = node
    names = tuple(attr.name.casefold() for attr in attributes) + tuple(t.name.casefold() for t in tables) + SYSTEM_NAMES + (() if app is None else tuple(app._definitions))
    return prepare_handlers(program, source_text=source if type(source) is str else '',
                            external_names=names, constructors=CALLBACK_CONSTRUCTORS, repairs=REPAIRS+('authority_checkpoints',))


def invoke_form(session, handler, side, arguments, *, _export_routine=None):
    # Replica schemas are validated before installation; names may arrive after
    # the client's declaration-only factory was first prepared. Recompile only
    # the owned declarations, never renderer-supplied source or a module body.
    schema=frozenset(session.form._static)|frozenset(session.form._tables)
    if schema != session._direct_form_schema:
        program,source=session._direct_form_source
        attributes=tuple(session.form._attributes[name] for name in session.form._static)
        tables=tuple(table.schema for table in session.form._tables.values())
        session._direct_handlers=prepare_form(session,program,source,attributes,tables,install_metadata=False)
    if _export_routine is None:
        routine=session._bind(handler,side,len(arguments))
    else:
        routine=_export_routine
        if (side != 'server' or routine.execution_context != side or not routine.module_context
                or session.interpreter.server_routines.get(handler.casefold()) is not routine
                or len(routine.parameters)!=len(arguments)
                or any(not parameter.by_value or parameter.default is not None for parameter in routine.parameters)):
            raise BoundaryViolation('direct RPC endpoint binding changed')
    @contextmanager
    def scope():
        vm = session.interpreter
        previous_transactions = getattr(vm, "_transaction_activation_allowed", True)
        vm._transaction_activation_allowed = False
        vm._context_stack.append(side)
        vm._module_context_stack.append(True)
        try: yield
        finally:
            vm._module_context_stack.pop()
            vm._context_stack.pop()
            vm._transaction_activation_allowed = previous_transactions
    # Server module variables are activation-local; client variables persist.
    state = {} if side == 'server' else session.interpreter.variables
    if _export_routine is not None:
        return session._direct_handlers.invoke_export(handler, side, arguments,
                is_function=routine.is_function,state=state,
                context_factory=lambda: FormBoundary(session,routine),execution_scope=scope)
    return session._direct_handlers.invoke(handler, side, arguments, state=state,
                context_factory=lambda: FormBoundary(session,routine), execution_scope=scope)


def invoke_export(session,routine,arguments):
    """Execute only the exact endpoint already admitted by ReplicatedFormServer."""
    return invoke_form(session,routine.name,'server',arguments,_export_routine=routine)
