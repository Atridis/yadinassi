"""Owned synchronous source startup, without admitting arbitrary VM subclasses.

SourceApplication still owns compilation selection, module access, safe mode,
transactions and closure. Unsupported crossings/receivers fail before effects.
"""
from contextlib import contextmanager
from decimal import localcontext
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation, _MISSING
from .experimental_naked_collections import prepare, _Cell
from .experimental_naked_live_state import _ForwardReference
from .experimental_naked_errors import convert_error
from .python_direct import REPAIRS, _snapshot, _nodes
from .python_direct_services import ServicesBoundary, CONSTRUCTORS
from .syntax import ast
from .values import HostFunction, Reference
from . import safe_mode, source_transactions, database_transactions
from . import python_direct_source_storage as storage
from . import python_direct_source_query as query


def check_owner(owner):
    from .configuration_source_runtime import SourceApplication, _SourceInterpreter, _DIRECT_SOURCE_ABI
    if type(owner) is not _SourceInterpreter:
        raise BoundaryViolation('direct source object/form interpreter is not integrated')
    app=owner.application
    if type(app) is not SourceApplication:
        raise BoundaryViolation('direct source application is not integrated')
    if any(name in vars(owner) or getattr(_SourceInterpreter,name) is not expected for name,expected in _DIRECT_SOURCE_ABI):
        raise BoundaryViolation("custom source-host hooks are not integrated")
    root=app.interpreter
    if (app.state not in ('starting','running') or owner._family_owner is not root
            or owner._scheduler is not root._scheduler or root._family_closed
            or owner._family_released or owner._family_generation!=root._family_generation
            or owner._scheduler.pending or owner._scheduler._active_task is not None):
        raise BoundaryViolation('direct source owner is no longer active')
    if (source_transactions._current.get() is not app or safe_mode._CURRENT.get() is not app.safe_mode
            or database_transactions._execution.get() is not None or owner.database_context is not None
            or owner._configuration_runtime is not None or not owner._has_module_context
            or owner.locals is not None or owner.execution_backend!='python-direct'
            or owner.compilation_profile!=app.compilation_profile):
        raise BoundaryViolation('direct source execution scope changed')
    if type(owner.variables) is not dict or type(owner.functions) is not dict or type(owner.types) is not dict:
        raise BoundaryViolation('direct source requires canonical namespace mappings')
    return app


def _manager_key(key):
    # Common modules may themselves be named "Manager". Their third key
    # element is Boolean; a metadata manager key carries its String name.
    return (type(key) is tuple and len(key)==3 and key[0]=='manager'
            and type(key[1]) is str and type(key[2]) is str)


def _external_names(owner,declared=()):
    from .python_direct_names import NAMES
    app=owner.application
    from .source_manager_modules import MANAGER_NAMES
    names=set(NAMES)|set(app.modules)|set(MANAGER_NAMES)|{
        'metadata','метаданные','xdtofactory','фабрикаxdto','constants','константы',
        'sessionparameters','параметрысеанса','enums','перечисления',
        'configurationextensions','расширенияконфигурации',
        'configurationextensionssource','источникрасширенийконфигурации'}
    names.update(app.interpreter.exported_variables)
    return tuple(names-set(declared)-set(owner.module_names))


def _source_text(program):
    nodes=tuple(_nodes(program))
    lines={n.token.line:n.token.source_line for n in nodes if n.token is not None}
    return '\n'.join(lines.get(i,'') for i in range(1,max(lines,default=0)+1))


def _signature(node):
    if type(node) is not ast.Routine or type(node.parameters) is not list:
        raise BoundaryViolation('source routine signature is not canonical')
    if (type(node.name) is not str or type(node.execution_context) is not str
            or any(type(v) is not bool for v in (node.is_function,node.is_async,node.is_dual,node.module_context,node.exported))
            or any(type(p) is not ast.Parameter or type(p.name) is not str or type(p.by_value) is not bool for p in node.parameters)):
        raise BoundaryViolation('source routine parameters are not canonical')
    return (node.name,node.execution_context,node.is_function,node.is_async,node.is_dual,
        node.module_context,node.exported,tuple((p.name,p.by_value,p.default is None) for p in node.parameters))


