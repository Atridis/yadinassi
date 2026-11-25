"""Generated posting handlers inside the existing writer's atomic savepoint.

This adapter grants only public members of the current document's buffers and
its query results. It does not own transactions or run Interpreter dispatch.
"""
from decimal import localcontext
from types import MethodType, MappingProxyType
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Cell
from yadinassi.execution.codegen.direct_emitter import compile_owned
from yadinassi.execution.codegen.experimental_naked_errors import convert_error
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
from .python_direct import REPAIRS
from yadinassi.execution.codegen.native_targets import target_context
from yadinassi.types.values import Reference, HostFunction
from yadinassi.collections.structures import BSLStructure
from yadinassi.collections.value_tables import (BSLValueTable, BSLValueTableRow,
    BSLValueTableColumn, BSLValueTableColumnCollection)
from yadinassi.db.document.document_lines import BSLDocumentLines, BSLDocumentLine
from yadinassi.db.document.document_posting_values import BSLRecorderCollection, BSLRecorderSet, BSLRecorderRow, DOCUMENT_WRITE_MODES
from yadinassi.db.registers.accumulation_posting_values import BSLAccumulationCollection, BSLAccumulationSet, BSLAccumulationRow, ACCUMULATION_RECORD_TYPES
from yadinassi.db.query.queries import (BSLQuery, BSLQueryResult, BSLQueryResultSelection,
    _DIRECT_QUERY_RESULT_UNLOAD, _DIRECT_QUERY_RESULT_UNLOAD_CODE)
from yadinassi.db.query.query_packages import BSLTempTablesManager, TEMP_TABLE_MANAGER_NAMES

SELF=('thisobject','этотобъект')
SYSTEM={'accumulationrecordtype':ACCUMULATION_RECORD_TYPES,'виддвижениянакопления':ACCUMULATION_RECORD_TYPES,
        'documentwritemode':DOCUMENT_WRITE_MODES,'режимзаписидокумента':DOCUMENT_WRITE_MODES}
OWNED=(BSLDocumentLines,BSLDocumentLine,BSLRecorderCollection,BSLRecorderSet,BSLRecorderRow,
       BSLAccumulationCollection,BSLAccumulationSet,BSLAccumulationRow,BSLStructure,
       BSLQuery,BSLQueryResult,BSLQueryResultSelection,BSLTempTablesManager)
_OWNED_IDS=frozenset(map(id,OWNED))
_TABLE_CHILD_IDS=frozenset(map(id,(BSLValueTableRow,BSLValueTableColumnCollection,BSLValueTableColumn)))

class PostingBoundary(BoundaryContext):
    def __init__(self,vm):
        super().__init__(services=vm.functions)
        self.vm=vm;self.document=vm._document
        self._owned={id(self.document):self.document}
        self._owned.update((id(value),value) for value in SYSTEM.values())
        self._services.update(('new:'+name,value) for name,value in vm.types.items() if name in _POSTING_CONSTRUCTORS)
    def _check(self):
        super()._check()
        owner=self.vm._family_owner
        if (self.vm._family_closed or self.vm._family_released or owner._family_closed
                or self.vm._family_generation != owner._family_generation
                or self.document._posting_active is None):
            raise BoundaryViolation('document posting boundary is closed')
    def checkpoint(self):
        # Generated loop headers replace visitor steps in this backend. Keep
        # the writer-owned counter shared by all handlers of one activation.
        from yadinassi.db.document import document_posting as posting
        self._check()
        steps=self.vm._steps;limit=posting.MAX_STEPS
        if type(steps) is not int or steps<0 or type(limit) is not int or limit<1:
            raise BoundaryViolation('posting checkpoint budget changed')
        self.vm._steps=steps+1
        if self.vm._steps>limit:
            raise posting.PostingLimitError('document handler execution budget')
    def _adopt(self,value,receiver=None):
        kind=id(type(value))
        if kind in _OWNED_IDS:
            self._owned[id(value)]=value
        elif kind in _TABLE_CHILD_IDS:
            parent=receiver.table if type(receiver) is BSLValueTableColumnCollection else receiver
            if (type(parent) is BSLValueTable and value.table is parent
                    and self._owned.get(id(parent)) is parent):
                self._owned[id(value)]=value
        return value
    def _receiver(self,value):
        self._check()
        if self._owned.get(id(value)) is not value:raise BoundaryViolation('unbound posting receiver')
    def external_get(self,name):
        self._check()
        if name in SELF:return self.document
        if name in SYSTEM:return SYSTEM[name]
        return self._adopt(self.document.get_member(name))
    def external_set(self,name,value):
        self._check()
        if name in SELF or name in SYSTEM:raise ValueError('posting namespace is read-only')
        self.document.set_member(name,value)
    def external_reference(self,name):
        self.external_get(name)
        return _ForwardReference(Reference(lambda:self.external_get(name),lambda value:self.external_set(name,value)))
    def resolve_service(self,*args,**kwargs):
        bound=super().resolve_service(*args,**kwargs)
        def invoke(*values):return self._adopt(bound(*values))
        if hasattr(bound,'requires_reference'):invoke.requires_reference=bound.requires_reference
        return invoke
    def get_member(self,value,name):
        self._receiver(value)
        result=value.get_member(name)
        if type(result) is HostFunction:raise BoundaryViolation('captured posting methods are unsupported')
        return self._adopt(result,value)
    def resolve_set_member(self,value,name):
        self._receiver(value)
        def write(new):
            self._receiver(value);value.set_member(name,new)
        return write
    def reference_member(self,value,name):
        self.get_member(value,name)
        return _ForwardReference(Reference(lambda:self.get_member(value,name),lambda new:self.resolve_set_member(value,name)(new)))
    def resolve_member(self,value,name):
        self._receiver(value)
        if name=='__iter__':
            if type(value) is not BSLDocumentLines:raise BoundaryViolation('unsupported posting iteration')
            def iterate():
                for row in value:
                    self._receiver(value);yield self._adopt(row)
            return iterate
        if value is self.document:raise BoundaryViolation('recursive document methods are unsupported')
        method=value.get_method(name)
        bound=self.resolve_callable(method,allow_references=True)
        if (type(value) is BSLQueryResult and type(method) is HostFunction
                and type(method.function) is MethodType and method.function.__self__ is value
                and method.function.__func__ is _DIRECT_QUERY_RESULT_UNLOAD):
            original=method.function
            def unload(*args):
                self._receiver(value)
                canonical=(not args and method.function is original
                           and _DIRECT_QUERY_RESULT_UNLOAD.__code__ is _DIRECT_QUERY_RESULT_UNLOAD_CODE)
                result=bound(*args)
                if canonical and type(result) is BSLValueTable:
                    # Publish the detached output, not arbitrary exact tables
                    # passed in through other values or host extensions.
                    self._owned[id(result)]=result
                return result
            unload.requires_reference=bound.requires_reference
            return unload
        def invoke(*args):
            self._receiver(value)
            return self._adopt(bound(*args),value)
        invoke.requires_reference=bound.requires_reference
        return invoke


