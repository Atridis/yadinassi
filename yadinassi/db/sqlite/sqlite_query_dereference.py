"""Closed physical lowering for monomorphic query reference paths.

SQL identifiers originate from the opened layout and aliases belong to this
compiler. The entire projection, including target-presence evidence, is read
from one statement on the caller's already-owned query view.
"""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import (BackendError, CatalogComparison, CatalogKey,
                                                   CatalogPredicate, FieldSchema)
from yadinassi.db.catalog.catalog_qualifiers import validate_string
from yadinassi.db.document.document_backend import DocumentKey
from .sqlite_catalog_layout import quote_identifier
from .sqlite_typed_rows import (PhysicalFields, attribute_column, bounded_attribute_sql,
                                bounded_value_sql, decode_typed_columns)


_ZERO = '00000000-0000-0000-0000-000000000000'
_DATE = FieldSchema(UUID(int=1),'Date','datetime',('DateTime',))
_LINE = FieldSchema(UUID(int=0),'LineNumber','number',(10,0,'Nonnegative'))


@dataclass(frozen=True, slots=True)
class _Cell:
    sql: tuple
    kind: str
    field: object = None
    reference: tuple | None = None


@dataclass(slots=True)
class _Relation:
    table: str
    joins: list
    where: str
    parameters: tuple
    ties: tuple
    columns: dict
    proofs: tuple
    header: tuple | None = None  # (family, identity, alias)


def _id(raw, *, canonical=False):
    if type(raw) is not str or not 32<=len(raw)<=36:
        raise BackendError('integrity')
    value = UUID(raw)
    if not value.int or canonical and str(value)!=raw: raise BackendError('integrity')
    return value


def _integer(value):
    if type(value) is not int or not 1<=value<2**63:
        raise BackendError('integrity')


def _declared(schemas, identity):
    return next((schema for schema in schemas if schema.identity==identity),None)


def _typed(columns, specs, names, alias):
    for field, name in zip(specs,names):
        column = alias+'.'+quote_identifier(name)
        ref = ('catalog',field.target_catalog_id) if field.kind=='catalog_ref' else None
        columns[field.identity] = _Cell((column,),field.kind,field,ref)


def _catalog(view, identity, alias):
    backend = view._backend
    schema = _declared(backend._schemas,identity)
    if schema is None: raise BackendError('schema_changed')
    if backend.storage_version<2 or schema.hierarchy!='none': return None
    layout = backend._layout
    table = quote_identifier(layout.table_name(identity))
    cols = {
        'ref':_Cell((alias+'.record_id',),'catalog_ref',reference=('catalog',identity)),
        'code':_Cell((alias+'.code',),'string',schema.code_length),
        'description':_Cell((alias+'.description',),'string',schema.description_length),
        'deletion_mark':_Cell((alias+'.deletion_mark',),'boolean'),
    }
    _typed(cols,schema.fields,(layout.field_name(identity,f.identity) for f in schema.fields),alias)
    return table,schema,cols


def _document(view, identity, alias):
    from .sqlite_document_layout import data_table
    backend = view._backend
    schema = _declared(backend._document_schemas,identity)
    if schema is None: raise BackendError('schema_changed')
    joins = []
    columns = {
        'ref':_Cell((alias+'.record_id',),'document_ref',reference=('document',identity)),
        'number':_Cell((alias+'.number',),'string',schema.number_length),
        'date':_Cell((alias+'.date',),'datetime'),
        'deletion_mark':_Cell((alias+'.deletion_mark',),'boolean'),
    }
    attribute_alias = alias+'a'
    if schema.fields:
        joins.append(('attributes','LEFT JOIN '+quote_identifier(data_table(schema))+' AS '+attribute_alias+
            f' ON {attribute_alias}.record_id={alias}.record_id AND {attribute_alias}.document_id={alias}.document_id'))
        _typed(columns,schema.fields,(attribute_column(f) for f in schema.fields),attribute_alias)
    if backend.format_version in (13,14,15,16):
        p = alias+'p'
        joins.append(('posted',f'LEFT JOIN document_posting_state AS {p} ON '
                     f'{p}.record_id={alias}.record_id AND {p}.document_id={alias}.document_id'))
        columns['posted'] = _Cell((alias+'.revision',p+'.document_revision',p+'.posted'),'posted')
    else:
        columns['posted'] = _Cell(('0',),'boolean')
    return schema,columns,joins


