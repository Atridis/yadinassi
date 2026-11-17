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
from . import python_direct_fixed as fixed
from .syntax import ast
from .values import HostFunction, Reference
from . import safe_mode, source_transactions, database_transactions
from . import python_direct_source_storage as storage
from . import python_direct_source_query as query
from . import python_direct_source_sessions as sessions
from . import python_direct_source_enums as enums
from . import python_direct_source_extensions as extensions
from . import python_direct_source_host_info as host_info
from . import python_direct_source_temporary as temporary
from . import python_direct_source_templates as templates
from . import python_direct_source_resources as resources
from . import python_direct_source_value_storage as stored_values
from . import python_direct_source_xdto as xdto


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



def _signature_matches(node, saved):
    """Revalidate every mutable declaration field without allocating a signature."""
    if type(node) is not ast.Routine or type(node.parameters) is not list:
        raise BoundaryViolation('source routine signature is not canonical')
    if (type(node.name) is not str or type(node.execution_context) is not str
            or type(node.is_function) is not bool or type(node.is_async) is not bool
            or type(node.is_dual) is not bool or type(node.module_context) is not bool
            or type(node.exported) is not bool):
        raise BoundaryViolation('source routine parameters are not canonical')
    parameters=saved[7]
    matches=(node.name==saved[0] and node.execution_context==saved[1]
        and node.is_function is saved[2] and node.is_async is saved[3]
        and node.is_dual is saved[4] and node.module_context is saved[5]
        and node.exported is saved[6] and len(node.parameters)==len(parameters))
    for index,p in enumerate(node.parameters):
        if type(p) is not ast.Parameter or type(p.name) is not str or type(p.by_value) is not bool:
            raise BoundaryViolation('source routine parameters are not canonical')
        if matches:
            old=parameters[index]
            matches=(p.name==old[0] and p.by_value is old[1] and (p.default is None) is old[2])
    return matches


def _check_plan(owner,plan):
    shadows=plan._source_implicit_shadows
    if shadows:
        exports=owner.application.interpreter.exported_variables
        if type(exports) is not set or any(type(name) is not str for name in exports):
            raise BoundaryViolation('source application export names changed')
        if not shadows.isdisjoint(exports):
            raise BoundaryViolation('source implicit shadow conflicts with current application exports')
    if getattr(owner,'_direct_source_scalar_reuse',False) is not plan._source_scalar_reuse:
        raise BoundaryViolation('source scalar routine contract changed')
    if frozenset(owner.module_names)!=plan._source_layout:
        raise BoundaryViolation("source module layout changed; redeclare")
    for node,signature in plan._source_routines:
        registry=owner.server_routines if signature[1]=='server' else owner.routines
        if registry.get(signature[0].casefold()) is not node or not _signature_matches(node,signature):
            raise BoundaryViolation('source declaration binding changed')


