"""SQLite-only bounded groups-and-items graph, separate from scalar layouts."""
from uuid import UUID
from .catalog_backend import BackendError, CatalogKey

HIERARCHY_DDL = ('CREATE TABLE catalog_hierarchy(catalog_id TEXT NOT NULL REFERENCES catalog_schema(identity),record_id TEXT NOT NULL,parent_id TEXT,is_folder INTEGER NOT NULL,PRIMARY KEY(catalog_id,record_id))',)
MAX_DEPTH = 32
MAX_ROWS = 10000


def _id(raw):
    if type(raw) is not str or len(raw) != 36: raise BackendError('integrity')
    result = UUID(raw)
    if not result.int or str(result) != raw: raise BackendError('integrity')
    return result


def clear(view):
    view._hierarchy_cache = None


def validate(graph, *, error='integrity'):
    # The whole proposed graph is checked, including descendants of a move.
    for identity, (parent, folder) in graph.items():
        if parent is not None and (parent not in graph or not graph[parent][1]):
            raise BackendError(error)
        path = set(); current = identity
        while current is not None:
            if current in path or len(path) >= MAX_DEPTH: raise BackendError(error)
            path.add(current)
            current = graph[current][0]


def load(view, schema):
    if schema.hierarchy == 'none': return {}
    if view._backend.storage_version != 10: raise BackendError('unsupported')
    cache = getattr(view, '_hierarchy_cache', None)
    if cache is None:
        cache = {}; view._hierarchy_cache = cache
    if schema.identity in cache: return cache[schema.identity]
    connection = view._connection
    args = (str(schema.identity),)
    if connection.execute("SELECT 1 FROM catalog_hierarchy WHERE catalog_id=? AND (typeof(record_id)!='text' OR length(CAST(record_id AS BLOB))!=36 OR (parent_id IS NOT NULL AND (typeof(parent_id)!='text' OR length(CAST(parent_id AS BLOB))!=36)) OR typeof(is_folder)!='integer' OR is_folder NOT IN (0,1)) LIMIT 1",args).fetchone():
        raise BackendError('integrity')
    count = connection.execute('SELECT COUNT(*) FROM catalog_hierarchy WHERE catalog_id=?',args).fetchone()[0]
    if count > MAX_ROWS: raise BackendError('unsupported')
    graph = {_id(record): (None if parent is None else _id(parent), bool(folder))
             for record,parent,folder in connection.execute('SELECT record_id,parent_id,is_folder FROM catalog_hierarchy WHERE catalog_id=?',args)}
    table,_,where,source_args = view._source(schema)
    if connection.execute('SELECT COUNT(*) FROM %s WHERE %s' % (table,where), source_args).fetchone()[0] > MAX_ROWS:
        raise BackendError('unsupported')
    ids = {_id(row[0]) for row in connection.execute('SELECT record_id FROM %s WHERE %s' % (table,where),source_args)}
    if len(graph) != count or set(graph) != ids: raise BackendError('integrity')
    validate(graph)
    cache[schema.identity] = graph
    return graph


def values(view, schema, identity):
    if schema.hierarchy == 'none': return None, False
    parent, folder = load(view, schema)[identity]
    return (None if parent is None else CatalogKey(view.database_id,schema.identity,parent)), folder


def check_draft(view, schema, draft):
    if type(draft.is_folder) is not bool: raise BackendError('invalid_input')
    if schema.hierarchy == 'none':
        if draft.parent is not None or draft.is_folder: raise BackendError('invalid_input')
        return
    if view._backend.storage_version != 10: raise BackendError('unsupported')
    parent = draft.parent
    if parent is not None:
        if (type(parent) is not CatalogKey or type(parent.database_id) is not UUID
                or type(parent.catalog_id) is not UUID or type(parent.record_id) is not UUID
                or parent.database_id != view.database_id or parent.catalog_id != schema.identity
                or not parent.record_id.int):
            raise BackendError('invalid_input')


def prepare(view, schema, draft, *, creating):
    if schema.hierarchy == 'none': return
    graph = dict(load(view,schema))
    old = graph.get(draft.key.record_id)
    if creating and old is not None: raise BackendError('duplicate_identity')
    if not creating and old is None: raise BackendError('conflict')
    if old is not None and old[1] is not draft.is_folder: raise BackendError('invalid_input')
    parent = None if draft.parent is None else draft.parent.record_id
    if parent is not None and parent not in graph: raise BackendError('not_found')
    graph[draft.key.record_id] = (parent,draft.is_folder)
    validate(graph,error='invalid_input')


def store(view, schema, draft, *, creating):
    if schema.hierarchy == 'none': return
    row = (None if draft.parent is None else str(draft.parent.record_id),int(draft.is_folder),str(schema.identity),str(draft.key.record_id))
    if creating:
        view._connection.execute('INSERT INTO catalog_hierarchy(parent_id,is_folder,catalog_id,record_id) VALUES(?,?,?,?)',row)
    else:
        view._connection.execute('UPDATE catalog_hierarchy SET parent_id=?,is_folder=? WHERE catalog_id=? AND record_id=?',row)
    clear(view)
