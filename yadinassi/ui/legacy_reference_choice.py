"""Host-owned выбор ссылки autoform; не предоставляет права записи.

Интегратор проверяет busy/source/row в witness и применяет возвращённую ссылку
через существующий typed change. На wire нет новых идентификаторов записей.
"""
import secrets
from uuid import UUID

from .catalog_view import CatalogRepository
from .protocol import CatalogRef, UIError, encode_line

PAGE_SIZE = 32
MAX_ACTIONS = 1024


def _immutable(value):
    return (type(value) in (str, int, bool, UUID, type(None), CatalogRef)
            or type(value) is tuple and all(_immutable(item) for item in value))


class LegacyReferenceChooser:
    def __init__(self, backend, target, witness, *, preflight=encode_line):
        if type(target) is not UUID or not target.int or not callable(witness) or not callable(preflight):
            raise TypeError('explicit legacy chooser owner required')
        self._backend, self._target = backend, target
        self._witness, self._preflight = witness, preflight
        self._pin = None
        self._ticket = None
        self._snapshot = None
        self._choices, self._cursors = {}, {}
        self._query, self._page, self._actions = '', 0, 0

    def _check(self, ticket):
        if type(ticket) is not str or self._ticket is None or ticket != self._ticket:
            raise UIError('invalid_value')
        try:
            current = self._witness()
        except BaseException:
            self.cancel()
            raise
        if current != self._pin:
            self.cancel()
            raise UIError('catalog_unavailable')
        if self._actions >= MAX_ACTIONS:
            self.cancel()
            raise UIError('message_limit')

    def _load(self):
        repository = CatalogRepository(self._backend, own_backend=False)
        try:
            return repository.load_summary(str(self._target))
        finally:
            repository.close()

    def _publish(self, snapshot, query, page, pin, ticket):
        # select validates the query before any state is published.
        selected = snapshot.select(query=query)
        rows = tuple(row for row in selected.cards if not row.values[2])
        pages = max(1, (len(rows)+PAGE_SIZE-1)//PAGE_SIZE)
        if type(page) is not int or not 0 <= page < pages:
            raise UIError('page')
        cursors = {}
        previous = next_cursor = None
        if page:
            previous = 'legacy-reference-page-'+secrets.token_hex(16)
            cursors[previous] = page-1
        if page+1 < pages:
            next_cursor = 'legacy-reference-page-'+secrets.token_hex(16)
            cursors[next_cursor] = page+1
        choices, wire = {}, []
        for row in rows[page*PAGE_SIZE:(page+1)*PAGE_SIZE]:
            token = secrets.token_hex(16)
            if token in choices:
                raise UIError('catalog_unavailable')
            choices[token] = row.reference
            wire.append({'choice': token, 'code': row.values[0], 'description': row.values[1]})
        result = {'ticket': ticket, 'rows': wire, 'navigation': {
            'page': page+1, 'pages': pages, 'total': len(rows), 'query': query,
            'previous': previous, 'next': next_cursor}}
        self._preflight(result)
        if self._witness() != pin:
            raise UIError('catalog_unavailable')
        self._snapshot, self._pin, self._ticket = snapshot, pin, ticket
        self._choices, self._cursors = choices, cursors
        self._query, self._page = query, page
        self._actions += 1
        return result

    def begin(self):
        self.cancel()
        pin = self._witness()
        # Witness must be a detached immutable tuple supplied by the controller.
        if type(pin) is not tuple or not pin or not _immutable(pin):
            raise UIError('invalid_value')
        return self._publish(self._load(), '', 0, pin, secrets.token_hex(16))

    def search(self, ticket, query):
        self._check(ticket)
        return self._publish(self._snapshot, query, 0, self._pin, ticket)

    def page(self, ticket, cursor):
        self._check(ticket)
        if type(cursor) is not str or cursor not in self._cursors:
            raise UIError('page')
        return self._publish(self._snapshot, self._query, self._cursors[cursor], self._pin, ticket)

    def refresh(self, ticket):
        self._check(ticket)
        return self._publish(self._load(), self._query, 0, self._pin, ticket)

    def apply(self, ticket, choice):
        self._check(ticket)
        if type(choice) is not str or choice not in self._choices:
            raise UIError('invalid_value')
        reference = self._choices[choice]
        repository = CatalogRepository(self._backend, own_backend=False)
        try:
            fresh = repository.load(str(self._target), summary_only=True, record=UUID(reference.record))
            card = fresh.card(reference)
            if card.values[2]:
                raise UIError('record_not_found')
        finally:
            repository.close()
        self._check(ticket)
        self.cancel()
        return reference

    def clear(self, ticket):
        self._check(ticket)
        reference = CatalogRef(str(self._target), str(UUID(int=0)))
        self.cancel()
        return reference

    def cancel(self):
        self._pin = self._ticket = self._snapshot = None
        self._choices, self._cursors = {}, {}
        self._query, self._page, self._actions = '', 0, 0