def _source(view, family, entity, part):
    backend = view._backend
    if family=='catalog':
        admitted = _catalog(view,entity,'s' if part is None else 'h')
        if admitted is None: return None
        table,schema,columns = admitted
        if part is None:
            return _Relation(table+' AS s',[],'',(),('s.record_id COLLATE yadinassi_uuid_v1','s.rowid'),
                columns,(('uuid','s.record_id'),('int','s.revision')),('catalog',entity,'s'))
        section = _declared(schema.tabular_sections,part)
        if section is None: raise BackendError('schema_changed')
        layout = backend._section_layout
        columns = {'ref':_Cell(('s.owner_id',),'catalog_ref',reference=('catalog',entity))}
        _typed(columns,section.fields,(layout.field_name(entity,part,f.identity) for f in section.fields),'s')
        parts = quote_identifier(layout.table_name(entity,part))
        return _Relation(parts+' AS s',[('header','LEFT JOIN '+table+' AS h ON h.record_id=s.owner_id')],
            '',(),('s.owner_id COLLATE yadinassi_uuid_v1','s.row_id COLLATE yadinassi_uuid_v1'),
            columns,(('canonical_uuid','s.owner_id'),('canonical_uuid','s.row_id'),('line','s.row_number'),('int','h.revision')),
            ('catalog',entity,'h'))
    if family=='document':
        alias = 's' if part is None else 'h'
        schema,columns,joins = _document(view,entity,alias)
        ties = (alias+'.date',alias+'.number COLLATE BINARY',alias+'.record_id')
        headers = ((('number',schema.number_length),alias+'.number'),('date',alias+'.date'))
        if part is None:
            return _Relation('document_record AS s',joins,'s.document_id=?',(str(entity),),ties,
                columns,(('canonical_uuid','s.record_id'),('int','s.revision'),*headers),('document',entity,'s'))
        from .sqlite_document_layout import section_table
        section = _declared(schema.tabular_sections,part)
        if section is None: raise BackendError('schema_changed')
        columns = {
            'ref':_Cell(('s.record_id',),'document_ref',reference=('document',entity)),
            'line_number':_Cell(('s.row_number',),'line'),
        }
        _typed(columns,section.fields,(attribute_column(f) for f in section.fields),'s')
        parent = 'LEFT JOIN document_record AS h ON h.record_id=s.record_id AND h.document_id=s.document_id'
        return _Relation(quote_identifier(section_table(schema,section))+' AS s',[('header',parent),*joins],
            's.document_id=?',(str(entity),),(*ties,'s.row_number'),columns,
            (('canonical_uuid','s.record_id'),('canonical_uuid','s.row_id'),('line','s.row_number'),('int','h.revision'),*headers),
            ('document',entity,'h'))
    if part is not None: return None
    if family=='information_register':
        from .sqlite_register_layout import RegisterLayout, _key_expression
        schema = _declared(backend._register_schemas,entity)
        if schema is None: return None  # raw recorder has a separate physical family
        layout = RegisterLayout(schema)
        columns = {}
        _typed(columns,schema.fields,(attribute_column(f) for f in schema.fields),'s')
        order = tuple(_key_expression(f,'s.'+col) for f,col in zip(schema.key_fields,layout.keys))
        return _Relation(layout.table+' AS s',[],'',(),order,columns,(('int','s.revision'),))
    if family not in ('recorder','accumulation_register'): return None
    from .sqlite_movement_layout import table_name
    accumulation = family=='accumulation_register'
    internal = 'accumulation' if accumulation else 'recorder'
    schemas = backend._accumulation_schemas if accumulation else backend._recorder_schemas
    schema = _declared(schemas,entity)
    if schema is None: return None
    columns = {'active':_Cell(('s.active',),'boolean'),'line_number':_Cell(('s.line_number',),'line')}
    if accumulation: columns['period'] = _Cell(('s.period',),'datetime')
    if len(schema.recorder_documents)==1:
        columns['recorder'] = _Cell(('s.record_id',),'document_ref',reference=('document',schema.recorder_documents[0]))
    _typed(columns,schema.fields,(attribute_column(f) for f in schema.fields),'s')
    parent = (f'LEFT JOIN {internal}_partition AS part ON part.register_id=s.register_id AND '
              'part.document_id=s.document_id AND part.record_id=s.record_id')
    hints = 'LEFT JOIN document_record AS h ON h.document_id=s.document_id AND h.record_id=s.record_id'
    proofs = ((tuple(schema.recorder_documents),'s.document_id'),('canonical_uuid','s.record_id'),
              ('line','s.line_number'),('int','part.revision'),('int','h.revision'))
    if accumulation: proofs += (('active','s.active'),)
    header = ('document',schema.recorder_documents[0],'h') if len(schema.recorder_documents)==1 else None
    return _Relation(quote_identifier(table_name(internal,schema))+' AS s',[('header',parent),('header',hints)],
        's.register_id=?',(str(entity),),('s.document_id','s.record_id','s.line_number'),columns,proofs,header)