from dataclasses import dataclass

_POSTING_CONSTRUCTORS=('query','запрос',*TEMP_TABLE_MANAGER_NAMES)
# Core child bindings, never the parent's mutable custom registrations.
_POSTING_CALLABLE_FIELDS=('number','число','date','дата')
_POSTING_REPAIRS=tuple(REPAIRS)+('authority_checkpoints',)
_POSTING_NAMES=frozenset(SELF)|frozenset(SYSTEM)|frozenset({
    'number','date','posted','ref','deletionmark',
    'additionalproperties','дополнительныесвойства','registerrecords','движения',
    'номер','дата','проведен','проведён','ссылка','пометкаудаления'})

@dataclass(frozen=True,slots=True)
class PreparedPosting:
    # Source-bound code and immutable signature metadata, never activation state.
    _key: tuple
    _plan: object
    _signatures: object


def prepared_posting(runtime,document,parent):
    identity=document._key.document_id
    schema=document._manager._schema
    key=(runtime._direct_sources[identity],schema,parent.native_target,_POSTING_REPAIRS,_POSTING_CONSTRUCTORS,_POSTING_CALLABLE_FIELDS)
    cached=runtime._direct_plans.get(identity)
    if type(cached) is PreparedPosting and cached._key==key:return cached
    program=runtime._programs[identity]
    names=_POSTING_NAMES|{field.name.casefold() for field in schema.fields}|{section.name.casefold() for section in schema.tabular_sections}
    with target_context(parent.native_target):
        plan=compile_owned(program,retain_generated=False,source_text='',source_name='<document-posting>',
                     external_names=tuple(names),constructors=_POSTING_CONSTRUCTORS,
                     exports=True,meter_loops=True,constructor_profile=_POSTING_CONSTRUCTORS,
                     reference_names=tuple(key for key,value in parent.functions.items()
                         if type(value) is HostFunction and value.reference_parameters))
    result=PreparedPosting(key,plan,MappingProxyType({routine.name.casefold():tuple(p.by_value for p in routine.parameters) for routine in program}))
    runtime._direct_plans[identity]=result
    return result


def invoke_posting(vm,routine,values):
    from yadinassi.db.database_transactions import admission
    prepared=vm._direct_posting_plan
    plan=prepared._plan
    name=routine.name.casefold()
    by_value=prepared._signatures[name]
    names=('Cancel','PostingMode') if len(routine.parameters)==2 else ('Cancel','WriteMode','PostingMode')[:len(routine.parameters)]
    slots=[values.get_member(name) if byval else _Cell(values.get_member(name))
           for byval,name in zip(by_value,names)]
    context=PostingBoundary(vm)
    with admission(False),target_context(vm.native_target),localcontext() as decimal_context:
        decimal_context.prec=38
        context.enter()
        try:
            exports=plan.function({},plan.constants,[],context)
            exports[routine.name.casefold()](*slots)
            for name,byval,slot in zip(names,by_value,slots):
                if not byval:values.set_member(name,slot.value)
        except Exception as error:
            converted=convert_error(error,'<document-posting>','')
            if converted is error:raise
            raise converted from None
        finally:
            try:context._check()
            finally:context.leave()
