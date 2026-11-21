"""Finite synchronous source storage protocol, retaining canonical transactions."""
from types import GeneratorType
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction, InterpreterCall
from yadinassi.db.metadata.source_constants_runtime import SourceConstants, SourceConstant, SourceConstantSet, ConstantCall, ConstantSetCall
from yadinassi.db.metadata.source_constant_managers import SourceConstantValueManager, ValueManagerCall
from yadinassi.configuration.source_manager_modules import SourceManagers, MANAGER_NAMES
from yadinassi.db.metadata.source_references import SourceReferenceManager, SourceReferenceCall
from yadinassi.db.catalog.source_catalog_runtime import SourceCatalogObject, SourceCatalogSelection, SourceCatalogCall
from yadinassi.db.catalog.catalog_types import BSLCatalogReference
from yadinassi.db.document.document_types import BSLDocumentReference
from yadinassi.db.document.source_document_runtime import SourceDocumentObject, SourceDocumentSelection, SourceDocumentCall
from yadinassi.db.document.source_document_sections import SourceDocumentSection, SourceDocumentRow, SourceDocumentSectionCall

TYPES=(SourceConstants,SourceConstant,SourceConstantSet,SourceConstantValueManager,
       SourceManagers,SourceReferenceManager,SourceCatalogObject,SourceCatalogSelection,BSLCatalogReference,
       SourceDocumentObject,SourceDocumentSelection,BSLDocumentReference,SourceDocumentSection,SourceDocumentRow)


def finish(operation):
    if type(operation) is not GeneratorType:
        raise BoundaryViolation('source storage requires canonical synchronous operation')
    try:
        try:next(operation)
        except StopIteration as result:return result.value
        raise BoundaryViolation('source storage suspension is not integrated')
    finally:operation.close()


def owns(value):return type(value) in TYPES


def namespace(boundary,name):
    if name in ('constants','константы'):return SourceConstants(boundary.app)
    if name in MANAGER_NAMES:return SourceManagers(boundary.app,MANAGER_NAMES[name])
    return None


def check(boundary,value):
    boundary._check();kind=type(value);caller=boundary.vm
    if kind is SourceConstant:return check(boundary,value._owner)
    if kind in (SourceConstantSet,SourceConstantValueManager):
        check(boundary,value.owner)
        if kind is SourceConstantValueManager:
            if value.interpreter is not None:
                from .python_direct_source_constants import check_manager
                check_manager(value,caller)
            value.authorize(caller)
        return
    if kind is SourceConstants:
        if value._application() is not boundary.app:raise BoundaryViolation('foreign source constants')
        value._store(caller);return
    if kind is SourceManagers:
        if value._application() is not boundary.app:raise BoundaryViolation('foreign source namespace')
        value.authorize(caller);return
    if kind is SourceReferenceManager:
        if value._app() is not boundary.app:raise BoundaryViolation('foreign source manager')
        value.authorize(caller);return
    if kind is SourceDocumentRow:
        if type(value.section) is not SourceDocumentSection:raise BoundaryViolation('foreign source document row')
        check(boundary,value.section);value.authorize(caller);return
    if kind is SourceDocumentSection:
        if type(value.owner) is not SourceDocumentObject:raise BoundaryViolation('foreign source document section')
        check(boundary,value.owner);value.authorize(caller);return
    if kind in (SourceCatalogObject,SourceCatalogSelection,SourceDocumentObject,SourceDocumentSelection):
        check(boundary,value.manager)
        if kind in (SourceCatalogObject,SourceDocumentObject):
            if value.interpreter is not None:
                if kind is SourceDocumentObject:
                    from .python_direct_source_document import check_object
                else:
                    from .python_direct_source_catalog import check_object
                check_object(value,caller)
            value.authorize(caller)
        else:
            if kind is SourceDocumentSelection:
                from yadinassi.db.document.source_document_runtime import store_for
            else:
                from yadinassi.db.catalog.source_catalog_runtime import store_for
            store_for(value.manager,caller)
        return
    if kind in (BSLCatalogReference,BSLDocumentReference):
        if kind is BSLDocumentReference:
            from yadinassi.db.document.source_document_runtime import _reference_manager
        else:
            from yadinassi.db.catalog.source_catalog_runtime import _reference_manager
        _reference_manager(caller,value);return
    raise BoundaryViolation('source storage receiver is not integrated')