def _fetch_columns(cell):
    if type(cell.field) is FieldSchema: return (bounded_attribute_sql(cell.sql[0],cell.field),)
    if cell.kind=='string': return (bounded_value_sql(cell.sql[0],cell.field*4),)
    if cell.kind in ('catalog_ref','document_ref','datetime'):
        return (bounded_value_sql(cell.sql[0],14 if cell.kind=='datetime' else 36),)
    return cell.sql


def _decode_cell(view, cell, raw):
    from .sqlite_catalog import _decode
    if type(cell.field) is FieldSchema:
        schema = PhysicalFields((cell.field,))
        domain = view._backend._enum_domain
        encoded, = decode_typed_columns(raw,schema,enum_domain=domain)
        return _decode(encoded,cell.field,view.database_id,enum_domain=domain)
    if cell.kind=='posted':
        from .sqlite_document_posting_state import decode_posted
        return decode_posted(*raw)
    value, = raw
    if cell.kind in ('catalog_ref','document_ref'):
        key = DocumentKey if cell.kind=='document_ref' else CatalogKey
        return key(view.database_id,cell.reference[1],_id(value,canonical=cell.kind=='document_ref'))
    if cell.kind=='string':
        validate_string(value,cell.field)
        return value
    if cell.kind=='datetime':
        return _decode(['d',value],_DATE,view.database_id)
    if cell.kind=='line':
        _integer(value)
        return Decimal(value)
    if cell.kind=='boolean':
        if type(value) is not int or value not in (0,1): raise BackendError('integrity')
        return bool(value)
    raise BackendError('unsupported')


