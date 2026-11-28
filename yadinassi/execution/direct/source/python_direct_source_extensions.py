"""Finite read-only extension inventory using the actual source caller."""
from weakref import ReferenceType
from yadinassi.configuration.source_extensions import SourceExtensions,SourceExtensionSources,ExtensionCall,_DIRECT_EXTENSIONS_ABI
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.safe_mode import require_external_access


def owns(value):return type(value) in (SourceExtensions,SourceExtensionSources)


def _abi(value):
    for cls,methods in _DIRECT_EXTENSIONS_ABI:
        if type(value) is cls:
            if any(name in vars(value) or getattr(cls,name) is not expected for name,expected in methods):
                raise BoundaryViolation('source extension hooks changed')
            return
    raise BoundaryViolation('noncanonical source extension receiver')


def check(boundary,value):
    boundary._check();_abi(value)
    if type(value) is SourceExtensionSources:return
    app=boundary.app;caller=boundary.vm
    if (type(value) is not SourceExtensions or value is not app.extensions
            or type(value._application) is not ReferenceType or value._application() is not app):
        raise BoundaryViolation('foreign source extension manager')
    app.require_open();caller._require_family()
    if (caller._family_owner is not app.interpreter or caller._scheduler is not app.interpreter._scheduler
            or caller.execution_context!='server' or caller._scheduler._active_task is not None):
        raise ValueError('extension registry requires owning synchronous server context')
    if app.constant_store is None:
        raise ValueError('extension state requires an explicitly created source scratch database')
    from yadinassi.db.metadata.source_constant_store import SourceConstantStore
    from yadinassi.db.catalog.source_catalog_store import SourceCatalogStore
    from yadinassi.db.document.source_document_store import SourceDocumentStore
    from yadinassi.db.document.source_document_section_store import SourceDocumentSectionStore
    if type(app.constant_store) not in (SourceConstantStore,SourceCatalogStore,SourceDocumentStore,SourceDocumentSectionStore):
        raise BoundaryViolation('source extension scratch store changed')
    require_external_access('source extension registry database')


def namespace(boundary,name):
    if name in ('configurationextensions','расширенияконфигурации'):
        value=boundary.app.extensions;check(boundary,value);return value
    if name in ('configurationextensionssource','источникрасширенийконфигурации'):
        boundary._check();value=SourceExtensionSources();_abi(value);return value
    return None


def get(boundary,value,name):
    check(boundary,value)
    if type(name) is not str or name.startswith('_'):raise BoundaryViolation('private extension member')
    result=value.get_member(name)
    check(boundary,value);return result


def set_member(boundary,value,name):
    check(boundary,value)
    def reject(new_value):
        check(boundary,value);raise ValueError('extension attachment and mutation are not supported')
    return reject


def captured(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    if type(function) is not HostFunction or type(function.function) is not ExtensionCall:return None
    marker=function.function;_abi(marker)
    manager=marker.manager;operation=marker.operation
    def validate():
        boundary._check();_abi(marker)
        if (type(manager) is not SourceExtensions or function.function is not marker
                or marker.manager is not manager or marker.operation is not operation
                or type(operation) is not str or operation not in ('get','issues')):
            raise BoundaryViolation('source extension operation changed')
        check(boundary,manager)
    validate();maximum=2 if operation=='get' else 0
    if argument_count is not None and not 0<=argument_count<=maximum:
        raise TypeError('invalid source extension argument count')
    def invoke(*values):
        validate()
        if len(values)>maximum:raise TypeError('invalid source extension argument count')
        try:return marker.invoke(boundary.vm,list(values))
        finally:validate()
    bound=boundary.resolve_callable(HostFunction(function.name,invoke,returns_value=True),
        require_value=require_value,allow_references=allow_references)
    def omissions(current,positions,count):
        validate()
        if count>maximum or any(index>=maximum for index in positions):
            raise TypeError('invalid source extension argument count')
        return current,{index:None for index in positions}
    bound.prepare_omissions=omissions
    return bound


def resolve(boundary,value,name,**contract):
    function=get(boundary,value,name)
    bound=captured(boundary,function,**contract)
    if bound is None:raise ValueError('source extension member is not callable')
    return bound