def _compile(owner,program,*,exports=False,layout=(),_extra_externals=(),_callable_externals=()):
    names={n.name.casefold() for n in program if type(n) is ast.Routine}
    names.update(name.casefold() for n in program if type(n) is ast.Var for name in n.names)
    from .configuration_source_runtime import _SourceInterpreter
    from .source_manager_modules import MANAGER_NAMES
    shadowable=tuple(sorted(set(MANAGER_NAMES)-set(owner.application.interpreter.exported_variables))) if type(owner) is _SourceInterpreter else ()
    plan=prepare(_source_text(program),source_name=program[0].token.source if program else '<source>',
        parsed_ast=_snapshot(program),repairs=REPAIRS+('authority_checkpoints',),
        module_names=tuple(layout),external_names=tuple(dict.fromkeys((*_external_names(owner,names|set(layout)),*_extra_externals))),
        constructors=tuple(CONSTRUCTORS)+query.CONSTRUCTOR_NAMES+host_info.CONSTRUCTORS+resources.CONSTRUCTOR_NAMES+stored_values.CONSTRUCTOR_NAMES+('uuid','уникальныйидентификатор'),
        _trusted_entry=True,_export_routines=exports,_initialize_module=not exports,
        _return_last_expression=not exports,_source_routine_scopes=True,
        _source_callable_externals=_callable_externals,_source_shadowable_externals=shadowable,
        _source_scalar_routines=getattr(owner,'_direct_source_scalar_reuse',False))
    native={'array','массив','structure','структура','map','соответствие','uuid','уникальныйидентификатор'}
    plan._source_scalar_reuse=getattr(owner,'_direct_source_scalar_reuse',False)
    plan._source_layout=frozenset(layout)
    plan._source_routines=tuple((n,_signature(n)) for n in program if type(n) is ast.Routine)
    # Crossing defaults are snapshotted at compilation, not first invocation.
    # Nonliteral defaults retain their ordinary same-side behavior but cannot
    # acquire authority through the bounded all-Val crossing adapter.
    plan._source_crossing_defaults={n.name.casefold(): tuple(
        (p, p.default, p.default.value if type(p.default) is ast.Literal else _MISSING)
        for p in n.parameters) for n in program if type(n) is ast.Routine}
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
        from .python_direct_source_server import check_activation
        check_activation(self.vm)
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
        if hasattr(bound,'prepare_named_value'):invoke.prepare_named_value=bound.prepare_named_value
        if hasattr(bound,'prepare_argument_shapes'):invoke.prepare_argument_shapes=bound.prepare_argument_shapes
        if hasattr(bound,'bind_eval'):invoke.bind_eval=bound.bind_eval
        return invoke
    def resolve_callable(self,value,*,require_value=False,allow_references=False):
        bound=xdto.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=stored_values.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=resources.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=templates.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=temporary.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=host_info.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=extensions.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        captured=storage.captured(self,value,require_value=require_value,allow_references=allow_references)
        if captured is not None:return captured
        bound=super().resolve_callable(value,require_value=require_value,allow_references=allow_references)
        return self._guard_references(bound) if allow_references else bound
    def leave(self):
        self._active=False
        from .python_direct_source_fragments import release
        release(self)
    @contextmanager
    def routine_scope(self):
        self._check()
        with self.app.safe_mode.routine(self.vm,self.vm):
            try:yield
            finally:self._check()
    def scalar_values(self,values):
        self._check()
        from .invocation import _encode_scalar
        for value in values:_encode_scalar(value)
        self._check()
    def scalar_result(self,value):
        self.scalar_values((value,))
        return value
    def external_get(self,name):
        self._check()
        from .python_direct_names import NAMES
        if name in NAMES:return NAMES[name]
        extension=extensions.namespace(self,name)
        if extension is not None:return extension
        enumeration=enums.namespace(self,name)
        if enumeration is not None:return enumeration
        session=sessions.namespace(self,name)
        if session is not None:return session
        namespace=storage.namespace(self,name)
        if namespace is not None:return namespace
        if name in ('xdtofactory','фабрикаxdto'):return xdto.namespace(self,name)
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
        if key.startswith('new:') and key[4:] in stored_values.CONSTRUCTOR_NAMES:
            return stored_values.resolve_constructor(self,key,**kwargs)
        if key.startswith('new:') and key[4:] in resources.CONSTRUCTOR_NAMES:
            return resources.resolve_constructor(self,key,**kwargs)
        if key.startswith('new:') and key[4:] in host_info.CONSTRUCTORS:
            return host_info.resolve_constructor(self,key,**kwargs)
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
            if self.side=='client' and self.vm is self.app._session_owner:
                registry=self.vm.server_routines
                if type(registry) is not dict or any(type(name) is not str for name in registry):
                    raise BoundaryViolation('source session crossing requires canonical registry names')
                server=registry.get(key)
                if server is not None:
                    from .python_direct_source_server import resolve_session
                    return resolve_session(self,server,**kwargs)
            selected=self.app.resolve_global(key,self.vm)
            if selected is None:raise ValueError('Переменная или функция не определена: '+name)
            routine,owner=selected
            return self._routine(owner,routine,**kwargs)
        function=self._services.get(key)
        template_call=templates.captured(self,function,require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if template_call is not None:return template_call
        temporary_call=temporary.captured(self,function,require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if temporary_call is not None:return temporary_call
        host_call=host_info.captured(self,function,require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if host_call is not None:return host_call
        captured=storage.captured(self,function,require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if captured is not None:return captured
        if type(function) is HostFunction:
            from .source_transactions import SourceTransactionCall
            impl=function.function
            if type(impl) is SourceTransactionCall:
                self._validate_host_function(function,kwargs.get('require_value',False),kwargs.get('allow_references',False))
                def invoke(*values):
                    self._check()
                    if function.function is not impl:raise BoundaryViolation('source service binding changed')
                    try:return impl.invoke(self.vm,list(values))
                    finally:self._check()
                if kwargs.get('allow_references'):invoke.requires_reference=lambda index:False
                return invoke
        bound=super().resolve_service(name,*args,**kwargs)
        return self._guard_references(bound) if kwargs.get("allow_references") else bound
    def _routine(self,owner,routine,*,require_value=False,allow_references=False,argument_count=None,qualified=False,**unused):
        check_owner(owner);_preflight(owner,routine)
        if (routine.execution_context!=self.side or owner._logical_side!=self.side
                or routine.is_async or routine.is_dual or not routine.module_context):
            raise ValueError('direct source crossing/async/NoContext routine is not integrated')
        if type(self.app._reuse_routines) is not dict or type(self.app._direct_source_reuse_entries) is not dict:
            raise BoundaryViolation('source reusable registry changed')
        entry=self.app._reuse_routines.get(id(routine))
        if (self.app._direct_source_reuse_entries.get(id(routine)) is not entry
                or entry is not None and (type(entry) is not tuple or len(entry)!=5 or entry[0] is not routine)):
            raise BoundaryViolation('source reusable entry changed')
        scalar_reuse=entry is not None and entry[4] is True
        keys=tuple(k for k,v in self.app._instances.items() if v is owner)
        def provenance():
            from .python_direct_source_server import check_activation
            if owner is self.vm and check_activation(owner):return
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
        from .python_direct_source_reuse import prepare as prepare_reuse
        reuse=prepare_reuse(self,owner,routine,provenance,server=scalar_reuse) if qualified else None
        minimum=max((i+1 for i,p in enumerate(routine.parameters) if p.default is None),default=0)
        if argument_count is not None and not minimum<=argument_count<=len(routine.parameters):
            raise TypeError('Неверное количество аргументов: '+routine.name)
        refs=frozenset(i for i,p in enumerate(routine.parameters) if not p.by_value)
        def call(*values):
            self._check();check_owner(owner);provenance();_preflight(owner,routine)
            if (owner.server_routines if self.side=='server' else owner.routines).get(routine.name.casefold()) is not routine:
                raise BoundaryViolation('source routine binding changed')
            values=tuple(_ForwardReference(v) if i in refs and type(v) is Reference else v for i,v in enumerate(values))
            try:
                if scalar_reuse:
                    from .invocation import _encode_scalar
                    for value in values:_encode_scalar(value)
                result=reuse(values,lambda:invoke(owner,routine,values)) if reuse is not None else invoke(owner,routine,values)
                if scalar_reuse:_encode_scalar(result)
                return result
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
        if xdto.owns(value):return xdto.get(self,value,name)
        if stored_values.owns(value):return stored_values.get(self,value,name)
        if resources.owns(value):return resources.get(self,value,name)
        if fixed.owns(value):return fixed.get(self,value,name)
        if name.startswith('_'):raise BoundaryViolation('private source member')
        if host_info.owns(value):return host_info.get(self,value,name)
        if extensions.owns(value):return extensions.get(self,value,name)
        if enums.supports(self,value):return enums.get(self,value,name)
        if sessions.owns(value):return sessions.get(self,value,name)
        if query.supports(value):return query.get_member(self,value,name)
        if storage.owns(value):return storage.get(self,value,name)
        if self._metadata(value) or self._module(value) is not None:
            try:return value.get_member(name)
            finally:self._check()
        raise ValueError('direct source receiver is not integrated')
    def resolve_source_member(self,value,name,*,require_value=False,argument_count=None,allow_references=False):
        self._check()
        if xdto.owns(value):return xdto.resolve(self,value,name,require_value=require_value,argument_count=argument_count,allow_references=allow_references)
        if stored_values.owns(value):return stored_values.resolve(self,value,name,require_value=require_value,argument_count=argument_count,allow_references=allow_references)
        if resources.owns(value):return resources.resolve(self,value,name,require_value=require_value,argument_count=argument_count,allow_references=allow_references)
        if fixed.owns(value):return fixed.resolve(self,value,name,require_value=require_value,allow_references=allow_references)
        if host_info.owns(value):return host_info.resolve(self,value,name,require_value=require_value,
            argument_count=argument_count,allow_references=allow_references)
        if extensions.owns(value):return extensions.resolve(self,value,name,require_value=require_value,
            argument_count=argument_count,allow_references=allow_references)
        if enums.supports(self,value):return enums.resolve(self,value,name,require_value=require_value,
            argument_count=argument_count,allow_references=allow_references)
        if sessions.owns(value):return sessions.resolve(self,value,name,require_value=require_value,
            argument_count=argument_count,allow_references=allow_references)
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
            routine=value.routine(name)
            if self.side=='client' and routine.execution_context=='server':
                from .python_direct_source_server import resolve
                return resolve(self,owner,routine,require_value=require_value,
                    argument_count=argument_count,allow_references=allow_references)
            return self._routine(owner,routine,qualified=True,require_value=require_value,
                argument_count=argument_count,allow_references=allow_references)
        function=self.resolve_member(value,name)
        return self.resolve_callable(HostFunction(name,function),require_value=require_value,
                                     allow_references=allow_references)
    def set_member(self,value,name,new_value):
        return self.resolve_set_member(value,name)(new_value)
    def reference_member(self,value,name):
        if storage.owns(value) or query.supports(value) or sessions.owns(value):
            self.get_member(value,name)
            from .experimental_naked_boundaries import _HostMemberReference
            return _HostMemberReference(self,value,name)
        return super().reference_member(value,name)
    def resolve_set_member(self,value,name):
        self._check()
        if fixed.owns(value):return fixed.resolve(self,value,'__setitem__')
        if host_info.owns(value):return host_info.set_member(self,value,name)
        if extensions.owns(value):return extensions.set_member(self,value,name)
        if enums.supports(self,value):return enums.set_member(self,value,name)
        if sessions.owns(value):return sessions.set_member(self,value,name)
        if query.supports(value):return query.resolve_set_member(self,value,name)
        if storage.owns(value):return storage.set_member(self,value,name)
        if self._metadata(value):raise ValueError('source metadata is read-only')
        return super().resolve_set_member(value,name)
    def resolve_member(self,value,name):
        self._check()
        if stored_values.owns(value):return stored_values.resolve(self,value,name)
        if resources.owns(value):return resources.resolve(self,value,name)
        if fixed.owns(value):return fixed.resolve(self,value,name)
        if host_info.owns(value):return host_info.resolve(self,value,name)
        if extensions.owns(value):return extensions.resolve(self,value,name)
        if enums.supports(self,value):return enums.resolve(self,value,name)
        if sessions.owns(value):return sessions.resolve(self,value,name)
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
            return self._routine(owner,routine,qualified=True)
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
        if enums.supports(self,value):
            yield from enums.iterate(self,value);return
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
        from .python_direct_source_requests import request_scope
        with request_scope(owner),target_context(owner.native_target),execution_backend_policy('python-direct'),localcontext() as decimal:
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
    if any(type(n) is ast.Import for n in _nodes(program)):
        raise ValueError('direct source imports are not integrated')
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
