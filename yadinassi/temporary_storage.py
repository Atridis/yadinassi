"""Application-owned values with measured same-context aliasing; no disk storage."""
from decimal import Decimal
import re
import weakref
from .unique_identifiers import BSLUUID
from .value_storage import capture

MAX_ENTRIES=128
MAX_RETAINED_UNITS=32*1024*1024
MAX_SNAPSHOT_NODES=100000
_ADDRESS=re.compile(r'yadinassi-temp:[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}')
_OMITTED=object()


def put_marker(*args):
    raise ValueError('temporary storage requires the executing application')
def get_marker(*args):
    raise ValueError('temporary storage requires the executing application')
def delete_marker(*args):
    raise ValueError('temporary storage requires the executing application')
def recognize_marker(*args):
    raise ValueError('temporary storage requires the executing application')
MARKERS=(put_marker,get_marker,delete_marker,recognize_marker)


def _cost(snapshot):
    # Capture has already admitted an immutable private graph. Charge exact
    # string/binary bytes plus bounded structural and Decimal storage overhead.
    pending=[snapshot._root];nodes=0;units=0
    while pending:
        value=pending.pop();nodes+=1
        if nodes>MAX_SNAPSHOT_NODES:raise ValueError('temporary storage node quota exceeded')
        if type(value) is tuple:
            units+=32+8*len(value);pending.extend(value)
        elif type(value) is str:units+=64+4*len(value)
        elif type(value) is bytes:units+=64+len(value)
        elif type(value) is Decimal:units+=Decimal.__sizeof__(value)
        elif type(value) in (int,bool) or value is None:units+=32
        else:raise ValueError('unknown private snapshot field')
        if units>MAX_RETAINED_UNITS:raise ValueError('temporary storage byte quota exceeded')
    return units,nodes


class ApplicationTemporaryStorage:
    def __init__(self,application):
        self._application=weakref.ref(application)
        self._entries={}
        self._units=0
        self._nodes=0
        self._closed=False

    def authorize(self,caller):
        app=self._application()
        if (self._closed or app is None or caller._configuration_runtime is not app
                or caller._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler):
            raise ValueError('temporary storage belongs to another or closed application')
        app.require_open();caller._require_family()
        if app.state not in ('starting','running') or caller.execution_context!='server':
            raise ValueError('temporary storage requires an active server application context')
        return app

    @staticmethod
    def is_address(address):
        return type(address) is str and len(address)==51 and _ADDRESS.fullmatch(address) is not None

    def put(self,caller,value,owner=_OMITTED):
        self.authorize(caller)
        if type(owner) is BSLUUID:
            address='yadinassi-temp:'+BSLUUID().text
            if address in self._entries:raise ValueError('temporary storage address collision')
            owner_id=owner.text
            previous=None
            if len(self._entries)>=MAX_ENTRIES:raise ValueError('temporary storage entry quota exceeded')
        elif self.is_address(owner) and owner in self._entries:
            address=owner;previous=self._entries[address];owner_id=previous[3]
        else:
            # Ownerless/cross-event and missing-address behavior await native
            # measurement. Do not silently create persistent ambient storage.
            raise ValueError('temporary storage requires an explicit UUID owner or owned existing address')
        # Native same-server-context storage retains collection identity. The
        # snapshot is validation/accounting only; never substitute its copy.
        costs=self._measure(excluding=address if previous is not None else None)
        units,nodes=_cost(capture(value))
        next_units=sum(c[0] for c in costs.values())+units
        next_nodes=sum(c[1] for c in costs.values())+nodes
        if next_units>MAX_RETAINED_UNITS or next_nodes>MAX_SNAPSHOT_NODES:
            raise ValueError('temporary storage aggregate quota exceeded')
        self._apply_costs(costs)
        self._entries[address]=(value,units,nodes,owner_id)
        self._units=next_units;self._nodes=next_nodes
        return address

    def _measure(self,excluding=None):
        costs={};units=0;nodes=0
        for address,entry in self._entries.items():
            if address==excluding:continue
            cost=_cost(capture(entry[0]));units+=cost[0];nodes+=cost[1]
            if units>MAX_RETAINED_UNITS or nodes>MAX_SNAPSHOT_NODES:
                raise ValueError('temporary storage aggregate quota exceeded')
            costs[address]=cost
        return costs

    def _apply_costs(self,costs):
        for address,(units,nodes) in costs.items():
            old=self._entries[address]
            self._entries[address]=(old[0],units,nodes,old[3])
        self._units=sum(entry[1] for entry in self._entries.values())
        self._nodes=sum(entry[2] for entry in self._entries.values())

    def get(self,caller,address):
        self.authorize(caller)
        if not self.is_address(address):raise ValueError('invalid temporary storage address')
        entry=self._entries.get(address)
        if entry is None:return None
        self._apply_costs(self._measure())
        return entry[0]

    def delete(self,caller,address):
        self.authorize(caller)
        if not self.is_address(address):raise ValueError('invalid temporary storage address')
        entry=self._entries.pop(address,None)
        if entry is not None:self._units-=entry[1];self._nodes-=entry[2]

    def recognize(self,caller,address):
        self.authorize(caller)
        if type(address) is not str:raise TypeError('temporary storage address requires String')
        return self.is_address(address)

    def close(self):
        self._closed=True;self._entries.clear();self._units=0;self._nodes=0

    def invoke(self,caller,marker,arguments):
        self.authorize(caller)
        if marker is put_marker and 1<=len(arguments)<=2:return self.put(caller,*arguments)
        if len(arguments)!=1:raise TypeError('temporary storage function arity')
        if marker is get_marker:return self.get(caller,*arguments)
        if marker is delete_marker:return self.delete(caller,*arguments)
        if marker is recognize_marker:return self.recognize(caller,*arguments)
        raise ValueError('unknown temporary storage operation')
