"""Small direct managed-form event bridge; no AST execution fallback."""
from contextlib import contextmanager
from functools import partial
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem
from yadinassi.execution import safe_mode
from yadinassi.db import source_transactions, database_transactions
from yadinassi.forms import form_runtime
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .python_direct import REPAIRS, _snapshot
from .python_direct_handlers import prepare_handlers
from .python_direct_services import TYPE_QUALIFIER_CONSTRUCTORS
from yadinassi.syntax import ast
from .python_direct_configuration import ConfigurationBoundary, check_owner, _COMMAND_SCOPE
from .python_direct_names import VALUE_LIST_CONSTRUCTOR_ALIASES, VALUE_LIST_CHOICE_ALIASES
from yadinassi.db.database_context import SQLiteDBContext
from . import python_direct_user_messages as user_messages

CALLBACK_CONSTRUCTORS=('callbackdescription','описаниеоповещения')
DECLARATION_CONSTRUCTORS=('typedescription','описаниетипов','formattribute','реквизитформы')
VALUE_LIST_SERVICES=tuple('new:'+name for name in VALUE_LIST_CONSTRUCTOR_ALIASES)

SYSTEM_NAMES = ('thisobject','этотобъект','items','элементы','commands','команды',
                'parameters','параметры','formfieldtype','видполяформы',
                'questiondialogmode','режимдиалогавопрос','dialogreturncode','кодвозвратадиалога')

