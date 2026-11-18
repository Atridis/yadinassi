"""Generated BeforeWrite over existing catalog buffers and the writer's read view.

No persistence endpoint is exposed here. CatalogObject._write retains source
selection, schema validation, transaction ownership and uncertain-write recovery.
"""
from decimal import Decimal, localcontext
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .experimental_naked_collections import prepare, _Cell
from .experimental_naked_live_state import _ForwardReference
from .experimental_naked_errors import convert_error
from .python_direct import REPAIRS
from .values import Reference, HostFunction
from .catalogs import BSLCatalogObject
from .catalog_types import BSLCatalogReference
from .catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from .maps import BSLMap
from .user_messages import BSLUserMessage
from .catalog_backend import BackendError


class CatalogPreparationBoundary(BoundaryContext):
    def __init__(self, vm):
        super().__init__()
        self.vm=vm
        self._transaction_scope=getattr(vm,"_direct_transaction_preparation_scope",None)
        self.receiver=vm.receiver_object
        self.catalogs=self.receiver._manager._catalogs
        self._owned={id(self.receiver):self.receiver}
        self._services=dict(vm.functions)
        self._services.update(('new:'+name,value) for name,value in vm.types.items())

    def _check(self):
        super()._check()
        if self.vm._family_closed:raise BoundaryViolation('catalog preparation is closed')
        if self._transaction_scope is not None:self._transaction_scope.check()

    def preparation_step(self):
        # Per invocation only: prepared validators cache code, never counters.
        self._check()
        self.vm.remaining-=1
        if self.vm.remaining<0:raise ValueError('catalog preparation: step budget')

    def preparation_value(self,value):
        self._check()
        if type(value) is Decimal and (not value.is_finite()
                or value.__sizeof__()>256 or abs(value.adjusted())>64):
            raise ValueError('catalog preparation: numeric budget')
        if type(value) is str:
            # Per-result guard precedes encoding, then cumulative UTF-8 cost.
            if len(value)>65536:raise ValueError('catalog preparation: text budget')
            self.vm.text_budget-=len(value.encode('utf-8'))
            if self.vm.text_budget<0:raise ValueError('catalog preparation: text budget')
        return value

    def checkpoint(self):
        super().checkpoint()
        self.preparation_step()

    def _adopt(self,value):
        if self._transaction_scope is not None:self._check()
        kind=type(value)
        if kind is BSLCatalogObject:
            if value._manager._catalogs is not self.catalogs:raise ValueError('catalog preparation: foreign object')
        elif kind is BSLCatalogReference:
            if value.value_type.snapshot is not self.catalogs._metadata:raise ValueError('catalog preparation: foreign reference')
        elif kind is BSLCatalogSection:
            self._adopt(value._owner)
        elif kind is BSLCatalogSectionRow:
            self._adopt(value._section)
        elif kind is BSLUserMessage:
            if value._context is not self.vm.user_messages:raise ValueError('catalog preparation: foreign message')
        elif kind is not BSLMap:return value
        self._owned[id(value)]=value
        return value

    def _receiver(self,value):
        self._check()
        if self._owned.get(id(value)) is not value:
            raise ValueError('catalog preparation: unbound receiver')

    def external_get(self,name):
        self._check()
        from .catalog_object_preparation import _SELF
        return self.receiver if name in _SELF else self._adopt(self.receiver.get_member(name))

    def external_set(self,name,value):
        self._check()
        from .catalog_object_preparation import _SELF
        if name in _SELF:raise ValueError('catalog preparation: ThisObject is read-only')
        try:self.receiver.set_member(name,value)
        finally:
            if self._transaction_scope is not None:self._check()

    def external_reference(self,name):
        from .catalog_object_preparation import _SELF
        if name in _SELF:raise ValueError('catalog preparation: ThisObject is read-only')
        return _ForwardReference(Reference(lambda:self.external_get(name),lambda value:self.external_set(name,value)))

    def resolve_service(self,*args,**kwargs):
        bound=super().resolve_service(*args,**kwargs)
        def invoke(*values):
            if (self._transaction_scope is not None
                    and args[0].casefold() not in ('значениезаполнено','valueisfilled')
                    and any(type(value) is BSLCatalogReference for value in values)):
                raise ValueError('catalog transaction preparation: reference presentation unavailable')
            return self._adopt(bound(*values))
        if hasattr(bound,'requires_reference'):invoke.requires_reference=bound.requires_reference
        return invoke

    def _read_object(self,reference):
        if type(reference) is not BSLCatalogReference or reference.value_type.snapshot is not self.catalogs._metadata:
            raise TypeError('catalog preparation: same snapshot reference required')
        view=self.vm.write_view
        if view is None:return self._adopt(reference.get_object(reference))
        manager=self.catalogs._manager_by_metadata_uuid(reference.value_type.metadata_uuid)
        if (view.database_id != self.catalogs._metadata._database_id
                or view.configuration_generation != self.catalogs._metadata._generation
                or view.catalog_schema(manager._schema.identity) != manager._schema):
            raise BackendError('schema_changed')
        card=view.read_catalog(manager._key(reference.reference_uuid))
        if self._transaction_scope is not None:self._check()
        return None if card is None else self._adopt(BSLCatalogObject(manager,card))

    def get_member(self,value,name):
        self._receiver(value)
        from .catalog_object_preparation import _METHODS
        if self._transaction_scope is not None and type(value) is BSLCatalogReference:
            raise ValueError('catalog transaction preparation: use GetObject for reference reads')
        if name.casefold() not in self.vm.member_names|_METHODS:
            raise ValueError('catalog preparation: unavailable member')
        result=value.get_member(name)
        if type(result) is HostFunction:raise ValueError('catalog preparation: captured method forbidden')
        return self._adopt(result)

    def resolve_set_member(self,value,name):
        self._receiver(value)
        if name.casefold() not in self.vm.member_names:
            raise ValueError('catalog preparation: unavailable assignment')
        def write(new):
            self._receiver(value)
            try:value.set_member(name,new)
            finally:
                if self._transaction_scope is not None:self._check()
        return write

    def set_member(self,value,name,new):return self.resolve_set_member(value,name)(new)

    def reference_member(self,value,name):
        self.get_member(value,name)
        return _ForwardReference(Reference(lambda:self.get_member(value,name),lambda new:self.set_member(value,name,new)))

    def resolve_member(self,value,name):
        self._receiver(value)
        key=name.casefold()
        if key=='__iter__':
            if type(value) is not BSLCatalogSection:raise TypeError('catalog preparation: unsupported iteration')
            def iterate():
                self._receiver(value)
                for row in value:
                    self._receiver(value)
                    yield self._adopt(row)
            return iterate
        from .catalog_object_preparation import _METHODS
        if key not in _METHODS:raise ValueError('catalog preparation: unavailable method')
        if key in ('getobject','получитьобъект'):
            def get_object(*args):
                self._receiver(value)
                if args:raise TypeError('catalog preparation: GetObject takes no arguments')
                return self._read_object(value)
            return get_object
        method=value.get_method(name)
        if type(method) is not HostFunction:raise TypeError('catalog preparation: canonical method required')
        def invoke(*args):
            self._receiver(value)
            return self._adopt(method(*args))
        return invoke


