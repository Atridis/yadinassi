"""Deterministic document attributes and parts, linked to shared owner headers."""
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.document.document_backend import DocumentSchema
from .sqlite_typed_rows import attribute_column, attribute_definitions


def document_data_table(identity):
    if type(identity) is not UUID or not identity.int:
        raise BackendError('invalid_input')
    return 'document_data_' + identity.hex


def data_table(schema):
    if type(schema) is not DocumentSchema:
        raise BackendError('invalid_input')
    return document_data_table(schema.identity)


def section_table(schema, section):
    if type(section.identity) is not UUID or not section.identity.int:
        raise BackendError('invalid_input')
    return 'document_part_' + schema.identity.hex + '_' + section.identity.hex


def document_data_ddls(schemas, catalog_layout, *, enum_domain=None):
    """Closed vocabulary produced from admitted metadata, never caller names."""
    result = []
    for schema in schemas:
        owner = "document_id TEXT NOT NULL CHECK(document_id='%s'), record_id TEXT NOT NULL" % schema.identity
        fk = ('FOREIGN KEY(document_id,record_id) REFERENCES document_record(document_id,record_id) '
              'ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED')
        if schema.fields:
            columns = (owner,*attribute_definitions(schema.fields,catalog_layout,enum_domain=enum_domain),
                       'PRIMARY KEY(document_id,record_id)',fk)
            result.append('CREATE TABLE '+data_table(schema)+'('+', '.join(columns)+')')
        for section in schema.tabular_sections:
            columns = (owner,'row_id TEXT NOT NULL','row_number INTEGER NOT NULL CHECK(row_number>0)',
                       *attribute_definitions(section.fields,catalog_layout,enum_domain=enum_domain),
                       'PRIMARY KEY(document_id,record_id,row_number)',
                       'UNIQUE(document_id,record_id,row_id)',fk)
            result.append('CREATE TABLE '+section_table(schema,section)+'('+', '.join(columns)+')')
    return tuple(result)