class FormBoundary(ConfigurationBoundary):
    def __init__(self, session, routine):
        BoundaryContext.__init__(self)
        self._command_scope=_COMMAND_SCOPE.get()
        if self._command_scope is not None:
            raise BoundaryViolation('scalar configuration commands cannot enter form execution')
        self.session = session
        self.routine = routine
        self.owner = session.interpreter
        self.vm = self.owner
        self.app = self.owner._configuration_runtime
        self.database = self.owner.database_context
        self._services = session.interpreter.functions
        self.generation = session.interpreter._family_owner._family_generation

    def _check_command_scope(self):
        if self._command_scope is not None or _COMMAND_SCOPE.get() is not None:
            raise BoundaryViolation('scalar configuration commands cannot enter form execution')

    def _check(self):
        BoundaryContext._check(self)
        FormBoundary._check_command_scope(self)
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
        if self.owner._configuration_runtime is not None:
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
            from yadinassi.forms.form_dialogs import QUESTION_DIALOG_MODES
            return QUESTION_DIALOG_MODES
        if name in ('dialogreturncode','кодвозвратадиалога'):
            from yadinassi.forms.form_dialogs import DIALOG_RETURN_CODES
            return DIALOG_RETURN_CODES
        if name in ('formfieldtype','видполяформы'):
            from yadinassi.forms.form_model import FORM_FIELD_VIEWS
            return FORM_FIELD_VIEWS
        if self.owner._configuration_runtime is not None and name in self.app._definitions:
            return ConfigurationBoundary.external_get(self,name)
        return form.get_member(name)

    def external_set(self, name, value):
        self._check()
        if name in SYSTEM_NAMES or self.owner._configuration_runtime is not None and name in self.app._definitions: raise ValueError('Форма: поле только для чтения')
        self.session.form.set_member(name, value)

    def _qualifier_constructor(self, name, expected):
        from yadinassi.types.values import HostFunction
        self._check()
        factory=self.owner.types.get(name)
        def validate():
            if (self.owner.types.get(name) is not factory
                    or type(factory) is not HostFunction or factory.function is not expected
                    or type(factory.reference_parameters) is not frozenset or factory.reference_parameters
                    or factory.returns_value is not True):
                raise BoundaryViolation('form qualifier constructor requires canonical registration')
        validate()
        def construct(*values):
            self._before('call_value',name)
            validate()
            return expected(*values)
        construct.requires_reference=lambda index:False
        return construct

    def resolve_service(self,*args,**kwargs):
        if args and args[0].startswith('new:'):
            name=args[0][4:].casefold()
            qualifier=TYPE_QUALIFIER_CONSTRUCTORS.get(name)
            if qualifier is not None:return self._qualifier_constructor(name,qualifier)
        if args and args[0].casefold() in user_messages.CONSTRUCTOR_SERVICES:
            return user_messages.constructor(self,args[0],**kwargs)
        if args and args[0].casefold() in VALUE_LIST_SERVICES:
            from yadinassi.types.values import HostFunction
            name=args[0][4:].casefold()
            self._check()
            count=kwargs.get('argument_count')
            if type(count) is not int or count != 0:
                raise TypeError('ValueList constructor takes no arguments')
            factory=self.owner.types.get(name)
            if (type(factory) is not HostFunction or factory.function is not BSLValueList
                    or type(factory.reference_parameters) is not frozenset
                    or factory.reference_parameters or factory.returns_value is not True):
                raise BoundaryViolation('form ValueList requires canonical constructor')
            # The registration is a witness, not a mutable callable to replay
            # after argument evaluation. The detached constructor is exact.
            return BSLValueList
        if args:
            function=self._services.get(args[0].casefold())
            if (type(function) is user_messages.HostFunction and type(function.function) is user_messages.MethodType
                    and type(function.function.__self__) is user_messages.BSLUserMessage):
                return user_messages.captured(self,function,operation="call",**kwargs)
        if args and args[0].casefold() in tuple('new:'+name for name in DECLARATION_CONSTRUCTORS):
            from yadinassi.types.values import HostFunction
            from yadinassi.types.type_descriptions import BSLTypeDescription
            from yadinassi.forms.form_runtime import _FormInterpreter
            self._check()
            name=args[0].split(':',1)[1].casefold()
            factory=self.owner.types.get(name)
            function=factory.function if type(factory) is HostFunction else None
            canonical=(function is BSLTypeDescription if name in ('typedescription','описаниетипов') else
                       getattr(function,'__self__',None) is self.owner and
                       getattr(function,'__func__',None) is _FormInterpreter._make_attribute)
            if not canonical:
                raise BoundaryViolation('form declaration constructor requires canonical registration')
            return BoundaryContext.resolve_callable(self,factory)
        if args and args[0].casefold() in ('changeattributes','изменитьреквизиты'):
            bound=(ConfigurationBoundary.resolve_service(self,*args,**kwargs) if self.owner._configuration_runtime is not None
                   else BoundaryContext.resolve_service(self,*args,**kwargs))
            def change(*values):
                from yadinassi.types.values import BSLArray
                converted=[]
                for value in values:
                    if type(value) is list:
                        array=BSLArray();array.items=list(value);value=array
                    converted.append(value)
                return bound(*converted)
            if hasattr(bound,'requires_reference'):change.requires_reference=bound.requires_reference
            return change
        if args and args[0].casefold() in self.owner._invocation_bindings:
            self._check()
            key=args[0].casefold()
            binding=self.owner._invocation_bindings[key]
            routine,invoke=binding
            from yadinassi.execution.invocation import InvocationBinding, InvocationPort, _FormInvocation
            remote=type(invoke) is _FormInvocation
            # InvocationPort registers an empty NoContext transport stub, not
            # a local form server handler carrying ThisObject.
            if type(routine) is not ast.Routine:
                raise BoundaryViolation('form invocation binding changed')
            signature=(routine.is_function,tuple((p.name,p.by_value,p.default) for p in routine.parameters))
            if remote:
                port,contract=invoke.port,invoke.binding
                if type(port) is not InvocationPort or type(contract) is not InvocationBinding:
                    raise BoundaryViolation('form invocation binding changed')
                name,endpoint,parameters,returns=contract.name,contract.endpoint,contract.parameters,contract.is_function
                if (name.casefold()!=key or returns is not routine.is_function
                        or parameters!=tuple(p.name for p in routine.parameters)):
                    raise BoundaryViolation('form invocation binding changed')
            def check():
                self._check()
                if (self.owner.execution_context!='client'
                        or self.owner._invocation_bindings.get(key) is not binding
                        or self.owner.server_routines.get(key) is not routine
                        or routine.execution_context!='server' or routine.module_context is not (not remote)
                        or remote and (type(routine.body) is not list or routine.body
                            or invoke.port is not port or invoke.binding is not contract
                            or contract.name is not name or contract.endpoint is not endpoint
                            or contract.parameters is not parameters or contract.is_function is not returns)
                        or (routine.is_function,tuple((p.name,p.by_value,p.default) for p in routine.parameters))!=signature
                        or any(not p.by_value or p.default is not None for p in routine.parameters)):
                    raise BoundaryViolation('form invocation binding changed')
                if self.owner._configuration_runtime is not None:self.app.check_call(routine,self.owner)
            check()
            if kwargs.get('require_value',False) and not routine.is_function:
                raise TypeError('Процедура не возвращает значение: '+routine.name)
            def call(*values):
                check()
                if len(values)!=len(routine.parameters):
                    raise TypeError('form invocation argument count')
                if not remote:
                    try:return invoke(list(values))
                    finally:self._check()
                from .python_direct_server import _LateNamedValue
                unpacked=[]
                for value in values:
                    if type(value) is _LateNamedValue:
                        try:value=value.reference.get()
                        finally:check()
                    unpacked.append(value)
                def output(message):
                    check()
                    self.owner.output(message)
                    check()
                try:return port.invoke(contract,unpacked,output=output,_check_reply=check)
                finally:check()
            if remote:
                from .python_direct_server import _LateNamedValue
                call.prepare_named_value=_LateNamedValue
            if kwargs.get('allow_references',False):call.requires_reference=lambda index:False
            return call
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
            bound=(ConfigurationBoundary.resolve_service(self,*args,**kwargs) if self.owner._configuration_runtime is not None
                   else BoundaryContext.resolve_service(self,*args,**kwargs))
            def attributes(*values):
                from yadinassi.types.values import BSLArray
                result=bound(*values)
                if type(result) is not BSLArray:raise BoundaryViolation('form attribute service result')
                return result.items
            if hasattr(bound,'requires_reference'):attributes.requires_reference=bound.requires_reference
            return attributes
        if self.owner._configuration_runtime is not None:return ConfigurationBoundary.resolve_service(self,*args,**kwargs)
        return BoundaryContext.resolve_service(self,*args,**kwargs)

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if type(value) is user_messages.BSLUserMessage:
            return user_messages.resolve(self,value,name,require_value=require_value,omitted=omitted)
        kind=type(value)
        if kind is BSLValueList or kind is BSLValueListItem:
            if kind is BSLValueList and name.casefold() in VALUE_LIST_CHOICE_ALIASES:
                return self._bind_value_selection(value,name,require_value,omitted)
            if omitted:raise TypeError('form ValueList argument omission is unsupported')
            # These native data methods carry no form or host authority.
            # Form entry/exit still check the owning event; only the UI method
            # above crosses an effect boundary.
            method=kind.get_method(value,name)
            self._validate_host_function(method,require_value)
            return method
        return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)

    def resolve_callable(self,value,**kwargs):
        if (type(value) is user_messages.HostFunction and type(value.function) is user_messages.MethodType
                and type(value.function.__self__) is user_messages.BSLUserMessage):
            return user_messages.captured(self,value,**kwargs)
        return super().resolve_callable(value,**kwargs)

    def set_member(self,value,name,new_value):
        from . import python_direct_form_objects as objects
        if value is self.session.form or objects.recognized(value):
            return self.resolve_set_member(value,name)(new_value)
        return BoundaryContext.set_member(self,value,name,new_value)

    def reference_member(self,value,name):
        from . import python_direct_form_objects as objects
        from yadinassi.execution.codegen.experimental_naked_boundaries import _HostMemberReference
        if value is self.session.form or objects.recognized(value):
            # A byref argument requires a readable slot, not an eager write grant.
            # Every later read/write returns through the current form protocol.
            self.get_member(value,name)
            return _HostMemberReference(self,value,name)
        return BoundaryContext.reference_member(self,value,name)

    def get_member(self,value,name):
        if type(value) is user_messages.BSLUserMessage:return user_messages.get(self,value,name)
        kind=type(value)
        if kind is BSLValueList or kind is BSLValueListItem:
            return kind.get_member(value,name)
        from . import python_direct_form_objects as objects
        if objects.recognized(value):return objects.get(self,value,name)
        from yadinassi.forms.form_dialogs import QUESTION_DIALOG_MODES,DIALOG_RETURN_CODES
        if value is QUESTION_DIALOG_MODES or value is DIALOG_RETURN_CODES:
            self._check()
            return value.get_member(name)
        from yadinassi.forms.direct_form_parameters import is_parameters,get_parameter
        if is_parameters(self.session,value):
            self._check()
            return get_parameter(self.session,value,name)
        if value is self.session.form and name.casefold() in ('close','закрыть'):
            from yadinassi.types.values import HostFunction
            return HostFunction(name,self.resolve_member(value,name),returns_value=False)
        if value is self.session.form:
            self._check()
            if name.startswith('_'):raise BoundaryViolation('private form member')
            try:return value.get_member(name)
            finally:self._check()
        return BoundaryContext.get_member(self,value,name)

    def resolve_member(self,value,name):
        if type(value) is user_messages.BSLUserMessage:return user_messages.resolve(self,value,name)
        from . import python_direct_form_objects as objects
        if objects.recognized(value):return objects.method(self,value,name)
        from yadinassi.forms.direct_form_parameters import is_parameters,bind_parameter_method
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
        if self.owner._configuration_runtime is not None:return ConfigurationBoundary.resolve_member(self,value,name)
        return BoundaryContext.resolve_member(self,value,name)

    def resolve_set_member(self,value,name):
        if type(value) is user_messages.BSLUserMessage:return user_messages.setter(self,value,name)
        if type(value) is BSLValueListItem:
            return partial(BSLValueListItem.set_member,value,name)
        from . import python_direct_form_objects as objects
        if objects.recognized(value):return objects.setter(self,value,name)
        from yadinassi.forms.direct_form_parameters import is_parameters,bind_parameter_write
        if is_parameters(self.session,value):
            self._check()
            write=bind_parameter_write(self.session,value,name)
            def invoke(new_value):
                self._check()
                try:return write(new_value)
                finally:self._check()
            return invoke
        if value is self.session.form:
            self._check()
            if name.startswith('_'):raise BoundaryViolation('private form member')
            def write(new_value):
                self._check()
                if value is not self.session.form:raise BoundaryViolation('form receiver changed')
                try:value.set_member(name,new_value)
                finally:self._check()
            return write
        return BoundaryContext.resolve_set_member(self,value,name)


