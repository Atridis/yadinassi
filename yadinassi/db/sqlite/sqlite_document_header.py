"""One physical SELECT for an opened ordinary DocumentRef field."""
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalog_qualifiers import validate_string
from .sqlite_catalog_layout import quote_identifier
from .sqlite_document_layout import attribute_column, document_data_table
from .sqlite_document_posting_state import decode_posted
from .sqlite_single_statement import fetch_all
from .sqlite_typed_rows import (PhysicalFields, bounded_attribute_sql, bounded_value_sql as bounded,
                               decode_typed_columns)


def read_field(connection, key, generation, header, selected, *, domain, target):
    """Validate the current database, manifest, header and selected field together."""
    number_length, has_attributes, manifest = header
    attributes, present, value, refers = '', '1', 'NULL', '0'
    if has_attributes:
        table = 'main.'+quote_identifier(document_data_table(key.document_id))
        link = 'a.document_id=r.document_id AND a.record_id=r.record_id'
        if type(selected) is str:
            present = f'EXISTS(SELECT 1 FROM {table} a WHERE {link})'
        else:
            attributes = f' LEFT JOIN {table} a ON {link}'
            present = bounded('a.record_id',36)
            column = 'a.'+quote_identifier(attribute_column(selected))
            value = bounded_attribute_sql(column,selected)
            if target is not None:
                refers = f'EXISTS(SELECT 1 FROM main.{target} t WHERE t.record_id={column} COLLATE BINARY)'

    fields = (bounded('i.database_uuid',36),'i.generation','i.activated',bounded('r.record_id',36),
              bounded('r.number',36),bounded('r.date',14),'r.deletion_mark',bounded('p.record_id',36),
              'r.revision','p.document_revision','p.posted',present,value,refers,
              'EXISTS(SELECT 1 FROM main.document_schema d WHERE d.identity=? AND d.name=? AND d.definition=?)')
    sql = ('SELECT '+','.join(fields)+' FROM main.database_info i'
           ' LEFT JOIN main.document_record r ON r.document_id=? AND r.record_id=?'
           ' LEFT JOIN main.document_posting_state p ON p.document_id=r.document_id AND p.record_id=r.record_id'
           +attributes+" WHERE i.singleton=1 AND i.activation_issues='[]' LIMIT 2")
    record_id = str(key.record_id)
    rows = fetch_all(connection,sql,(*manifest,str(key.document_id),record_id))
    if len(rows)!=1: raise BackendError('schema_changed')
    database,current,active,record,number,date,mark,state,revision,state_revision,posted,attrs,raw,exists,declared = rows[0]
    if ((database,current,active)!=(str(key.database_id),generation,1)
            or type(current) is not int or type(active) is not int or declared!=1):
        raise BackendError('schema_changed')
    if record is None: return None
    standard = type(selected) is str
    if (type(record) is not str or record!=record_id or not key.record_id.int
            or type(mark) is not int or mark not in (0,1) or not number
            or attrs!=(1 if standard else record)
            or (state is not None and (state!=record or state_revision is None or posted is None))):
        raise BackendError('integrity')

    from .sqlite_documents import _DATE_FIELD
    from .sqlite_catalog import _decode
    validate_string(number,number_length)
    date = _decode(['d',date],_DATE_FIELD,key.database_id)
    posted = decode_posted(revision,state_revision,posted)
    if standard:
        return {'number':number,'date':date,'deletion_mark':bool(mark),'posted':posted,'ref':key}[selected]

    encoded, = decode_typed_columns((raw,),PhysicalFields((selected,)),enum_domain=domain)
    value = _decode(encoded,selected,key.database_id,enum_domain=domain)
    if target is not None and value.record_id.int and exists!=1:
        raise BackendError('integrity')
    return value
