"""Exact source fragment admission over live caller slots and inherited scopes."""
from contextlib import contextmanager
from contextvars import ContextVar
from weakref import WeakKeyDictionary
from .experimental_naked_boundaries import BoundaryViolation

_ACTIVE=ContextVar('direct_source_fragments',default=())
_UNITS=WeakKeyDictionary()

def prepared_cache(context,kind):
    from .python_direct_source import SourceBoundary
    if type(context) is not SourceBoundary:
        raise BoundaryViolation('foreign source fragment cache owner')
    context._check()
    if hasattr(context,'_execute_units') or hasattr(context,'_eval_units'):
        raise BoundaryViolation('source fragment cache replaced')
    caches=_UNITS.get(context)
    if caches is None:caches=_UNITS[context]=({}, {})
    return caches[0 if kind=='execute' else 1]

def release(context):
    _UNITS.pop(context,None)


@contextmanager
def execution(context,kind,parent,bindings,visible):
    from .configuration_source_runtime import SourceApplication
    app=getattr(context,'app',None)
    vm=getattr(context,'vm',None)
    source=type(app) is SourceApplication or type(getattr(vm,'application',None)) is SourceApplication
    if not source:
        yield None;return
    from .python_direct_source import SourceBoundary,_external_names
    if type(context) is not SourceBoundary:
        raise BoundaryViolation('source fragments require an ordinary source boundary')
    context._check()
    from .python_direct_execute import FragmentScope
    if (type(parent) not in (dict,FragmentScope) or type(bindings) is not dict
            or any(type(name) is not str for name in bindings)
            or visible is not None and (type(visible) is not tuple or any(type(name) is not str for name in visible))):
        raise BoundaryViolation('source fragment visibility changed')
    if any(type(name) is not str for name in parent):
        raise BoundaryViolation('source fragment storage names changed')
    from .python_direct_services import CONSTRUCTORS
    from . import python_direct_source_query as query,python_direct_source_host_info as host_info
    from . import python_direct_source_resources as resources,python_direct_source_value_storage as storage
    names=set(bindings)
    names.update(parent if visible is None else set(visible).intersection(parent))
    constructors=tuple(CONSTRUCTORS)+query.CONSTRUCTOR_NAMES+host_info.CONSTRUCTORS+resources.CONSTRUCTOR_NAMES+storage.CONSTRUCTOR_NAMES+('uuid','уникальныйидентификатор')
    externals=tuple(sorted(set(_external_names(vm))-names))
    active=_ACTIVE.get()
    shared=next((entry for entry in reversed(active) if entry[0] is app),None)
    if shared is None:shared=(app,[0],[0])
    counter=shared[1 if kind=='execute' else 2]
    field='_execute_depth' if kind=='execute' else '_eval_depth'
    absent=object();previous=getattr(context,field,absent)
    def valid(value):return type(value) is list and len(value)==1 and type(value[0]) is int and value[0]>=0
    if not valid(counter) or previous is not absent and not valid(previous):
        raise BoundaryViolation('source fragment depth changed')
    setattr(context,field,counter)
    token=_ACTIVE.set((*active,shared))
    try:
        with context.routine_scope():
            yield (constructors,externals)
    finally:
        changed=getattr(context,field,None) is not counter or not valid(counter)
        if previous is absent:delattr(context,field)
        else:setattr(context,field,previous)
        _ACTIVE.reset(token)
        context._check()
        if changed:raise BoundaryViolation('source fragment depth changed')
