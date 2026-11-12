"""Bounded application-owned client reuse; not a global or distributed cache."""
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from time import monotonic

MAX_AGE_SECONDS=1200
MAX_IDLE_SECONDS=360
MAX_ENTRIES=256
MAX_RETAINED_UNITS=16*1024*1024

@dataclass(frozen=True,slots=True)
class Reservation:
    owner: object
    epoch: int
    key: tuple

class ReusableValueCache:
    """Aliased values are remeasured on reuse; accounting is not a live heap cap."""
    def __init__(self,*,clock=monotonic):
        self._clock=clock;self._identity=object();self._epoch=0
        self._entries=OrderedDict();self._units=0;self._closed=False
    def _open(self):
        if self._closed:raise ValueError('reusable cache is closed')
    @staticmethod
    def _key(key):
        if type(key) is not tuple:raise TypeError('cache key must be a canonical tuple')
        pending=[(key,0)];count=units=0
        while pending:
            item,depth=pending.pop();count+=1
            if count>4096 or depth>32:raise ValueError('cache key too large')
            if type(item) is tuple:
                if len(item)>4096-count-len(pending):raise ValueError('cache key too large')
                pending.extend((child,depth+1) for child in item)
            elif type(item) not in (str,int,bool,bytes,type(None)):raise TypeError('unsupported key field')
            elif type(item) in (str,bytes):
                if len(item)>65536:raise ValueError('key field too large')
                units+=len(item)*(4 if type(item) is str else 1)
            elif type(item) is int:
                if item.bit_length()>8192:raise ValueError('key integer too large')
                units+=32+(item.bit_length()+7)//8
            if units>1024*1024:raise ValueError('key too large')
        return units+32*count
    def lookup(self,key):
        self._open();self._key(key);entry=self._entries.get(key)
        if entry is None:return False,None
        now=self._clock()
        if now-entry[2]>=MAX_AGE_SECONDS or now-entry[3]>=MAX_IDLE_SECONDS:
            self.discard(key);return False,None
        self._entries[key]=(entry[0],entry[1],entry[2],now);self._entries.move_to_end(key)
        return True,entry[0]
    def reserve(self,key):
        self._open();self._key(key);return Reservation(self._identity,self._epoch,key)
    def publish(self,reservation,value,retained_units):
        self._open()
        if type(reservation) is not Reservation or reservation.owner is not self._identity:raise ValueError('foreign reservation')
        if type(retained_units) is not int or not 0<=retained_units<=MAX_RETAINED_UNITS:raise ValueError('retention bound')
        if reservation.epoch!=self._epoch:return False
        key=reservation.key;units=retained_units+self._key(key)
        if units>MAX_RETAINED_UNITS:raise ValueError('retention bound')
        self.discard(key)
        while self._entries and (len(self._entries)>=MAX_ENTRIES or self._units+units>MAX_RETAINED_UNITS):
            _,old=self._entries.popitem(last=False);self._units-=old[1]
        now=self._clock();self._entries[key]=(value,units,now,now);self._units+=units;return True
    def revalidate(self,key,retained_units):
        self._open();entry=self._entries.get(key)
        if entry is None:return
        if type(retained_units) is not int or retained_units<0:raise ValueError('invalid retention estimate')
        units=retained_units+self._key(key)
        if units>MAX_RETAINED_UNITS:
            self.discard(key);raise ValueError('mutated value exceeds retention bound')
        self._units+=units-entry[1];self._entries[key]=(entry[0],units,entry[2],entry[3]);self._entries.move_to_end(key)
        while self._units>MAX_RETAINED_UNITS:
            _,old=self._entries.popitem(last=False);self._units-=old[1]
    def discard(self,key):
        self._open();entry=self._entries.pop(key,None)
        if entry is not None:self._units-=entry[1]
    def refresh(self):
        self._open();self._epoch+=1;self._entries.clear();self._units=0
    def close(self):
        if not self._closed:self.refresh();self._closed=True

