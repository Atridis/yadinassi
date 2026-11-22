"""Ordinary independent-register admission under its actual SQLite lock.

The descriptor is an open-time comparison image, not a row proof, epoch
cache or source authority. Every use checks the touched domain again on the
same connection/transaction that will read or mutate it.
"""
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_register_layout import register_table
from .sqlite_typed_rows import bounded_value_sql as _bounded


@dataclass(frozen=True, slots=True)
class _RegisterDescriptor:
    index: int
    schema: object
    tables: tuple
    ddl: frozenset
    manifest: tuple
    references: frozenset


class RegisterRuntimeData:
    def __init__(self, backend, connection, application_id, metadata):
        self.metadata = metadata
        self.identity = (UUID(int=backend.database_id.int),backend.configuration_generation)
        self.versions = (application_id,backend.format_version,backend._sqlite_schema_version)
        self.schemas = deepcopy(backend._register_schemas)
        manifests = {record[0]: record for record in backend._register_snapshot}
        catalogs = {record[0]: record for record in backend._schema_snapshot}
        ddl = tuple(connection.execute('SELECT type,name,tbl_name,rootpage,sql FROM main.sqlite_schema'))
        by_id = {}
        for index,schema in enumerate(self.schemas):
            targets = {field.target_catalog_id for field in schema.fields if field.kind=='catalog_ref'}
            references = frozenset((*catalogs[str(identity)],backend._layout.table_name(identity))
                                   for identity in targets)
            tables = {'database_info','information_register_schema',
                      'information_register_sequence',register_table(schema)}
            if references:
                tables.update(('catalog_schema','catalog_storage_map'))
                tables.update(row[3] for row in references)
            by_id[schema.identity] = _RegisterDescriptor(index,schema,tuple(sorted(tables)),
                frozenset(row for row in ddl if row[2] in tables),
                manifests[str(schema.identity)],references)
        self.descriptors = MappingProxyType(by_id)

    def descriptor(self,backend,schema,database,generation):
        from yadinassi.configuration.configuration_inventory_enums import _same
        from yadinassi.db.registers.register_backend import InformationRegisterSchema

        if (self is not backend._register_runtime_data or backend.activation_issues
                or backend.format_version!=backend.storage_version
                or backend.format_version!=self.versions[1] or not backend.activated):
            raise BackendError('schema_changed')
        if (type(database) is not UUID or type(generation) is not int
                or (database,generation)!=self.identity
                or (backend.database_id,backend.configuration_generation)!=self.identity
                or type(schema) is not InformationRegisterSchema
                or type(schema.identity) is not UUID or type(schema.identity.int) is not int):
            raise BackendError('schema_changed')
        descriptor = self.descriptors.get(schema.identity)
        schemas = backend._register_schemas
        if (descriptor is None or type(schemas) is not tuple or descriptor.index>=len(schemas)
                or not _same(descriptor.schema,schema)):
            raise BackendError('schema_changed')
        live = schemas[descriptor.index]
        if live is not schema and not _same(descriptor.schema,live):
            raise BackendError('schema_changed')
        return descriptor

    def admit(self,connection,descriptor,*,readonly):
        # Tag batches inside one statement; no reparse of any persisted
        # metadata, no fresh query/version check after obtaining the view.
        pad = lambda count: ',NULL'*count
        metadata = (
            'SELECT 0,'+_bounded('d.database_uuid',36)+',d.generation,d.activated,'+
            _bounded('d.activation_issues',65536)+',a.application_id,u.user_version,v.schema_version,'+
            _bounded('g.identity',36)+','+_bounded('g.name',512)+','+_bounded('g.definition',262144)+
            ',q.next_value,j.journal_mode,f.foreign_keys,o.query_only '
            'FROM main.database_info d '
            'JOIN pragma_application_id a JOIN pragma_user_version u JOIN pragma_schema_version v '
            'JOIN pragma_journal_mode j JOIN pragma_foreign_keys f JOIN pragma_query_only o '
            'LEFT JOIN main.information_register_schema g ON g.identity=? '
            'LEFT JOIN main.information_register_sequence q ON q.register_id=? WHERE d.singleton=1')
        ddl = ('SELECT 1,'+_bounded('type',32)+','+_bounded('name',1024)+','+
               _bounded('tbl_name',1024)+',rootpage,'+_bounded('sql',1048576)+pad(9)+
               ' FROM main.sqlite_schema WHERE tbl_name COLLATE NOCASE IN ('+','.join('?' for _ in descriptor.tables)+')')
        sql = metadata+' UNION ALL '+ddl
        identity = descriptor.manifest[0]
        parameters = (identity,identity,*descriptor.tables)
        if descriptor.references:
            sql += (' UNION ALL SELECT 2,'+_bounded('c.identity',36)+','+
                    _bounded('c.name',512)+','+_bounded('c.definition',262144)+','+
                    _bounded('m.physical_name',1024)+pad(10)+
                    ' FROM main.catalog_schema c LEFT JOIN main.catalog_storage_map m ON m.catalog_id=c.identity '
                    'WHERE c.identity IN ('+','.join('?' for _ in descriptor.references)+')')
            parameters += tuple(row[0] for row in descriptor.references)
        expected = (*self.metadata,*self.versions,*descriptor.manifest)
        ddls, references = set(descriptor.ddl), set(descriptor.references)
        seen = False
        cursor = connection.execute(sql,parameters)
        try:
            for tag,*row in cursor:
                if tag==0:
                    if seen or tuple(row[:10])!=expected: raise BackendError('schema_changed')
                    value,journal,foreign,query = row[10:]
                    if (type(value) is not int or not 1<=value<2**63):
                        raise BackendError('integrity')
                    if (journal,foreign,query)!=('delete',1,int(readonly)):
                        raise BackendError('unsupported')
                    seen = True
                elif tag==1:
                    item = tuple(row[:5])
                    if item not in ddls: raise BackendError('schema_changed')
                    ddls.remove(item)
                elif tag==2:
                    item = tuple(row[:4])
                    if item not in references: raise BackendError('schema_changed')
                    references.remove(item)
                else: raise BackendError('integrity')
        finally:
            cursor.close()
        if not seen or ddls or references: raise BackendError('schema_changed')
        return self.identity
