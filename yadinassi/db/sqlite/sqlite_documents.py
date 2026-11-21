"""SQLite v7 non-posting documents using the owned application's transaction.

Distinct document tables/keys; catalog layouts remain distinct.
The closed tagged scalar codec is shared, never exposed as a native codec.
"""
from decimal import Decimal
import json
from uuid import UUID, uuid4

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogSchema, FieldSchema, CatalogKey, TabularRow, TabularSectionRows, _TabularSectionChanges
from yadinassi.db.catalog.catalog_qualifiers import normalize_field, normalize_string, validate_string
from .sqlite_catalog_layout import quote_identifier
from .sqlite_document_layout import data_table, section_table
from .sqlite_typed_rows import PhysicalFields, attribute_column, encode_typed_columns, decode_typed_columns
from yadinassi.db.document.document_backend import (DocumentSchema, DocumentKey, DocumentRevision, DocumentCard,
                               DocumentDraft, DocumentWriteOutcome, DocumentSelection,
                               DocumentScanRequest, DocumentPage)

DOCUMENT_DDL = (
    'CREATE TABLE document_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE document_record(document_id TEXT NOT NULL REFERENCES document_schema(identity), record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), number TEXT NOT NULL, date TEXT NOT NULL, deletion_mark INTEGER NOT NULL CHECK(deletion_mark IN(0,1)), PRIMARY KEY(document_id,record_id), UNIQUE(document_id,number))',
    'CREATE TABLE document_sequence(document_id TEXT PRIMARY KEY REFERENCES document_schema(identity), next_value INTEGER NOT NULL CHECK(next_value>0))',
)
_MAX_ROW = 1024 * 1024
_MAX_TOTAL = 16 * 1024 * 1024
_DATE_FIELD = FieldSchema(UUID(int=1), 'Date', 'datetime', ('DateTime',))
_RESERVED = {'number','номер','date','дата','posted','проведен','проведён','ref','ссылка',
             'deletionmark','пометкаудаления','write','записать','isnew','этоновый',
             'metadata','метаданные','getobject','получитьобъект','setnewobjectref','установитьссылкунового'}


def _storage():
    # Lazy import keeps the shared application admission/import graph acyclic.
    from . import sqlite_catalog
    return sqlite_catalog


def schema_data(schema, *, enum_domain=None):
    if type(schema) is not DocumentSchema or type(schema.number_length) is not int or not 1 <= schema.number_length <= 9:
        raise BackendError('invalid_input')
    surrogate = CatalogSchema(schema.identity, schema.name, schema.number_length, 0,
                              schema.fields, schema.tabular_sections, schema.numbering)
    data = _storage()._schema_data(surrogate,enum_domain=enum_domain)
    names = _RESERVED.copy(); ids = {schema.identity}
    for item in (*schema.fields, *schema.tabular_sections):
        if item.identity in ids or item.name.casefold() in names: raise BackendError('invalid_input')
        ids.add(item.identity); names.add(item.name.casefold())
        if hasattr(item, 'fields'):
            for field in item.fields:
                if field.identity in ids or field.name.casefold() in ('linenumber','номерстроки'):
                    raise BackendError('invalid_input')
                ids.add(field.identity)
    # This is a versioned local schema encoding, not a catalog registration.
    return ['enum_document_v1' if enum_domain is not None else 'nonposting_document_v1', data]


def parse_schema(raw, *, enum_domain=None):
    if type(raw) is not str or len(raw) > 65536: raise BackendError('integrity')
    data = json.loads(raw)
    if type(data) is not list or len(data) != 2 or data[0] != ('enum_document_v1' if enum_domain is not None else 'nonposting_document_v1'): raise BackendError('integrity')
    old = _storage()._schema(_storage()._json(data[1]), allow_numbering=True,enum_domain=enum_domain)
    schema = DocumentSchema(old.identity, old.name, old.code_length, old.fields, old.tabular_sections, old.numbering)
    if schema_data(schema,enum_domain=enum_domain) != data: raise BackendError('integrity')
    return schema


def load_schemas(connection, catalogs, *, allow_empty=False, enum_domain=None):
    invalid = connection.execute("SELECT 1 FROM document_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone()
    count, size = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(definition AS BLOB))),0) FROM document_schema').fetchone()
    if invalid or not (0 if allow_empty else 1) <= count <= 512 or size > _MAX_TOTAL: raise BackendError('integrity')
    rows = tuple(connection.execute('SELECT identity,name,definition FROM document_schema ORDER BY identity'))
    schemas = tuple(parse_schema(row[2],enum_domain=enum_domain) for row in rows)
    if any(row[:2] != (str(s.identity),s.name) for row,s in zip(rows,schemas)):
        raise BackendError('integrity')
    catalog_ids = {s.identity for s in catalogs}
    identities = set()
    for s in (*catalogs, *schemas):
        for item in (s, *s.fields, *s.tabular_sections, *(f for section in s.tabular_sections for f in section.fields)):
            if item.identity in identities: raise BackendError('integrity')
            identities.add(item.identity)
    if len({s.name.casefold() for s in schemas}) != len(schemas): raise BackendError('integrity')
    if sum(len(s.tabular_sections) for s in (*catalogs,*schemas)) > 512: raise BackendError('unsupported')
    if any(f.target_catalog_id not in catalog_ids for s in schemas for f in (*s.fields, *(f for section in s.tabular_sections for f in section.fields)) if f.kind == 'catalog_ref'):
        raise BackendError('integrity')
    expected = {str(s.identity): 10 ** s.number_length for s in schemas if s.numbering == 'decimal_v1'}
    if connection.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0] != len(expected): raise BackendError('integrity')
    for identity, value in connection.execute('SELECT document_id,next_value FROM document_sequence'):
        if identity not in expected or type(value) is not int or not 1 <= value <= expected[identity]: raise BackendError('integrity')
    return schemas, rows


