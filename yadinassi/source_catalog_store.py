"""Version 4 source records, sharing the constants connection and transactions."""
import json
import sqlite3
from uuid import UUID
from .source_constant_store import SourceConstantStore, _json, _encode, _decode, _DDL, _MAX_DATABASE_BYTES

_RECORD_DDL = (
 'CREATE TABLE source_catalog_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
 'CREATE TABLE source_catalog_record(catalog_identity TEXT NOT NULL REFERENCES source_catalog_schema(identity), record_identity TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), payload TEXT NOT NULL CHECK(length(payload)<=65536), code TEXT NOT NULL, PRIMARY KEY(catalog_identity,record_identity), UNIQUE(catalog_identity,code))',
)
_MAX_RECORDS = 10000
_MAX_RECORD_BYTES = 16 * 1024 * 1024


def _definitions(source, enums=None, refs=None):
    from .source_catalog_definitions import source_catalog_definitions, catalog_definition_record
    definitions, errors = source_catalog_definitions(source, enums, refs)
    rows = tuple(sorted((str(d.identity), d.name, _json(catalog_definition_record(d))) for d in definitions.values()))
    return definitions, errors, rows


def encode_record(definition, values):
    if type(values) is not dict or set(values) != {f.name.casefold() for f in definition.fields}:
        raise ValueError('all source catalog fields require explicit values')
    result = [[str(f.identity), json.loads(_encode(values[f.name.casefold()], f))] for f in definition.fields]
    raw = _json(result)
    if len(raw.encode('utf-8')) > 65536:
        raise ValueError('source catalog record byte bound')
    if not values['code']:
        raise ValueError('source catalog requires a nonempty explicit Code')
    return raw


def decode_record(definition, raw):
    if type(raw) is not str or len(raw.encode('utf-8')) > 65536:
        raise ValueError('source catalog record byte bound')
    try:
        rows = json.loads(raw)
        if type(rows) is not list or len(rows) != len(definition.fields):
            raise ValueError('source catalog field inventory')
        values = {}
        for field, row in zip(definition.fields, rows):
            if type(row) is not list or len(row) != 2 or row[0] != str(field.identity):
                raise ValueError('source catalog field identity')
            values[field.name.casefold()] = _decode(_json(row[1]), field)
        if encode_record(definition, values) != raw:
            raise ValueError('source catalog canonical payload')
        return values
    except (TypeError, KeyError, IndexError, RecursionError) as error:
        raise ValueError('source catalog payload integrity') from error