from dataclasses import dataclass

# This fixed constructor set matches _ObjectInterpreter's closed allowlist.
# Changing that profile requires changing these compiler options together.
_VALIDATOR_CONSTRUCTORS=('соответствие','сообщениепользователю')
_VALIDATOR_EXTRA_REPAIRS=('authority_checkpoints',)

@dataclass(frozen=True,slots=True)
class PreparedCatalogValidator:
    # Code only: no receiver, interpreter, write view or event closure.
    _key: tuple
    _program: tuple
    _plan: object


def _validator_key(manager,source,repairs):
    from .native_targets import current_native_target
    from .execution_policy import current_backend
    return (source,manager._schema,current_native_target(),current_backend(),repairs,_VALIDATOR_CONSTRUCTORS,'scalar-bounds-v1')


def prepared_validator(manager,source,*,prepared=None):
    """One explicit last-plan slot per schema-bound manager, never authority."""
    repairs=tuple(REPAIRS)+_VALIDATOR_EXTRA_REPAIRS
    key=_validator_key(manager,source,repairs)
    if prepared is not None:
        if type(prepared) is not PreparedCatalogValidator or prepared._key != key:
            raise ValueError('catalog preparation: prepared source/schema/options changed')
        return prepared
    previous=getattr(manager,'_direct_validator_plan',None)
    if type(previous) is PreparedCatalogValidator and previous._key == key:return previous
    from .catalog_object_preparation import _admit_catalog_object_source,_ALIASES,_SELF
    program=_admit_catalog_object_source(source,manager._schema)
    names=_ALIASES|{field.name.casefold() for field in manager._schema.fields}|{section.name.casefold() for section in manager._schema.tabular_sections}
    if names & (_SELF|{'отказ'}):raise ValueError('catalog preparation: reserved object member')
    plan=prepare(source,source_name='<catalog-preparation>',repairs=repairs,
                 constructors=_VALIDATOR_CONSTRUCTORS,
                 external_names=tuple(names|_SELF),parsed_ast=program,
                 _trusted_entry=True,_export_routines=True,_catalog_preparation_bounds=True)
    result=PreparedCatalogValidator(key,tuple(program),plan)
    manager._direct_validator_plan=result
    return result


def run_catalog_preparation(source,program,vm,cancel,*,prepared=None):
    """Invoke generated source functions, never Interpreter.execute/block/call."""
    prepared=prepared_validator(vm.receiver_object._manager,source,prepared=prepared)
    plan=prepared._plan
    context=CatalogPreparationBoundary(vm)
    argument=_Cell(cancel)
    context.enter()
    try:
        with localcontext() as decimal_context:
            decimal_context.prec=38
            exports=plan.function({},plan.constants,[],context)
            exports['передзаписью'](argument)
        return argument.value
    except Exception as error:
        converted=convert_error(error,'<catalog-preparation>',source)
        if converted is error:raise
        raise converted from None
    finally:
        try:context._check()
        finally:context.leave()