class DocumentView:
    """One pinned application transaction; one document write per transaction."""
    def __init__(self, view):
        self._view = view
        self.database_id = view.database_id
        self.configuration_generation = view.configuration_generation
        self._outcome = None
        self._register_read_view = None
        if view._backend.storage_version not in (7, 8, 9, 10):
            self._schemas = ()
        else:
            self._schemas = view._backend._document_schemas
    @property
    def _connection(self): return self._view._connection
    def close(self): self._view.close()
    def rollback(self): self._view.rollback()
    def catalog_schema(self, identity): return self._view.catalog_schema(identity)
    def scan_catalog_values(self, identity, request, fields):
        return self._view.scan_catalog_values(identity, request, fields)

    def aggregate_catalog(self, identity, request):
        # Forward the closed catalog capability through the same owned snapshot
        # already used by enum/report packages; acquire no new connection.
        aggregate = self._view.aggregate_catalog
        return None if aggregate is None else aggregate(identity, request)
    def ordered_catalog_values(self, identity, request, fields):
        return self._view.ordered_catalog_values(identity, request, fields)

    def scan_catalog_section(self, identity, section_id, request):
        return self._view.scan_catalog_section(identity, section_id, request)
    def _register_reader(self):
        self._view._require()
        if self._register_read_view is None:
            from .sqlite_registers import RegisterView
            self._register_read_view = RegisterView(self._view)
        return self._register_read_view
    def registers(self): return self._register_reader().registers()
    def register_schema(self, identity): return self._register_reader().register_schema(identity)
    def scan_register(self, identity, request):
        return self._register_reader().scan_register(identity, request)
    def ordered_register_records(self, identity, order, limit):
        return self._register_reader().ordered_register_records(identity,order,limit)

    def periodic_records(self, identity, filters=(), start=None, end=None, edge=None, limit=1000):
        return self._register_reader().periodic_records(identity,filters,start,end,edge,limit)

    def documents(self): self._view._require(); return self._schemas
    def document_schema(self, identity):
        self._view._require(); _storage()._uuid(identity)
        schema = next((s for s in self._schemas if s.identity == identity), None)
        if schema is None: raise BackendError('not_found')
        return schema

    def _key(self, key):
        if type(key) is not DocumentKey or key.database_id != self.database_id: raise BackendError('invalid_input')
        _storage()._uuid(key.record_id, empty=True)
        return self.document_schema(key.document_id)

    def _preflight(self, schema):
        self._view._require()
        cache_key = ('document-coarse', schema.identity, schema)
        if self._view._cache_validation_allowed() and cache_key in self._view._validated_sources:
            return self._view._validated_sources[cache_key][0]
        args = (str(schema.identity),)
        invalid = self._connection.execute("SELECT 1 FROM document_record WHERE document_id=? AND (typeof(record_id)!='text' OR length(CAST(record_id AS BLOB))!=36 OR typeof(revision)!='integer' OR revision<1 OR typeof(number)!='text' OR length(CAST(number AS BLOB))>36 OR typeof(date)!='text' OR length(date)!=14 OR typeof(deletion_mark)!='integer' OR deletion_mark NOT IN(0,1)) LIMIT 1", args).fetchone()
        count, size = self._connection.execute(
            'SELECT COUNT(*),COALESCE(SUM(length(CAST(number AS BLOB))+128),0) FROM document_record WHERE document_id=?', args).fetchone()
        if invalid: raise BackendError('integrity')
        tables = ([(data_table(schema),schema.fields,0)] if schema.fields else [])
        tables.extend((section_table(schema,section),section.fields,52) for section in schema.tabular_sections)
        for table, fields, overhead in tables:
            units = [str(overhead)] + ['COALESCE(length(CAST('+quote_identifier(attribute_column(f))+' AS BLOB)),0)' for f in fields]
            row_size = '+'.join(units)
            used, largest = self._connection.execute(
                'SELECT COALESCE(SUM('+row_size+'),0),COALESCE(MAX('+row_size+'),0) FROM '+quote_identifier(table)).fetchone()
            if largest > _MAX_ROW: raise BackendError('integrity')
            size += used
            if size > _MAX_TOTAL: raise BackendError('unsupported')
        if count > 10000 or size > _MAX_TOTAL: raise BackendError('unsupported')
        if self._view._cache_validation_allowed():
            self._view._validated_sources[cache_key] = (count,)
        return count

    def _reference_candidates(self, fields, values, *, writing=False):
        # Prefetch is NOT validation: malformed data is left to the original
        # ordered decoder, preserving its error and selection-limit frontier.
        if type(values) is not (tuple if writing else list) or len(values) != len(fields):
            return
        for field, value in zip(fields, values):
            if field.kind != 'catalog_ref':
                continue
            try:
                key = value if writing else _storage()._decode(value, field, self.database_id,
                    enum_domain=self._view._backend._enum_domain)
                if (type(key) is CatalogKey and key.database_id == self.database_id
                        and key.catalog_id == field.target_catalog_id
                        and type(key.record_id) is UUID and key.record_id.int):
                    yield key
            except (BackendError, ValueError, TypeError, AttributeError):
                continue

    def _section_candidates(self, schema, contents, *, writing=False):
        if type(contents) is not (tuple if writing else list) or len(contents) > 16:
            return
        definitions = {s.identity: s for s in schema.tabular_sections}
        total = 0
        for item in contents:
            if writing:
                if type(item) is not TabularSectionRows or type(item.rows) is not tuple:
                    continue
                identity, rows = item.section_id, item.rows
            else:
                if type(item) is not list or len(item) != 2 or type(item[1]) is not list:
                    continue
                try: identity = UUID(item[0])
                except (ValueError, TypeError, AttributeError): continue
                rows = item[1]
            if type(identity) is not UUID or identity not in definitions: continue
            total += len(rows)
            if total > 1000: return
            for row in rows:
                if writing:
                    if type(row) is not TabularRow: continue
                    values = row.values
                else:
                    if type(row) is not list or len(row) != 2: continue
                    values = row[1]
                yield from self._reference_candidates(definitions[identity].fields, values, writing=writing)

    def _presence(self, keys):
        from .sqlite_catalog_layout import reference_presence
        def source(identity):
            schema = self._view.catalog_schema(identity)
            table, _, where, args = self._view._source(schema)
            return table, where, args
        return reference_presence(self._connection, keys, source)

    def _record_presence(self, schema, rows):
        if self._view._backend.format_version not in (15, 16): return {}
        def keys():
            for row in rows:
                if type(row) is BackendError: continue
                values, sections = row[5:7]
                yield from self._reference_candidates(schema.fields, values)
                yield from self._section_candidates(schema, sections)
        return self._presence(keys())

    def _projection_presence(self, schema, rows, *, section=False, attributes=()):
        if self._view._backend.format_version not in (15, 16): return {}
        def keys():
            for row in rows:
                if row[4] is None: continue
                payload = row[4]
                if section: yield from self._section_candidates(schema, payload)
                else: yield from self._reference_candidates(attributes,payload)
        return self._presence(keys())

    def _require_references(self, values, writing, presence):
        keys = tuple(v for v in values if type(v) is CatalogKey and v.record_id.int)
        if presence is None: presence = self._presence(keys)
        for key in keys:
            pair = (key.catalog_id, key.record_id)
            # A bounded prefetch may omit malformed/oversized later input. It
            # never authorizes an unexamined key or changes validation order.
            exists = presence[pair] if pair in presence else self._view._reference_exists(key)
            if not exists: raise BackendError('not_found' if writing else 'integrity')

    def _values(self, fields, values, *, writing=False, presence=None):
        s = _storage()
        if type(values) is not (tuple if writing else list) or len(values) != len(fields): raise BackendError('invalid_input' if writing else 'integrity')
        if writing:
            result = []; size = 0
            for field,value in zip(fields,values):
                encoded = s._encode(normalize_field(value,field),field,self.database_id,enum_domain=self._view._backend._enum_domain)
                size += len(s._json(encoded)) + 1
                if size > _MAX_ROW: raise BackendError('invalid_input')
                result.append(encoded)
            self._require_references(values, True, presence)
            return result
        decoded = tuple(s._decode(v,f,self.database_id,enum_domain=self._view._backend._enum_domain) for f,v in zip(fields,values))
        if self._view._backend.format_version in (15,16):
            self._require_references(decoded, False, presence)
        return decoded

    def _sections(self, schema, contents, *, writing=False, presence=None, sparse=False):
        if type(contents) is not (tuple if writing else list) or len(contents) > 16: raise BackendError('invalid_input' if writing else 'integrity')
        if presence is None and (writing or self._view._backend.format_version in (15, 16)):
            presence = self._presence(self._section_candidates(schema, contents, writing=writing))
        definitions = {s.identity:s for s in schema.tabular_sections}
        supplied = {}; total = 0; size = 0
        for item in contents:
            if writing:
                if type(item) is not TabularSectionRows or type(item.rows) is not tuple: raise BackendError('invalid_input')
                identity, rows = item.section_id, item.rows
            else:
                if type(item) is not list or len(item) != 2 or type(item[1]) is not list: raise BackendError('integrity')
                identity, rows = UUID(item[0]), item[1]
                if str(identity) != item[0]: raise BackendError('integrity')
            if identity not in definitions or identity in supplied: raise BackendError('integrity')
            total += len(rows)
            if total > 1000: raise BackendError('unsupported')
            result = []; seen = set()
            for row in rows:
                if writing:
                    if type(row) is not TabularRow: raise BackendError('invalid_input')
                    row_id, values = row.identity, row.values
                else:
                    if type(row) is not list or len(row) != 2: raise BackendError('integrity')
                    row_id, values = UUID(row[0]), row[1]
                    if str(row_id) != row[0]: raise BackendError('integrity')
                _storage()._uuid(row_id)
                if row_id in seen: raise BackendError('integrity')
                seen.add(row_id)
                values = self._values(definitions[identity].fields, values, writing=writing, presence=presence)
                encoded = [str(row_id),values] if writing else TabularRow(row_id,values)
                if writing:
                    size += len(_storage()._json(encoded)) + 1
                    if size > _MAX_ROW: raise BackendError('invalid_input')
                result.append(encoded)
            supplied[identity] = result
        if not writing and set(supplied) != set(definitions): raise BackendError('integrity')
        return ([[str(identity),supplied.get(identity,[])] for identity in sorted(supplied if sparse else definitions,key=str)] if writing else
                tuple(TabularSectionRows(section.identity,tuple(supplied[section.identity])) for section in schema.tabular_sections))

    def _posted_value(self, key):
        if self._view._backend.format_version not in (13, 14, 15, 16): return False
        from .sqlite_document_posting_state import read_posted
        return read_posted(self._connection, self.database_id, key)

    def _record_sql(self, schema, *, where='r.document_id=?', order=False, limit=False,
                    attributes=True, posted=True):
        posted = posted and self._view._backend.format_version in (13,14,15,16)
        attributes = schema.fields if attributes is True else attributes or ()
        columns = ['r.record_id','r.revision','r.number','r.date','r.deletion_mark']
        columns.extend(('p.document_revision','p.posted') if posted else ('NULL','NULL'))
        if attributes:
            columns.append('a.record_id')
            columns.extend('a.'+quote_identifier(attribute_column(f)) for f in attributes)
        sql = 'SELECT '+','.join(columns)+' FROM document_record AS r'
        if attributes:
            sql += (' LEFT JOIN '+quote_identifier(data_table(schema))+' AS a ON '
                    'a.document_id=r.document_id AND a.record_id=r.record_id')
        if posted:
            sql += (' LEFT JOIN document_posting_state AS p ON p.document_id=r.document_id'
                    ' AND p.record_id=r.record_id')
        sql += ' WHERE ' + where
        if order: sql += ' ORDER BY r.date,r.number,r.record_id'
        if limit: sql += ' LIMIT ?'
        return sql

    def _physical_attributes(self, fields, row):
        if not fields.fields: return []
        if len(row) != 8+len(fields.fields) or row[7] != row[0]:
            raise BackendError('integrity')
        return decode_typed_columns(row[8:],fields,enum_domain=self._view._backend._enum_domain)

    @staticmethod
    def _projected_attributes(schema, fields):
        return tuple(field for field in schema.fields if field.identity in fields)

    def _part_rows(self, schema, rows, sections):
        owners = tuple(dict.fromkeys(row[0] for row in rows))
        contents = {owner:[] for owner in owners}
        totals = dict.fromkeys(owners,0)
        for section in sections:
            table = quote_identifier(section_table(schema,section))
            projected = ['record_id','row_id','row_number']
            projected.extend(quote_identifier(attribute_column(f)) for f in section.fields)
            result = {owner:[] for owner in owners}
            for start in range(0,len(owners),128):
                batch = owners[start:start+128]
                sql = ('SELECT '+','.join(projected)+' FROM '+table+
                       ' WHERE document_id=? AND record_id IN ('+','.join('?' for _ in batch)+')'
                       ' ORDER BY record_id,row_number')
                cur = self._connection.execute(sql,(str(schema.identity),*batch))
                try:
                    for owner, raw_id, position, *fields in cur:
                        target = result.get(owner)
                        if target is None: raise BackendError('integrity')
                        totals[owner] += 1
                        if totals[owner] <= 1001:
                            target.append((raw_id,position,fields))
                finally:
                    cur.close()
            for owner, lines in result.items(): contents[owner].append((section,lines))
        return contents

    def _physical_parts(self, contents):
        domain = self._view._backend._enum_domain
        if sum(len(lines) for _,lines in contents)>1000: raise BackendError('unsupported')
        sections = []
        for section, lines in contents:
            selected = []
            for expected,(raw_id,position,attrs) in enumerate(lines,1):
                if type(position) is not int or position != expected: raise BackendError('integrity')
                selected.append([raw_id,decode_typed_columns(attrs,section,enum_domain=domain)])
            sections.append([str(section.identity),selected])
        return sections

    def _full_rows(self, schema, rows):
        parts = self._part_rows(schema,rows,schema.tabular_sections)
        result = []
        for row in rows:
            try:
                record = (*row[:5],self._physical_attributes(schema,row),
                          self._physical_parts(parts[row[0]]),*row[5:7])
            except BackendError as error:
                # Batch IO may look ahead, but a later malformed record must
                # not preempt an earlier bounded selection's overflow/error.
                record = error
            result.append(record)
        return tuple(result)

    def _projected_rows(self, schema, rows, fields, section=None):
        parts = self._part_rows(schema,rows,(section,)) if section is not None else None
        attributes = PhysicalFields(self._projected_attributes(schema,fields) if section is None else ())
        return tuple((row[0],*row[2:5],
                      self._physical_parts(parts[row[0]]) if parts is not None else
                      self._physical_attributes(attributes,row) if attributes.fields else None,
                      row[1],*row[5:7]) for row in rows)

    def _decode_record(self, schema, row, *, presence=None):
        if type(row) is BackendError: raise row
        if presence is None: presence = self._record_presence(schema, (row,))
        record, revision, number, date, mark, values, sections = row[:7]
        identity = UUID(record); _storage()._uuid(identity)
        if str(identity) != record or type(revision) is not int or not 1 <= revision < 2**63: raise BackendError('integrity')
        validate_string(number,schema.number_length)
        if not number or type(mark) is not int or mark not in (0,1): raise BackendError('integrity')
        key = DocumentKey(self.database_id,schema.identity,identity)
        posted = False
        if self._view._backend.format_version in (13, 14, 15, 16):
            if len(row) == 9:
                from .sqlite_document_posting_state import decode_posted
                posted = decode_posted(revision, row[7], row[8])
            else:
                posted = self._posted_value(key)
        return (key, DocumentRevision(self.database_id,self.configuration_generation,
                schema.identity,identity,str(revision)), number,
                _storage()._decode(['d',date],_DATE_FIELD,self.database_id),bool(mark),
                self._values(schema.fields,values, presence=presence),
                self._sections(schema,sections, presence=presence),posted)

    def _card(self, schema, row, *, presence=None):
        return DocumentCard(*self._decode_record(schema, row, presence=presence))

    def _record_proof_key(self, schema, key):
        return ('document-record', schema.identity, schema, key.record_id)

    def _validate_record(self, schema, key):
        """Point reads preserve their old full selected-record validation scope."""
        self._preflight(schema)
        proof_key = self._record_proof_key(schema, key)
        if self._view._cache_validation_allowed() and (
                proof_key in self._view._validated_sources or
                ('document-full', schema.identity, schema) in self._view._validated_sources):
            return
        row = self._connection.execute(self._record_sql(schema,
            where='r.document_id=? AND r.record_id=?'),
            (str(schema.identity),str(key.record_id))).fetchone()
        if row is not None: self._decode_record(schema, self._full_rows(schema,(row,))[0])
        if self._view._cache_validation_allowed():
            self._view._validated_sources[proof_key] = ()

    def _load_record(self, schema, key):
        return self._connection.execute(self._record_sql(schema,
            where='r.document_id=? AND r.record_id=?'),
            (str(schema.identity),str(key.record_id))).fetchone()

    def read_document(self, key):
        schema = self._key(key); self._preflight(schema)
        row = self._load_record(schema,key)
        card = None if row is None else self._card(schema,self._full_rows(schema,(row,))[0])
        if self._view._cache_validation_allowed():
            self._view._validated_sources[self._record_proof_key(schema, key)] = ()
        return card

    def _projection_fields(self, schema, fields, section=None):
        definitions = schema.fields if section is None else section.fields
        standard = ('ref','number','date','deletion_mark','posted') if section is None else ('ref','line_number')
        if (type(fields) is not tuple or not 1 <= len(fields) <= 128 or
                any((type(f) is not str and type(f) is not UUID) or
                    (f not in standard and not any(f == d.identity for d in definitions)) for f in fields)):
            raise BackendError('invalid_input')
        return definitions

    def _projection_sql(self, schema, fields, *, where, order=False, section=False):
        return self._record_sql(schema,where=where,order=order,
                                attributes=self._projected_attributes(schema,fields) if not section else (),
                                posted='posted' in fields)

    def _project_header(self, schema, fields, row, *, presence=None):
        from yadinassi.db.document.document_backend import DocumentValueRow
        record, number, date, mark, payload, revision, state_revision, posted = row
        identity = UUID(record); _storage()._uuid(identity)
        if (str(identity) != record or type(revision) is not int or not 1<=revision<2**63
                or type(mark) is not int or mark not in (0,1)):
            raise BackendError('integrity')
        validate_string(number,schema.number_length)
        if not number: raise BackendError('integrity')
        key = DocumentKey(self.database_id,schema.identity,identity)
        definitions = self._projected_attributes(schema,fields) if payload is not None else ()
        values = (dict(zip((field.identity for field in definitions),self._values(definitions,payload,presence=presence)))
                  if definitions else {})
        if self._view._backend.format_version in (13,14,15,16) and 'posted' in fields:
            from .sqlite_document_posting_state import decode_posted
            posted = decode_posted(revision,state_revision,posted)
        else: posted = False
        values.update(ref=key,number=number,date=_storage()._decode(['d',date],_DATE_FIELD,self.database_id),
                      deletion_mark=bool(mark),posted=posted)
        return DocumentValueRow(key,tuple(values[f] for f in fields))

    def read_document_values(self, key, fields):
        schema = self._key(key)
        self._projection_fields(schema,fields)
        # This read-only optimization never borrows a writer's stale proof.
        if self._view._operation_id is not None: raise BackendError('unsupported')
        self._validate_record(schema,key)
        row = self._connection.execute(self._projection_sql(schema,fields,
            where='r.document_id=? AND r.record_id=?'),
            (str(schema.identity),str(key.record_id))).fetchone()
        return None if row is None else self._project_header(schema,fields,self._projected_rows(schema,(row,),fields)[0])

    def select_documents(self, identity, request):
        schema = self.document_schema(identity)
        if type(request) is not DocumentSelection or type(request.limit) is not int or not 1 <= request.limit <= 1000: raise BackendError('invalid_input')
        where = ['r.document_id=?']; args = [str(identity)]
        for value, operator in ((request.start,'>='),(request.end,'<=')):
            if value is not None:
                encoded = _storage()._encode(value,_DATE_FIELD,self.database_id)[1]
                where.append('r.date'+operator+'?'); args.append(encoded)
        if request.start is not None and request.end is not None and request.start > request.end: raise BackendError('invalid_input')
        self._validate_query_source(schema, selection=request)
        rows = self._connection.execute(self._record_sql(schema,where=' AND '.join(where),order=True,limit=True),
                                        (*args,request.limit+1)).fetchall()
        if len(rows)>request.limit: raise BackendError('unsupported')
        # Keep the selection's complete detached snapshot, including GetObject.
        rows = self._full_rows(schema,rows)
        presence = self._record_presence(schema, rows)
        return tuple(self._card(schema,row,presence=presence) for row in rows)

    def _validate_query_source(self, schema, *, selection=None):
        """Validate all logical data once; retain only bounded aggregate costs."""
        self._view._require()
        key = ('document-full', schema.identity, schema)
        if self._view._cache_validation_allowed() and key in self._view._validated_sources:
            return self._view._validated_sources[key]
        self._preflight(schema)
        count = cells = text = selected = 0
        validation = self._connection.execute(
            self._record_sql(schema,order=selection is not None), (str(schema.identity),))
        try:
            def batches():
                while rows := validation.fetchmany(64):
                    rows = self._full_rows(schema,rows)
                    presence = self._record_presence(schema, rows)
                    for row in rows: yield row, presence
            for row, presence in batches():
                decoded = self._decode_record(schema, row, presence=presence)
                if (selection is not None
                        and (selection.start is None or decoded[3] >= selection.start)
                        and (selection.end is None or decoded[3] <= selection.end)):
                    selected += 1
                    # Preserve the old sorted Select failure frontier: overflow
                    # wins over corruption in rows not yet reached. No proof is
                    # published for a truncated or failed validation.
                    if selected > selection.limit: raise BackendError('unsupported')
                count += 1
                cells += 5 + len(decoded[5])
                text += len(decoded[2]) + sum(len(v) for v in decoded[5] if type(v) is str)
                for section in decoded[6]:
                    for line in section.rows:
                        cells += 2 + len(line.values)
                        text += sum(len(v) for v in line.values if type(v) is str)
        finally:
            validation.close()
        result = (count, cells, text)
        if self._view._cache_validation_allowed():
            self._view._validated_sources[key] = result
        return result

    def _document_where(self, schema, predicate):
        from yadinassi.db.catalog.catalog_backend import CatalogComparison
        from datetime import datetime
        if type(predicate) is not tuple or len(predicate) > 128: raise BackendError('invalid_input')
        where, args = [], []
        for term in predicate:
            if type(term) is not CatalogComparison or type(term.field) is not str or type(term.operator) is not str:
                raise BackendError('invalid_input')
            if term.operator not in ('eq','ne','lt','le','gt','ge'): raise BackendError('invalid_input')
            field, value = term.field, term.value
            if field == 'number' and type(value) is str:
                validate_string(value, schema.number_length)
                column = 'r.number COLLATE yadinassi_casefold_v1'
            elif field == 'date' and type(value) is datetime:
                value = _storage()._encode(value, _DATE_FIELD, self.database_id)[1]
                column = 'r.date'
            elif field == 'deletion_mark' and type(value) is bool and term.operator in ('eq','ne'):
                value, column = int(value), 'r.deletion_mark'
            else: raise BackendError('invalid_input')
            where.append(column + ' ' + {'eq':'=','ne':'!=','lt':'<','le':'<=','gt':'>','ge':'>='}[term.operator] + ' ?')
            args.append(value)
        return where,args

    def ordered_document_values(self, identity, request, fields):
        """One bounded query-language page over owned native columns."""
        from yadinassi.db.catalog.catalog_backend import CatalogOrder, CatalogPredicate, CatalogScanRequest
        from yadinassi.db.document.document_backend import DocumentValuePage
        view=self._view
        view._require()
        if not view._query_language or view._operation_id is not None: return None
        if view._backend._active is not view: raise BackendError('closed')
        schema = self.document_schema(identity)
        fields_sql = {'ref':'r.record_id COLLATE BINARY',
                      'number':'r.number COLLATE yadinassi_casefold_v1',
                      'date':'r.date COLLATE BINARY','deletion_mark':'r.deletion_mark'}
        if (type(request) is not CatalogScanRequest or type(request.page_size) is not int
                or not 1 <= request.page_size <= 10000 or request.continuation is not None
                or type(request.order) is not tuple or not 1 <= len(request.order) <= 16
                or type(request.string_comparison) is not str or request.string_comparison != 'casefold_v1'
                or type(fields) is not tuple):
            raise BackendError('invalid_input')
        self._projection_fields(schema,fields)
        attributes = self._projected_attributes(schema,fields)
        for field in attributes:
            physical = 'a.'+quote_identifier(attribute_column(field))
            if field.kind == 'string':
                fields_sql[field.identity] = physical+' COLLATE yadinassi_casefold_v1'
            elif field.kind == 'catalog_ref':
                fields_sql[field.identity] = ("COALESCE("+physical+",'00000000-0000-0000-0000-000000000000') "
                                              "COLLATE yadinassi_uuid_v1")
            elif field.kind in ('datetime','boolean','number'):
                fields_sql[field.identity] = physical
        order = []
        for item in request.order:
            if (type(item) is not CatalogOrder or (type(item.field) is not str and type(item.field) is not UUID)
                    or type(item.descending) is not bool): raise BackendError('invalid_input')
            column = fields_sql.get(item.field)
            if column is None: return None
            order.append(column + (' DESC' if item.descending else ' ASC'))
        # The residual stable sort loads documents in this exact source order.
        order.extend(('r.date ASC','r.number COLLATE BINARY ASC','r.record_id ASC'))
        predicate = request.predicate
        if predicate is None:
            terms = ()
        elif type(predicate) is CatalogPredicate and type(predicate.kind) is str and predicate.kind == 'and':
            terms = predicate.terms
        else:
            return None
        where,args = self._document_where(schema,terms)
        _storage()._close_document_scan(view)
        view._scan_cursor = None
        sql = self._projection_sql(schema,fields,where=' AND '.join(('r.document_id=?',*where)))
        cursor = self._connection.execute(sql+' ORDER BY '+','.join(order)+' LIMIT ?',
                                          (str(identity),*args,request.page_size))
        try:
            projected = self._projected_rows(schema,tuple(cursor),fields)
            presence = self._projection_presence(schema,projected,attributes=attributes) if attributes else None
            rows = tuple(self._project_header(schema,fields,row,presence=presence) for row in projected)
        finally:
            cursor.close()
        view._require()
        if view._backend._active is not view: raise BackendError('closed')
        return DocumentValuePage(rows,None)

    def scan_document_values(self, identity, request, fields, section_id=None, predicate=()):
        """Closed SQLite projection port, never a partial DocumentCard.

        The first pass validates ALL fields/sections, including excluded data.
        Subsequent materialization reads only the requested header or section.
        """
        from yadinassi.db.document.document_backend import DocumentValueRow, DocumentValuePage
        self._view._require()
        if self._view._operation_id is not None: raise BackendError('unsupported')
        schema = self.document_schema(identity)
        section = None
        if section_id is not None:
            section = next((s for s in schema.tabular_sections if s.identity == section_id), None)
            if section is None: raise BackendError('invalid_input')
        definitions = self._projection_fields(schema,fields,section)
        if type(request) is not DocumentScanRequest or type(request.page_size) is not int or not 1 <= request.page_size <= 1000:
            raise BackendError('invalid_input')
        where, args = self._document_where(schema,predicate)
        binding = ('document-values', identity, request.page_size, fields, section_id, predicate)
        if request.continuation is not None:
            cursor = self._view._scan_cursor
            if (type(request.continuation) is not str or len(request.continuation) != 32 or cursor is None
                    or cursor[:2] != (request.continuation, binding) or self._view._document_scan_stream is None):
                raise BackendError('invalid_input')
        else:
            _storage()._close_document_scan(self._view)
            self._view._scan_cursor = None
            self._validate_query_source(schema)
        try:
            if request.continuation is None:
                self._view._document_scan_stream = self._connection.execute(
                    self._projection_sql(schema,fields,where='r.document_id=?'+
                        ((' AND '+' AND '.join(where)) if where else ''),order=True,section=section is not None),
                    (str(identity),*args))
            stream = self._view._document_scan_stream
            pending = self._view._document_scan_lookahead
            rows = [] if pending is None else [pending]
            rows.extend(stream.fetchmany(request.page_size + 1 - len(rows)))
            more = len(rows) > request.page_size
            output = []
            projected = self._projected_rows(schema,rows[:request.page_size],fields,section)
            presence = self._projection_presence(schema,projected,section=section is not None,
                attributes=self._projected_attributes(schema,fields) if section is None else ())
            for row in projected:
                if section is None:
                    output.append(self._project_header(schema,fields,row,presence=presence))
                else:
                    record, number, date, mark, payload, revision, state_revision, posted = row
                    key = DocumentKey(self.database_id,identity,UUID(record))
                    contents = next(item[1] for item in payload if item[0] == str(section_id))
                    for n, (_, line) in enumerate(contents, 1):
                        values = dict(zip((d.identity for d in definitions), self._values(definitions, line,presence=presence)))
                        values.update(ref=key, line_number=Decimal(n))
                        output.append(DocumentValueRow(key, tuple(values[f] for f in fields), n))
            token = uuid4().hex if more else None
            if more:
                self._view._document_scan_lookahead = rows[-1]
                self._view._scan_cursor = (token, binding)
            else: _storage()._close_document_scan(self._view)
            return DocumentValuePage(tuple(output), token)
        except BaseException:
            _storage()._close_document_scan(self._view)
            raise

    def scan_documents(self, identity, request):
        """Page complete cards without weakening the ordinary selection limit.

        A shared cursor makes tokens single-use and invalidates them when a new
        catalog or document scan begins. SQL and offsets never leave this port.
        """
        self._view._require()
        if self._view._operation_id is not None: raise BackendError('unsupported')
        schema = self.document_schema(identity)
        if (type(request) is not DocumentScanRequest or type(request.page_size) is not int
                or not 1 <= request.page_size <= 1000):
            raise BackendError('invalid_input')
        binding = ('document', identity, request.page_size)
        if request.continuation is not None:
            if type(request.continuation) is not str or len(request.continuation) != 32:
                raise BackendError('invalid_input')
            cursor = self._view._scan_cursor
            if cursor is None or cursor[0] != request.continuation or cursor[1] != binding:
                raise BackendError('invalid_input')
            if self._view._document_scan_stream is None: raise BackendError('invalid_input')
        else:
            _storage()._close_document_scan(self._view)
            self._view._scan_cursor = None
            self._validate_query_source(schema)
        try:
            if request.continuation is None:
                # Keep one SQLite stream, not an OFFSET sort per page. The
                # connection owns its lifetime, including backend-level close.
                self._view._document_scan_stream = self._connection.execute(
                    self._record_sql(schema,order=True), (str(identity),))
            stream = self._view._document_scan_stream
            pending = self._view._document_scan_lookahead
            rows = ([] if pending is None else [pending])
            rows.extend(stream.fetchmany(request.page_size + 1 - len(rows)))
            more = len(rows) > request.page_size
            full_rows = self._full_rows(schema,rows[:request.page_size])
            presence = self._record_presence(schema, full_rows)
            cards = tuple(self._card(schema, row,presence=presence) for row in full_rows)
            token = uuid4().hex if more else None
            if more:
                self._view._document_scan_lookahead = rows[-1]
                self._view._scan_cursor = (token, binding)
            else:
                _storage()._close_document_scan(self._view)
            return DocumentPage(cards, token)
        except BaseException as error:
            try: _storage()._close_document_scan(self._view)
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            raise

    def find_document_number(self, identity, number):
        schema = self.document_schema(identity); validate_string(number,schema.number_length)
        self._preflight(schema)
        row = self._connection.execute('SELECT record_id FROM document_record WHERE document_id=? AND number=?',
                                       (str(identity),number)).fetchone()
        if row is None: return None
        key = DocumentKey(self.database_id,identity,UUID(row[0]))
        if str(key.record_id)!=row[0]: raise BackendError('integrity')
        self._validate_record(schema,key)
        return key

    def _intent(self, draft, expected):
        if type(draft) is not DocumentDraft or type(draft.auto_number) is not bool or type(draft.deletion_mark) is not bool: raise BackendError('invalid_input')
        schema = self._key(draft.key); _storage()._uuid(draft.key.record_id)
        number = normalize_string(draft.number,schema.number_length)
        if draft.auto_number:
            if expected is not None or schema.numbering != 'decimal_v1' or number != '': raise BackendError('invalid_input')
        elif not number: raise BackendError('invalid_input')
        if expected is not None:
            if type(expected) is not DocumentRevision or (expected.database_id,expected.configuration_generation,expected.document_id,expected.record_id) != (self.database_id,self.configuration_generation,schema.identity,draft.key.record_id): raise BackendError('conflict')
            _storage()._revision_number(expected.token)
        values = self._values(schema.fields,draft.values,writing=True)
        contents = draft.tabular_sections
        sparse = type(contents) is _TabularSectionChanges
        if sparse:
            if expected is None or self._view._backend.format_version not in (15, 16):
                raise BackendError('invalid_input')
            contents = contents.sections
            if type(contents) is not tuple: raise BackendError('invalid_input')
        sections = None if contents is None else self._sections(schema,contents,writing=True,sparse=sparse)
        date = _storage()._encode(draft.date,_DATE_FIELD,self.database_id)[1]
        intent = ['document_write_v1',str(schema.identity),str(draft.key.record_id),number,date,draft.deletion_mark,values,sections,draft.auto_number,None if expected is None else expected.token]
        dump = _storage()._json
        if sparse:
            intent[7] = None
            envelope = len(dump(intent))-4  # replace JSON null with the exact section payload
            intent[7] = sections
            size = envelope+len(dump(sections))
        else:
            envelope = None
            size = len(dump(intent))
        if size > _MAX_ROW: raise BackendError('invalid_input')
        return schema,intent,(size,envelope)

    def create(self, draft): self._write(draft,None)
    def update(self, draft, expected):
        if expected is None: raise BackendError('invalid_input')
        self._write(draft,expected)

    def _write_attributes(self, schema, document, record, values, create):
        if not schema.fields: return
        table = quote_identifier(data_table(schema))
        cols = tuple(quote_identifier(attribute_column(field)) for field in schema.fields)
        raw = encode_typed_columns(values,schema,enum_domain=self._view._backend._enum_domain)
        if create:
            sql = 'INSERT INTO '+table+'(document_id,record_id,'+','.join(cols)+') VALUES('+','.join('?' for _ in range(len(raw)+2))+')'
            self._connection.execute(sql,(document,record,*raw))
        else:
            sql = 'UPDATE '+table+' SET '+','.join(column+'=?' for column in cols)+' WHERE document_id=? AND record_id=?'
            if self._connection.execute(sql,(*raw,document,record)).rowcount != 1: raise BackendError('integrity')

    def _write_parts(self, schema, document, record, sections):
        if not sections: return
        values = dict(sections)
        domain = self._view._backend._enum_domain
        for section in schema.tabular_sections:
            rows = values.get(str(section.identity))
            if rows is None: continue
            table = quote_identifier(section_table(schema,section))
            self._connection.execute('DELETE FROM '+table+' WHERE document_id=? AND record_id=?',(document,record))
            if not rows: continue
            columns = ('document_id','record_id','row_id','row_number',
                       *(quote_identifier(attribute_column(field)) for field in section.fields))
            sql = 'INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')'
            self._connection.executemany(sql,
                ((document,record,raw_id,n,*encode_typed_columns(data,section,enum_domain=domain))
                 for n,(raw_id,data) in enumerate(rows,1)))

    def _write(self, draft, expected, *, max_intent=None):
        self._view._require(True)
        if self._outcome is not None: raise BackendError('unsupported')
        schema,intent,(intent_size,envelope) = self._intent(draft,expected)
        _,document,record,number,date,mark,values,sections,auto,_ = intent
        count = self._preflight(schema)
        row = self._load_record(schema,draft.key)
        stored = None if row is None else self._full_rows(schema,(row,))[0]
        old = None if stored is None else self._card(schema,stored)
        if expected is None:
            if old is not None: raise BackendError('duplicate_identity')
            if count >= 10000: raise BackendError('unsupported')
            revision = 1
        else:
            if old is None or old.revision != expected: raise BackendError('conflict')
            revision = int(expected.token)+1
        with self._view._atomic_record():
            if auto:
                next_value = self._connection.execute('SELECT next_value FROM document_sequence WHERE document_id=?',(document,)).fetchone()[0]
                while next_value < 10**schema.number_length:
                    number = str(next_value).zfill(schema.number_length); next_value += 1
                    if not self._connection.execute('SELECT 1 FROM document_record WHERE document_id=? AND number=?',(document,number)).fetchone(): break
                else: raise BackendError('number_exhausted')
                self._connection.execute('UPDATE document_sequence SET next_value=? WHERE document_id=?',(next_value,document))
            if self._connection.execute('SELECT 1 FROM document_record WHERE document_id=? AND number=? AND record_id!=?',(document,number,record)).fetchone(): raise BackendError('duplicate_number')
            dump = _storage()._json
            changed_sections = sections
            if envelope is not None:
                # Charge the same resulting logical document, but persist
                # only explicitly modified physical child tables.
                merged = dict(stored[6]); merged.update(sections)
                if sum(len(rows) for rows in merged.values()) > 1000: raise BackendError('unsupported')
                intent_size = envelope+len(dump(sorted(merged.items())))
                if intent_size > _MAX_ROW: raise BackendError('invalid_input')
                if max_intent is not None and intent_size > max_intent: raise BackendError('unsupported')
            elif len(dump(values))+len(dump(sections if sections is not None else
                                               stored[6] if stored is not None else [])) > _MAX_ROW:
                raise BackendError('invalid_input')
            scalars = (revision,number,date,int(mark),document,record)
            if old is None:
                self._connection.execute('INSERT INTO document_record(revision,number,date,deletion_mark,document_id,record_id) VALUES(?,?,?,?,?,?)',scalars)
            else:
                self._connection.execute('UPDATE document_record SET revision=?,number=?,date=?,deletion_mark=? WHERE document_id=? AND record_id=?',scalars)
            self._write_attributes(schema,document,record,values,old is None)
            self._write_parts(schema,document,record,changed_sections)
            self._preflight(schema)
            # Allocate the result while rollback still covers this row
            # and its sequence. After RELEASE install only existing references.
            outcome = DocumentWriteOutcome(DocumentRevision(self.database_id,self.configuration_generation,schema.identity,draft.key.record_id,str(revision)),number)
        self._outcome = outcome
        return intent_size

    def _confirm_commit(self):
        self._view._require(True)
        if self._outcome is None: raise BackendError('invalid_input')
        # Caller publishes this acknowledged outcome, then closes its view.
        _storage()._confirm_sqlite_commit(self._connection)
        self._view._committed = True
        return self._outcome

    def commit(self):
        try:
            result = self._confirm_commit()
            self.close()
        except BaseException as error:
            try: self.close()
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            raise
        return result