def _check_plan(owner,plan):
    if frozenset(owner.module_names)!=plan._source_layout:
        raise BoundaryViolation("source module layout changed; redeclare")
    for node,signature in plan._source_routines:
        registry=owner.server_routines if signature[1]=='server' else owner.routines
        if registry.get(signature[0].casefold()) is not node or _signature(node)!=signature:
            raise BoundaryViolation('source declaration binding changed')


def _compile(owner,program,*,exports=False,layout=()):
    names={n.name.casefold() for n in program if type(n) is ast.Routine}
    names.update(name.casefold() for n in program if type(n) is ast.Var for name in n.names)
    plan=prepare(_source_text(program),source_name=program[0].token.source if program else '<source>',
        parsed_ast=_snapshot(program),repairs=REPAIRS+('authority_checkpoints',),
        module_names=tuple(layout),external_names=_external_names(owner,names|set(layout)),
        constructors=tuple(CONSTRUCTORS)+query.CONSTRUCTOR_NAMES+('uuid','уникальныйидентификатор'),
        _trusted_entry=True,_export_routines=exports,_initialize_module=not exports,
        _return_last_expression=not exports,_source_routine_scopes=True)
    native={'array','массив','structure','структура','map','соответствие','uuid','уникальныйидентификатор'}
    plan._source_layout=frozenset(layout)
    plan._source_routines=tuple((n,_signature(n)) for n in program if type(n) is ast.Routine)
    plan._source_constructors=frozenset(n.name.casefold() for n in _nodes(program)
        if type(n) is ast.New and n.name.casefold() in native)
    from .python_direct import _admit_bindings
    _admit_bindings(owner,frozenset(),plan._source_constructors,frozenset())
    return plan


