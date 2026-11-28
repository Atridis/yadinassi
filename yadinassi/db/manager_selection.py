"""Detached bounded pages for manager selections; no retained SQLite leases."""
from yadinassi.db.catalog.catalog_backend import BackendError

PAGE_SIZE = 16
MAX_CATALOG_PAGE_SIZE = 256


class SelectionRows:
    __slots__ = ('_rows','_continuation','_first','_position','current','_requested_size')

    def __init__(self, page, *, restart=False):
        self._first = page if restart else None
        self.install(page)
        self.current = None

    def install(self, page, *, requested_size=PAGE_SIZE):
        self._rows, self._continuation = page
        self._position = 0
        self._requested_size = requested_size

    def next_catalog_page_size(self):
        # Called only at an actual refill; a catalog rewind installs the
        # original first page and starts growth at the beginning again.
        size = self._requested_size
        if type(size) is not int or not PAGE_SIZE <= size <= MAX_CATALOG_PAGE_SIZE:
            raise BackendError('integrity')
        return min(size*2,MAX_CATALOG_PAGE_SIZE)

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
