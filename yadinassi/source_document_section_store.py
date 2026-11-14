"""Opt-in v6 document sections; aggregate writes share the owner's revision."""
import json
import sqlite3
from .source_document_store import SourceDocumentStore
from .source_catalog_store import SourceCatalogStore
from .source_constant_store import _json, _encode, _decode

_MAX_ROWS=1000
_MAX_SECTION_BYTES=262144
_MAX_DOCUMENT_BYTES=1048576
_SECTION_DDL=(
 'CREATE TABLE source_document_section(document_identity TEXT NOT NULL, record_identity TEXT NOT NULL, section_identity TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(document_identity,record_identity,section_identity), FOREIGN KEY(document_identity,record_identity) REFERENCES source_document_record(document_identity,record_identity))',
)

def _definitions(source,enums=None,refs=None):
    from .source_document_definitions import source_document_definitions,document_definition_record
    definitions,errors=source_document_definitions(source,enums,refs,allow_sections=True)
    return definitions,errors,tuple(sorted((str(d.identity),d.name,_json(document_definition_record(d))) for d in definitions.values()))

def encode_section(section,rows):
    if type(rows) is not tuple or len(rows)>_MAX_ROWS:raise ValueError('section row count/type bound')
    result=[];size=2
    for row in rows:
        if type(row) is not dict or set(row)!={f.name.casefold() for f in section.fields}:
            raise ValueError('all section fields require explicit assignment')
        cells=[]
        for field in section.fields:
            raw_value=_encode(row[field.name.casefold()],field)
            size+=len(raw_value.encode())+1
            if size>_MAX_SECTION_BYTES:raise ValueError('section byte bound')
            cells.append(json.loads(raw_value))
        size+=3
        result.append(cells)
    raw=_json(result)
    if len(raw.encode())>_MAX_SECTION_BYTES:raise ValueError('section byte bound')
    return raw

def decode_section(section,raw):
    if type(raw) is not str or len(raw.encode())>_MAX_SECTION_BYTES:raise ValueError('section byte bound')
    try:
        rows=json.loads(raw)
        if type(rows) is not list or len(rows)>_MAX_ROWS:raise ValueError('section row bound')
        result=[]
        for row in rows:
            if type(row) is not list or len(row)!=len(section.fields):raise ValueError('section field inventory')
            result.append({f.name.casefold():_decode(_json(v),f) for f,v in zip(section.fields,row)})
        result=tuple(result)
        if encode_section(section,result)!=raw:raise ValueError('section canonical integrity')
        return result
    except (TypeError,KeyError,RecursionError) as error:raise ValueError('section payload integrity') from error


