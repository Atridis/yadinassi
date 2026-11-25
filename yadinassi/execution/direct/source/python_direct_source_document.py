"""Direct document-object bodies within the canonical object transaction lifecycle."""
from contextlib import contextmanager
from decimal import localcontext
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext,BoundaryViolation
from yadinassi.execution.codegen.direct_collections import _Cell
from yadinassi.execution.codegen.direct_live_state import _ForwardReference
from yadinassi.execution.codegen.direct_errors import convert_error
from yadinassi.execution.direct.python_direct_source import SourceBoundary,_compile,_nodes,_check_plan,_preflight,_signature
from yadinassi.syntax import ast
from yadinassi.types.values import HostFunction,Reference
from yadinassi.execution import safe_mode
from yadinassi.db import source_transactions, database_transactions
from uuid import UUID
from yadinassi.db.metadata.source_references import SourceReferenceManager
from yadinassi.db.document.source_document_runtime import SourceDocumentObject,_ObjectInterpreter,_ALIASES,_OBJECT_METHODS

_SEAL=object()
EXTERNALS=('ref','ссылка','thisobject','этотобъект',*_ALIASES,*_OBJECT_METHODS)


def _identity(vm,*,sealed=True):
    from yadinassi.configuration.configuration_source_runtime import SourceApplication,_SourceInterpreter,_DIRECT_SOURCE_ABI
    from yadinassi.db.document.source_document_runtime import _DIRECT_DOCUMENT_ABI
    if type(vm) is not _ObjectInterpreter:raise BoundaryViolation('document interpreter is not canonical')
    obj=vm.object
    if type(obj) is not SourceDocumentObject or type(obj.manager) is not SourceReferenceManager:
        raise BoundaryViolation('document object owner is not canonical')
    app=vm.application
    if type(app) is not SourceApplication or obj.manager._app() is not app or obj.interpreter is not vm:
        raise BoundaryViolation('document object binding changed')
    for cls,entries in ((_ObjectInterpreter,_DIRECT_DOCUMENT_ABI),(_SourceInterpreter,_DIRECT_SOURCE_ABI)):
        if any(name in vars(vm) or getattr(cls,name) is not expected for name,expected in entries):
            raise BoundaryViolation('document interpreter hooks changed')
    root=app.interpreter
    if (app.state not in ('starting','running') or obj._closed or vm._family_owner is not root
            or vm._scheduler is not root._scheduler or root._family_closed or vm._family_released
            or vm._family_generation!=root._family_generation or vm._scheduler.pending
            or vm._scheduler._active_task is not None or vm._logical_side!='server'
            or vm.compilation_profile!=app.compilation_profile
            or vm.database_context is not None or vm._configuration_runtime is not None):
        raise BoundaryViolation('document object lifecycle changed')
    if any(type(value) is not dict for value in (vm.variables,vm.functions,vm.types)):
        raise BoundaryViolation('document namespaces changed')
    from yadinassi.db.document.source_document_store import SourceDocumentStore
    from yadinassi.db.document.source_document_section_store import SourceDocumentSectionStore
    if (type(obj.manager.family) is not str or obj.manager.family!='Document'
            or type(obj.manager.name) is not str or type(obj.identity) is not UUID
            or type(app.constant_store) not in (SourceDocumentStore,SourceDocumentSectionStore)):
        raise BoundaryViolation('document object store or identity changed')
    if app.constant_store.document(obj.manager.name) is not obj.definition:
        raise BoundaryViolation('document object definition changed')
    fields=obj.fields;canonical=obj.definition.fields
    if (type(fields) is not dict or any(type(key) is not str for key in fields)
            or len(fields)!=len(canonical)
            or any(fields.get(field.name.casefold()) is not field for field in canonical)):
        raise BoundaryViolation('document object field mapping changed')
    from yadinassi.db.document.source_document_sections import SourceDocumentSection
    sections=obj.sections;definitions=obj.definition.sections
    if (type(sections) is not dict or any(type(key) is not str for key in sections)
            or len(sections)!=len(definitions)):
        raise BoundaryViolation('document section mapping changed')
    for definition in definitions:
        section=sections.get(definition.name.casefold())
        if (type(section) is not SourceDocumentSection or section.owner is not obj
                or section.definition is not definition or section.live is not True
                or type(section.fields) is not dict or any(type(key) is not str for key in section.fields)
                or len(section.fields)!=len(definition.fields)
                or any(section.fields.get(field.name.casefold()) is not field for field in definition.fields)):
            raise BoundaryViolation('document section owner or definition changed')
    if sealed:
        seal=getattr(vm,'_direct_document_seal',None)
        if (type(seal) is not tuple or len(seal)!=9 or seal[0] is not _SEAL
                or seal[1] is not obj or seal[2] is not obj.manager or seal[3] is not app
                or seal[4] is not app.constant_store or seal[5] is not obj.definition
                or seal[6] is not obj.identity or seal[7]!=obj.manager.name
                or seal[8] is not obj.fields):
            raise BoundaryViolation('document object lacks current direct admission')
    return app,obj


