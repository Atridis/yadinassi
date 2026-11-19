"""Scalar source-form NoContext execution without form capabilities or VM dispatch."""
from contextlib import contextmanager
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct_services import ServicesBoundary, CONSTRUCTORS
from yadinassi.execution.direct.python_direct_handlers import prepare_handlers
from yadinassi.execution.direct.python_direct_source import _signature, _signature_matches, _source_text, _external_names, SourceBoundary
from yadinassi.execution.direct.python_direct import _snapshot, REPAIRS
from yadinassi.syntax import ast
from yadinassi.types.values import HostFunction
from yadinassi.db import source_transactions, database_transactions
from yadinassi.execution import safe_mode


_SCALAR_SERVICES=frozenset(('message','сообщить','string','строка','number','число',
    'boolean','булево','type','тип','typeof','типзнч','valueisfilled','значениезаполнено',
    'int','цел','round','окр','min','мин','max','макс','strlen','стрдлина',
    'upper','врег','lower','нрег','trimall','сокрлп','safemode','безопасныйрежим',
    'setsafemode','установитьбезопасныйрежим'))

def _check(server, *, preparing=False):
    from yadinassi.forms.source_forms import _SourceNoContextServer, _SourceNoContextInterpreter, _DIRECT_SOURCE_NOCONTEXT_ABI
    from yadinassi.configuration.configuration_source_runtime import SourceApplication
    if type(server) is not _SourceNoContextServer or type(server.prototype) is not _SourceNoContextInterpreter:
        raise BoundaryViolation('source NoContext executor changed')
    vm=server.prototype; app=server.application
    if (type(app) is not SourceApplication or vm.application is not app or app.state!='running'
            or vm._family_owner is not app.interpreter or vm._scheduler is not app.interpreter._scheduler
            or vm._family_released or app.interpreter._family_closed
            or vm._family_generation!=app.interpreter._family_generation
            or vm.database_context is not None or vm._configuration_runtime is not None
            or vm.execution_backend!='python-direct' or app.constant_store is not None):
        raise BoundaryViolation('source NoContext owner is inactive')
    for cls,name,expected in _DIRECT_SOURCE_NOCONTEXT_ABI:
        instance=server if cls is _SourceNoContextServer else vm
        if getattr(cls,name) is not expected or name in vars(instance):
            raise BoundaryViolation('source NoContext hooks changed')
    prepared, routines, signatures, bindings=server._direct_nocontext
    if vm.server_routines is not routines:
        raise BoundaryViolation('source NoContext registry changed')
    for routine, signature in signatures:
        if not _signature_matches(routine,signature) or routines.get(signature[0].casefold()) is not routine:
            raise BoundaryViolation('source NoContext declaration changed')
    for current,(original,entries) in zip((vm.functions,vm.types),bindings):
        if current is not original or len(current)!=len(entries):
            raise BoundaryViolation('source NoContext host registry changed')
        for name,wrapper,function,spelling,references,returns_value in entries:
            if (current.get(name) is not wrapper or wrapper.function is not function
                    or wrapper.name is not spelling or wrapper.reference_parameters is not references
                    or wrapper.returns_value is not returns_value):
                raise BoundaryViolation('source NoContext host binding changed')
    if not preparing:
        from yadinassi.forms.source_forms import _DIRECT_SOURCE_NOCONTEXT_TRANSPORT_ABI
        from yadinassi.execution.invocation import InvocationServer, InvocationPort
        transport,callbacks,callback_items,routines,routine_items,message_scope,gate=server._direct_transport
        if (type(transport) is not InvocationServer or server.server is not transport
                or transport._callbacks is not callbacks or transport._routines is not routines
                or len(callbacks)!=len(callback_items) or len(routines)!=len(routine_items)
                or any(callbacks.get(key) is not value for key,value in callback_items)
                or any(routines.get(key) is not value for key,value in routine_items)
                or transport._message_scope is not message_scope or transport._gate is not gate):
            raise BoundaryViolation('source NoContext transport changed')
        for cls,name,expected in _DIRECT_SOURCE_NOCONTEXT_TRANSPORT_ABI:
            if getattr(cls,name) is not expected:
                raise BoundaryViolation('source NoContext transport hooks changed')
        if any(name in vars(transport) for name in ('exchange','_reply','_message')):
            raise BoundaryViolation('source NoContext transport override')
        port_binding=getattr(server,'_direct_port',None)
        if hasattr(server,'_direct_source_sessions') and port_binding is None:
            raise BoundaryViolation('source NoContext installed port seal missing')
        if port_binding is not None:
            port,exchange,port_gate=port_binding
            if type(port) is not InvocationPort or port._exchange is not exchange or port._gate is not port_gate or 'invoke' in vars(port):
                raise BoundaryViolation('source NoContext port changed')
    return prepared