class SourceDocumentSectionStore(SourceDocumentStore):
    PROFILE='source-document-sections-v6'
    @classmethod
    def ddl(cls):return super().ddl()+_SECTION_DDL
    @classmethod
    def initialize_extra(cls,connection,source,enum_namespace,reference_scope):
        SourceCatalogStore.initialize_extra(connection,source,enum_namespace,reference_scope)
        _,_,rows=_definitions(source,enum_namespace,reference_scope)
        connection.executemany('INSERT INTO source_document_schema VALUES(?,?,?)',rows)
    @classmethod
    def attach_extra(cls,result,source,enum_namespace,reference_scope):
        SourceCatalogStore.attach_extra(result,source,enum_namespace,reference_scope)
        result.document_definitions,result.document_errors,result._document_rows=_definitions(source,enum_namespace,reference_scope)
    def verify_extra(self):
        super().verify_extra()
        if self._connection.execute("SELECT count(*) FROM source_document_section WHERE typeof(document_identity)!='text' OR length(CAST(document_identity AS BLOB))!=36 OR typeof(record_identity)!='text' OR length(CAST(record_identity AS BLOB))!=36 OR typeof(section_identity)!='text' OR length(CAST(section_identity AS BLOB))!=36 OR typeof(payload)!='text' OR length(CAST(payload AS BLOB))>262144").fetchone()[0]:raise ValueError('section storage bounds')
        count,total=self._connection.execute('SELECT count(*),coalesce(sum(length(CAST(payload AS BLOB))),0) FROM source_document_section').fetchone()
        if count>160000 or total>16777216:raise ValueError('section aggregate storage bound')
    def _sections(self,definition,identity):
        count,total=self._connection.execute('SELECT count(*),coalesce(sum(length(CAST(payload AS BLOB))),0) FROM source_document_section WHERE document_identity=? AND record_identity=?',(str(definition.identity),str(identity))).fetchone()
        if count!=len(definition.sections) or total>_MAX_DOCUMENT_BYTES:raise ValueError('document section inventory/byte bound')
        rows=self._connection.execute('SELECT section_identity,payload FROM source_document_section WHERE document_identity=? AND record_identity=? ORDER BY section_identity',(str(definition.identity),str(identity))).fetchall()
        known={str(s.identity):s for s in definition.sections}
        if {r[0] for r in rows}!=set(known) or len(rows)!=len(known):raise ValueError('section inventory integrity')
        if sum(len(raw.encode()) for _,raw in rows)>_MAX_DOCUMENT_BYTES:raise ValueError('document section byte bound')
        result={known[sid].name.casefold():decode_section(known[sid],raw) for sid,raw in rows}
        if sum(map(len,result.values()))>_MAX_ROWS:raise ValueError('document section row bound')
        return result
    def validate_records(self):
        super().validate_records()
        known={str(d.identity):d for d in self.document_definitions.values()}
        for did,rid in self._connection.execute('SELECT document_identity,record_identity FROM source_document_record'):
            self._sections(known[did],rid)
        if self._connection.execute('PRAGMA foreign_key_check').fetchone() is not None:raise ValueError('section foreign key integrity')
    def read_documents(self,name,identity=None):
        owned=not self.transaction_active
        try:
            if owned:self.begin_transaction()
            result=super().read_documents(name,identity)
            definition=self.document(name)
            for rid,_,_ in result:self._sections(definition,rid)
            if owned:self.rollback_transaction()
            return result
        except BaseException:
            self._abort();raise
    def read_document_bundle(self,name,identity):
        owned=not self.transaction_active
        try:
            if owned:self.begin_transaction()
            self._open()
            rid,revision,values=super().read_documents(name,identity)[0]
            sections=self._sections(self.document(name),rid)
            if owned:self.rollback_transaction()
            return rid,revision,values,sections
        except BaseException:
            self._abort();raise
    def write_document(self,name,identity,revision,values,*,_handled=None):
        if self.document(name).sections:
            self._abort();raise ValueError('section-bearing document requires aggregate Write')
        return super().write_document(name,identity,revision,values,_handled=_handled)
    def write_document_bundle(self,name,identity,revision,values,sections,*,_handled=None):
        owned=not self.transaction_active
        try:
            definition=self.document(name)
            if type(sections) is not dict or set(sections)!={s.name.casefold() for s in definition.sections}:raise ValueError('document section inventory')
            encoded=[(str(s.identity),encode_section(s,sections[s.name.casefold()])) for s in definition.sections]
            if sum(len(raw.encode()) for _,raw in encoded)>_MAX_DOCUMENT_BYTES or sum(len(r) for r in sections.values())>_MAX_ROWS:raise ValueError('document section aggregate bound')
            if owned:self.begin_transaction()
            new_revision=super().write_document(name,identity,revision,values,_handled=_handled)
            self._connection.execute('DELETE FROM source_document_section WHERE document_identity=? AND record_identity=?',(str(definition.identity),str(identity)))
            self._connection.executemany('INSERT INTO source_document_section VALUES(?,?,?,?)',[(str(definition.identity),str(identity),sid,raw) for sid,raw in encoded])
            self._open();self._sections(definition,identity)
            if owned:self.commit_transaction()
            return new_revision
        except BaseException:
            self._abort();raise
    def validate_source_update(self,source):
        SourceCatalogStore.validate_source_update(self,source)
        _,errors,rows=_definitions(source)
        if rows!=self._document_rows or errors!=self.document_errors:raise ValueError('source section schema migration unsupported')
    @classmethod
    def update_source(cls,path,source):
        return super(SourceDocumentStore,cls).update_source(path,source)
    @classmethod
    def upgrade_copy(cls, original, destination):
        """Readonly v5 snapshot -> distinct v6 file; never open original writable."""
        import os
        from pathlib import Path
        from .sqlite_catalog import _private_parent
        from .source_constant_store import _file_identity, _schema
        original = _private_parent(os.path.abspath(os.fspath(original)))
        identity = _file_identity(original)
        if any(os.path.lexists(original+s) for s in ('-journal','-wal','-shm')):
            raise ValueError('upgrade requires clean-close source')
        raw=os.fspath(destination)
        if type(raw) is not str or not raw or raw.startswith(('file:','//','\\\\')) or '\x00' in raw:
            raise ValueError('invalid document upgrade destination')
        target_path=_private_parent(os.path.abspath(raw))
        source=SourceDocumentStore.load_source(original)
        old=sqlite3.connect(Path(original).as_uri()+'?mode=ro',uri=True,isolation_level=None)
        target=None
        try:
            old.execute('PRAGMA trusted_schema=OFF');old.execute('BEGIN')
            if _schema(old)!=SourceDocumentStore.expected_schema():
                raise ValueError('upgrade requires exact v5 schema')
            fd=os.open(target_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            target_identity=_file_identity(target_path)
            target=sqlite3.connect(target_path,isolation_level=None)
            old.backup(target)
            if _file_identity(original)!=identity:raise ValueError('source identity changed')
            old.execute('ROLLBACK');target.close();target=None
            # Validate all v5 data on the private copy before conversion, not original.
            checked=SourceDocumentStore.reopen(target_path,source)
            try:
                checked._connection.execute('BEGIN IMMEDIATE');checked._open();checked.validate_records()
                for statement in _SECTION_DDL:checked._connection.execute(statement)
                _,_,rows=_definitions(source)
                # v5 cannot contain section-bearing documents; preserve every existing
                # supported definition and row, then admit formerly blocked declarations.
                oldrows={r[0]:r for r in checked._document_rows}
                newrows={r[0]:r for r in rows}
                if any(newrows.get(k)!=v for k,v in oldrows.items()):
                    raise ValueError('upgrade would alter existing document schema')
                checked._connection.executemany('INSERT INTO source_document_schema VALUES(?,?,?)',[r for r in rows if r[0] not in oldrows])
                checked._connection.execute('UPDATE source_binding SET profile=?',(cls.PROFILE,))
                if _file_identity(target_path)!=target_identity:raise ValueError('target identity changed')
                checked._connection.execute('COMMIT')
            finally:checked.close()
            verified=cls.reopen(target_path,source);verified.close()
            return target_path
        finally:
            if target is not None:target.close()
            old.close()