def check_object(obj,caller):
    if type(obj) is not SourceDocumentObject or type(obj.interpreter) is not _ObjectInterpreter:
        raise BoundaryViolation('document object is not direct-owned')
    app,_=_identity(obj.interpreter)
    if (getattr(caller,'application',None) is not app or caller._family_owner is not app.interpreter
            or caller._scheduler is not app.interpreter._scheduler or caller._family_released
            or caller._family_generation!=app.interpreter._family_generation
            or caller.execution_context!='server' or caller._scheduler._active_task is not None
            or (not obj._ready and caller is not obj.interpreter)):
        raise BoundaryViolation('document object caller is not active owner')
    return obj.interpreter


def _scope(vm):
    app,_=_identity(vm)
    if (source_transactions._current.get() is not app or safe_mode._CURRENT.get() is not app.safe_mode
            or database_transactions._execution.get() is not None or not vm._has_module_context
            or vm.execution_context!='server' or vm.locals is not None):
        raise BoundaryViolation('document object execution scope changed')


class SourceDocumentBoundary(SourceBoundary):
    def _check(self):
        BoundaryContext._check(self);_scope(self.vm);_check_plan(self.vm,self.plan)
        from yadinassi.execution.direct.python_direct import _admit_bindings
        _admit_bindings(self.vm,frozenset(),self.plan._source_constructors,frozenset())
        if (not self._active or self.vm.variables is not self.storage or self.vm.functions is not self._services
                or self.vm.types is not self.types or self.vm._family_generation!=self.generation
                or frozenset(self.vm.module_names)!=self.layout):
            raise BoundaryViolation('document object activation changed')

    def external_get(self,name):
        self._check()
        if name in ('thisobject','этотобъект'):return self.vm.object
        if name in _OBJECT_METHODS or self.vm.field(name):return self.vm.object.property_read(self.vm,name)
        return super().external_get(name)

    def external_set(self,name,value):
        self._check()
        if name in ('thisobject','этотобъект'):raise ValueError('ThisObject is read-only')
        if self.vm.field(name):return self.vm.object.property_write(self.vm,name,value)
        return super().external_set(name,value)

    def external_reference(self,name):
        if not self.vm.field(name):return super().external_reference(name)
        self.external_get(name)
        ref=Reference(lambda:self.external_get(name),lambda value:self.external_set(name,value))
        ref._direct_name_sink=True
        return _ForwardReference(ref)

    def resolve_service(self,name,*args,**contract):
        if name.casefold() in _OBJECT_METHODS:
            self._check()
            from .python_direct_source_storage import captured
            return captured(self,self.vm.object.get_member(name),
                require_value=contract.get('require_value',False),allow_references=contract.get('allow_references',False),
                argument_count=contract.get('argument_count'))
        key=name.casefold()
        for field_name,factory,function in self.vm._direct_document_field_services:
            if key==field_name:
                self._check()
                if self.vm.functions.get(key) is not factory or factory.function is not function:
                    raise BoundaryViolation('document field service binding changed')
                bound=super().resolve_service(name,*args,**contract)
                def invoke(*values):
                    self._check()
                    if self.vm.functions.get(key) is not factory or factory.function is not function:
                        raise BoundaryViolation('document field service binding changed')
                    return bound(*values)
                for attribute in ('requires_reference','prepare_omissions','prepare_named_value'):
                    if hasattr(bound,attribute):setattr(invoke,attribute,getattr(bound,attribute))
                return invoke
        return super().resolve_service(name,*args,**contract)

    def _routine(self,owner,routine,**contract):
        if owner is self.vm:return _bind(self,owner,routine,**contract)
        return super()._routine(owner,routine,**contract)


