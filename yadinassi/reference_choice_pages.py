"""Detached catalog chooser pages; no form authority or browser identities."""
from secrets import token_hex
from uuid import UUID
from .catalog_backend import (BackendError,CatalogKey,CatalogComparison,CatalogPredicate,
    CatalogOrder,CatalogScanRequest,CatalogValuePage,CatalogValueRow)

MAX_ROWS=8192
MAX_BYTES=4*1024*1024
PAGE_SIZE=32
MAX_NAVIGATIONS=1024


class SnapshotLimit(Exception):
    pass


def load_choices(manager, code=''):
    if type(code) is not str or len(code)>manager._schema.code_length or '\x00' in code:
        raise ValueError('bounded exact code required')
    predicate=CatalogComparison('deletion_mark','eq',False)
    if code:predicate=CatalogPredicate('and',(predicate,CatalogComparison('code','eq',code)))
    view=manager._view(); rows=[]; seen=set(); cursors=set(); size=0
    try:
        token=None
        while True:
            page=view.scan_catalog_values(manager._schema.identity,
                CatalogScanRequest(predicate=predicate,order=(CatalogOrder('code'),),page_size=256,
                                   continuation=token),('code','description'))
            if type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows)>256:
                raise BackendError('integrity')
            for record in page.rows:
                if (type(record) is not CatalogValueRow or type(record.key) is not CatalogKey
                        or any(type(v) is not UUID for v in (record.key.database_id,record.key.catalog_id,record.key.record_id))
                        or record.key.database_id!=view.database_id or record.key.catalog_id!=manager._schema.identity
                        or not record.key.record_id.int or record.key in seen
                        or type(record.values) is not tuple or len(record.values)!=2
                        or any(type(v) is not str or '\x00' in v for v in record.values)
                        or len(record.values[0])>manager._schema.code_length
                        or len(record.values[1])>manager._schema.description_length):
                    raise BackendError('integrity')
                try:size+=64+sum(len(v.encode('utf-8')) for v in record.values)
                except UnicodeError:raise BackendError('integrity') from None
                seen.add(record.key);rows.append(record)
                if len(rows)>MAX_ROWS or size>MAX_BYTES:raise SnapshotLimit()
            token=page.continuation
            if token is None:break
            if (type(token) is not str or len(token)!=32 or any(c not in '0123456789abcdef' for c in token)
                    or token in cursors or not page.rows):raise BackendError('integrity')
            cursors.add(token)
        return ChoicePages(tuple(rows), full=not code)
    finally:view.close()


class ChoicePages:
    def __init__(self, rows, *, full):
        self.rows=rows;self.full=full;self.query='';self.page=1
        self.filtered=rows;self.cursors={};self.issued=0

    def search(self, query):
        if type(query) is not str or len(query)>128 or '\x00' in query:raise ValueError('bounded query required')
        try:query.encode('utf-8')
        except UnicodeError:raise ValueError('bounded query required') from None
        self.query=query;self.page=1
        folded=query.casefold()
        self.filtered=tuple(r for r in self.rows if any(folded in v.casefold() for v in r.values))

    def turn(self, cursor):
        if type(cursor) is not str or cursor not in self.cursors:raise ValueError('retired choice page')
        self.page=self.cursors[cursor]

    def project(self):
        if self.issued>=MAX_NAVIGATIONS:raise ValueError('choice page budget')
        self.issued+=1;self.cursors={}
        pages=max(1,(len(self.filtered)+PAGE_SIZE-1)//PAGE_SIZE)
        def cursor(page):
            if not 1<=page<=pages:return None
            token='reference-page-'+token_hex(16);self.cursors[token]=page;return token
        nav=dict(page=self.page,pages=pages,total=len(self.filtered),previous=cursor(self.page-1),
                 next=cursor(self.page+1),query=self.query)
        rows=[];choices={}
        for record in self.filtered[(self.page-1)*PAGE_SIZE:self.page*PAGE_SIZE]:
            token=token_hex(16);choices[token]=record.key
            rows.append(dict(choice=token,code=record.values[0],description=record.values[1]))
        return rows,choices,nav
