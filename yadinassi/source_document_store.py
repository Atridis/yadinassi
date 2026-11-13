"""Explicit v5 source document records; v4 catalog tables remain unchanged."""
import json
import sqlite3
from uuid import UUID
from .source_catalog_store import SourceCatalogStore, _MAX_RECORDS, _MAX_RECORD_BYTES
from .source_constant_store import _json, _encode, _decode, _MAX_DATABASE_BYTES

_DOCUMENT_DDL = (
 'CREATE TABLE source_document_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
 'CREATE TABLE source_document_record(document_identity TEXT NOT NULL REFERENCES source_document_schema(identity), record_identity TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), payload TEXT NOT NULL CHECK(length(payload)<=65536), number TEXT NOT NULL, PRIMARY KEY(document_identity,record_identity), UNIQUE(document_identity,number))',
)

def _definitions(source,enums=None,refs=None):
    from .source_document_definitions import source_document_definitions, document_definition_record
    definitions,errors=source_document_definitions(source,enums,refs)
    rows=tuple(sorted((str(d.identity),d.name,_json(document_definition_record(d))) for d in definitions.values()))
    return definitions,errors,rows

def encode_record(definition, values):
    if type(values) is not dict or set(values) != {f.name.casefold() for f in definition.fields}:
        raise ValueError('all source document fields require explicit values')
    result = [[str(f.identity), json.loads(_encode(values[f.name.casefold()], f))] for f in definition.fields]
    raw = _json(result)
    if len(raw.encode('utf-8')) > 65536:
        raise ValueError('source document record byte bound')
    if not values['number']:
        raise ValueError('source document requires a nonempty explicit Number')
    if values['posted'] is not False:
        raise ValueError('source document posting unsupported')
    return raw


def decode_record(definition, raw):
    if type(raw) is not str or len(raw.encode('utf-8')) > 65536:
        raise ValueError('source document record byte bound')
    try:
        rows = json.loads(raw)
        if type(rows) is not list or len(rows) != len(definition.fields):
            raise ValueError('source document field inventory')
        values = {}
        for field, row in zip(definition.fields, rows):
            if type(row) is not list or len(row) != 2 or row[0] != str(field.identity):
                raise ValueError('source document field identity')
            values[field.name.casefold()] = _decode(_json(row[1]), field)
        if encode_record(definition, values) != raw:
            raise ValueError('source document canonical payload')
        return values
    except (TypeError, KeyError, IndexError, RecursionError) as error:
        raise ValueError('source document payload integrity') from error