def prepare(server, nodes):
    if type(nodes) is not list or not nodes:
        raise ValueError('source NoContext requires declarations')
    for routine in nodes:
        _signature(routine)
        if (routine.execution_context!='server' or routine.module_context or routine.is_async or routine.is_dual
                or any(not p.by_value or p.default is not None for p in routine.parameters)):
            raise ValueError('source NoContext requires synchronous all-Val routines without defaults')
    vm=server.prototype
    view=_snapshot(nodes)
    for routine in view: routine.module_context=True
    # Form constructors are recognized only to produce an invocation-time denial.
    from yadinassi.execution.direct.python_direct_forms import DECLARATION_CONSTRUCTORS, SYSTEM_NAMES
    compiled=prepare_handlers(view,source_text=_source_text(nodes),
        external_names=tuple(dict.fromkeys((*_external_names(vm),*SYSTEM_NAMES))),
        constructors=tuple(CONSTRUCTORS)+DECLARATION_CONSTRUCTORS,
        repairs=REPAIRS+('authority_checkpoints',),_source_routine_scopes=True)
    vm.server_routines={r.name.casefold():r for r in nodes}
    server._direct_nocontext=(compiled,vm.server_routines,tuple((r,_signature(r)) for r in nodes),vm._direct_source_host_bindings)
    _check(server,preparing=True)


class NoContextBoundary(ServicesBoundary,BoundaryContext):
    def __init__(self,server):
        self.server=server; self.vm=server.prototype;self.app=server.application
        super().__init__(services=self.vm.functions)
        self._services=self.vm.functions
        self._active=True;self._seal=server._direct_nocontext
        self._budget=self.vm._source_call_budget
    def _check(self):
        BoundaryContext._check(self);_check(self.server)
        if (not self._active or self.server.prototype is not self.vm
                or self.server.application is not self.app or self.vm.application is not self.app
                or self._services is not self.vm.functions
                or self.server._direct_nocontext is not self._seal or self.vm.execution_context!='server' or self.vm._has_module_context
                or source_transactions._current.get() is not self.app
                or safe_mode._CURRENT.get() is not self.app.safe_mode
                or self.vm._transaction_activation_allowed is not False
                or self.vm._scheduler.pending or self.vm._scheduler._active_task is not None):
            raise BoundaryViolation('source NoContext invocation scope changed')
        budget=self.vm._source_call_budget
        if (budget is not self._budget or type(budget) is not list or len(budget)!=1
                or type(budget[0]) is not int or budget[0]<0):
            raise BoundaryViolation('source NoContext budget changed')
    def checkpoint(self):
        self._check();self.vm._source_call_budget[0]+=1
        if self.vm._source_call_budget[0]>100000:
            from yadinassi.forms.form_runtime import FormLimitError
            raise FormLimitError('Source NoContext execution limit')
    @contextmanager
    def routine_scope(self):
        self.checkpoint()
        with self.app.safe_mode.routine(self.vm,self.vm):
            try:yield
            finally:self._check()
    def leave(self):self._active=False
    def external_get(self,name):
        self._check()
        if name in ('metadata','метаданные'):return self.app.metadata
        raise ValueError('source NoContext namespace is unavailable: '+name)
    def resolve_service(self,name,*args,**kwargs):
        self._check()
        if name.casefold() not in _SCALAR_SERVICES:
            raise ValueError('source NoContext service is unavailable: '+name)
        # No source markers, transactions, managers, form services or callbacks.
        function=self._services.get(name.casefold())
        if function is None:raise ValueError('source NoContext service is unavailable: '+name)
        return super().resolve_service(name,*args,**kwargs)
    def get_member(self,value,name):
        self._check()
        if not SourceBoundary._metadata(self,value):raise ValueError('source NoContext receiver unavailable')
        try:return value.get_member(name)
        finally:self._check()
    def resolve_source_member(self,value,name,*,require_value=False,argument_count=None,allow_references=False):
        self._check()
        if not SourceBoundary._metadata(self,value):raise ValueError('source NoContext receiver unavailable')
        function=value.get_method(name)
        return self.resolve_callable(function if type(function) is HostFunction else HostFunction(name,function),
            require_value=require_value,allow_references=allow_references)


