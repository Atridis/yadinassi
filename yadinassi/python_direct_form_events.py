"""Generated execution of already-admitted detached catalog form events."""
from decimal import localcontext
from .experimental_naked_boundaries import BoundaryContext,BoundaryViolation
from .experimental_naked_collections import prepare,_Cell
from .experimental_naked_errors import convert_error
from .python_direct import REPAIRS,_snapshot,_nodes
from .python_direct_catalog_preparation import CatalogPreparationBoundary
from .values import HostFunction,Reference
from .user_messages import BSLUserMessage
from .syntax import ast

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
            from .catalogs import BSLCatalogObject
            if (type(receiver) is not BSLCatalogObject or receiver._manager is not self.vm._list_manager
                    or receiver.is_new() or sum(len(section._rows) for section in receiver._sections.values())>32):
                raise ValueError('product list: saved bounded product required')
        if (not checking and receiver is not self.receiver) or type(cancel) is not Reference or type(cancel.get()) is not bool:
            raise ValueError('product form preparation requires owned receiver and Boolean reference')
        from .catalog_object_preparation import _ObjectInterpreter,validate_catalog_object_source,_SELF
        from .syntax.parser import parse
        source=(self.vm._list_object_source if checking else self.vm._product_object_source).decode('utf-8-sig')
        validate_catalog_object_source(source,receiver._manager._schema)
        child=_ObjectInterpreter(receiver,self.vm._list_sink if checking else self.vm._product_sink,self.vm.write_view)
        try:
            plan=prepare(source,parsed_ast=parse(source),repairs=REPAIRS,constructors=tuple(child.types),
                         external_names=tuple(child.object_names|_SELF),_trusted_entry=True,_export_routines=True)
            context=CatalogPreparationBoundary(child);context.enter();slot=_Cell(cancel.get())
            try:
                plan.function({},plan.constants,[],context)['проверитьданные' if checking else 'подготовитьданныекзаписи'](slot)
                if type(slot.value) is not bool:raise TypeError('product form cancellation requires Boolean')
                cancel.set(slot.value)
            finally:
                try:context._check()
                finally:context.leave()
        finally:child.close()


def run_event(vm,program,routine,source,*,product=False,controls=()):
    owned=_snapshot(program)
    if product:
        # Only this source-hash-admitted method has an object-module reference
        # parameter. Preserve receiver evaluation as the first actual argument.
        for node in _nodes(owned):
            if type(node) is ast.Call and type(node.callee) is ast.Attribute and node.callee.name.casefold() in ('подготовитьданныекзаписи','проверитьданные'):
                receiver=node.callee.object
                node.callee=ast.Name(node.callee.token,'_direct_check_object' if node.callee.name.casefold()=='проверитьданные' else '_direct_prepare_object')
                node.arguments=[receiver,*node.arguments]
    plan=prepare(source,parsed_ast=owned,repairs=REPAIRS,constructors=tuple(vm.types),
                 module_names=tuple(vm.variables),_trusted_entry=True,_export_routines=True)
    context=ProductEventBoundary(vm,controls) if product else ScalarEventBoundary(vm)
    slots=[vm.variables[p.name.casefold()] if p.by_value else _Cell(vm.variables[p.name.casefold()]) for p in routine.parameters]
    from .database_transactions import admission
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