def _run(vm,plan,callback=None):
    from yadinassi.execution.codegen.native_targets import target_context
    _scope(vm)
    boundary=SourceDocumentBoundary(vm,plan)
    previous=getattr(vm,'_direct_source_active',0);vm._direct_source_active=previous+1
    try:
        with target_context(vm.native_target),localcontext() as decimal:
            decimal.prec=38;boundary.enter()
            try:
                try:
                    result=plan.function(vm.variables,plan.constants,boundary)
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
    app,obj=_identity(vm,sealed=False)
    if hasattr(vm,'_direct_document_seal') or getattr(vm,'_direct_source_active',0):
        raise BoundaryViolation('document object cannot be redeclared')
    if type(program) is not list:raise TypeError('document program requires canonical AST')
    declarations=[node for node in program if type(node) in (ast.Routine,ast.Var)]
    if any(type(node) in (ast.Import,ast.Execute) for node in _nodes(program)):
        raise ValueError('direct document imports/Execute not integrated')
    for node in declarations:
        if type(node) is ast.Routine and (node.execution_context!='server' or node.is_async or node.is_dual or not node.module_context):
            raise ValueError('direct document routine side or context is unsupported')
    declared={name.casefold() for node in declarations if type(node) is ast.Var for name in node.names}
    layout=set(vm.module_names)|declared
    externals=(*EXTERNALS,*obj.fields,*obj.sections)
    callable_names=tuple(dict.fromkeys((*_OBJECT_METHODS,*(name for name in externals if vm.field(name) and name in vm.functions))))
    declaration_plan=_compile(vm,declarations,exports=True,layout=layout,_extra_externals=externals,_callable_externals=callable_names) if declarations else None
    statements=[node for node in program if type(node) not in (ast.Routine,ast.Var)]
    statement_plan=_compile(vm,statements,layout=layout,_extra_externals=externals,_callable_externals=callable_names)
    if any(type(vm.functions[name]) is not HostFunction for name in callable_names if name not in _OBJECT_METHODS):
        raise BoundaryViolation('document field service is not canonical')
    vm._direct_document_field_services=tuple((name,vm.functions[name],vm.functions[name].function) for name in callable_names if name not in _OBJECT_METHODS)
    vm.module_names.update(declared);vm._direct_source_plans={}
    for node in declarations:
        if type(node) is ast.Routine:
            vm.server_routines[node.name.casefold()]=node
            vm._direct_source_plans[node.name.casefold()]=(node,declaration_plan)
        else:
            for name in node.names:vm.variables.setdefault(name.casefold(),None)
            vm.exported_variables.update(name.casefold() for name in node.exported_names)
    vm._direct_document_seal=(_SEAL,obj,obj.manager,app,app.constant_store,obj.definition,obj.identity,obj.manager.name,obj.fields)
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
        raise ValueError('unsupported direct document event signature')
    cancel=_Cell(False);_invoke(vm,routine,(cancel,));return cancel.value


def _bind(boundary,vm,routine,*,require_value=False,allow_references=False,argument_count=None,**unused):
    obj=vm.object
    def validate():
        boundary._check();check_object(obj,boundary.vm);_preflight(vm,routine)
        if routine.execution_context!='server' or routine.is_async or routine.is_dual or not routine.module_context:
            raise BoundaryViolation('document routine context changed')
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
        from yadinassi.execution.codegen.direct_collections import _OMITTED_REF
        return current,{i:_OMITTED_REF for i in positions}
    bound.prepare_omissions=omissions
    return bound


def bind_export(boundary,obj,name,**contract):
    vm=check_object(obj,boundary.vm)
    routine=obj.exported_routine(boundary.vm,name)
    return _bind(boundary,vm,routine,**contract)
