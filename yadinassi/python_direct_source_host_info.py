"""Finite source target information and explicit synchronous scratch session."""
from weakref import ReferenceType
from .values import HostFunction
from .experimental_naked_boundaries import BoundaryViolation
from .source_system_info import SourceSystemInfo,SourceSystemInfoFactory
from .source_host_session import SourceHostSession,SourceSessionCall

CONSTRUCTORS=('systeminfo','системнаяинформация')


def owns(value):return type(value) in (SourceSystemInfo,SourceHostSession)


def _abi(value):
    from .source_system_info import _DIRECT_SYSTEM_INFO_ABI
    from .source_host_session import _DIRECT_HOST_SESSION_ABI
    for cls,methods in (*_DIRECT_SYSTEM_INFO_ABI,*_DIRECT_HOST_SESSION_ABI):
        if type(value) is cls:
            if any(name in vars(value) or getattr(cls,name) is not expected for name,expected in methods):
                raise BoundaryViolation('source host information hooks changed')
            return
    raise BoundaryViolation('noncanonical source host information receiver')


def check(boundary,value):
    boundary._check();_abi(value)
    if (type(value) not in (SourceSystemInfo,SourceSystemInfoFactory,SourceHostSession)
            or type(value._application) is not ReferenceType or value._application() is not boundary.app):
        raise BoundaryViolation('foreign source host information owner')
    boundary.app.require_open()
    if type(value) is SourceHostSession:
        if value is not boundary.app.host_session:raise BoundaryViolation('source host session replaced')
        value.authorize(boundary.vm)
        from .source_constant_store import SourceConstantStore
        from .source_catalog_store import SourceCatalogStore
        from .source_document_store import SourceDocumentStore
        from .source_document_section_store import SourceDocumentSectionStore
        if type(boundary.app.constant_store) not in (SourceConstantStore,SourceCatalogStore,SourceDocumentStore,SourceDocumentSectionStore):
            raise BoundaryViolation('source host scratch store changed')
        if value._background_job is not None:raise BoundaryViolation('source host session background identity changed')


def get(boundary,value,name):
    check(boundary,value)
    if type(name) is not str or name.startswith('_'):raise BoundaryViolation('private host information member')
    try:return value.get_member(name)
    finally:check(boundary,value)


def set_member(boundary,value,name):
    check(boundary,value)
    def reject(new_value):
        check(boundary,value);raise ValueError('source host information is read-only')
    return reject


def captured(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    if type(function) is not HostFunction or type(function.function) is not SourceSessionCall:return None
    marker=function.function;_abi(marker);session=marker.session;operation=marker.current
    def validate():
        boundary._check();_abi(marker)
        if (type(session) is not SourceHostSession or function.function is not marker
                or marker.session is not session or marker.current is not operation
                or not (type(operation) is bool or type(operation) is str and operation=='connection')):
            raise BoundaryViolation('source host session operation changed')
        check(boundary,session)
    validate()
    if argument_count is not None and argument_count!=0:raise TypeError('source session query takes no arguments')
    def invoke(*values):
        validate()
        if values:raise TypeError('source session query takes no arguments')
        try:return marker.invoke(boundary.vm,[])
        finally:validate()
    return boundary.resolve_callable(HostFunction(function.name,invoke),require_value=require_value,allow_references=allow_references)


def resolve(boundary,value,name,**contract):
    function=get(boundary,value,name);bound=captured(boundary,function,**contract)
    if bound is None:raise ValueError('source host information member is not callable')
    return bound


def resolve_constructor(boundary,name,*,require_value=True,argument_count=None,allow_references=False,**unused):
    boundary._check();key=name.casefold().removeprefix('new:')
    if key not in CONSTRUCTORS:raise BoundaryViolation('unknown source host information constructor')
    registration=boundary.vm.types.get(key)
    factory=registration.function if type(registration) is HostFunction else None
    def validate():
        boundary._check()
        if (type(registration) is not HostFunction or type(factory) is not SourceSystemInfoFactory
                or any(boundary.vm.types.get(alias) is not registration for alias in CONSTRUCTORS)
                or registration.function is not factory):
            raise BoundaryViolation('source system information constructor changed')
        check(boundary,factory)
        from . import source_system_info
        from .source_system_info import _DIRECT_SYSTEM_INFO_ABI
        methods=dict(dict(_DIRECT_SYSTEM_INFO_ABI)[SourceSystemInfo])
        if (source_system_info.SourceSystemInfo is not SourceSystemInfo
                or any(getattr(SourceSystemInfo,name) is not methods[name] for name in ('__new__','__init__'))):
            raise BoundaryViolation('source system information class changed')
    validate()
    if argument_count is not None and argument_count!=0:raise TypeError('SystemInfo constructor takes no arguments')
    def construct(*values):
        validate()
        if values:raise TypeError('SystemInfo constructor takes no arguments')
        try:
            result=factory()
            if type(result) is not SourceSystemInfo:raise BoundaryViolation('noncanonical source system information')
            check(boundary,result);return result
        finally:validate()
    return boundary.resolve_callable(HostFunction(name,construct),require_value=require_value,allow_references=allow_references)
