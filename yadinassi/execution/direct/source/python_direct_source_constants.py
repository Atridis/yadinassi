"""Direct constant-manager bodies within the canonical manager transaction lifecycle."""
from contextlib import contextmanager
from decimal import localcontext
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Cell
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
from yadinassi.execution.codegen.experimental_naked_errors import convert_error
from yadinassi.execution.direct.python_direct_source import SourceBoundary,_compile,_nodes,_check_plan,_preflight,_signature
from yadinassi.syntax import ast
from yadinassi.types.values import HostFunction,Reference
from yadinassi.execution import safe_mode
from yadinassi.db import source_transactions, database_transactions
from yadinassi.db.metadata.source_constants_runtime import SourceConstants
from yadinassi.db.metadata.source_constant_managers import SourceConstantValueManager,_ValueInterpreter

_SEAL=object()
EXTERNALS=('value','значение','thisobject','этотобъект')


def _identity(vm,*,sealed=True):
    from yadinassi.configuration.configuration_source_runtime import SourceApplication,_SourceInterpreter,_DIRECT_SOURCE_ABI
    from yadinassi.db.metadata.source_constant_managers import _DIRECT_CONSTANT_ABI
    if type(vm) is not _ValueInterpreter:raise BoundaryViolation('constant interpreter is not canonical')
    manager=vm.manager
    if type(manager) is not SourceConstantValueManager or type(manager.owner) is not SourceConstants:
        raise BoundaryViolation('constant manager owner is not canonical')
    app=vm.application
    if type(app) is not SourceApplication or manager.owner._application() is not app or manager.interpreter is not vm:
        raise BoundaryViolation('constant manager binding changed')
    for cls,entries in ((_ValueInterpreter,_DIRECT_CONSTANT_ABI),(_SourceInterpreter,_DIRECT_SOURCE_ABI)):
        if any(name in vars(vm) or getattr(cls,name) is not expected for name,expected in entries):
            raise BoundaryViolation('constant interpreter hooks changed')
    root=app.interpreter
    if (app.state not in ('starting','running') or manager._closed or vm._family_owner is not root
            or vm._scheduler is not root._scheduler or root._family_closed or vm._family_released
            or vm._family_generation!=root._family_generation or vm._scheduler.pending
            or vm._scheduler._active_task is not None or vm._logical_side!='server'
            or vm.execution_backend!='python-direct' or vm.compilation_profile!=app.compilation_profile
            or vm.database_context is not None or vm._configuration_runtime is not None):
        raise BoundaryViolation('constant manager lifecycle changed')
    if any(type(value) is not dict for value in (vm.variables,vm.functions,vm.types)):
        raise BoundaryViolation('constant namespaces changed')
    if sealed:
        seal=getattr(vm,'_direct_constant_seal',None)
        if (type(seal) is not tuple or len(seal)!=6 or seal[0] is not _SEAL
                or seal[1] is not manager or seal[2] is not manager.owner or seal[3] is not app
                or seal[4] is not app.constant_store or seal[5]!=manager.name):
            raise BoundaryViolation('constant manager lacks current direct admission')
    return app,manager


def check_manager(manager,caller):
    if type(manager) is not SourceConstantValueManager or type(manager.interpreter) is not _ValueInterpreter:
        raise BoundaryViolation('constant manager is not direct-owned')
    app,_=_identity(manager.interpreter)
    if (getattr(caller,'application',None) is not app or caller._family_owner is not app.interpreter
            or caller._scheduler is not app.interpreter._scheduler or caller._family_released
            or caller._family_generation!=app.interpreter._family_generation
            or caller.execution_context!='server' or caller._scheduler._active_task is not None
            or (not manager._ready and caller is not manager.interpreter)):
        raise BoundaryViolation('constant manager caller is not active owner')
    return manager.interpreter


def _scope(vm):
    app,_=_identity(vm)
    if (source_transactions._current.get() is not app or safe_mode._CURRENT.get() is not app.safe_mode
            or database_transactions._execution.get() is not None or not vm._has_module_context
            or vm.execution_context!='server' or vm.locals is not None):
        raise BoundaryViolation('constant manager execution scope changed')


class SourceConstantBoundary(SourceBoundary):
    def _check(self):
        BoundaryContext._check(self);_scope(self.vm);_check_plan(self.vm,self.plan)
        from yadinassi.execution.direct.python_direct import _admit_bindings
        _admit_bindings(self.vm,frozenset(),self.plan._source_constructors,frozenset())
        if (not self._active or self.vm.variables is not self.storage or self.vm.functions is not self._services
                or self.vm.types is not self.types or self.vm._family_generation!=self.generation
                or frozenset(self.vm.module_names)!=self.layout):
            raise BoundaryViolation('constant manager activation changed')

    def external_get(self,name):
        self._check()
        if name in ('value','значение'):return self.vm.manager.value_read(self.vm)
        if name in ('thisobject','этотобъект'):return self.vm.manager
        return super().external_get(name)

    def external_set(self,name,value):
        self._check()
        if name in ('value','значение'):return self.vm.manager.value_write(self.vm,value)
        if name in ('thisobject','этотобъект'):raise ValueError('ThisObject is read-only')
        return super().external_set(name,value)

    def external_reference(self,name):
        if name not in ('value','значение'):return super().external_reference(name)
        self.external_get(name)
        ref=Reference(lambda:self.external_get(name),lambda value:self.external_set(name,value))
        ref._direct_name_sink=True
        return _ForwardReference(ref)

    def _routine(self,owner,routine,**contract):
        if owner is self.vm:return _bind(self,owner,routine,**contract)
        return super()._routine(owner,routine,**contract)


