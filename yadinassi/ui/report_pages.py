"""Detached, bounded pages of an already validated read-only report projection.

This object cannot read a database or resolve a receipt. A page is another view
of the original saved snapshot, not a new query; Refresh must install a new one.
The owning application retires it on form mutation, new filters or shutdown.
"""
import json
import secrets


class ReportPageError(ValueError):
    pass


MAX_ROWS = 1000
MAX_CELLS = 25000
MAX_HEADER_BYTES = 16384
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
MAX_PAGE_BYTES = 65536
PAGE_ROWS = 50


def _encode(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ReportPageError('invalid_projection') from None


class ReportPages:
    """One application-owned sealed snapshot, with opaque idempotent cursors.

    Admission and scalar/column validation precede install. No producer or caller
    receives a mutable alias to retained data. A retired cursor never re-targets
    a later report, even when both have the same source and filter values.
    """
    def __init__(self):
        self._nonce = secrets.token_urlsafe(24)
        self._generation = 0
        self.clear()

    def clear(self):
        self._header = None
        self._rows = ()
        self._bounds = ()
        self._cursors = ()
        self._snapshot = None

    @property
    def active(self):
        return self._header is not None

    def install(self, projection):
        # A failed refresh must not leave navigation into a different old result.
        self.clear()
        if (type(projection) is not dict or type(projection.get('columns')) is not list
                or not 1 <= len(projection['columns']) <= 32
                or type(projection.get('rows')) is not list
                or len(projection['rows']) > MAX_ROWS
                or len(projection['rows']) * len(projection['columns']) > MAX_CELLS
                or 'page' in projection):
            raise ReportPageError('invalid_projection')
        header = _encode({k: v for k, v in projection.items() if k != 'rows'})
        if len(header) > MAX_HEADER_BYTES:
            raise ReportPageError('unsupported')
        rows = []
        size = len(header)
        for row in projection['rows']:
            if type(row) is not list or len(row) != len(projection['columns']):
                raise ReportPageError('invalid_projection')
            raw = _encode(row)
            size += len(raw)
            if size > MAX_SNAPSHOT_BYTES:
                raise ReportPageError('unsupported')
            rows.append(raw)
        # Reserve a conservative fixed budget for opaque cursor metadata. A row
        # is never split or truncated; an oversized row refuses the whole result.
        available = MAX_PAGE_BYTES - len(header) - 1024
        bounds = []
        start = used = 0
        for index, raw in enumerate(rows):
            charge = len(raw) + 1
            if charge > available:
                raise ReportPageError('unsupported')
            if index - start == PAGE_ROWS or used + charge > available:
                bounds.append((start, index))
                start, used = index, 0
            used += charge
        bounds.append((start, len(rows)))
        self._generation += 1
        snapshot = 'report-' + self._nonce + '-' + str(self._generation)
        cursors = tuple('page-' + secrets.token_urlsafe(24) for _ in bounds)
        if len(set(cursors)) != len(cursors):
            raise ReportPageError('unavailable')
        self._header, self._rows = header, tuple(rows)
        self._bounds, self._cursors = tuple(bounds), cursors
        self._snapshot = snapshot
        return self.read(snapshot, cursors[0])

    def read(self, snapshot, cursor):
        if (type(snapshot) is not str or type(cursor) is not str
                or snapshot != self._snapshot or not self.active
                or cursor not in self._cursors):
            raise ReportPageError('retired_page')
        index = self._cursors.index(cursor)
        start, end = self._bounds[index]
        result = json.loads(self._header)
        result['rows'] = [json.loads(raw) for raw in self._rows[start:end]]
        result['page'] = {'snapshot': snapshot, 'cursor': cursor,
            'previous': self._cursors[index - 1] if index else None,
            'next': self._cursors[index + 1] if index + 1 < len(self._bounds) else None,
            'offset': start, 'total': len(self._rows)}
        if len(_encode(result)) > MAX_PAGE_BYTES:
            self.clear()
            raise ReportPageError('unsupported')
        return result