def get(boundary,value,name):
    check(boundary,value)
    if name.startswith('_'):raise BoundaryViolation('private source storage member')
    kind=type(value);caller=boundary.vm
    try:
        if kind in (SourceConstants,SourceManagers,SourceReferenceManager):return value.member(caller,name)
        if kind is SourceConstantSet:
            if name.casefold() in ('read','прочитать','write','записать'):return value.get_member(name)
            return value.read_property(caller,name)
        if kind in (SourceConstantValueManager,SourceCatalogObject,SourceCatalogSelection,SourceDocumentObject,SourceDocumentSelection,SourceDocumentSection,SourceDocumentRow):return value.property_read(caller,name)
        if kind in (BSLCatalogReference,BSLDocumentReference):
            if kind is BSLDocumentReference:
                from yadinassi.db.document.source_document_runtime import reference_member
            else:
                from yadinassi.db.catalog.source_catalog_runtime import reference_member
            return reference_member(caller,value,name)
        return value.get_member(name)
    finally:check(boundary,value)


def set_member(boundary,value,name):
    check(boundary,value)
    if name.startswith('_'):raise BoundaryViolation('private source storage member')
    kind=type(value)
    if kind in (BSLCatalogReference,BSLDocumentReference):
        if kind is BSLDocumentReference:
            from yadinassi.db.document.source_document_runtime import readonly_reference
        else:
            from yadinassi.db.catalog.source_catalog_runtime import readonly_reference
        def reject(new_value):
            check(boundary,value)
            return readonly_reference(boundary.vm,value,name,new_value)
        return reject
    if kind is SourceConstantSet:method=value.write_property
    elif kind in (SourceConstantValueManager,SourceCatalogObject,SourceCatalogSelection,SourceDocumentObject,SourceDocumentSelection,SourceDocumentSection,SourceDocumentRow):method=value.property_write
    else:raise ValueError('source storage namespace is read-only')
    def assign(new_value):
        check(boundary,value)
        try:return method(boundary.vm,name,new_value)
        finally:check(boundary,value)
    return assign


def resolve(boundary,value,name,*,require_value=False,allow_references=False,argument_count=None):
    check(boundary,value)
    if type(value) is SourceDocumentObject:
        from yadinassi.db.document.source_document_runtime import _OBJECT_METHODS
        if name.casefold() not in _OBJECT_METHODS:
            from .python_direct_source_document import bind_export
            return bind_export(boundary,value,name,require_value=require_value,
                allow_references=allow_references,argument_count=argument_count)
    if type(value) is SourceCatalogObject:
        from yadinassi.db.catalog.source_catalog_runtime import _OBJECT_METHODS
        if name.casefold() not in _OBJECT_METHODS:
            from .python_direct_source_catalog import bind_export
            return bind_export(boundary,value,name,require_value=require_value,
                allow_references=allow_references,argument_count=argument_count)
    if type(value) is SourceConstantValueManager:
        from yadinassi.db.metadata.source_constant_managers import _STANDARD_METHODS
        if name.casefold() not in _STANDARD_METHODS:
            from .python_direct_source_constants import bind_export
            return bind_export(boundary,value,name,require_value=require_value,
                allow_references=allow_references,argument_count=argument_count)
    if name=='__getitem__' and type(value) is SourceDocumentSection:
        def row(index):
            check(boundary,value)
            try:return value.get_index(boundary.vm,index)
            finally:check(boundary,value)
        return row
    if name=='__iter__' and type(value) is SourceDocumentSection:return lambda:iterate(boundary,value)
    if name=='__getitem__' and type(value) in (SourceConstants,SourceManagers):
        def item(key):
            check(boundary,value)
            try:return value.member(boundary.vm,key)
            finally:check(boundary,value)
        return item
    if name=='__iter__' and type(value) is SourceConstants:return lambda:iterate(boundary,value)
    function=get(boundary,value,name)
    return bind(boundary,value,function,name,require_value=require_value,allow_references=allow_references,argument_count=argument_count)