def argument_key(values):
    """Closed typed primitive/flat Structure keys; unsupported inputs refuse."""
    from .dates import BSLDate
    from .structures import BSLStructure
    from .values import NULL
    def scalar(value):
        if value is None:return ('undefined',)
        if value is NULL:return ('null',)
        if type(value) is bool:return ('boolean',value)
        if type(value) is str:return ('string',value) if len(value)<=65536 else None
        if type(value) is BSLDate:return None if value.boundary else ('date',value.ticks)
        if type(value) is Decimal:
            if not value.is_finite() or value.__sizeof__()>4096:return None
            sign,digits,exponent=value.as_tuple()
            if len(digits)>4096 or abs(exponent)>100000:return None
            digits=list(digits)
            if not any(digits):return ('number',0,(),0)
            while digits[-1]==0:digits.pop();exponent+=1
            return ('number',sign,tuple(digits),exponent)
        return None
    if type(values) is not tuple or len(values)>128:return None
    result=[]
    for value in values:
        part=scalar(value)
        if part is None and type(value) is BSLStructure:
            if len(value._items)>128:return None
            fields=[]
            for name,(_,item) in value._items.items():
                leaf=scalar(item)
                if leaf is None:return None
                fields.append((name,leaf))
            part=('structure',tuple(sorted(fields)))
        if part is None:return None
        result.append(part)
    result=tuple(result)
    try:ReusableValueCache._key(result)
    except (ValueError,TypeError):return None
    return result

def refresh_reusable_marker():
    raise ValueError('reusable values require an active configuration application')

def _snapshot_cost(snapshot):
    # Local recovery seam: same immutable snapshot walk as pending #290 storage;
    # no storage API or dependency is introduced before that branch merges.
    pending=[snapshot._root];nodes=units=0
    while pending:
        value=pending.pop();nodes+=1
        if nodes>100000:raise ValueError('reusable snapshot node quota')
        if type(value) is tuple:units+=32+8*len(value);pending.extend(value)
        elif type(value) is str:units+=64+4*len(value)
        elif type(value) is bytes:units+=64+len(value)
        elif type(value) is Decimal:units+=Decimal.__sizeof__(value)
        elif type(value) in (int,bool) or value is None:units+=32
        else:raise ValueError('unknown private snapshot field')
        if units>MAX_RETAINED_UNITS:raise ValueError('reusable snapshot byte quota')
    return units

class ApplicationReusableValues:
    def __init__(self,application):
        import weakref
        self._application=weakref.ref(application);self._session=ReusableValueCache();self._closed=False;self._request_key=object()
    def authorize(self,caller):
        app=self._application()
        if (self._closed or app is None or caller._configuration_runtime is not app or caller._family_owner is not app.interpreter or caller._scheduler is not app.interpreter._scheduler):raise ValueError('foreign reusable owner')
        app.require_open();caller._require_family()
        if app.state not in ('starting','running','before_exit','exiting') or caller.execution_context!='client':raise ValueError('active client application required')
        if caller._scheduler._active_task is not None:raise ValueError('async reusable continuations unsupported')
        return app
    @staticmethod
    def measure(value):
        from .value_storage import capture
        return _snapshot_cost(capture(value))
    def cache(self,caller,mode):
        self.authorize(caller)
        if mode=='DuringSession':return self._session
        if mode!='DuringRequest':raise ValueError('unsupported reuse scope')
        state=caller._scheduler.active_context.request_cache
        if state is None:raise ValueError('synchronous request boundary required')
        if self._request_key not in state:state[self._request_key]=ReusableValueCache()
        return state[self._request_key]
    def refresh(self,caller):
        self.authorize(caller);self._session.refresh();state=caller._scheduler.active_context.request_cache
        if state is not None and self._request_key in state:state[self._request_key].refresh()
    def close(self):
        self._session.close();self._closed=True
