"""Generated posting handlers inside the existing writer's atomic savepoint.

This adapter grants only public members of the current document's buffers and
its query results. It does not own transactions or run Interpreter dispatch.
"""
from decimal import localcontext
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .experimental_naked_collections import prepare, _Cell
from .experimental_naked_errors import convert_error
from .experimental_naked_live_state import _ForwardReference
from .python_direct import REPAIRS
from .native_targets import target_context
from .values import Reference, HostFunction
from .structures import BSLStructure
from .document_lines import BSLDocumentLines, BSLDocumentLine
from .document_posting_values import BSLRecorderCollection, BSLRecorderSet, BSLRecorderRow, DOCUMENT_WRITE_MODES
from .accumulation_posting_values import BSLAccumulationCollection, BSLAccumulationSet, BSLAccumulationRow, ACCUMULATION_RECORD_TYPES
from .queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection

SELF=('thisobject','этотобъект')
SYSTEM={'accumulationrecordtype':ACCUMULATION_RECORD_TYPES,'виддвижениянакопления':ACCUMULATION_RECORD_TYPES,
        'documentwritemode':DOCUMENT_WRITE_MODES,'режимзаписидокумента':DOCUMENT_WRITE_MODES}
OWNED=(BSLDocumentLines,BSLDocumentLine,BSLRecorderCollection,BSLRecorderSet,BSLRecorderRow,
       BSLAccumulationCollection,BSLAccumulationSet,BSLAccumulationRow,BSLStructure,
       BSLQuery,BSLQueryResult,BSLQueryResultSelection)

class PostingBoundary(BoundaryContext):
    def __init__(self,vm):
        super().__init__(services=vm.functions)
        self.vm=vm;self.document=vm._document
        self._owned={id(self.document):self.document}
        self._owned.update((id(value),value) for value in SYSTEM.values())
        self._services.update(('new:'+name,value) for name,value in vm.types.items() if name in ('query','запрос'))
    def _check(self):
        super()._check()
        owner=self.vm._family_owner
        if (self.vm._family_closed or self.vm._family_released or owner._family_closed
                or self.vm._family_generation != owner._family_generation
                or self.document._posting_active is None):
            raise BoundaryViolation('document posting boundary is closed')
    def _adopt(self,value):
        if id(type(value)) in tuple(map(id,OWNED)):
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
        return self._adopt(result)
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
        def invoke(*args):
            self._receiver(value)
            return self._adopt(bound(*args))
        invoke.requires_reference=bound.requires_reference
        return invoke


def invoke_posting(vm,routine,values):
    from .database_transactions import admission
    program=list(vm.routines.values())
    doc=vm._document
    names=set(doc._values)|set(doc._sections)|set(SELF)|set(SYSTEM)|{
        'additionalproperties','дополнительныесвойства','registerrecords','движения',
        'номер','дата','проведен','проведён','ссылка','пометкаудаления'}
    plan=prepare('',source_name='<document-posting>',repairs=REPAIRS,parsed_ast=program,
                 external_names=tuple(names),constructors=('query','запрос'),
                 _trusted_entry=True,_export_routines=True)
    names=('Cancel','PostingMode') if len(routine.parameters)==2 else ('Cancel','WriteMode','PostingMode')[:len(routine.parameters)]
    slots=[values.get_member(name) if parameter.by_value else _Cell(values.get_member(name))
           for parameter,name in zip(routine.parameters,names)]
    context=PostingBoundary(vm)
    with admission(False),target_context(vm.native_target),localcontext() as decimal_context:
        decimal_context.prec=38
        context.enter()
        try:
            exports=plan.function({},plan.constants,[],context)
            exports[routine.name.casefold()](*slots)
            for name,parameter,slot in zip(names,routine.parameters,slots):
                if not parameter.by_value:values.set_member(name,slot.value)
        except Exception as error:
            converted=convert_error(error,'<document-posting>','')
            if converted is error:raise
            raise converted from None
        finally:
            try:context._check()
            finally:context.leave()