def invoke(server,routine,values,*,output=None):
    from yadinassi.execution.invocation import _encode_scalar
    from yadinassi.execution.codegen.native_targets import target_context
    from yadinassi.execution.execution_policy import execution_backend_policy
    from decimal import localcontext
    prepared=_check(server);vm=server.prototype
    seal=server._direct_nocontext
    if (vm.server_routines.get(routine.name.casefold()) is not routine
            or len(values)!=len(routine.parameters) or getattr(server,'_direct_busy',False)):
        raise BoundaryViolation('source NoContext invocation changed or busy')
    for value in values:_encode_scalar(value)
    previous_output=vm.output
    vm.output=server._message if output is None else output
    vm._source_call_budget=[0];server._direct_busy=True
    vm._context_stack.append('server');vm._module_context_stack.append(False)
    try:
        with source_transactions.execution(server.application),server.application.safe_mode.execution(),database_transactions.admission(False),target_context(vm.native_target),execution_backend_policy('python-direct'),localcontext() as decimal:
            decimal.prec=38
            result=prepared.invoke_export(routine.name,'server',values,is_function=routine.is_function,
                state={},context_factory=lambda:NoContextBoundary(server))
            if server.prototype is not vm or server._direct_nocontext is not seal:
                raise BoundaryViolation('source NoContext execution inventory changed')
            _encode_scalar(result)
            return result
    finally:
        vm._module_context_stack.pop();vm._context_stack.pop()
        vm.output=previous_output;server._direct_busy=False


def resolve(boundary,name,*,require_value=False,argument_count=None,allow_references=False):
    server=getattr(boundary.session,'_direct_source_nocontext_server',None)
    if server is None:return None
    _check(server)
    sessions=getattr(server,'_direct_source_sessions',None)
    if type(sessions) is not tuple or not any(session is boundary.session for session in sessions):
        raise BoundaryViolation('source NoContext executor belongs to another form')
    key=name.casefold();routine=server.prototype.server_routines.get(key)
    if routine is None:return None
    def check():
        boundary._check();_check(server)
        if (getattr(server,'_direct_source_sessions',None) is not sessions
                or getattr(boundary.session,'_direct_source_nocontext_server',None) is not server
                or boundary.app is not server.application
                or server.prototype.server_routines.get(key) is not routine):
            raise BoundaryViolation('source NoContext form binding changed')
        if require_value and not routine.is_function:raise TypeError('Procedure has no result')
        if argument_count is not None and argument_count!=len(routine.parameters):raise TypeError('NoContext argument count')
    check()
    if boundary.side=='client':
        safe_mode.require_transfer('source NoContext call')
        database_transactions.forbid_transfer(boundary.vm._transaction_backend())
    binding=None
    if boundary.side=='client':
        binding=boundary.vm._invocation_bindings.get(key)
        installed=dict(server._direct_client_bindings).get(key)
        if binding is None or binding is not installed:
            raise BoundaryViolation('source NoContext installed port binding changed')
        stub,port_call=binding
        stub_signature=_signature(stub)
        if (stub.module_context or stub.execution_context!='server' or stub.is_function is not routine.is_function
                or len(stub.parameters)!=len(routine.parameters)
                or any(not p.by_value or p.default is not None for p in stub.parameters)):
            raise BoundaryViolation('source NoContext port signature changed')
    def call(*values):
        check()
        try:
            if binding is not None:
                if (boundary.vm._invocation_bindings.get(key) is not binding
                        or boundary.vm.server_routines.get(key) is not stub
                        or not _signature_matches(stub,stub_signature)):
                    raise BoundaryViolation('source NoContext port binding changed')
                safe_mode.require_transfer('source NoContext call')
                database_transactions.forbid_transfer(boundary.vm._transaction_backend())
                return port_call(list(values))
            return invoke(server,routine,list(values),output=boundary.vm.output)
        finally:boundary._check()
    if allow_references:call.requires_reference=lambda index:False
    return call