class SourceCatalogStore(SourceConstantStore):
    PROFILE = 'source-catalog-records-v4'

    @classmethod
    def ddl(cls):
        return _DDL + _RECORD_DDL

    @classmethod
    def initialize_extra(cls, connection, source, enum_namespace, reference_scope):
        _, _, rows = _definitions(source, enum_namespace, reference_scope)
        connection.executemany('INSERT INTO source_catalog_schema VALUES(?,?,?)', rows)

    @classmethod
    def attach_extra(cls, result, source, enum_namespace, reference_scope):
        result.catalog_definitions, result.catalog_errors, result._catalog_rows = _definitions(source, enum_namespace, reference_scope)

    def verify_extra(self):
        if self._connection.execute("SELECT count(*) FROM source_catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>1024 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>65536").fetchone()[0]:
            raise ValueError('source catalog schema byte bound')
        if self._connection.execute("SELECT count(*) FROM source_catalog_record WHERE typeof(catalog_identity)!='text' OR length(CAST(catalog_identity AS BLOB))!=36 OR typeof(record_identity)!='text' OR length(CAST(record_identity AS BLOB))!=36 OR typeof(code)!='text' OR length(CAST(code AS BLOB))>256 OR typeof(payload)!='text' OR length(CAST(payload AS BLOB))>65536 OR typeof(revision)!='integer' OR revision<1 OR revision>9007199254740992").fetchone()[0]:
            raise ValueError('source catalog record storage bounds')
        if self._connection.execute('PRAGMA page_count').fetchone()[0]*self._connection.execute('PRAGMA page_size').fetchone()[0]>_MAX_DATABASE_BYTES:
            raise ValueError('source catalog database size bound')
        rows = tuple(self._connection.execute('SELECT identity,name,definition FROM source_catalog_schema ORDER BY identity LIMIT 4097'))
        if rows != self._catalog_rows:
            raise ValueError('source catalog schema binding integrity')
        counts = self._connection.execute('SELECT count(*),coalesce(max(length(CAST(payload AS BLOB))),0),coalesce(sum(length(CAST(payload AS BLOB))),0) FROM source_catalog_record').fetchone()
        if counts[0] > _MAX_RECORDS or counts[1] > 65536 or counts[2] > _MAX_RECORD_BYTES:
            raise ValueError('source catalog record bounds')

    @classmethod
    def reopen(cls, path, source, **kwargs):
        result = super().reopen(path, source, **kwargs)
        try:
            result._connection.execute('BEGIN')
            result._open()
            result.validate_records()
            result._connection.execute('ROLLBACK')
            return result
        except BaseException:
            result.close()
            raise

    def validate_records(self):
        known = {str(d.identity):d for d in self.catalog_definitions.values()}
        for cid, rid, rev, raw, code in self._connection.execute('SELECT catalog_identity,record_identity,revision,payload,code FROM source_catalog_record LIMIT ?', (_MAX_RECORDS+1,)):
            if cid not in known or type(rid) is not str or str(UUID(rid)) != rid or UUID(rid).int == 0 or type(rev) is not int or not 1 <= rev <= 2**53:
                raise ValueError('source catalog record identity/revision integrity')
            if decode_record(known[cid], raw)['code'] != code:
                raise ValueError('source catalog code integrity')

    def catalog(self, name):
        if type(name) is not str:
            raise TypeError('source catalog name requires String')
        if name.casefold() in self.catalog_errors:
            raise ValueError('source catalog unsupported: '+name+': '+self.catalog_errors[name.casefold()])
        try:
            return self.catalog_definitions[name.casefold()]
        except KeyError:
            raise ValueError('unknown source catalog: '+name) from None

    def _abort(self):
        if self._connection.in_transaction:
            self._connection.execute('ROLLBACK')
        self._explicit_transaction = False

    def read_records(self, name, identity=None):
        definition = self.catalog(name)
        owned = not self.transaction_active
        try:
            if owned:self._connection.execute('BEGIN')
            self._open()
            sql = 'SELECT record_identity,revision,payload,code FROM source_catalog_record WHERE catalog_identity=?'
            args = [str(definition.identity)]
            if identity is not None:
                sql += ' AND record_identity=?'; args.append(str(identity))
            sql += ' ORDER BY record_identity LIMIT ?';args.append(_MAX_RECORDS+1)
            rows = self._connection.execute(sql, args).fetchall()
            if len(rows)>_MAX_RECORDS:raise ValueError('source catalog record bound')
            result=[]
            for rid,rev,raw,code in rows:
                if type(rid) is not str or str(UUID(rid))!=rid or UUID(rid).int==0 or type(rev) is not int or not 1<=rev<=2**53:
                    raise ValueError('source catalog record identity/revision integrity')
                values=decode_record(definition,raw)
                if values['code']!=code:raise ValueError('source catalog code integrity')
                result.append((UUID(rid),rev,values))
            if identity is not None and not result:raise ValueError('source catalog record not found')
            if owned:self._connection.execute('ROLLBACK')
            return result
        except BaseException:
            self._abort();raise

    def write_record(self, name, identity, revision, values):
        definition=self.catalog(name)
        owned=not self.transaction_active
        try:
            raw=encode_record(definition,values)
            if type(identity) is not UUID or identity.int==0 or type(revision) is not int or not 0<=revision<2**53:
                raise ValueError('source catalog write identity/revision')
            if owned:self._connection.execute('BEGIN IMMEDIATE')
            self._open()
            if revision==0:
                if self._connection.execute('SELECT count(*) FROM source_catalog_record').fetchone()[0]>=_MAX_RECORDS:
                    raise ValueError('source catalog record bound')
                self._connection.execute('INSERT INTO source_catalog_record VALUES(?,?,?,?,?)',(str(definition.identity),str(identity),1,raw,values['code']))
            else:
                count=self._connection.execute('UPDATE source_catalog_record SET revision=?,payload=?,code=? WHERE catalog_identity=? AND record_identity=? AND revision=?',(revision+1,raw,values['code'],str(definition.identity),str(identity),revision)).rowcount
                if count!=1:raise ValueError('source catalog stale revision; Read again')
            self._open()
            if owned:self._connection.execute('COMMIT')
            return revision+1
        except BaseException as error:
            self._abort()
            if isinstance(error,sqlite3.Error):raise ValueError('source catalog write refused') from None
            raise

    @classmethod
    def update_source(cls, path, source):
        previous=cls.load_source(path)
        old,errors,rows=_definitions(previous)
        new,new_errors,new_rows=_definitions(source)
        if rows!=new_rows or errors!=new_errors:
            raise ValueError('source catalog schema migration unsupported; preserve original database')
        # New object modules/subscriptions change the parser blockers and are refused above.
        return super().update_source(path,source)

    @classmethod
    def upgrade_copy(cls, original, destination):
        """Explicit v3 -> v4 copy; never modifies or replaces the original file."""
        import os
        from .sqlite_catalog import _private_parent
        from .source_constant_store import _file_identity
        source=SourceConstantStore.load_source(original)
        old=SourceConstantStore.reopen(original,source)
        target=None
        try:
            raw=os.fspath(destination)
            if type(raw) is not str or not raw or raw.startswith(('file:','//','\\\\')) or '\x00' in raw:
                raise ValueError('invalid source catalog copy destination')
            path=_private_parent(os.path.abspath(raw))
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            identity=_file_identity(path)
            target=sqlite3.connect(path,isolation_level=None)
            target.execute('PRAGMA trusted_schema=OFF')
            old.require_empty_extension_registry();old._connection.execute('BEGIN');old._open()
            old._connection.backup(target)
            old._connection.execute('ROLLBACK')
            target.execute('BEGIN IMMEDIATE')
            for statement in _RECORD_DDL:target.execute(statement)
            cls.initialize_extra(target,source,None,None)
            target.execute('UPDATE source_binding SET profile=?',(cls.PROFILE,))
            if _file_identity(path)!=identity:raise ValueError('source catalog copy file identity changed')
            target.execute('COMMIT');target.close();target=None
            verified=cls.reopen(path,source);verified.close()
            return path
        finally:
            if target is not None:target.close()
            old.close()
