"""Value-only object access services for generated Python execution.

No AST evaluation, legacy visitor, node dispatcher or fallback is performed here.
Generated code supplies evaluated values and retains node error boundaries.
Preparation stages MUST precede index/RHS evaluation: authorization, receiver
validation and bound-method lookup have observable ordering in the old runtime.
Attribute/assignment receivers must already use the import-or-value receiver rule;
index-read receivers use ordinary expression evaluation, matching the runtime.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class IndexRead:
    _finish: object
    _suspending: bool = False
    def finish(self, index):
        if self._suspending:
            return (yield from self._finish(index))
        return self._finish(index)


def read_attribute(vm, value, name):
    from . import runtime as R
    from .source_document_sections import SourceDocumentSection, SourceDocumentRow
    if type(value) in (SourceDocumentSection, SourceDocumentRow):return value.property_read(vm,name)
    from .source_document_runtime import is_source_reference as document_reference, reference_member as document_member, SourceDocumentObject, SourceDocumentSelection
    if document_reference(value):return document_member(vm,value,name)
    if type(value) in (SourceDocumentObject,SourceDocumentSelection):return value.property_read(vm,name)
    from .source_catalog_runtime import is_source_reference, reference_member, SourceCatalogObject, SourceCatalogSelection
    if is_source_reference(value):return reference_member(vm,value,name)
    from .source_manager_modules import SourceManagers
    if type(value) is SourceManagers:return value.member(vm,name)
    if type(value) in (SourceCatalogObject,SourceCatalogSelection):return value.property_read(vm,name)
    from .source_references import SourceReferenceManager
    if type(value) is SourceReferenceManager:return value.member(vm,name)
    from .source_constant_managers import SourceConstantValueManager
    if type(value) is SourceConstantValueManager:return value.property_read(vm,name)
    from .source_constants_runtime import SourceConstants, SourceConstantSet
    if type(value) is SourceConstantSet:
        if name.casefold() in ('read','прочитать','write','записать'):return value.get_member(name)
        return value.read_property(vm,name)
    if type(value) is SourceConstants:return value.member(vm,name)
    if type(value) is R.BSLSessionParameters:return (yield from value.read(vm,name))
    if type(value) is R._Module:
        vm._require_module_storage_context();return value.get_member(name)
    if not isinstance(value,R.BSLObject):raise TypeError('Значение не имеет методов или свойств')
    return value.get_member(name)


def prepare_index_read(vm,value):
    from . import runtime as R
    # The form interpreter extends indexing for its owned data collections.
    # Preserve its exact context boundary and bind the method before evaluating
    # the index; get_index performs the live form/session checks afterwards.
    from .form_runtime import _FormInterpreter
    from .source_forms import _SourceFormInterpreter
    from .form_tables import BSLFormDataCollection
    if (type(vm) is _FormInterpreter or type(vm) is _SourceFormInterpreter) and type(value) is BSLFormDataCollection:
        return IndexRead(value.get_index)
    from .source_document_sections import SourceDocumentSection
    if type(value) is SourceDocumentSection:
        method=value.get_index
        return IndexRead(lambda index:method(vm,index))
    from .source_manager_modules import SourceManagers
    if type(value) is SourceManagers:
        value.authorize(vm);method=value.member
        return IndexRead(lambda index:method(vm,index))
    from .source_constants_runtime import SourceConstants
    if type(value) is SourceConstants:
        method=value.member
        return IndexRead(lambda index:method(vm,index))
    from .source_metadata_properties import SourcePropertyDomain
    if type(value) is SourcePropertyDomain:return IndexRead(value.get_index)
    if type(value) is R.BSLSessionParameters:
        value._authorize(vm)
        # Runtime resolves read AFTER the index expression, not at preparation.
        return IndexRead(lambda index:value.read(vm,index),True)
    if (type(value) is R.BSLCommonModuleMetadataCollection
            or any(type(value) is cls for cls in (R.BSLChars,R.BSLCatalogs,R.BSLDocuments))
            or R.is_metadata_collection(value) or type(value) is R.BSLEnumerations or type(value) is R.BSLEnumManager):
        return IndexRead(value.get_index)
    if not isinstance(value,R._COLLECTIONS):raise TypeError('Индексирование поддерживается только для коллекций')
    def finish(index):
        if isinstance(value,(R.BSLFixedMap,*R._TABLE_COLLECTIONS)):return value.get_index(index)
        return value.get(index)
    return IndexRead(finish)


def _source_write_guard(vm,value,attribute):
    """Return bound source writer; reject readonly before operand side effects."""
    from .source_document_sections import SourceDocumentSection, SourceDocumentRow
    if type(value) in (SourceDocumentSection,SourceDocumentRow):
        if not attribute:raise ValueError('source document section replacement unsupported')
        return value.property_write
    from .source_document_runtime import is_source_reference as document_reference, SourceDocumentObject
    if document_reference(value):raise ValueError('source document reference fields are readonly; use GetObject().Write()')
    if type(value) is SourceDocumentObject:
        if not attribute:raise ValueError('source document object indexing unsupported')
        return value.property_write
    from .source_catalog_runtime import is_source_reference, SourceCatalogObject
    if is_source_reference(value):raise ValueError('source reference fields are readonly; use GetObject().Write()')
    if type(value) is SourceCatalogObject:
        if not attribute:raise ValueError('source catalog object indexing unsupported')
        return value.property_write
    from .source_constant_managers import SourceConstantValueManager
    if type(value) is SourceConstantValueManager:
        if not attribute:raise ValueError('unsupported value manager indexing')
        return value.property_write
    from .source_constants_runtime import SourceConstantSet
    if type(value) is SourceConstantSet:
        if not attribute:raise ValueError('constant set indexing unsupported')
        return value.write_property
    return None


def prepare_attribute_write(vm,value,name):
    from . import runtime as R
    writer=_source_write_guard(vm,value,True)
    if writer is not None:return lambda rhs:writer(vm,name,rhs)
    if type(value) is R.BSLSessionParameters:
        value._authorize(vm);writer=value.write
        return lambda rhs:writer(vm,name,rhs)
    if type(value) is R._Module:vm._require_module_storage_context()
    if type(value) is not R._Module and not isinstance(value,R.BSLObject):
        raise TypeError('Значение не имеет методов или свойств')
    writer=value.set_member
    return lambda rhs:writer(name,rhs)


def prepare_index_write(vm,value):
    """Return bind(index)->setter(rhs); call each stage in source order."""
    from . import runtime as R
    _source_write_guard(vm,value,False)
    if type(value) is R.BSLSessionParameters:
        value._authorize(vm)
        def bind_session(index):
            writer=value.write
            return lambda rhs:writer(vm,index,rhs)
        return bind_session
    if R.is_metadata_collection(value) or any(type(value) is cls for cls in (R.BSLChars,R.BSLCatalogs,R.BSLDocuments,R.BSLEnumerations,R.BSLEnumManager)):
        writer=value.set_index
        return lambda index:lambda rhs:writer(index,rhs)
    if not isinstance(value,R._COLLECTIONS):raise TypeError('Индексирование поддерживается только для коллекций')
    def bind_collection(index):
        writer=value.set_index if isinstance(value,R._TABLE_COLLECTIONS) else value.set
        return lambda rhs:writer(index,rhs)
    return bind_collection