def _projection(view, source, paths, filtered):
    joins = list(source.joins)
    active_joins = {'header'}
    bindings, witnesses, expanded = [], [], {}
    params = ()
    source_header = source.header
    if 'posted' in filtered: active_joins.add('posted')
    if source_header is not None and any(source.columns[field].sql[0].startswith(source_header[2]+'a.')
                                        for field in filtered):
        active_joins.add('attributes')
    for path in paths:
        if (type(path) is not tuple or len(path)!=4 or type(path[0]) not in (str,UUID)):
            raise BackendError('invalid_input')
        field,family,identity,target = path
        base = source.columns.get(field)
        if base is None: return None
        source_alias = source_header[2] if source_header is not None else None
        if source_alias is not None and base.sql[0].startswith(source_alias+'a.'):
            active_joins.add('attributes')
        if family is None:
            if identity is not None or target is not None: raise BackendError('invalid_input')
            cell,missing,receipt = base,None,None
            if field=='posted': active_joins.add('posted')
        else:
            if (type(family) is not str or family not in ('catalog','document')
                    or type(identity) is not UUID or not identity.int or type(target) not in (str,UUID)):
                raise BackendError('invalid_input')
            if base.reference!=(family,identity): raise BackendError('invalid_input')
            own = source_header is not None and source_header[:2]==(family,identity) and field in ('ref','recorder')
            key = (field,family,identity)
            lookup = expanded.get(key)
            if lookup is None:
                alias = source_header[2] if own else 'j'+str(len(expanded))
                if family=='catalog':
                    declared = _catalog(view,identity,alias)
                    if declared is None: return None
                    table,_,columns = declared
                    extra = []
                else:
                    _,columns,extra = _document(view,identity,alias)
                    table = 'document_record'
                if not own:
                    condition = f'{alias}.record_id={base.sql[0]}'
                    if family=='document':
                        condition += f' AND {alias}.document_id=?'
                        params += (str(identity),)
                    joins.append(('header',f'LEFT JOIN {table} AS {alias} ON {condition}'))
                    joins.extend((alias+kind,sql) for kind,sql in extra)
                    missing = len(witnesses)
                    witnesses.append((base.sql[0],alias+'.record_id',alias+'.revision'))
                else:
                    missing = None
                lookup = expanded[key] = (alias,columns,missing,own)
            alias,columns,missing,own = lookup
            cell = columns.get(target)
            if cell is None: return None
            receipt = None
            if cell.sql[0].startswith(alias+'a.'):
                active_joins.add('attributes' if own else alias+'attributes')
                receipt = ((alias+'a.record_id',alias+'.record_id'),'attributes')
            if target=='posted': active_joins.add('posted' if own else alias+'posted')
        bindings.append((cell,missing,receipt))
    if 'attributes' in active_joins:
        alias = source_header[2]
        source.proofs += (('canonical_uuid',alias+'a.record_id'),)
    return bindings,witnesses,[sql for key,sql in joins if key in active_joins],params


def _order(bindings, witnesses, order):
    out = []
    seen = set()
    for spec in order:
        if (type(spec) is not tuple or len(spec)!=2 or type(spec[0]) is not int
                or not 0<=spec[0]<len(bindings) or type(spec[1]) is not bool):
            raise BackendError('invalid_input')
        index,descending = spec
        if index in seen: continue
        seen.add(index)
        cell,missing,_ = bindings[index]
        direction = ' DESC' if descending else ' ASC'
        kind = {'line':'number','posted':'boolean'}.get(cell.kind,cell.kind)
        if missing is not None:
            # Existing relational ordering compares presence before the
            # same-type keys: NULL first ASC and last DESC for all kinds.
            hit = witnesses[missing][1]
            out.append(f'CASE WHEN {hit} IS NULL THEN 0 ELSE 1 END'+direction)
        expression = cell.sql[-1] if cell.kind=='posted' else cell.sql[0]
        if kind=='string': expression += ' COLLATE yadinassi_casefold_v1'
        elif kind in ('catalog_ref','document_ref','enum_ref'):
            expression = f"COALESCE({expression},'{_ZERO}') COLLATE yadinassi_uuid_v1"
        if cell.kind=='posted': expression = f'COALESCE({expression},0)'
        out.append(expression+direction)
    return out


