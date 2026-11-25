"""Live source application instances with a reverse identity lookup."""
from collections.abc import MutableMapping


class SourceInstances(MutableMapping):
    def __init__(self):
        self._forward = {}
        self._reverse = {}
        self._next = 0

    def __getitem__(self, key):
        return self._forward[key][0]

    def __contains__(self, key):
        return key in self._forward

    def get(self, key, default=None):
        entry = self._forward.get(key)
        return default if entry is None else entry[0]

    def __setitem__(self, key, owner):
        # The runtime's keys are source names or three-part role keys. Their
        # hashes and equality never execute Python code during a mutation.
        if not (type(key) is str or type(key) is tuple and
                all(type(part) is str or type(part) is bool for part in key)):
            raise TypeError('noncanonical source instance key')
        previous = self._forward.get(key)
        if previous is None:
            order = self._next
            self._next += 1
        else:
            old, order = previous
            if old is owner:
                return
            self._forget(key, old)
        self._forward[key] = owner, order
        self._reverse.setdefault(id(owner), {})[key] = order

    def _forget(self, key, owner):
        identity = id(owner)
        bucket = self._reverse[identity]
        del bucket[key]
        if not bucket:
            del self._reverse[identity]

    def __delitem__(self, key):
        owner, _ = self._forward.pop(key)
        self._forget(key, owner)

    def __iter__(self):
        return iter(self._forward)

    def __len__(self):
        return len(self._forward)

    def clear(self):
        # Keep all owners alive until both structures show the cleared state.
        previous = self._forward
        self._forward = {}
        self._reverse = {}
        self._next = 0
        previous.clear()

    def keys_for_owner(self, owner):
        bucket = self._reverse.get(id(owner))
        if not bucket:
            return ()
        if len(bucket) == 1:
            return tuple(bucket)
        # Replacement does not reposition an existing forward key.
        return tuple(sorted(bucket, key=bucket.__getitem__))


def instance_keys(app, owner):
    registry = app._instances
    if type(registry) is not SourceInstances:
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        raise BoundaryViolation('source instance registry changed')
    return registry.keys_for_owner(owner)
