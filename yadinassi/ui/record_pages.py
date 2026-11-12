"""Ограниченные снимки списков: короткое чтение, без живых SQL-курсоров в UI.

Поиск и сортировка являются host UI semantics, не заявлением native parity.
В navigation нет идентификаторов базы/записей; capabilities строк выдаёт broker.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import secrets
import re
from uuid import UUID

from ..catalog_backend import (BackendError, CatalogKey, CatalogSchema, CatalogScanRequest,
    CatalogOrder, CatalogValuePage, CatalogValueRow)
from ..document_backend import (DocumentSchema, DocumentKey, DocumentScanRequest,
    DocumentValuePage, DocumentValueRow)

MAX_RECORDS = 8192
MAX_BYTES = 4 * 1024 * 1024
PAGE_SIZE = 50
MAX_GENERATION = 2147483647


@dataclass(frozen=True, slots=True)
class RecordRow:
    key: CatalogKey | DocumentKey
    values: tuple


@dataclass(frozen=True, slots=True)
class RecordSnapshot:
    database_id: UUID
    generation: int
    source_digest: str
    schema_id: UUID
    document: bool
    rows: tuple[RecordRow, ...]


@dataclass(frozen=True, slots=True)
class RecordPage:
    entry: int
    snapshot: str
    page: int
    pages: int
    total: int
    query: str
    order: str
    previous: str | None
    next: str | None
    rows: tuple[RecordRow, ...]

    @property
    def navigation(self):
        return {name:getattr(self,name) for name in
                ('snapshot','page','pages','total','query','order','previous','next')}


def validate_navigation(navigation, *, document, row_count):
    names = {'snapshot','page','pages','total','query','order','previous','next'}
    if type(navigation) is not dict or set(navigation) != names or type(document) is not bool:
        raise BackendError('invalid_input')
    n = navigation
    if (any(type(n[k]) is not int for k in ('page','pages','total')) or type(row_count) is not int
            or not 0 <= n['total'] <= MAX_RECORDS
            or n['pages'] != max(1,(n['total']+PAGE_SIZE-1)//PAGE_SIZE)
            or not 1 <= n['page'] <= n['pages']
            or row_count != min(PAGE_SIZE,max(0,n['total']-(n['page']-1)*PAGE_SIZE))
            or type(n['snapshot']) is not str
            or re.fullmatch(r'records-[0-9a-f]{32}-[1-9][0-9]{0,9}',n['snapshot']) is None
            or int(n['snapshot'].rsplit('-',1)[1]) > MAX_GENERATION):
        raise BackendError('invalid_input')
    _text(n['query'],128)
    if type(n['order']) is not str or n['order'] not in (('date','number') if document else ('code','description')):
        raise BackendError('invalid_input')
    for name, absent in (('previous',n['page']==1),('next',n['page']==n['pages'])):
        token=n[name]
        if absent:
            if token is not None: raise BackendError('invalid_input')
        elif type(token) is not str or re.fullmatch(r'records-page-[0-9a-f]{32}',token) is None:
            raise BackendError('invalid_input')
    if n['previous'] is not None and n['previous']==n['next']:
        raise BackendError('invalid_input')


def _text(value, limit):
    if type(value) is not str or len(value) > limit or '\x00' in value:
        raise BackendError('invalid_input')
    try: return len(value.encode('utf-8'))
    except UnicodeError: raise BackendError('invalid_input') from None


def _source(files):
    if type(files) is not dict or not 1 <= len(files) <= 2048:
        raise BackendError('invalid_input')
    size = 0
    for path, raw in files.items():
        size += _text(path, 256)
        if type(raw) is not bytes or len(raw) > 1048576:
            raise BackendError('invalid_input')
        size += len(raw)
    if size > 8 * 1024 * 1024: raise BackendError('unsupported')
    return sha256(b''.join(p.encode()+b'\0'+sha256(raw).digest()
                          for p, raw in sorted(files.items()))).hexdigest()


def _row(row, document, database, schema_id):
    if type(row) is not RecordRow or type(row.values) is not tuple:
        raise BackendError('integrity')
    key = row.key
    cls = DocumentKey if document else CatalogKey
    if (type(key) is not cls or type(key.database_id) is not UUID
            or type(key.record_id) is not UUID or not key.record_id.int
            or key.database_id != database):
        raise BackendError('integrity')
    target = key.document_id if document else key.catalog_id
    if type(target) is not UUID or target != schema_id: raise BackendError('integrity')
    values = row.values
    if len(values) != (4 if document else 3): raise BackendError('integrity')
    size = 64 + _text(values[0], 1024)
    if document:
        if (type(values[1]) is not datetime or values[1].tzinfo is not None
                or values[1].microsecond or values[1].fold or type(values[3]) is not bool):
            raise BackendError('integrity')
        size += 32
    else: size += _text(values[1], 1152)
    if type(values[2]) is not bool: raise BackendError('integrity')
    return size


def load_record_snapshot(backend, schema, *, document=False, source_files):
    from ..sqlite_catalog import SQLiteCatalogBackend
    from ..database_transactions import require_admission, current
    require_admission()
    if (type(backend) is not SQLiteCatalogBackend or type(document) is not bool
            or type(schema) is not (DocumentSchema if document else CatalogSchema)
            or current(backend) is not None):
        raise BackendError('unsupported')
    digest = _source(source_files)
    if backend.export_configuration() != source_files: raise BackendError('schema_changed')
    identity = (backend.database_id, backend.configuration_generation)
    view = backend.begin_document_read() if document else backend.begin_read()
    rows, seen, tokens, size = [], set(), set(), 0
    try:
        if (view.database_id, view.configuration_generation) != identity:
            raise BackendError('schema_changed')
        actual = view.document_schema(schema.identity) if document else view.catalog_schema(schema.identity)
        if actual != schema: raise BackendError('schema_changed')
        token = None
        while True:
            if document:
                page = view.scan_document_values(schema.identity, DocumentScanRequest(256, token),
                    ('number', 'date', 'deletion_mark', 'posted'))
                page_type, row_type = DocumentValuePage, DocumentValueRow
            else:
                page = view.scan_catalog_values(schema.identity,
                    CatalogScanRequest(order=(CatalogOrder('code'),), page_size=256, continuation=token),
                    ('code', 'description', 'deletion_mark'))
                page_type, row_type = CatalogValuePage, CatalogValueRow
            if type(page) is not page_type or type(page.rows) is not tuple or len(page.rows) > 256:
                raise BackendError('integrity')
            for value in page.rows:
                if type(value) is not row_type: raise BackendError('integrity')
                row = RecordRow(value.key, value.values)
                size += _row(row, document, identity[0], schema.identity)
                if row.key in seen: raise BackendError('integrity')
                seen.add(row.key); rows.append(row)
                if len(rows) > MAX_RECORDS or size > MAX_BYTES: raise BackendError('unsupported')
            token = page.continuation
            if token is None: break
            if (type(token) is not str or len(token) != 32 or token in tokens or not page.rows
                    or any(c not in '0123456789abcdef' for c in token)):
                raise BackendError('integrity')
            tokens.add(token)
    finally:
        view.close()
    if ((backend.database_id, backend.configuration_generation) != identity
            or backend.export_configuration() != source_files):
        raise BackendError('schema_changed')
    return RecordSnapshot(*identity, digest, schema.identity, document, tuple(rows))


class RecordPages:
    """Один detached snapshot и не более двух актуальных токенов навигации."""
    def __init__(self, source_files):
        _source(source_files)
        self._source_files = dict(source_files)
        self._backend = None
        self._generation = 0
        self.clear()

    def clear(self):
        self._snapshot = None
        self._tokens = {}
        self._token = None
        self._rows = ()
        self._page = 1
        self._entry = None
        self._query = ''
        self._order = None

    def capture(self, context, entry, catalog_schema=None, document_schema=None,
                query='', order=None, page=0):
        from ..database_context import SQLiteDBContext
        if (type(context) is not SQLiteDBContext or (catalog_schema is None) == (document_schema is None)
                or type(page) is not int or page < 0):
            raise BackendError('invalid_input')
        self.clear()
        self._backend = context.backend
        try:
            snapshot = load_record_snapshot(context.backend,
                document_schema if document_schema is not None else catalog_schema,
                document=document_schema is not None, source_files=self._source_files)
            self.replace(snapshot,entry=entry,query=query,order=order)
            self._page = min(max(1,page),max(1,(len(self._rows)+PAGE_SIZE-1)//PAGE_SIZE))
            return self._project()
        except BaseException:
            self.clear()
            raise

    def _verify_context(self, context):
        from ..database_context import SQLiteDBContext
        if (type(context) is not SQLiteDBContext or context.backend is not self._backend
                or self._snapshot is None):
            raise BackendError('schema_changed')
        backend = context.backend
        if ((backend.database_id,backend.configuration_generation) !=
                (self._snapshot.database_id,self._snapshot.generation)
                or backend.export_configuration() != self._source_files):
            self.clear()
            raise BackendError('schema_changed')

    def replace(self, snapshot, *, entry, query='', order=None, preserve_page=False):
        if (type(snapshot) is not RecordSnapshot or type(entry) is not int or entry < 1
                or type(preserve_page) is not bool or type(snapshot.document) is not bool
                or type(snapshot.rows) is not tuple or len(snapshot.rows) > MAX_RECORDS
                or type(snapshot.database_id) is not UUID or not snapshot.database_id.int
                or type(snapshot.schema_id) is not UUID or not snapshot.schema_id.int
                or type(snapshot.generation) is not int or snapshot.generation < 1
                or type(snapshot.source_digest) is not str or len(snapshot.source_digest) != 64
                or any(c not in '0123456789abcdef' for c in snapshot.source_digest)):
            raise BackendError('invalid_input')
        size = sum(_row(row,snapshot.document,snapshot.database_id,snapshot.schema_id) for row in snapshot.rows)
        if size > MAX_BYTES or len({r.key for r in snapshot.rows}) != len(snapshot.rows):
            raise BackendError('unsupported')
        _text(query, 128)
        order = order or ('date' if snapshot.document else 'code')
        if type(order) is not str or order not in (('date','number') if snapshot.document else ('code','description')):
            raise BackendError('invalid_input')
        same = (self._snapshot is not None and self._entry == entry and self._query == query
            and self._order == order and
            (self._snapshot.database_id,self._snapshot.generation,self._snapshot.source_digest,self._snapshot.schema_id) ==
            (snapshot.database_id,snapshot.generation,snapshot.source_digest,snapshot.schema_id))
        old_page = self._page if preserve_page and same else 1
        folded = query.casefold()
        rows = tuple(r for r in snapshot.rows if not folded or
                     any(folded in v.casefold() for v in (r.values[:1] if snapshot.document else r.values[:2])))
        def sort(row):
            a,b = row.values[:2]
            if snapshot.document: return (b,a,row.key.record_id.int) if order=='date' else (a.casefold(),b,row.key.record_id.int)
            return (a.casefold(),b.casefold(),row.key.record_id.int) if order=='code' else (b.casefold(),a.casefold(),row.key.record_id.int)
        rows = tuple(sorted(rows,key=sort))
        if self._generation >= MAX_GENERATION: raise BackendError('unsupported')
        self._generation += 1
        self._snapshot,self._entry,self._query,self._order = snapshot,entry,query,order
        self._rows = rows
        self._token = 'records-'+secrets.token_hex(16)+'-'+str(self._generation)
        self._page = min(old_page,max(1,(len(rows)+PAGE_SIZE-1)//PAGE_SIZE))
        return self._project()

    def filter(self, context, *, query, order=None):
        self._verify_context(context)
        if self._snapshot is None: raise BackendError('invalid_input')
        return self.replace(self._snapshot,entry=self._entry,query=query,order=order or self._order)

    def navigate(self, context, snapshot_token, cursor):
        self._verify_context(context)
        if (type(snapshot_token) is not str or snapshot_token != self._token
                or type(cursor) is not str or cursor not in self._tokens):
            raise BackendError('invalid_input')
        self._page = self._tokens[cursor]
        return self._project()

    def _project(self):
        pages = max(1,(len(self._rows)+PAGE_SIZE-1)//PAGE_SIZE)
        self._tokens = {}
        def token(page):
            if not 1 <= page <= pages: return None
            value = 'records-page-'+secrets.token_hex(16)
            self._tokens[value] = page
            return value
        previous,next_page = token(self._page-1),token(self._page+1)
        return RecordPage(self._entry,self._token,self._page,pages,len(self._rows),self._query,
            self._order,previous,next_page,self._rows[(self._page-1)*PAGE_SIZE:self._page*PAGE_SIZE])
