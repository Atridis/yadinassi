"""Backend-owned positive source admission, never a parser/VM authority cache.

Callers still read, bound and hash actual source bytes and validate persisted
metadata in their current SQLite snapshot. Keys include the complete checked
source inventory and database/profile/schema identity. Only immutable importer
results are retained, and only after the caller's entire admission succeeds.
There is no process-wide state, negative cache or connection data_version key.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Admission:
    key: tuple
    value: object


class PreparedSource:
    """One bounded positive admission for one backend's fixed source profile."""
    __slots__ = ('_entry',)

    def __init__(self):
        self._entry = None

    def lookup(self, key):
        entry = self._entry
        return entry.value if entry is not None and entry.key == key else None

    def remember(self, key, value):
        # Publishing is deliberately separate from parsing: schema/marker/row
        # admission must finish first. An exception cannot publish a candidate.
        if type(key) is not tuple or value is None:
            raise TypeError('prepared source requires a complete positive admission')
        # A backend is admitted to one fixed source identity. A different
        # candidate must still go through every caller guard, but must not
        # replace that identity while an outer comparison can still reject it.
        if self._entry is None:
            self._entry = _Admission(key, value)

    def clear(self):
        self._entry = None
