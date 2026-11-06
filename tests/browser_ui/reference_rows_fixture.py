"""Authored logical reference-row fixture; no imported source, native or user data."""
import json
from pathlib import Path
import sys
from uuid import UUID

from yadinassi.catalog_backend import (
    CatalogDraft, CatalogKey, CatalogSchema, CatalogSelection, FieldSchema,
    TabularSectionSchema,
)
from yadinassi.configuration_xml import ConfigurationFile, ConfigurationImport
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

CONFIGURATION = UUID('61000000-0000-0000-0000-000000000001')
WAREHOUSES = UUID('62000000-0000-0000-0000-000000000001')
PRODUCTS = UUID('62000000-0000-0000-0000-000000000002')
SECTION = UUID('63000000-0000-0000-0000-000000000001')
WAREHOUSE_FIELD = UUID('64000000-0000-0000-0000-000000000001')
WAREHOUSE_RECORD = UUID('65000000-0000-0000-0000-000000000001')


def configuration():
    # Explicit logical schema, not Designer XML import or original demo admission.
    return ConfigurationImport(
        config_uuid=CONFIGURATION, name='OwnedReferenceRows', activation_issues=(),
        catalogs=(
            CatalogSchema(WAREHOUSES, 'Warehouses', 8, 100),
            CatalogSchema(PRODUCTS, 'Products', 8, 100, (), (
                TabularSectionSchema(SECTION, 'Warehouses', (
                    FieldSchema(WAREHOUSE_FIELD, 'Warehouse', 'catalog_ref', (), WAREHOUSES),
                )),
            )),
        ),
        files=(ConfigurationFile('Configuration.xml', b'<owned-reference-row-fixture/>', 'xml'),),
        modules=(),
    )


def seed(root):
    backend = SQLiteCatalogBackend.create(root / 'owned.sqlite', configuration())
    tx = None
    try:
        tx = backend.begin_write(UUID('66000000-0000-0000-0000-000000000001'))
        key = CatalogKey(backend.database_id, WAREHOUSES, WAREHOUSE_RECORD)
        tx.create(CatalogDraft(key, 'WH1', 'Main warehouse', False, ()))
        tx.commit()
    finally:
        try:
            if tx is not None:
                tx.close()
        finally:
            backend.close()
    return {'seeded': True, 'schema': 'authored-logical-reference-rows'}


def audit(root):
    """Independent read-only audit after the UI has created the single product."""
    backend = SQLiteCatalogBackend(root / 'owned.sqlite', read_only=True)
    view = None
    try:
        view = backend.begin_read()
        warehouses = view.select_catalog(WAREHOUSES, CatalogSelection(limit=10))
        products = view.select_catalog(PRODUCTS, CatalogSelection(limit=10))
        if len(warehouses) != 1 or len(products) != 1:
            raise ValueError('owned_record_count_mismatch')
        warehouse, product = warehouses[0], products[0]
        if (warehouse.code, warehouse.description, warehouse.deletion_mark) != ('WH1', 'Main warehouse', False):
            raise ValueError('warehouse_mismatch')
        if warehouse.key.record_id != WAREHOUSE_RECORD or warehouse.values or warehouse.tabular_sections:
            raise ValueError('warehouse_identity_mismatch')
        if (product.code, product.description, product.deletion_mark) != ('ROWQA1', 'Browser row persistence', False):
            raise ValueError('product_mismatch')
        if product.values or len(product.tabular_sections) != 1:
            raise ValueError('product_shape_mismatch')
        section = product.tabular_sections[0]
        if section.section_id != SECTION or len(section.rows) != 1:
            raise ValueError('reference_row_count_mismatch')
        row = section.rows[0]
        if row.values != (warehouse.key,):
            raise ValueError('warehouse_reference_mismatch')
        # Used in memory for exact before/after comparisons, never exported as raw DB data.
        return {
            'durable': True, 'warehouses': 1, 'products': 1, 'referenceRows': 1,
            'productIdentity': str(product.key.record_id), 'productRevision': product.revision.token,
            'rowIdentity': str(row.identity), 'warehouseIdentity': str(warehouse.key.record_id),
            'warehouseRevision': warehouse.revision.token,
        }
    finally:
        try:
            if view is not None:
                view.close()
        finally:
            backend.close()


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('seed', 'audit'):
            raise ValueError('invalid_arguments')
        root = Path(sys.argv[2])
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError('invalid_owned_root')
        result = (seed if sys.argv[1] == 'seed' else audit)(root)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print('{"error":"owned_reference_rows_fixture_failed"}', file=sys.stderr)
        raise SystemExit(1) from None
