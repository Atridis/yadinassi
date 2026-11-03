"""Owned browser-only fixture: public XML/catalog APIs, never user data or SQL."""
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys
from uuid import UUID

from ui_catalog_fixture import CATEGORY, PRODUCT, configuration_files
from yadinassi.catalog_backend import CatalogDraft, CatalogKey, CatalogSelection
from yadinassi.configuration_xml import import_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


def seed(root):
    path = root / 'owned.sqlite'
    backend = SQLiteCatalogBackend.create(path, import_configuration(configuration_files()))
    try:
        tx = backend.begin_write(UUID('30000000-0000-0000-0000-000000000001'))
        category = CatalogKey(backend.database_id, CATEGORY, UUID('40000000-0000-0000-0000-000000000001'))
        tx.create(CatalogDraft(category, '10', 'Owned category', False, ()))
        for i, code in enumerate(('30', '10', '20'), 1):
            key = CatalogKey(backend.database_id, PRODUCT, UUID(f'50000000-0000-0000-0000-{i:012d}'))
            tx.create(CatalogDraft(key, code, 'Owned product ' + code, False,
                ('typed text', Decimal('12.50'), True, datetime(2024, 2, 29, 12, 30, 45), category)))
        tx.commit()
    finally:
        backend.close()
    return {'seeded': True}


def audit(root):
    backend = SQLiteCatalogBackend(root / 'owned.sqlite', read_only=True)
    view = None
    try:
        view = backend.begin_read()
        categories = view.select_catalog(CATEGORY, CatalogSelection(limit=10))
        products = view.select_catalog(PRODUCT, CatalogSelection(limit=10))
        if [(r.code, r.description) for r in categories] != [('10', 'Owned category'), ('40', 'Browser persisted edit')]:
            raise ValueError('category_durability_mismatch')
        if [r.code for r in products] != ['10', '20', '30']:
            raise ValueError('product_identity_mismatch')
        row = products[0]
        category = categories[0].key
        expected = ('Browser scalar', Decimal('123.40'), False, datetime(2025, 6, 7, 8, 9, 10), category)
        if row.values != expected or row.description != 'Owned product 10':
            raise ValueError('typed_durability_mismatch')
        return {'durable': True, 'categories': len(categories), 'products': len(products),
                'exactScalars': True, 'referencePreserved': True}
    finally:
        try:
            if view is not None:
                view.close()
        finally:
            backend.close()


if __name__ == '__main__':
    # The harness passes only its freshly created private temporary directory.
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('seed', 'audit'):
            raise ValueError('invalid_arguments')
        root = Path(sys.argv[2])
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError('invalid_owned_root')
        result = (seed if sys.argv[1] == 'seed' else audit)(root)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print('{"error":"owned_fixture_failed"}', file=sys.stderr)
        raise SystemExit(1) from None
