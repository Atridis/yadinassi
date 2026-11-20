"""Generated execution of already-admitted detached catalog form events."""
from decimal import localcontext
from dataclasses import dataclass
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Cell
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.execution.codegen.experimental_naked_errors import convert_error
from .python_direct import REPAIRS,_snapshot,_nodes
from .python_direct_catalog_preparation import CatalogPreparationBoundary
from yadinassi.types.values import HostFunction,Reference
from yadinassi.application.user_messages import BSLUserMessage
from yadinassi.syntax import ast

class ScalarEventBoundary(BoundaryContext):
    def __init__(self,vm):
        super().__init__(services=vm.functions);self.vm=vm
        self._owned={id(vm.variables['объект']):vm.variables['объект']}
        self._services.update(('new:'+name,value) for name,value in vm.types.items())
    def _check(self):
        super()._check()
        if self.vm._family_closed:raise BoundaryViolation('form event closed')
    def _receiver(self,value):
        self._check()
        if self._owned.get(id(value)) is not value:raise BoundaryViolation('foreign form event receiver')
    def resolve_service(self,*args,**kwargs):
        bound=super().resolve_service(*args,**kwargs)
        def call(*values):
            value=bound(*values)
            if type(value) is BSLUserMessage and value._context is self.vm.user_messages:self._owned[id(value)]=value
            return value
        if hasattr(bound,'requires_reference'):call.requires_reference=bound.requires_reference
        return call
    def get_member(self,value,name):
        self._receiver(value);return value.get_member(name)
    def resolve_set_member(self,value,name):
        self._receiver(value)
        def write(new):self._receiver(value);value.set_member(name,new)
        return write
    def resolve_member(self,value,name):
        self._receiver(value);method=value.get_method(name)
        if type(method) is not HostFunction:raise BoundaryViolation('invalid event method')
        def call(*args):
            self._receiver(value)
            try:return method(*args)
            finally:self._check()
        return call

class ProductEventBoundary(CatalogPreparationBoundary):
    def __init__(self,vm,controls):
        super().__init__(vm)
        self._controls={id(value):value for value in controls}
        self._owned.update(self._controls)
        self._services['_direct_check_object']=HostFunction('_direct_check_object',lambda receiver,cancel:self.prepare_object(receiver,cancel,checking=True),reference_parameters=frozenset({1}),returns_value=False)
        for value in vm.variables.values():self._adopt(value)
        self._services['_direct_prepare_object']=HostFunction('_direct_prepare_object',self.prepare_object,reference_parameters=frozenset({1}),returns_value=False)
    def get_member(self,value,name):
        if self._controls.get(id(value)) is value:
            self._receiver(value);return self._adopt(value.get_member(name))
        return super().get_member(value,name)
    def prepare_object(self,receiver,cancel,checking=False):
        self._check()
        if checking:
            from yadinassi.db.catalog.catalogs import BSLCatalogObject
            if (type(receiver) is not BSLCatalogObject or receiver._manager is not self.vm._list_manager
                    or receiver.is_new() or sum(len(section._rows) for section in receiver._sections.values())>32):
                raise ValueError('product list: saved bounded product required')
        if (not checking and receiver is not self.receiver) or type(cancel) is not Reference or type(cancel.get()) is not bool:
            raise ValueError('product form preparation requires owned receiver and Boolean reference')
        from yadinassi.db.catalog.catalog_object_preparation import _ObjectInterpreter
        from .python_direct_catalog_preparation import prepared_validator
        source=(self.vm._list_object_source if checking else self.vm._product_object_source).decode('utf-8-sig')
        prepared=prepared_validator(receiver._manager,source)
        # Borrow a caller's transaction/snapshot; otherwise own one read snapshot
        # for this preparation only. GetObject still checks each target schema.
        view=self.vm.write_view
        owned_view=view is None
        if owned_view:view=receiver._manager._view()
        try:
            child=_ObjectInterpreter(receiver,self.vm._list_sink if checking else self.vm._product_sink,view)
            try:
                plan=prepared._plan
                context=CatalogPreparationBoundary(child);context.enter();slot=_Cell(cancel.get())
                try:
                    plan.function({},plan.constants,[],context)['проверитьданные' if checking else 'подготовитьданныекзаписи'](slot)
                    if type(slot.value) is not bool:raise TypeError('product form cancellation requires Boolean')
                    cancel.set(slot.value)
                finally:
                    try:context._check()
                    finally:context.leave()
            finally:child.close()
        finally:
            if owned_view:view.close()


@dataclass(frozen=True,slots=True)
class PreparedEvent:
    # Code and profile only: never a VM, receiver, controls or authorization.
    key: tuple
    plan: object


def _event_plan(vm,program,source,product,owner):
    from yadinassi.execution.codegen.native_targets import current_native_target
    from yadinassi.execution.execution_policy import current_backend
    schema=(getattr(owner,'_schema',None) if product else getattr(owner,'_binding',None))
    key=(source,product,schema,tuple(sorted(vm.types)),tuple(sorted(vm.variables)),
         current_native_target(),current_backend(),tuple(REPAIRS))
    cache_owner=getattr(owner,'_direct_cache_owner',None)
    if cache_owner is None:cache_owner=owner
    # Two bounded purposes share a catalog manager, not one evicting slot.
    slot='_direct_list_event_plan' if product and hasattr(vm,'_list_object_source') else '_direct_event_plan'
    previous=getattr(cache_owner,slot,None) if cache_owner is not None else None
    if type(previous) is PreparedEvent and previous.key==key:return previous.plan
    owned=_snapshot(program)
    if product:
        # Transform only the already source-admitted object reference methods.
        for node in _nodes(owned):
            if type(node) is ast.Call and type(node.callee) is ast.Attribute and node.callee.name.casefold() in ('подготовитьданныекзаписи','проверитьданные'):
                receiver=node.callee.object
                node.callee=ast.Name(node.callee.token,'_direct_check_object' if node.callee.name.casefold()=='проверитьданные' else '_direct_prepare_object')
                node.arguments=[receiver,*node.arguments]
    plan=compile_owned(owned,retain_generated=False,source_text=source,source_name=owned[0].token.source if owned else '<form-event>',
                 constructors=tuple(vm.types),module_names=tuple(vm.variables),exports=True)
    if cache_owner is not None:setattr(cache_owner,slot,PreparedEvent(key,plan))
    return plan


def run_event(vm,program,routine,source,*,product=False,controls=(),prepared_owner=None):
    owner=prepared_owner
    if product:owner=vm.receiver_object._manager
    plan=_event_plan(vm,program,source,product,owner)
    context=ProductEventBoundary(vm,controls) if product else ScalarEventBoundary(vm)
    slots=[vm.variables[p.name.casefold()] if p.by_value else _Cell(vm.variables[p.name.casefold()]) for p in routine.parameters]
    from yadinassi.db.database_transactions import admission
    with admission(False),localcontext() as decimal_context:
        decimal_context.prec=38;context.enter()
        try:
            plan.function(vm.variables,plan.constants,[],context)[routine.name.casefold()](*slots)
            for parameter,slot in zip(routine.parameters,slots):
                if not parameter.by_value:vm.variables[parameter.name.casefold()]=slot.value
        except Exception as error:
            converted=convert_error(error,'<form-event>',source)
            if converted is error:raise
            raise converted from None
        finally:
            try:context._check()
            finally:context.leave()