class SourceDocumentStore(SourceCatalogStore):
    PROFILE = 'source-document-records-v5'

    @classmethod
    def ddl(cls):
        return super().ddl() + _DOCUMENT_DDL

    @classmethod
    def initialize_extra(cls,connection,source,enum_namespace,reference_scope):
        super().initialize_extra(connection,source,enum_namespace,reference_scope)
        _,_,rows=_definitions(source,enum_namespace,reference_scope)
        connection.executemany('INSERT INTO source_document_schema VALUES(?,?,?)',rows)

    @classmethod
    def attach_extra(cls,result,source,enum_namespace,reference_scope):
        super().attach_extra(result,source,enum_namespace,reference_scope)
        result.document_definitions,result.document_errors,result._document_rows=_definitions(source,enum_namespace,reference_scope)

    def verify_extra(self):
        super().verify_extra()
        if self._connection.execute("SELECT count(*) FROM source_document_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>1024 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>65536").fetchone()[0]:
            raise ValueError('source document schema byte bound')
        if self._connection.execute("SELECT count(*) FROM source_document_record WHERE typeof(document_identity)!='text' OR length(CAST(document_identity AS BLOB))!=36 OR typeof(record_identity)!='text' OR length(CAST(record_identity AS BLOB))!=36 OR typeof(number)!='text' OR length(CAST(number AS BLOB))>36 OR typeof(payload)!='text' OR length(CAST(payload AS BLOB))>65536 OR typeof(revision)!='integer' OR revision<1 OR revision>9007199254740992").fetchone()[0]:
            raise ValueError('source document record storage bounds')
        if self._connection.execute('PRAGMA page_count').fetchone()[0]*self._connection.execute('PRAGMA page_size').fetchone()[0]>_MAX_DATABASE_BYTES:
            raise ValueError('source document database size bound')
        rows = tuple(self._connection.execute('SELECT identity,name,definition FROM source_document_schema ORDER BY identity LIMIT 4097'))
        if rows != self._document_rows:
            raise ValueError('source document schema binding integrity')
        counts = self._connection.execute('SELECT count(*),coalesce(max(length(CAST(payload AS BLOB))),0),coalesce(sum(length(CAST(payload AS BLOB))),0) FROM source_document_record').fetchone()
        if counts[0] > _MAX_RECORDS or counts[1] > 65536 or counts[2] > _MAX_RECORD_BYTES:
            raise ValueError('source document record bounds')

    def validate_records(self):
        super().validate_records()
        known = {str(d.identity):d for d in self.document_definitions.values()}
        for cid, rid, rev, raw, number in self._connection.execute('SELECT document_identity,record_identity,revision,payload,number FROM source_document_record LIMIT ?', (_MAX_RECORDS+1,)):
            if cid not in known or type(rid) is not str or str(UUID(rid)) != rid or UUID(rid).int == 0 or type(rev) is not int or not 1 <= rev <= 2**53:
                raise ValueError('source document record identity/revision integrity')
            if decode_record(known[cid], raw)['number'] != number:
                raise ValueError('source document number integrity')

    def document(self, name):
        if type(name) is not str:
            raise TypeError('source document name requires String')
        if name.casefold() in self.document_errors:
            raise ValueError('source document unsupported: '+name+': '+self.document_errors[name.casefold()])
        try:
            return self.document_definitions[name.casefold()]
        except KeyError:
            raise ValueError('unknown source document: '+name) from None

    def _abort(self):
        if self._connection.in_transaction:
            self._connection.execute('ROLLBACK')
        self._explicit_transaction = False

    def read_documents(self, name, identity=None):
        definition = self.document(name)
        owned = not self.transaction_active
        try:
            if owned:self._connection.execute('BEGIN')
            self._open()
            sql = 'SELECT record_identity,revision,payload,number FROM source_document_record WHERE document_identity=?'
            args = [str(definition.identity)]
            if identity is not None:
                sql += ' AND record_identity=?'; args.append(str(identity))
            sql += ' ORDER BY record_identity LIMIT ?';args.append(_MAX_RECORDS+1)
            rows = self._connection.execute(sql, args).fetchall()
            if len(rows)>_MAX_RECORDS:raise ValueError('source document record bound')
            result=[]
            for rid,rev,raw,number in rows:
                if type(rid) is not str or str(UUID(rid))!=rid or UUID(rid).int==0 or type(rev) is not int or not 1<=rev<=2**53:
                    raise ValueError('source document record identity/revision integrity')
                values=decode_record(definition,raw)
                if values['number']!=number:raise ValueError('source document number integrity')
                result.append((UUID(rid),rev,values))
            if identity is not None and not result:raise ValueError('source document record not found')
            if owned:self._connection.execute('ROLLBACK')
            return result
        except BaseException:
            self._abort();raise

    def write_document(self, name, identity, revision, values):
        definition=self.document(name)
        owned=not self.transaction_active
        try:
            raw=encode_record(definition,values)
            if type(identity) is not UUID or identity.int==0 or type(revision) is not int or not 0<=revision<2**53:
                raise ValueError('source document write identity/revision')
            if owned:self._connection.execute('BEGIN IMMEDIATE')
            self._open()
            if revision==0:
                if self._connection.execute('SELECT count(*) FROM source_document_record').fetchone()[0]>=_MAX_RECORDS:
                    raise ValueError('source document record bound')
                self._connection.execute('INSERT INTO source_document_record VALUES(?,?,?,?,?)',(str(definition.identity),str(identity),1,raw,values['number']))
            else:
                count=self._connection.execute('UPDATE source_document_record SET revision=?,payload=?,number=? WHERE document_identity=? AND record_identity=? AND revision=?',(revision+1,raw,values['number'],str(definition.identity),str(identity),revision)).rowcount
                if count!=1:raise ValueError('source document stale revision; Read again')
            self._open()
            if owned:self._connection.execute('COMMIT')
            return revision+1
        except BaseException as error:
            self._abort()
            if isinstance(error,sqlite3.Error):raise ValueError('source document write refused') from None
            raise

    def validate_source_update(self, source):
        super().validate_source_update(source)
        _, errors, rows = _definitions(source)
        if rows != self._document_rows or errors != self.document_errors:
            raise ValueError('source document schema migration unsupported; preserve original database')

    @classmethod
    def update_source(cls, path, source):
        previous=cls.load_source(path)
        old,errors,rows=_definitions(previous)
        new,new_errors,new_rows=_definitions(source)
        if rows!=new_rows or errors!=new_errors:
            raise ValueError('source document schema migration unsupported; preserve original database')
        # New object modules/subscriptions change the parser blockers and are refused above.
        return super().update_source(path,source)

    @classmethod
    def upgrade_copy(cls, original, destination):
        """Readonly v4 snapshot -> distinct v5 file; never open original writable."""
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
        source=SourceCatalogStore.load_source(original)
        old=sqlite3.connect(Path(original).as_uri()+'?mode=ro',uri=True,isolation_level=None)
        target=None
        try:
            old.execute('PRAGMA trusted_schema=OFF');old.execute('BEGIN')
            if _schema(old)!=SourceCatalogStore.expected_schema():
                raise ValueError('upgrade requires exact v4 schema')
            fd=os.open(target_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            target_identity=_file_identity(target_path)
            target=sqlite3.connect(target_path,isolation_level=None)
            old.backup(target)
            if _file_identity(original)!=identity:raise ValueError('source identity changed')
            old.execute('ROLLBACK');target.close();target=None
            # Validate all v4 data on the private copy before conversion, not original.
            checked=SourceCatalogStore.reopen(target_path,source)
            try:
                checked._connection.execute('BEGIN IMMEDIATE');checked._open();checked.validate_records()
                for statement in _DOCUMENT_DDL:checked._connection.execute(statement)
                _,_,rows=_definitions(source)
                checked._connection.executemany('INSERT INTO source_document_schema VALUES(?,?,?)',rows)
                checked._connection.execute('UPDATE source_binding SET profile=?',(cls.PROFILE,))
                if _file_identity(target_path)!=target_identity:raise ValueError('target identity changed')
                checked._connection.execute('COMMIT')
            finally:checked.close()
            verified=cls.reopen(target_path,source);verified.close()
            return target_path
        finally:
            if target is not None:target.close()
            old.close()