def check_form_owner(app,owner):
    # Only form events use host-enrolled object bindings. This does not expose
    # Catalogs/Query to general configuration modules or bypass the host writer.
    if owner.database_context is not None and type(owner.database_context) is not SQLiteDBContext:
        raise BoundaryViolation('form database requires host-selected SQLite context')
    check_owner(app,owner,allow_database=True)


def prepare_form(session, program, source, attributes, tables, *, install_metadata=True, local_server_calls=False):
    from yadinassi.forms.form_runtime import _FormInterpreter
    from .source.python_direct_source_forms import is_source_session,check_source_session,external_names,CONSTRUCTORS
    source_mode=is_source_session(session)
    if source_mode:check_source_session(session)
    elif type(session.interpreter) is not _FormInterpreter:
        raise BoundaryViolation('direct specialized source-form runtime is not connected')
    from yadinassi.execution import safe_mode
    from yadinassi.db import source_transactions, database_transactions
    if not source_mode and (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
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
    if source_mode and install_metadata:
        from .python_direct_source import _signature
        session._direct_source_signatures=tuple((node,_signature(node)) for node in program if type(node) is ast.Routine)
        from .python_direct import _nodes
        native={'array','массив','structure','структура','map','соответствие','uuid','уникальныйидентификатор'}
        session._direct_source_constructors=frozenset(node.name.casefold() for node in _nodes(program)
            if type(node) is ast.New and node.name.casefold() in native)
        from .python_direct import _admit_bindings
        _admit_bindings(session.interpreter,frozenset(),session._direct_source_constructors,frozenset())
    names = tuple(attr.name.casefold() for attr in attributes) + tuple(t.name.casefold() for t in tables) + SYSTEM_NAMES + (() if app is None else tuple(app._definitions))
    if session._catalog_server is not None:
        from .python_direct_form_catalog import NAMES
        names += NAMES
    if source_mode:
        declared={node.name.casefold() for node in program if type(node) is ast.Routine}
        declared.update(name.casefold() for node in program if type(node) is ast.Var for name in node.names)
        names=tuple(dict.fromkeys((*names,*(name for name in external_names(session) if name not in declared))))
    # Source NoContext bodies must never share a lexical generated closure
    # with the form's contextual state. Their calls use the explicit formless
    # adapter; original declarations remain in the live signature registry.
    from yadinassi.forms.form_program import FormSideProgram
    detached = (not source_mode and type(source) is FormSideProgram and source.side == 'server')
    helpers = ([node for node in program if type(node) is ast.Routine and not node.module_context]
               if detached else [])
    if helpers and install_metadata:
        from .python_direct_form_nocontext import prepare
        session._direct_form_nocontext = prepare(session, helpers, source='')
    executable_program=([node for node in program
                         if type(node) is not ast.Routine or node.module_context]
                        if source_mode or helpers else program)
    prepared=prepare_handlers(executable_program, source_text=source if type(source) is str else '',
                            external_names=names, constructors=CALLBACK_CONSTRUCTORS+DECLARATION_CONSTRUCTORS+user_messages.NAMES+(CONSTRUCTORS if source_mode else (*VALUE_LIST_CONSTRUCTOR_ALIASES,*TYPE_QUALIFIER_CONSTRUCTORS)),
                            repairs=REPAIRS+('authority_checkpoints',),_source_routine_scopes=source_mode)
    if install_metadata and local_server_calls:
        vm=session.interpreter
        def bind(routine):
            def call(values):
                if (vm._configuration_runtime is not None or vm.database_context is not None
                        or session._owned_form_enrollment is not None or session.reference_scope is not None):
                    raise BoundaryViolation('local form server call requires standalone ownership')
                result=invoke_export(session,routine,values)
                return vm._copy_context_packet([result])[0]
            return call
        for node in program:
            if type(node) is ast.Routine and node.module_context and node.execution_context=='server' and not node.parameters:
                vm._invocation_bindings.setdefault(node.name.casefold(),(node,bind(node)))
    return prepared


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
        try:
            from contextlib import ExitStack
            from .source.python_direct_source_forms import is_source_session
            with ExitStack() as stack:
                if is_source_session(session):
                    stack.enter_context(source_transactions.execution(vm.application))
                    stack.enter_context(vm.application.safe_mode.execution())
                yield
        finally:
            vm._module_context_stack.pop()
            vm._context_stack.pop()
            vm._transaction_activation_allowed = previous_transactions
    # Server module variables are activation-local; client variables persist.
    state = {} if side == 'server' else session.interpreter.variables
    from .source.python_direct_source_forms import is_source_session,SourceFormBoundary
    boundary=SourceFormBoundary if is_source_session(session) else FormBoundary
    if (side == 'server' and boundary is FormBoundary
            and getattr(session, '_direct_form_nocontext', None) is not None):
        from .python_direct_form_nocontext import FormWithNoContext
        boundary = FormWithNoContext
    if side == 'server' and boundary is FormBoundary and session._catalog_server is not None:
        from .python_direct_form_catalog import PackageCatalogBoundary
        boundary = PackageCatalogBoundary
    if _export_routine is not None:
        return session._direct_handlers.invoke_export(handler, side, arguments,
                is_function=routine.is_function,state=state,
                context_factory=lambda: boundary(session,routine),execution_scope=scope)
    return session._direct_handlers.invoke(handler, side, arguments, state=state,
                context_factory=lambda: boundary(session,routine), execution_scope=scope)


def invoke_export(session,routine,arguments):
    """Execute an exact endpoint admitted by an RPC or standalone form binding."""
    return invoke_form(session,routine.name,'server',arguments,_export_routine=routine)