def _where(view, source, predicate):
    """Close the predicate over admitted base fields; no user-provided SQL."""
    from .sqlite_ordered_predicates import ordered_where

    fields = set()
    atoms = 0
    def lower(node, depth=0):
        nonlocal atoms
        atoms += 1
        if atoms>64 or depth>8: raise BackendError('unsupported')
        if type(node) is CatalogPredicate:
            if (type(node.kind) is not str or node.kind!='and'
                    or type(node.terms) is not tuple or not node.terms):
                raise BackendError('invalid_input')
            terms = tuple(lower(term,depth+1) for term in node.terms)
            return ('('+' AND '.join(sql for sql,_ in terms)+')',
                    tuple(arg for _,args in terms for arg in args))
        if (type(node) is not CatalogComparison or type(node.field) not in (UUID,str)
                or type(node.operator) is not str or node.field not in source.columns):
            raise BackendError('invalid_input')
        cell = source.columns[node.field]
        fields.add(node.field)
        if cell.reference is not None:
            value,operator = node.value,node.operator
            family,identity = cell.reference
            if family=='catalog':
                if type(value) is not CatalogKey: raise BackendError('invalid_input')
                actual = value.catalog_id
            else:
                if type(value) is not DocumentKey: raise BackendError('invalid_input')
                actual = value.document_id
            if (any(type(item) is not UUID or type(getattr(item,'int',None)) is not int
                    for item in (value.database_id,actual,value.record_id))
                    or value.database_id!=view.database_id or actual!=identity
                    or not 0<=value.record_id.int<2**128 or operator not in ('eq','ne')):
                raise BackendError('invalid_input')
            column = cell.sql[0]
            if type(cell.field) is FieldSchema:
                column = f"COALESCE({column},'{_ZERO}')"
            elif family=='catalog':
                # Catalog header IDs have historical accepted aliases.
                column += ' COLLATE yadinassi_uuid_v1'
            return f"({column} {'=' if operator=='eq' else '!='} ?)",(str(value.record_id),)
        if cell.kind=='enum_ref': raise BackendError('unsupported')
        column = cell.sql[0]
        definition = cell.field if type(cell.field) is FieldSchema else cell.kind
        if cell.kind=='string': column += ' COLLATE yadinassi_casefold_v1'
        elif cell.kind=='line': definition = _LINE
        elif cell.kind=='posted':
            definition = 'boolean'
            column = f'COALESCE({cell.sql[-1]},0)'
        return ordered_where(node,{node.field:(definition,column)})

    if predicate is None: return '',(),fields
    sql,args = lower(predicate)
    return sql,args,fields