def bind(boundary,value,function,name,*,require_value=False,allow_references=False,argument_count=None):
    if type(function) is not HostFunction:raise TypeError('source storage member is not callable')
    boundary._validate_host_function(function,require_value,allow_references)
    impl=function.function
    if type(impl) is InterpreterCall:
        marker=getattr(impl.authorize,'__self__',None)
        dispatch={'ConstantCall':ConstantCall.dispatch,'ConstantSetCall':ConstantSetCall.dispatch,'ValueManagerCall':ValueManagerCall.invoke}
        if (type(marker) not in (ConstantCall,ConstantSetCall,ValueManagerCall)
                or getattr(impl.authorize,'__func__',None) is not type(marker).authorize
                or getattr(impl.dispatch,'__self__',None) is not marker
                or getattr(impl.dispatch,'__func__',None) is not dispatch[type(marker).__name__]
                or impl!=marker.descriptor()):
            raise BoundaryViolation('noncanonical source storage descriptor')
        receiver=marker.owner if type(marker) is ConstantCall else marker.receiver
        check(boundary,receiver)
        if argument_count is not None:impl.prepare(boundary.vm,argument_count)
    elif type(impl) is SourceReferenceCall:
        if argument_count is not None and argument_count!=(1 if impl.operation=='ref' else 0):
            raise TypeError('source GetRef requires one explicit UUID' if impl.operation=='ref'
                            else 'source EmptyRef/Metadata take no arguments')
    elif type(impl) is SourceCatalogCall:
        from yadinassi.db.catalog.source_catalog_runtime import store_for
        manager=impl.receiver if type(impl.receiver) is SourceReferenceManager else impl.receiver.manager
        store_for(manager,boundary.vm)
        expected=2 if impl.operation in ('findattribute','finddescription') else 1 if impl.operation=='findcode' else 0
        if argument_count is not None and argument_count!=expected:raise TypeError('invalid source catalog argument count')
    elif type(impl) is SourceDocumentCall:
        check(boundary,impl.receiver)
        from yadinassi.db.document.source_document_runtime import store_for
        manager=impl.receiver if type(impl.receiver) is SourceReferenceManager else impl.receiver.manager
        store_for(manager,boundary.vm)
        if argument_count is not None and argument_count!=0:
            raise TypeError('source document methods accept no arguments; posting unsupported')
    elif type(impl) is SourceDocumentSectionCall:
        check(boundary,impl.section)
        expected=1 if impl.operation in ('get','delete') else 0
        if argument_count is not None and argument_count!=expected:raise TypeError('invalid document section argument count')
    elif type(value) not in (BSLCatalogReference,BSLDocumentReference):
        raise BoundaryViolation('source storage callable is not integrated')
    # Descriptors are frozen but their canonical operation markers are mutable.
    # An argument callback must not retarget a previously admitted capability.
    marker=impl.authorize.__self__ if type(impl) is InterpreterCall else impl
    fields=(('owner','name','writing') if type(marker) is ConstantCall else
            ('receiver','operation') if type(marker) in (ConstantSetCall,ValueManagerCall) else
            ('manager','operation') if type(marker) is SourceReferenceCall else
            ('receiver','operation','identity') if type(marker) in (SourceCatalogCall,SourceDocumentCall) else
            ('section','operation') if type(marker) is SourceDocumentSectionCall else ())
    state=tuple(getattr(marker,field) for field in fields)
    def invoke(*values):
        check(boundary,value)
        if function.function is not impl or any(getattr(marker,field) is not old for field,old in zip(fields,state)):
            raise BoundaryViolation('source storage operation changed')
        try:
            if type(impl) is InterpreterCall:return finish(impl.invoke(boundary.vm,list(values)))
            if type(impl) in (SourceCatalogCall,SourceDocumentCall):return finish(impl.invoke(boundary.vm,list(values)))
            if type(impl) in (SourceReferenceCall,SourceDocumentSectionCall):return impl.invoke(boundary.vm,list(values))
            return function(*values)
        finally:check(boundary,value)
    return boundary.resolve_callable(HostFunction(name,invoke,returns_value=function.returns_value),
        require_value=require_value,allow_references=allow_references)


def iterate(boundary,value):
    check(boundary,value)
    if type(value) is SourceDocumentSection:
        for item in value.iterate(boundary.vm):
            check(boundary,value);yield item
        check(boundary,value);return
    if type(value) is not SourceConstants:raise ValueError('source storage iteration is not integrated')
    for item in value.members(boundary.vm):
        check(boundary,value);yield item
    check(boundary,value)


def captured(boundary,function,**contract):
    if type(function) is not HostFunction:return None
    impl=function.function
    if type(impl) in (SourceCatalogCall,SourceReferenceCall,SourceDocumentCall,SourceDocumentSectionCall):
        value=impl.section if type(impl) is SourceDocumentSectionCall else impl.manager if type(impl) is SourceReferenceCall else impl.receiver
        check(boundary,value)
        return bind(boundary,value,function,function.name,**contract)
    if type(impl) is not InterpreterCall:return None
    marker=getattr(impl.authorize,'__self__',None)
    if type(marker) not in (ConstantCall,ConstantSetCall,ValueManagerCall):return None
    value=marker.owner if type(marker) is ConstantCall else marker.receiver
    check(boundary,value)
    return bind(boundary,value,function,function.name,**contract)
