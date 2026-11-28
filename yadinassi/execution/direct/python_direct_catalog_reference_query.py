"""One closed, borrowed-view Query shape for catalog handlers."""
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalog_types import BSLCatalogReference, BSLCatalogType
from yadinassi.db.catalog.catalog_sections import _MAX_ROWS as _MAX_SECTION_ROWS
from yadinassi.db.query import query_parser as syntax


_REF = frozenset(('ref', 'ссылка'))
_MARK = frozenset(('deletionmark', 'пометкаудаления'))


def _field(node, query, names):
    return (type(node) is syntax.Field and node.parts[-1].casefold() in names
            and (len(node.parts)==1 or len(node.parts)==2
                 and node.parts[0].casefold()==query.source_alias.casefold()))


class ReferenceQuery:
    __slots__=('catalog', 'parameter', 'references')

    def __init__(self, text):
        if type(text) is not str:raise TypeError('catalog preparation: query text required')
        query=syntax.parse_query(text)
        if (type(query) is not syntax.Select or query.family!='catalog' or query.section is not None
                or query.temporary or query.external or query.derived is not None or query.into is not None
                or query.joins or query.groups or query.having is not None or query.order
                or query.distinct or query.limit!=syntax.MAX_ROWS
                or len(query.projections)!=2 or type(query.predicate) is not syntax.Membership):
            raise ValueError('catalog preparation: unsupported reference query')
        condition=query.predicate
        if (not _field(condition.field,query,_REF) or type(condition.values) is not tuple
                or len(condition.values)!=1 or type(condition.values[0]) is not syntax.Parameter
                or any(not _field(p.field,query,names) or p.alias.casefold() not in names
                       for p,names in zip(query.projections,(_REF,_MARK)))):
            raise ValueError('catalog preparation: unsupported reference query')
        self.catalog=query.catalog
        self.parameter=condition.values[0].name.casefold()
        self.references=None

    def set_parameter(self, name, values):
        if type(name) is not str or name.casefold()!=self.parameter or type(values) is not list:
            raise TypeError('catalog preparation: reference-array parameter required')
        if len(values)>_MAX_SECTION_ROWS:
            raise ValueError('catalog preparation: reference-array is too large')
        self.references=tuple(values)

    def execute(self, boundary):
        if self.references is None:raise ValueError('catalog preparation: query parameter required')
        manager=boundary.catalogs.get_index(self.catalog)
        metadata=boundary.catalogs._metadata
        schema=manager._schema
        from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend, _View
        backend=manager._backend
        if type(backend) is not SQLiteCatalogBackend or schema.hierarchy!='none':
            raise BackendError('unsupported')
        keys=[]
        for ref in self.references:
            if (type(ref) is not BSLCatalogReference or type(ref.value_type) is not BSLCatalogType
                    or ref.value_type.snapshot is not metadata or type(ref.value_type.family) is not str
                    or ref.value_type.family!='ref' or type(ref.value_type.metadata_uuid) is not UUID
                    or ref.value_type.metadata_uuid!=schema.identity or type(ref.reference_uuid) is not UUID):
                raise TypeError('catalog preparation: same catalog reference required')
            if ref.reference_uuid.int:keys.append(ref.reference_uuid)
        if not keys:return ReferenceResult(())
        # Explicit host-only validation historically owns its reads. Every
        # actual write, transaction savepoint and form/list caller supplies
        # its already-admitted view and acquires nothing here.
        view=boundary.vm.write_view
        own=view is None
        if own:view=manager._view(data_backend=None)
        try:
            if backend._active is not view:
                from yadinassi.db.database_transactions import require_registered_query_lease
                require_registered_query_lease(backend,view)
            elif (type(view) is not _View or view._backend is not backend
                  or view._connection is None or not view._connection.in_transaction):
                raise BackendError('unsupported')
            if (view.database_id!=metadata._database_id
                    or view.configuration_generation!=metadata._generation
                    or view.catalog_schema(schema.identity)!=schema):
                raise BackendError('schema_changed')
            rows=_View._read_catalog_reference_marks(view,schema,tuple(keys))
            boundary._check()
            return ReferenceResult(tuple((manager._ref(identity),marked) for identity,marked in rows))
        finally:
            if own:view.close()


class ReferenceResult:
    __slots__=('rows',)
    def __init__(self,rows):self.rows=rows
    def select(self):return ReferenceCursor(self.rows)


class ReferenceCursor:
    __slots__=('rows','position')
    def __init__(self,rows):self.rows,self.position=rows,-1
    def next(self):
        if self.position+1>=len(self.rows):return False
        self.position+=1
        return True
    def field(self,key):
        if key in _REF:index=0
        elif key in _MARK:index=1
        else:raise ValueError('catalog preparation: unavailable query column')
        return None if self.position<0 else self.rows[self.position][index]