def _run(vm,plan,callback=None):
    from yadinassi.execution.codegen.native_targets import target_context
    from yadinassi.execution.execution_policy import execution_backend_policy
    _scope(vm)
    boundary=SourceConstantBoundary(vm,plan)
    previous=getattr(vm,'_direct_source_active',0);vm._direct_source_active=previous+1
    try:
        with target_context(vm.native_target),execution_backend_policy('python-direct'),localcontext() as decimal:
            decimal.prec=38;boundary.enter()
            try:
                try:
                    result=plan.function(vm.variables,plan.constants,[],boundary)
                    return result if callback is None else callback(result)
                finally:boundary._check()
            except Exception as error:
                converted=convert_error(error,plan.source_name,plan.source_text)
                if converted is error:raise
                raise converted from None
    finally:boundary.leave();vm._direct_source_active=previous


@contextmanager
def _server_scope(vm):
    vm._context_stack.append('server');vm._module_context_stack.append(True)
    try:yield
    finally:vm._module_context_stack.pop();vm._context_stack.pop()


def prepare_and_execute(vm,program):
    app,manager=_identity(vm,sealed=False)
    if hasattr(vm,'_direct_constant_seal') or getattr(vm,'_direct_source_active',0):
        raise BoundaryViolation('constant manager cannot be redeclared')
    if type(program) is not list:raise TypeError('constant program requires canonical AST')
    declarations=[node for node in program if type(node) in (ast.Routine,ast.Var)]
    if any(type(node) in (ast.Import,ast.Execute) for node in _nodes(program)):
        raise ValueError('direct constant imports/Execute not integrated')
    for node in declarations:
        if type(node) is ast.Routine and (node.execution_context!='server' or node.is_async or node.is_dual or not node.module_context):
            raise ValueError('direct constant routine side or context is unsupported')
    declared={name.casefold() for node in declarations if type(node) is ast.Var for name in node.names}
    layout=set(vm.module_names)|declared
    declaration_plan=_compile(vm,declarations,exports=True,layout=layout,_extra_externals=EXTERNALS) if declarations else None
    statements=[node for node in program if type(node) not in (ast.Routine,ast.Var)]
    statement_plan=_compile(vm,statements,layout=layout,_extra_externals=EXTERNALS)
    vm.module_names.update(declared);vm._direct_source_plans={}
    for node in declarations:
        if type(node) is ast.Routine:
            vm.server_routines[node.name.casefold()]=node
            vm._direct_source_plans[node.name.casefold()]=(node,declaration_plan)
        else:
            for name in node.names:vm.variables.setdefault(name.casefold(),None)
            vm.exported_variables.update(name.casefold() for name in node.exported_names)
    vm._direct_constant_seal=(_SEAL,manager,manager.owner,app,app.constant_store,manager.name)
    if not statements:return None
    with _server_scope(vm):return _run(vm,statement_plan)


def _invoke(vm,routine,values):
    _identity(vm);plan=_preflight(vm,routine)
    with _server_scope(vm):return _run(vm,plan,lambda exports:exports[routine.name.casefold()](*values))


def invoke_event(vm,routine):
    _signature(routine)
    if (routine.is_function or routine.execution_context!='server' or routine.is_async or routine.is_dual
            or not routine.module_context or len(routine.parameters)!=1 or routine.parameters[0].by_value
            or routine.parameters[0].default is not None):
        raise ValueError('unsupported direct constant event signature')
    cancel=_Cell(False);_invoke(vm,routine,(cancel,));return cancel.value


def _bind(boundary,vm,routine,*,require_value=False,allow_references=False,argument_count=None,**unused):
    manager=vm.manager
    def validate():
        boundary._check();check_manager(manager,boundary.vm);_preflight(vm,routine)
        if routine.execution_context!='server' or routine.is_async or routine.is_dual or not routine.module_context:
            raise BoundaryViolation('constant routine context changed')
    validate()
    minimum=max((i+1 for i,p in enumerate(routine.parameters) if p.default is None),default=0)
    if argument_count is not None and not minimum<=argument_count<=len(routine.parameters):
        raise TypeError('Неверное количество аргументов: '+routine.name)
    refs=frozenset(i for i,p in enumerate(routine.parameters) if not p.by_value)
    def call(*values):
        validate()
        forwarded=tuple(_ForwardReference(value) if i in refs and type(value) is Reference else value for i,value in enumerate(values))
        try:return _invoke(vm,routine,forwarded)
        finally:boundary._check()
    bound=boundary.resolve_callable(HostFunction(routine.name,call,returns_value=routine.is_function,reference_parameters=refs),
        require_value=require_value,allow_references=allow_references)
    def omissions(current,positions,count):
        validate()
        if count>len(routine.parameters) or any(i>=len(routine.parameters) or routine.parameters[i].default is None for i in positions):
            raise TypeError('Неверное количество аргументов: '+routine.name)
        from yadinassi.execution.codegen.experimental_naked_collections import _OMITTED_REF
        return current,{i:_OMITTED_REF for i in positions}
    bound.prepare_omissions=omissions
    return bound


def bind_export(boundary,manager,name,**contract):
    vm=check_manager(manager,boundary.vm)
    routine=manager.exported_routine(boundary.vm,name)
    return _bind(boundary,vm,routine,**contract)