class SourceBoundary(ServicesBoundary,BoundaryContext):
    def __init__(self,owner,plan):
        super().__init__(services=owner.functions)
        self.vm=owner;self.app=owner.application;self._services=owner.functions
        self.plan=plan
        self.side=owner.execution_context;self.generation=owner._family_generation
        self.logical_side=owner._logical_side;self.layout=frozenset(owner.module_names)
        self.storage=owner.variables;self.types=owner.types
        self._active=True
        self._instance_keys=tuple(k for k,v in self.app._instances.items() if v is owner)
    def _check(self):
        super()._check();check_owner(self.vm);_check_plan(self.vm,self.plan)
        from .python_direct import _admit_bindings
        _admit_bindings(self.vm,frozenset(),self.plan._source_constructors,frozenset())
        if (not self._active or self.vm.execution_context!=self.side or self.vm._family_generation!=self.generation
                or self.vm._logical_side!=self.logical_side or frozenset(self.vm.module_names)!=self.layout
                or self.vm.variables is not self.storage or self.vm.functions is not self._services
                or self.vm.types is not self.types):
            raise BoundaryViolation('direct source activation changed or ended')
        if any(self.app._instances.get(k) is not self.vm for k in self._instance_keys):
            raise BoundaryViolation('direct source module instance changed')
    def _guard_references(self,bound):
        def invoke(*values):
            guarded=[]
            for value in values:
                if type(value) is _ForwardReference:value=value.reference
                if type(value) is Reference:
                    def get(ref=value):
                        self._check()
                        try:return ref.get()
                        finally:self._check()
                    def put(new_value,ref=value):
                        self._check()
                        try:ref.set(new_value)
                        finally:self._check()
                    wrapped=Reference(get,put)
                    wrapped._direct_name_sink=getattr(value,'_direct_name_sink',False) is True
                    guarded.append(wrapped)
                else:guarded.append(value)
            return bound(*guarded)
        if hasattr(bound,'requires_reference'):invoke.requires_reference=bound.requires_reference
        if hasattr(bound,'prepare_omissions'):invoke.prepare_omissions=bound.prepare_omissions
        return invoke
    def resolve_callable(self,value,*,require_value=False,allow_references=False):
        captured=storage.captured(self,value,require_value=require_value,allow_references=allow_references)
        if captured is not None:return captured
        bound=super().resolve_callable(value,require_value=require_value,allow_references=allow_references)
        return self._guard_references(bound) if allow_references else bound
    def leave(self):
        self._active=False
    @contextmanager
    def routine_scope(self):
        self._check()
        with self.app.safe_mode.routine(self.vm,self.vm):
            try:yield
            finally:self._check()
    def external_get(self,name):
        self._check()
        from .python_direct_names import NAMES
        if name in NAMES:return NAMES[name]
        namespace=storage.namespace(self,name)
        if namespace is not None:return namespace
        if name in ('metadata','метаданные'):return self.app.metadata
        if name in self.app.modules:return self.app.module(name,self.vm)
        from .source_application_exports import variable
        ref=variable(self.vm,name)
        if ref is not None:return ref.get()
        raise ValueError('Переменная или функция не определена: '+name)
    def external_set(self,name,value):
        self._check()
        from .source_application_exports import variable
        ref=variable(self.vm,name)
        if ref is None:raise ValueError('source namespace is read-only: '+name)
        try:ref.set(value)
        finally:self._check()
    def external_reference(self,name):
        self._check()
        from .source_application_exports import variable
        ref=variable(self.vm,name)
        if ref is None:raise ValueError('source namespace is not an output slot: '+name)
        def get():
            self._check()
            try:return ref.get()
            finally:self._check()
        def put(value):
            self._check()
            try:ref.set(value)
            finally:self._check()
        canonical=Reference(get,put);canonical._direct_name_sink=True
        return _ForwardReference(canonical)
    def resolve_service(self,name,*args,**kwargs):
        self._check();key=name.casefold()
        if key.startswith('new:') and key[4:] in query.CONSTRUCTOR_NAMES:
            return query.resolve_constructor(self,key,**kwargs)
        if key.startswith('new:') and key[4:] in ('uuid','уникальныйидентификатор'):
            from .unique_identifiers import BSLUUID
            function=self.vm.types.get(key[4:])
            if type(function) is not HostFunction or function.function is not BSLUUID:
                raise BoundaryViolation('source UUID constructor binding changed')
            return self.resolve_callable(function)
        routine=(self.vm.server_routines if self.side=='server' else self.vm.routines).get(key)
        if routine is not None:return self._routine(self.vm,routine,**kwargs)
        if key not in self._services and not key.startswith('new:'):
            if args and args[0] is not _MISSING:
                return self.resolve_callable(args[0],require_value=kwargs.get('require_value',False),
                    allow_references=kwargs.get('allow_references',False))
            selected=self.app.resolve_global(key,self.vm)
            if selected is None:raise ValueError('Переменная или функция не определена: '+name)
            routine,owner=selected
            return self._routine(owner,routine,**kwargs)
        function=self._services.get(key)
        captured=storage.captured(self,function,require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if captured is not None:return captured
        if type(function) is HostFunction:
            from .source_transactions import SourceTransactionCall
            from .common_templates import SourceTemplateCall
            from .source_host_session import SourceSessionCall
            from .temporary_storage import SourceTemporaryCall
            impl=function.function
            if type(impl) in (SourceTransactionCall,SourceTemplateCall,SourceSessionCall,SourceTemporaryCall):
                self._validate_host_function(function,kwargs.get('require_value',False),kwargs.get('allow_references',False))
                if type(impl) is SourceTemplateCall:
                    impl.owner.authorize(self.vm)
                    if kwargs.get('argument_count') is not None and kwargs['argument_count']!=1:
                        raise TypeError('GetCommonTemplate requires one argument')
                if type(impl) is SourceTemporaryCall and kwargs.get('argument_count') is not None:
                    impl.authorize_call(self.vm,kwargs['argument_count'])
                def invoke(*values):
                    self._check()
                    if function.function is not impl:raise BoundaryViolation('source service binding changed')
                    try:return impl.invoke(self.vm,list(values))
                    finally:self._check()
                if kwargs.get('allow_references'):invoke.requires_reference=lambda index:False
                return invoke
        bound=super().resolve_service(name,*args,**kwargs)
        return self._guard_references(bound) if kwargs.get("allow_references") else bound
    def _routine(self,owner,routine,*,require_value=False,allow_references=False,argument_count=None,**unused):
        check_owner(owner);_preflight(owner,routine)
        if (routine.execution_context!=self.side or owner._logical_side!=self.side
                or routine.is_async or routine.is_dual or not routine.module_context):
            raise ValueError('direct source crossing/async/NoContext routine is not integrated')
        if id(routine) in self.app._reuse_routines:
            raise ValueError('direct source reusable routine is not integrated')
        keys=tuple(k for k,v in self.app._instances.items() if v is owner)
        def provenance():
            if owner is self.app.interpreter:return
            if not keys or any(self.app._instances.get(k) is not owner for k in keys):
                raise BoundaryViolation('source routine owner replaced')
            for key in keys:
                if type(key) is tuple and len(key)==3:
                    selected=(self.app.manager_module(key[1],key[2],self.vm) if _manager_key(key)
                              else self.app.module(key[0],self.vm,global_call=key[2]))
                    if selected is not owner._self_module:
                        raise BoundaryViolation('source module admission changed')
        provenance()
        minimum=max((i+1 for i,p in enumerate(routine.parameters) if p.default is None),default=0)
        if argument_count is not None and not minimum<=argument_count<=len(routine.parameters):
            raise TypeError('Неверное количество аргументов: '+routine.name)
        refs=frozenset(i for i,p in enumerate(routine.parameters) if not p.by_value)
        def call(*values):
            self._check();check_owner(owner);provenance();_preflight(owner,routine)
            if (owner.server_routines if self.side=='server' else owner.routines).get(routine.name.casefold()) is not routine:
                raise BoundaryViolation('source routine binding changed')
            values=tuple(_ForwardReference(v) if i in refs and type(v) is Reference else v for i,v in enumerate(values))
            try:return invoke(owner,routine,values)
            finally:self._check()
        bound=self.resolve_callable(HostFunction(routine.name,call,returns_value=routine.is_function,reference_parameters=refs),
                                    require_value=require_value,allow_references=allow_references)
        def omissions(current,positions,count):
            self._check();provenance()
            if count>len(routine.parameters) or any(i>=len(routine.parameters) or routine.parameters[i].default is None for i in positions):
                raise TypeError('Неверное количество аргументов: '+routine.name)
            from .experimental_naked_collections import _OMITTED_REF
            return current,{i:_OMITTED_REF for i in positions}
        bound.prepare_omissions=omissions
        return bound
    def _module(self,value):
        from .runtime import _Module
        if type(value) is not _Module:return None
        self._check()
        owner=value.interpreter
        keys=[key for key,child in self.app._instances.items() if child is owner]
        if not keys or any(type(key) is not tuple or len(key)!=3 or (not _manager_key(key) and key[2]) for key in keys):
            raise BoundaryViolation('foreign or non-qualified source module')
        for key in keys:
            selected=(self.app.manager_module(key[1],key[2],self.vm) if _manager_key(key)
                      else self.app.module(key[0],self.vm))
            if selected is not value:raise BoundaryViolation('source module binding changed')
        check_owner(owner)
        if value is not owner._self_module or not value.ready:raise BoundaryViolation('inactive source module')
        return owner
    def _metadata(self,value):
        from .configuration_source_metadata import SourceMetadataRoot,SourceMetadataObject
        from .metadata import _DeclaredMetadataCollection
        root=self.app.metadata
        from .source_metadata_properties import SourceObjectProperties,_SCRIPT_VARIANT,_COMPATIBILITY
        if type(value) is SourceObjectProperties or value is _SCRIPT_VARIANT or value is _COMPATIBILITY:return True
        if type(value) is SourceMetadataRoot:return value is root
        if type(value) is SourceMetadataObject:return value._root is root
        if type(value) is _DeclaredMetadataCollection:
            owners=[root,*root._objects.values()]
            return any(value is collection for owner in owners for collection in owner._collections.values())
        return False
    def _manager_export(self,value,name):
        from .source_references import SourceReferenceManager,_METHODS
        if type(value) is not SourceReferenceManager:return None
        storage.check(self,value)
        from .source_catalog_runtime import _MANAGER_METHODS as catalog_methods
        from .source_document_runtime import _MANAGER_METHODS as document_methods
        if (name.casefold() in _METHODS
                or value.family=='Catalog' and name.casefold() in catalog_methods
                or value.family=='Document' and name.casefold() in document_methods):return None
        return self._module(value.module(self.vm))
    def get_member(self,value,name):
        self._check()
        if name.startswith('_'):raise BoundaryViolation('private source member')
        if query.supports(value):return query.get_member(self,value,name)
        if storage.owns(value):return storage.get(self,value,name)
        if self._metadata(value) or self._module(value) is not None:
            try:return value.get_member(name)
            finally:self._check()
        raise ValueError('direct source receiver is not integrated')
    def resolve_source_member(self,value,name,*,require_value=False,argument_count=None,allow_references=False):
        self._check()
        if query.supports(value):return query.resolve_member(self,value,name,require_value=require_value,
            argument_count=argument_count,allow_references=allow_references)
        manager=self._manager_export(value,name)
        if manager is not None:
            return self._routine(manager,manager._self_module.routine(name),require_value=require_value,
                argument_count=argument_count,allow_references=allow_references)
        if storage.owns(value):return storage.resolve(self,value,name,require_value=require_value,
            argument_count=argument_count,allow_references=allow_references)
        owner=self._module(value)
        if owner is not None:
            return self._routine(owner,value.routine(name),require_value=require_value,
                argument_count=argument_count,allow_references=allow_references)
        function=self.resolve_member(value,name)
        return self.resolve_callable(HostFunction(name,function),require_value=require_value,
                                     allow_references=allow_references)
    def set_member(self,value,name,new_value):
        return self.resolve_set_member(value,name)(new_value)
    def reference_member(self,value,name):
        if storage.owns(value) or query.supports(value):
            self.get_member(value,name)
            from .experimental_naked_boundaries import _HostMemberReference
            return _HostMemberReference(self,value,name)
        return super().reference_member(value,name)
    def resolve_set_member(self,value,name):
        self._check()
        if query.supports(value):return query.resolve_set_member(self,value,name)
        if storage.owns(value):return storage.set_member(self,value,name)
        if self._metadata(value):raise ValueError('source metadata is read-only')
        return super().resolve_set_member(value,name)
    def resolve_member(self,value,name):
        self._check()
        if query.supports(value):return query.resolve_member(self,value,name)
        manager=self._manager_export(value,name)
        if manager is not None:return self._routine(manager,manager._self_module.routine(name))
        if storage.owns(value):return storage.resolve(self,value,name)
        if name in ('__getitem__','__setitem__','__iter__') and self._metadata(value):
            def operation(*args):
                self._check()
                if not self._metadata(value):raise BoundaryViolation('source metadata binding changed')
                try:
                    if name=='__getitem__':return value.get_index(*args)
                    if name=='__setitem__':raise ValueError('source metadata is read-only')
                    return self.iterate(value)
                finally:self._check()
            return operation
        if name.startswith('_'):raise BoundaryViolation('private source member')
        owner=self._module(value)
        if owner is not None:
            routine=value.routine(name)
            # Dynamic member lowering has no byref address contract yet.
            if any(not p.by_value for p in routine.parameters):
                raise ValueError('direct source qualified byref is not integrated')
            return self._routine(owner,routine)
        if self._metadata(value):
            function=value.get_method(name)
            def invoke_member(*values):
                self._check()
                if not self._metadata(value):raise BoundaryViolation('source metadata binding changed')
                try:return function(*values)
                finally:self._check()
            return invoke_member
        raise ValueError('direct source receiver is not integrated')
    def call_member(self,value,name,*args):
        self._check()
        if name=='__getitem__' and self._metadata(value):
            try:return value.get_index(*args)
            finally:self._check()
        return self.resolve_member(value,name)(*args)
    def iterate(self,value):
        self._check()
        if query.supports(value):
            yield from query.iterate(self,value);return
        if storage.owns(value):
            yield from storage.iterate(self,value);return
        if not self._metadata(value):raise ValueError('direct source iteration is not integrated')
        for item in value:
            self._check();yield item
        self._check()


def _run(owner,plan,callback=None):
    from .native_targets import target_context
    from .execution_policy import execution_backend_policy
    check_owner(owner)
    context=SourceBoundary(owner,plan)
    previous=getattr(owner,'_direct_source_active',0)
    owner._direct_source_active=previous+1
    try:
        with target_context(owner.native_target),execution_backend_policy('python-direct'),localcontext() as decimal:
            decimal.prec=38
            context.enter()
            try:
                try:
                    result=plan.function(owner.variables,plan.constants,[],context)
                    return result if callback is None else callback(result)
                finally:context._check()
            except Exception as error:
                converted=convert_error(error,plan.source_name,plan.source_text)
                if converted is error:raise
                raise converted from None
    finally:
        context.leave();owner._direct_source_active=previous


def execute(owner,program):
    check_owner(owner)
    if getattr(owner,"_direct_source_active",0):
        raise BoundaryViolation("reentrant direct source execution is not integrated")
    if type(program) is not list:raise TypeError('source execution requires parsed AST')
    declarations=[n for n in program if type(n) in (ast.Routine,ast.Var)]
    if any(type(n) in (ast.Import,ast.Execute) for n in _nodes(program)):
        raise ValueError('direct source imports/Execute are not integrated')
    for n in declarations:
        if type(n) is ast.Routine and (n.is_async or n.is_dual or not n.module_context):
            raise ValueError('direct source async/dual/NoContext routine is not integrated')
        if n.execution_context!=owner._logical_side:
            raise ValueError('direct source mixed-side declarations are not integrated')
    declared={name.casefold() for n in declarations if type(n) is ast.Var for name in n.names}
    layout=set(owner.module_names)|declared
    declaration_plan=_compile(owner,declarations,exports=True,layout=layout) if declarations else None
    statements=[n for n in program if type(n) not in (ast.Routine,ast.Var)]
    statement_plan=_compile(owner,statements,layout=layout)
    # Complete admission and compilation before publishing declarations/effects.
    owner.module_names.update(declared)
    for n in declarations:
        if type(n) is ast.Routine:
            registry=owner.server_routines if n.execution_context=='server' else owner.routines
            registry[n.name.casefold()]=n
            if not hasattr(owner,'_direct_source_plans'):owner._direct_source_plans={}
            owner._direct_source_plans[n.name.casefold()]=(n,declaration_plan)
        else:
            for name in n.names:
                owner.variables.setdefault(name.casefold(),None)
            owner.exported_variables.update(name.casefold() for name in n.exported_names)
    result=_run(owner,statement_plan)
    owner._self_module.ready=True
    return result


def _preflight(owner,routine):
    _signature(routine)
    binding=getattr(owner,'_direct_source_plans',{}).get(routine.name.casefold())
    if binding is None or binding[0] is not routine:raise BoundaryViolation('unprepared source routine')
    plan=binding[1]
    _check_plan(owner,plan)
    from .python_direct import _admit_bindings
    _admit_bindings(owner,frozenset(),plan._source_constructors,frozenset())
    return plan


def invoke(owner,routine,values):
    check_owner(owner)
    plan=_preflight(owner,routine)
    return _run(owner,plan,lambda exports:exports[routine.name.casefold()](*values))


def event(owner,routine,arguments):
    # These are host-built event slots, not arbitrary source AST evaluation.
    values=[];outputs=[]
    for argument in arguments:
        if type(argument) is ast.Literal:values.append(argument.value)
        elif type(argument) is ast.Attribute and type(argument.object) is ast.Literal:
            obj=argument.object.value
            from .structures import BSLStructure
            if type(obj) is not BSLStructure:raise BoundaryViolation('unsupported source event output owner')
            slot=_Cell(obj.get_member(argument.name));values.append(slot);outputs.append((obj,argument.name,slot))
        else:raise BoundaryViolation('unsupported source event argument')
    with source_transactions.execution(owner.application),owner.application.safe_mode.execution():
        try:return invoke(owner,routine,values)
        finally:
            for obj,name,slot in outputs:obj.set_member(name,slot.value)
