"""Qualified same-side reuse with live authority, canonical accounting and epochs."""
from collections import OrderedDict
from math import isfinite
from weakref import ReferenceType
from . import reusable_values as reuse
from .reusable_values import ApplicationReusableValues, ReusableValueCache, _DIRECT_REUSE_ABI
from .experimental_naked_boundaries import BoundaryViolation

_CLOCK=reuse.monotonic
_ARGUMENT_KEY=reuse.argument_key


def _hooks():
    for cls,name,expected in _DIRECT_REUSE_ABI:
        if getattr(cls,name) is not expected:
            raise BoundaryViolation('source reusable class hooks changed')
    for cls,fields in ((ReusableValueCache,('_clock','_identity','_epoch','_entries','_units','_closed')),
                       (ApplicationReusableValues,('_application','_source_family','_session','_request_key','_closed'))):
        if any(field in vars(base) for base in cls.__mro__ for field in fields):
            raise BoundaryViolation('source reusable field hooks changed')


def _cache(cache):
    _hooks()
    if (type(cache) is not ReusableValueCache or type(cache._entries) is not OrderedDict
            or type(cache._epoch) is not int or type(cache._units) is not int
            or type(cache._closed) is not bool or cache._clock is not _CLOCK):
        raise BoundaryViolation('noncanonical source reusable cache')
    for cls,name,expected in _DIRECT_REUSE_ABI:
        if getattr(cls,name) is not expected or (cls is ReusableValueCache and name in vars(cache)):
            raise BoundaryViolation('source reusable cache hooks changed')
    cache._open()
    total=0
    if len(cache._entries)>reuse.MAX_ENTRIES:raise BoundaryViolation('source reusable entry quota changed')
    for key,entry in cache._entries.items():
        ReusableValueCache._key(key)
        if (type(entry) is not tuple or len(entry)!=4 or type(entry[1]) is not int or entry[1]<0
                or any(type(t) not in (int,float) or not isfinite(t) for t in entry[2:])):
            raise BoundaryViolation('source reusable stored entry changed')
        total+=entry[1]
    if total!=cache._units or total>reuse.MAX_RETAINED_UNITS:
        raise BoundaryViolation('source reusable accounting changed')


def prepare(boundary,owner,routine,provenance,*,server=False):
    app=boundary.app;caller=boundary.vm
    if type(app._reuse_routines) is not dict or type(app._direct_source_reuse_entries) is not dict:
        raise BoundaryViolation('source reusable registries changed')
    entry=app._reuse_routines.get(id(routine))
    if app._direct_source_reuse_entries.get(id(routine)) is not entry:
        raise BoundaryViolation('source reusable entry changed')
    if entry is None:return None
    if (type(entry) is not tuple or len(entry)!=5 or entry[0] is not routine
            or entry[1] is not owner or entry[4] is not server
            or not routine.is_function or any(not p.by_value or p.default is not None for p in routine.parameters)):
        raise BoundaryViolation('direct source reuse requires admitted explicit Val function')
    _hooks()
    if type(app._direct_source_reusable) is not tuple or len(app._direct_source_reusable)!=3:
        raise BoundaryViolation('source reusable store seal changed')
    store,session,request_key=app._direct_source_reusable
    seal=owner._direct_source_reuse_seal
    def authorize():
        from .python_direct_source import check_owner,_preflight
        _hooks()
        boundary._check();check_owner(owner);provenance();_preflight(owner,routine)
        if (type(app._reuse_routines) is not dict or type(app._direct_source_reuse_entries) is not dict
                or app._reuse_routines.get(id(routine)) is not entry
                or app._direct_source_reuse_entries.get(id(routine)) is not entry
                or owner._direct_source_reuse_seal is not seal
                or app.reusable_values is not store or type(store) is not ApplicationReusableValues
                or type(store._closed) is not bool or store._session is not session or store._request_key is not request_key
                or type(store._application) is not ReferenceType or store._application() is not app
                or type(store._source_family) is not ReferenceType or store._source_family() is not app.interpreter
                or caller._source_reusable_runtime is not app):
            raise BoundaryViolation('source reusable authority changed')
        definition,xml,source=seal
        if (app.modules.get(definition.name.casefold()) is not definition
                or app.files.get(definition.path) is not xml
                or app.files.get('CommonModules/'+definition.name+'/Ext/Module.bsl') is not source):
            raise BoundaryViolation('source reusable module policy changed')
        for cls,name,expected in _DIRECT_REUSE_ABI:
            if getattr(cls,name) is not expected or (cls is ApplicationReusableValues and name in vars(store)):
                raise BoundaryViolation('source reusable owner hooks changed')
        if (reuse.ApplicationReusableValues is not ApplicationReusableValues
                or reuse.ReusableValueCache is not ReusableValueCache or reuse.argument_key is not _ARGUMENT_KEY):
            raise BoundaryViolation('source reusable factory changed')
        store.authorize(caller);_cache(session)
        state=caller._scheduler.active_context.request_cache
        if type(state) is not dict or any(type(key) is not object for key in state):
            raise BoundaryViolation('source reusable request scope changed')
        # Validate an existing request cache before canonical cache() can use it.
        if request_key in state:_cache(state[request_key])
        selected=store.cache(caller,entry[3]);_cache(selected)
        return selected,state
    authorize()
    def call(values,invoke):
        cache,state=authorize()
        if server:
            from .invocation import _encode_scalar
            for value in values:_encode_scalar(value)
        key=_ARGUMENT_KEY(tuple(values))
        if key is None:raise ValueError('unsupported reusable common-module argument')
        key=(str(entry[2]),routine.name.casefold(),'server' if server else boundary.side,key)
        found,cached=cache.lookup(key)
        if found:
            try:
                if server:_encode_scalar(cached)
                cache.revalidate(key,store.measure(cached))
            except (TypeError,ValueError):
                cache.discard(key);raise
            current,current_state=authorize()
            if current is not cache or current_state is not state:
                raise BoundaryViolation('source reusable scope changed on cache hit')
            return cached
        reservation=cache.reserve(key)
        result=invoke()
        if server:_encode_scalar(result)
        current,current_state=authorize()
        if current is not cache or current_state is not state:
            raise BoundaryViolation('source reusable scope changed before publication')
        units=store.measure(result)
        current,current_state=authorize()
        if current is not cache or current_state is not state:
            raise BoundaryViolation('source reusable scope changed during accounting')
        cache.publish(reservation,result,units)
        return result
    return call
