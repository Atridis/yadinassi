"""Deterministic native columns for independent register records."""
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.registers.register_backend import InformationRegisterSchema

from .sqlite_catalog_layout import quote_identifier
from .sqlite_typed_rows import attribute_column, attribute_definitions, PhysicalFields

_EMPTY_REF = str(UUID(int=0))


def register_table(schema):
    if type(schema) is not InformationRegisterSchema or type(schema.identity) is not UUID or not schema.identity.int:
        raise BackendError('invalid_input')
    return 'ireg_' + schema.identity.hex


def _key_expression(field, col):
    return f"COALESCE({col},'{_EMPTY_REF}')" if field.kind == 'catalog_ref' else col


class RegisterLayout:
    __slots__ = ('table', 'keys', 'values', 'columns', 'where', 'key_order',
                 'bytes', 'set_values', 'insert_params', 'dimensions', 'payload')

    def __init__(self, schema):
        self.table = quote_identifier(register_table(schema))
        self.dimensions = PhysicalFields(schema.key_fields)
        self.payload = PhysicalFields((*schema.resources,*schema.attributes))
        self.keys, self.values = (tuple(quote_identifier(attribute_column(f)) for f in block.fields)
                                  for block in (self.dimensions,self.payload))
        self.columns = ','.join(('revision', *self.keys, *self.values))
        expressions = tuple(_key_expression(f,c) for f,c in zip(schema.key_fields,self.keys))
        self.where = ' AND '.join(f'{expr}={_key_expression(f,"?")}'
                                  for expr,f in zip(expressions,schema.key_fields))
        self.key_order = ','.join(expressions)
        self.bytes = '+'.join(f'COALESCE(length(CAST({col} AS BLOB)),0)'
                              for col in (*self.keys,*self.values))
        self.set_values = ','.join(f'{col}=?' for col in self.values)
        self.insert_params = ','.join('?' for _ in range(1 + len(self.keys) + len(self.values)))

    def seek(self, keys):
        values = tuple(_EMPTY_REF if value is None else value for value in keys)
        return f' WHERE ({self.key_order})>({",".join("?" for _ in values)})', values


def register_data_ddls(schemas, catalog_layout):
    return tuple(f'CREATE TABLE {quote_identifier(register_table(s))}('
                 'revision INTEGER NOT NULL CHECK(revision>0),'
                 + ','.join(attribute_definitions(s.fields,catalog_layout)) + ')'
                 for s in schemas)


def register_index_ddls(schemas):
    # NULL (empty reference) is one logical key, not a separate SQLite value
    # for each insertion as it would be under a bare UNIQUE constraint.
    return tuple(f'CREATE UNIQUE INDEX {quote_identifier(register_table(s)+"_dimensions")}'
                 f' ON {layout.table}({layout.key_order})'
                 for s in schemas for layout in (RegisterLayout(s),))
