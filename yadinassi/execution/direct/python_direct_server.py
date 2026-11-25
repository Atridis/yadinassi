"""Synchronous logical server calls with fresh side-local state, no VM dispatch.

Module-context and NoContext calls support Val and named-variable copyback.
Dual declarations select a side-local NoContext plan.
"""
from decimal import Decimal
from types import MethodType
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .python_direct_database import CatalogBoundary
from .python_direct_services import ServicesBoundary
from yadinassi.types.values import HostFunction, Reference, NULL
from yadinassi.temporal.dates import BSLDate as _PacketDate
from yadinassi.execution.codegen.experimental_naked_collections import _Cell, _OMITTED_REF
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
from .python_direct_plain_array import _DIRECT_PLAIN_ARRAY_TYPE as _PlainArray


def transfer(value, *, standalone_arrays=False, native_numbers=False):
    """Copy the bounded direct Array/Structure envelope, preserving no aliases."""
    # The standalone compiler may publish either representation of an Array.
    # Both carry only detached list contents, with no ownership or host protocol.
    array_kind = _PlainArray if standalone_arrays else list
    # A packet of immutable scalars needs a fresh envelope, not a recursive copier.
    # Include the envelope itself in the same 10,000-node budget as the slow path.
    if type(value) is list and len(value)<10000:
        for item in value:
            kind = type(item)
            if (item is not None and item is not NULL and kind is not str
                    and kind is not bool and kind is not Decimal):
                break
        else:return value.copy()
    from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
    from yadinassi.runtime import Interpreter
    from yadinassi.types.values import BSLArray
    from yadinassi.collections.structures import BSLStructure
    active=set();remaining=10000
    def copy(item,depth):
        nonlocal remaining
        remaining-=1
        if remaining<0 or depth>64:raise ValueError('Межконтекстная передача: превышен предел размера или глубины')
        kind=type(item)
        if item is None or item is NULL or kind is str or kind is bool or kind is Decimal:return item
        if (standalone_arrays or native_numbers) and kind is int:return Decimal(item)
        direct_array=kind is list or kind is array_kind
        if not direct_array and kind is not _DirectStructure and kind is not BSLArray and kind is not BSLStructure:
            if kind is _PacketDate:return Interpreter._copy_context_packet([item])[0]
            raise TypeError("Межконтекстная передача поддерживает скаляры, Массив и Структуру")
        if id(item) in active:raise ValueError('Межконтекстная передача циклических коллекций пока не поддерживается')
        active.add(id(item))
        try:
            if direct_array:return [copy(child,depth+1) for child in list.__iter__(item)]
            if kind is BSLArray:
                result=BSLArray();result.items=[copy(child,depth+1) for child in item.items]
                return result
            if kind is BSLStructure:
                result=BSLStructure()
                for key,(spelling,child) in item._items.items():result._items[key]=(spelling,copy(child,depth+1))
                return result
            result=_DirectStructure()
            for key,(spelling,child) in dict.items(item):dict.__setitem__(result,key,(spelling,copy(child,depth+1)))
            result._version=item._version
            return result
        finally:active.remove(id(item))
    return copy(value,0)


# The boundary is shared with physical InvocationServer endpoints. Only the
# in-process server crossing may opt into the live metadata graph adapter.
_LOGICAL_METADATA = object()


