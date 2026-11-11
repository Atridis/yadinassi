"""Owned public-example database for the explicit catalog-form browser profile."""
from decimal import Decimal
from pathlib import Path
import json
import sys

from yadinassi.configuration_import import read_configuration_directory
from yadinassi.dates import BSLDate
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.catalog_view import CatalogRepository

SOURCE = Path(__file__).resolve().parents[2] / 'examples/configuration-catalog-forms'


def create(root):
    SQLiteCatalogBackend.create_catalog_forms(root / 'catalogs.sqlite',
        read_configuration_directory(SOURCE)).close()
    return {'created': True}


def audit(root):
    backend = SQLiteCatalogBackend(root / 'catalogs.sqlite', read_only=True)
    repository = CatalogRepository(backend, own_backend=False)
    try:
        view = backend.begin_read()
        try:
            schemas = {schema.name: schema for schema in view.catalogs()}
        finally:
            view.close()
        products = repository.load(str(schemas['Products'].identity)).cards
        categories = repository.load(str(schemas['Categories'].identity)).cards
        assert len(products) == 2 and len(categories) == 1
        by_code = {card.value('Code'): card for card in products}
        assert set(by_code) == {'P1', 'P2'}
        assert by_code['P1'].value('Description') == 'Renamed QA product'
        assert by_code['P1'].value('Price') == Decimal('9.00')
        assert by_code['P1'].value('Active') is True
        assert by_code['P1'].value('AvailableDate') == BSLDate(0)
        assert by_code['P2'].value('Description') == 'Independent draft'
        assert by_code['P2'].value('Price') == Decimal('5.00')
        assert categories[0].value('Code') == 'C1'
        assert categories[0].value('Description') == 'QA category'
        return {'durable': True, 'products': 2, 'categories': 1,
                'decimalPreserved': True, 'emptyDatePreserved': True}
    finally:
        repository.close()
        backend.close()


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('create', 'audit'):
            raise ValueError('invalid_arguments')
        root = Path(sys.argv[2])
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError('invalid_owned_root')
        print(json.dumps((create if sys.argv[1] == 'create' else audit)(root), sort_keys=True))
    except Exception:
        print('{"error":"owned_configuration_fixture_failed"}', file=sys.stderr)
        raise SystemExit(1) from None