def project(document_view, source, paths, order, limit, *, predicate=None):
    from .sqlite_catalog import SQLiteCatalogBackend, _View, _close_document_scan
    from .sqlite_documents import DocumentView
    from yadinassi.db.query.query_parser import MAX_ROWS
    from yadinassi.db.query.queries import _MAX_CELLS, _MAX_RESULT_TEXT

    if type(document_view) is not DocumentView: return None
    view = document_view._view
    view._require()
    backend = view._backend
    if type(backend) is not SQLiteCatalogBackend: return None
    if type(view) is _View:
        if not view._query_language or view._operation_id is not None: return None
        if (backend._active is not view or view._read_handle is None
                or view._read_handle is not backend._read_handle
                or view._connection is not view._read_handle.connection):
            raise BackendError('closed')
    else:
        from yadinassi.db.database_transactions import require_registered_query_lease
        require_registered_query_lease(backend,view)
    if (type(source) is not tuple or len(source)!=3 or type(source[0]) is not str
            or type(source[1]) is not UUID or not source[1].int
            or source[2] is not None and (type(source[2]) is not UUID or not source[2].int)
            or type(paths) is not tuple or not 1<=len(paths)<=128 or type(order) is not tuple
            or len(order)>16 or type(limit) is not int or not 1<=limit<=MAX_ROWS+1):
        raise BackendError('invalid_input')
    relation = _source(view,*source)
    if relation is None: return None
    filter_sql, filter_args, filtered = _where(view,relation,predicate)
    plan = _projection(view,relation,paths,filtered)
    if plan is None: return None
    bindings,witnesses,joins,params = plan
    order_sql = _order(bindings,witnesses,order)
    selected = []
    for kind,column in relation.proofs:
        if kind in ('uuid','canonical_uuid') or type(kind) is tuple and kind[0]!='number':
            column = bounded_value_sql(column,36)
        elif kind=='date': column = bounded_value_sql(column,14)
        elif type(kind) is tuple: column = bounded_value_sql(column,kind[1]*4)
        selected.append(column)
    for base,hit,revision in witnesses:
        selected.extend((bounded_value_sql(base,36),bounded_value_sql(hit,36),revision))
    offsets = []
    for cell,missing,receipt in bindings:
        start = len(selected)
        projection = _fetch_columns(cell)
        selected.extend(projection)
        stop = len(selected)
        if receipt is not None:
            selected.extend(bounded_value_sql(sql,36) for sql in receipt[0])
        offsets.append((cell,missing,start,stop,receipt is not None))
    # Predicate inputs need not appear in the output, but a selected row's
    # used physical values must still be valid. Standard identities and date /
    # number are already covered by source witnesses.
    projected_base = {path[0] for path in paths if path[1] is None}
    filter_witnesses = []
    for field in sorted(filtered-projected_base,key=str):
        if field in ('ref','number','date','recorder'): continue
        cell = relation.columns[field]
        start = len(selected)
        selected.extend(_fetch_columns(cell))
        filter_witnesses.append((cell,start,len(selected)))
    where = ' AND '.join(term for term in (relation.where,filter_sql) if term)
    if where: where = ' WHERE '+where
    sql = (f'SELECT {",".join(selected)} FROM {relation.table} {" ".join(joins)}{where}'
           +' ORDER BY '+','.join((*order_sql,*relation.ties))+' LIMIT ?')
    _close_document_scan(view)
    view._scan_cursor = None
    cursor = view._connection.execute(sql,params+relation.parameters+filter_args+(limit,))
    rows = []
    text = 0
    try:
        for raw in cursor:
            proof_count = len(relation.proofs)
            for (kind,_),value in zip(relation.proofs,raw):
                if kind=='int': _integer(value)
                elif kind=='line':
                    if type(value) is not int or not 1<=value<=1000: raise BackendError('integrity')
                elif kind=='active':
                    if type(value) is not int or value!=1: raise BackendError('integrity')
                elif kind=='date': _decode_cell(view,_Cell((None,),'datetime'),(value,))
                elif type(kind) is tuple and kind[0]=='number':
                    validate_string(value,kind[1])
                    if not value: raise BackendError('integrity')
                else:
                    identity = _id(value,canonical=kind!='uuid')
                    if type(kind) is tuple and identity not in kind: raise BackendError('integrity')
            present=[]
            for offset in range(proof_count,proof_count+3*len(witnesses),3):
                base,hit,revision=raw[offset:offset+3]
                if base is None or base==_ZERO:
                    if hit is not None: raise BackendError('integrity')
                    present.append(False)
                else:
                    _id(base,canonical=True)
                    if base!=hit: raise BackendError('integrity')
                    _integer(revision)
                    present.append(True)
            row=[]
            for cell,missing,start,stop,receipt in offsets:
                if missing is not None and not present[missing]:
                    value=None
                else:
                    if receipt and (raw[stop] is None or raw[stop]!=raw[stop+1]):
                        raise BackendError('integrity')
                    value=_decode_cell(view,cell,raw[start:stop])
                row.append(value)
                if type(value) is str: text+=len(value)
            for cell,start,stop in filter_witnesses:
                _decode_cell(view,cell,raw[start:stop])
            rows.append(tuple(row))
            if len(rows)*len(paths)>_MAX_CELLS or text>_MAX_RESULT_TEXT:
                raise BackendError('unsupported')
    finally:
        cursor.close()
    view._require()
    if type(view) is _View:
        if backend._active is not view: raise BackendError('closed')
    else:
        require_registered_query_lease(backend,view)
    return tuple(rows)
