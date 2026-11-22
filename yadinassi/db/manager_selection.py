"""Detached bounded pages for manager selections; no retained SQLite leases."""
from yadinassi.db.catalog.catalog_backend import BackendError

PAGE_SIZE = 16


class SelectionRows:
    __slots__ = ('_rows','_continuation','_first','_position','current')

    def __init__(self, page, *, restart=False):
        self._first = page if restart else None
        self.install(page)
        self.current = None

    def install(self, page):
        self._rows, self._continuation = page
        self._position = 0

    def continuation(self):
        if type(self._rows) is not tuple or type(self._position) is not int:
            raise BackendError('integrity')
        return self._continuation if self._position == len(self._rows) else None

    def next(self):
        if self._position == len(self._rows):
            first = self._first
            if first is None:
                self.current = None
            elif type(first) is tuple and len(first) == 2 and type(first[0]) is tuple:
                self.install(first)
            else:
                raise BackendError('integrity')
            return False
        self.current = self._rows[self._position]
        self._position += 1
        return True


def current_selection_row(state):
    if type(state) is not SelectionRows: raise BackendError('integrity')
    return state.current


def require_continuation(after, arity):
    if type(after) is not tuple or len(after) != arity or any(type(key) is not str for key in after):
        raise BackendError('invalid_input')