class ServerBoundary(ServicesBoundary,CatalogBoundary,BoundaryContext):
    _server_side=True
    # A ServerBoundary belongs to one crossing, including same-side NoContext.
    # Read-only metadata operations can never survive its exit.
    _live_metadata_epoch=None
    _live_metadata_active=True
    def __init__(self,parent,*,module_context=True,side="server",_logical_metadata=None):
        self._server_side=side=="server"
        self._logical_metadata=_logical_metadata
        self.side=side
        super().__init__()
        self.vm=parent.vm;self._services=self.vm.functions
        # The actual crossing is checked by resolve_server. The generated
        # body inherits its caller's mode, not a per-expression crossing.
        self._verify_context=parent._verify_context
        self._verify_dynamic_context=True
        self._restrict_python_extensions=not self.vm.allow_extensions
        self._execute_depth=getattr(parent,"_execute_depth",None)
        self._eval_depth=getattr(parent,"_eval_depth",None)
        if self.vm.execution_context==side:self._handled_errors=parent._handled_errors
        self.database=self.vm.database_context
        self._register_root=getattr(parent,'_register_root',None)
        self._routine_exports={};self.state={}
        self.module_context=module_context
    def leave(self):
        self._live_metadata_active=False
        return super().leave()

    def current_module(self):
        if self.module_context:return self.vm._self_module
        return super().current_module()

    def _check_role(self):
        vm=self.vm
        if (vm._family_closed or vm.database_context is not self.database
                or vm._configuration_runtime is not None or vm.locals is not None
                or vm._has_module_context!=self.module_context or vm.execution_context!=self.side):
            raise BoundaryViolation('direct server context changed at a host boundary')
    def _check_restrictions(self):
        from yadinassi.execution import safe_mode
        from yadinassi.db import source_transactions, database_transactions
        if (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
                or database_transactions._execution.get() is not None):
            raise BoundaryViolation('direct server context changed at a host boundary')
    def _check_effect(self):
        if self._verify_context:
            self._check()
            return
        self._check_lease()
        self._check_role()
        self._check_restrictions()
    def checkpoint(self):
        if self._verify_context:return super().checkpoint()
        self._check_lease()
        if self.loop_budget is not None and self.loop_backedges>=self.loop_budget:
            raise BoundaryViolation('generated loop backedge budget exhausted')
        self.loop_backedges+=1
    def _check(self):
        super()._check()
        self._check_role()
        self._check_restrictions()
    def resolve_optional_service(self,name,*args,**kwargs):
        key=name.casefold()
        module=getattr(self.vm,'_direct_routine_modules',{}).get(key)
        if self._server_side and module is not None and key in module.server_names:
            from .python_direct_routines import bind_omissions
            bound=self.resolve_service(name,*args,**kwargs)
            if getattr(self.vm,'_direct_routine_modules',{}).get(key) is module:
                return bind_omissions(bound)
            return bound
        return super().resolve_optional_service(name,*args,**kwargs)

    def _resolve_query(self,key):
        from yadinassi.db.catalog.catalogs import BSLCatalogs
        from yadinassi.db.database_context import SQLiteDBContext, require_database_context
        from yadinassi.runtime import _DIRECT_QUERY_FACTORY_ABI
        self._check_effect()
        vm=self.vm
        database=self.database
        if type(database) is not SQLiteDBContext:require_database_context()
        backend=database.backend
        catalogs=vm._catalogs
        factory=vm.types.get(key) if type(vm.types) is dict else None
        if type(factory) is not HostFunction or type(factory.name) is not str:
            raise BoundaryViolation('server query constructor requires canonical registration')
        method=factory.function
        if (type(method) is not MethodType or method.__func__ is not _DIRECT_QUERY_FACTORY_ABI
                or method.__self__ is not vm):
            raise BoundaryViolation('server query constructor requires its owning interpreter')

        def validate():
            if (type(vm.types) is not dict or vm.types.get(key) is not factory
                    or factory.function is not method or factory.returns_value is not True
                    or type(factory.reference_parameters) is not frozenset or factory.reference_parameters
                    or database.backend is not backend or backend._closed is not False
                    or vm._catalogs is not catalogs or type(catalogs) is not BSLCatalogs
                    or catalogs._context is not database or catalogs._metadata is not vm._metadata._catalogs):
                raise BoundaryViolation('server query constructor owner or binding changed')

        validate()
        name=factory.name.casefold()
        def construct(*args):
            self._before('call_value',name)
            self._check_effect()
            validate()
            return method(*args)
        return construct

    def resolve_service(self,name,*args,**kwargs):
        key=name.casefold()
        if key in ('new:query','new:запрос'):
            return self._resolve_query(key[4:])
        if self._verify_context:self._check()
        ports=getattr(self.vm,'_direct_invocation_ports',None)
        if ports is not None and key in ports:
            raise ValueError('Удалённый вызов доступен только из логического клиента')
        from .python_direct_routines import resolve
        routine=resolve(self,key,require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if routine is not None:return routine
        return super().resolve_service(name,*args,**kwargs)


class _LateNamedValue:
    __slots__=('reference',)
    def __init__(self,reference):self.reference=reference


def resolve_server(parent,module,name,*,require_value,allow_references,allow_omissions=False,non_name_actuals=()):
    vm=parent.vm
    references=module.signatures[name][3]
    copyout_references=references
    omitted=()
    module_context=name not in module.nocontext_names
    server_plan=module.server_plan if module_context else module.nocontext_plan
    if not getattr(parent,'module_context',True) and module_context:
        raise TypeError('Подпрограмма без контекста не может вызывать контекстную подпрограмму')
    def execute(context,arguments):
        exports=context._routine_exports.get(id(module))
        if exports is None:
            if module_context:
                for key in module.server_layout:context.state.setdefault(key,None)
            exports=server_plan.function(context.state,server_plan.constants,[],context)
            context._routine_exports[id(module)]=exports
        try:return exports[name](*arguments)
        except Exception as error:
            from yadinassi.execution.codegen.experimental_naked_errors import convert_error
            converted=convert_error(error,server_plan.source_name,server_plan.source_text)
            if converted is error:raise
            raise converted from None
    def invoke(*arguments):
        if getattr(parent,'_server_side',False):
            bound=tuple(_ForwardReference(value) if i in references and type(value) is Reference else value
                        for i,value in enumerate(arguments))
            if parent.module_context==module_context:return execute(parent,bound)
            # Contextual server -> NoContext is a same-side call: references stay
            # live, but globals and initializer capabilities do not follow it.
            parent._check_effect()
            context=ServerBoundary(parent,module_context=False,
                _logical_metadata=parent._logical_metadata if type(parent) is ServerBoundary else None)
            module_stack=vm._module_context_stack
            module_stack.append(False)
            try:
                context.enter()
                try:
                    if not context._verify_context:context._check_role()
                    try:return execute(context,bound)
                    finally:context._check_effect()
                finally:context.leave()
            finally:
                module_stack.pop()
                parent._check_effect()
        parent._check()
        outputs=[]
        for i,value in enumerate(arguments):
            if i in copyout_references:
                if type(value) is not Reference or getattr(value,'_direct_name_sink',False) is not True:
                    raise TypeError('Межконтекстные параметры без Знач пока требуют имя переменной')
                outputs.append((i,value))
        # Named byref actuals are storage: read only after all argument effects.
        def read_argument(index,value):
            reference=value.reference if type(value) is _LateNamedValue else value if index in copyout_references else None
            if reference is None:return value
            parent._check()
            try:return reference.get()
            finally:parent._check()
        packet=transfer([read_argument(i,value) for i,value in enumerate(arguments)],standalone_arrays=True)
        # Omission positions are call metadata, not values admitted by transfer.
        # Restore the marker only after the validated input packet was copied.
        if omitted:
            for i in omitted:packet[i]=_OMITTED_REF
        for i,_ in outputs:packet[i]=_Cell(packet[i])
        context=ServerBoundary(parent,module_context=module_context,_logical_metadata=_LOGICAL_METADATA)
        previous=getattr(vm,'_transaction_activation_allowed',True)
        vm._transaction_activation_allowed=False
        side_stack=vm._context_stack;module_stack=vm._module_context_stack
        side_stack.append('server');module_stack.append(module_context)
        try:
            context.enter()
            try:
                if not context._verify_context:context._check()
                try:
                    for initializer in (getattr(vm,'_direct_server_initializers',()) if module_context else ()):
                        for key in initializer.server_layout:context.state.setdefault(key,None)
                        plan=initializer.initializer_plan
                        try:plan.function(context.state,plan.constants,[],context)
                        except Exception as error:
                            from yadinassi.execution.codegen.experimental_naked_errors import convert_error
                            converted=convert_error(error,plan.source_name,plan.source_text)
                            if converted is error:raise
                            raise converted from None
                        context._check()
                    result=execute(context,packet)
                    outgoing=transfer([result]+[packet[i].value for i,_ in outputs],standalone_arrays=True)
                finally:context._check()
            finally:context.leave()
        finally:
            module_stack.pop();side_stack.pop()
            vm._transaction_activation_allowed=previous
            parent._check()
        # Publish only after the complete packet and current caller validate.
        # Ordered independent copy-out intentionally gives the rightmost alias.
        for (_,reference),value in zip(outputs,outgoing[1:]):reference.set(value)
        return outgoing[0]
    function=HostFunction(name,invoke,reference_parameters=references,returns_value=module.signatures[name][0])
    bound=parent.resolve_callable(function,require_value=require_value,allow_references=allow_references)
    if not getattr(parent,'_server_side',False):
        # Copy-out accepts only names. Reject the shape while binding, before
        # even an earlier by-value actual can run.
        if references and non_name_actuals and not references.isdisjoint(non_name_actuals):
            raise TypeError('Межконтекстные параметры без Знач пока требуют имя переменной')
        def prepare_named_value(reference):
            parent._check()
            if type(reference) is not Reference:raise TypeError('named server value requires a source reference')
            return _LateNamedValue(reference)
        bound.prepare_named_value=prepare_named_value
        if allow_omissions:
            def prepare_omissions(current,positions,count):
                nonlocal omitted,copyout_references
                omitted=positions
                copyout_references=references.difference(positions)
                return current,dict.fromkeys(positions,None)
            bound.prepare_omissions=prepare_omissions
    return bound


def resolve_dual_client(parent,module,name,*,require_value,allow_references):
    vm=parent.vm
    references=module.signatures[name][3]
    def invoke(*arguments):
        parent._check_effect()
        context=ServerBoundary(parent,module_context=False,side='client')
        stack=vm._module_context_stack
        lend=None
        if references:
            from .python_direct_lent_refs import scope
            lend=scope(parent)
        stack.append(False)
        try:
            context.enter()
            try:
                if not context._verify_context:context._check_role()
                exports=module.dual_plan.function({},module.dual_plan.constants,[],context)
                bound=tuple(_ForwardReference(value if lend is None else lend.wrap(value))
                            if i in references and type(value) is Reference else value
                            for i,value in enumerate(arguments))
                try:
                    try:return exports[name](*bound)
                    except Exception as error:
                        from yadinassi.execution.codegen.experimental_naked_errors import convert_error
                        converted=convert_error(error,module.dual_plan.source_name,module.dual_plan.source_text)
                        if converted is error:raise
                        raise converted from None
                finally:context._check_effect()
            finally:context.leave()
        finally:
            if lend is not None:lend.active=False
            stack.pop()
            parent._check_effect()
    function=HostFunction(name,invoke,reference_parameters=references,returns_value=module.signatures[name][0])
    return parent.resolve_callable(function,require_value=require_value,allow_references=allow_references)
