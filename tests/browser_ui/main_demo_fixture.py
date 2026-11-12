"""Owned unified-demo browser fixture; only warehouse options are pre-authored.

Audit returns observed durable values, not an assertion that a browser scenario
passed. The browser driver must compare these with its explicit expected input.
"""
from contextlib import closing
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from uuid import UUID

from yadinassi.catalog_backend import CatalogDraft, CatalogKey, CatalogSelection
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.document_backend import DocumentSelection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

SOURCE = Path(__file__).resolve().parents[2] / 'examples/demo'
DATABASE = 'main-demo.sqlite'
WAREHOUSE_BASE = 75000


def seed(root):
    configuration = import_main_demo_configuration(read_configuration_directory(SOURCE), profile=PROFILE)
    warehouse = next(c for c in configuration.catalogs if c.name == 'Склады')
    with closing(SQLiteCatalogBackend.create_main_demo(root / DATABASE, configuration)) as backend:
        tx = backend.begin_write(UUID(int=76001))
        try:
            for index in range(70):
                tx.create(CatalogDraft(CatalogKey(backend.database_id, warehouse.identity,
                    UUID(int=WAREHOUSE_BASE + index)), f'W{index:03}',
                    f'Warehouse {index:03}', False, ()))
            tx.commit()
        finally:
            tx.close()
    return {'database': DATABASE, 'authoredWarehouses': 70,
            'kindsInitially': 0, 'productsInitially': 0, 'documentsInitially': 0}


def public(value):
    if is_dataclass(value):
        return {field.name: public(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (UUID, Decimal, datetime)):
        return str(value)
    if isinstance(value, Enum):
        return public(value.value)
    if isinstance(value, (tuple, list)):
        return [public(item) for item in value]
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise ValueError('unsupported_audit_value')


def audit(root):
    database = root / DATABASE
    before = sha256(database.read_bytes()).hexdigest()
    with closing(SQLiteCatalogBackend(database, read_only=True)) as backend:
        if backend.export_configuration() != read_configuration_directory(SOURCE):
            raise ValueError('source_changed')
        configuration = backend.accumulation_configuration
        with closing(backend.begin_read()) as view:
            catalogs = {schema.name: view.select_catalog(schema.identity,
                CatalogSelection(limit=71)) for schema in configuration.catalogs}
        warehouses = catalogs['Склады']
        if len(warehouses) != 70:
            raise ValueError('warehouse_count')
        for row in warehouses:
            index = row.key.record_id.int - WAREHOUSE_BASE
            if not 0 <= index < 70 or (row.code, row.description, row.deletion_mark) != (
                    f'W{index:03}', f'Warehouse {index:03}', False):
                raise ValueError('authored_warehouse_changed')
        with closing(backend.begin_document_read()) as view:
            documents = {schema.name: public(view.select_documents(schema.identity,
                DocumentSelection())) for schema in configuration.documents}
        result = {'catalogs': {name: public(rows) for name, rows in catalogs.items()},
                  'documents': documents,
                  'catalogSchemas': {schema.name: public(schema) for schema in configuration.catalogs},
                  'documentSchemas': {schema.name: public(schema) for schema in configuration.documents},
                  'registerSchemas': {schema.name: public(schema) for schema in configuration.registers}}
    # Read-only physical movement witness supplements typed catalog/document reads.
    # No interpreter, write API, handler or arbitrary SQL from the browser is used.
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        movements = connection.execute('SELECT register_id,document_id,record_id,line_number,'
            'period,active,direction,values_json FROM accumulation_movement '
            'ORDER BY register_id,document_id,record_id,line_number LIMIT 101').fetchall()
        if len(movements) > 100:
            raise ValueError('audit_movement_budget')
        result['movementRows'] = public(movements)
    if sha256(database.read_bytes()).hexdigest() != before:
        raise ValueError('database_changed_during_audit')
    result['readOnlyAudit'] = True
    return result


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ('seed', 'audit'):
        raise SystemExit('invalid_arguments')
    root = Path(sys.argv[2])
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise SystemExit('owned_directory_required')
    print(json.dumps(seed(root) if sys.argv[1] == 'seed' else audit(root), sort_keys=True))
