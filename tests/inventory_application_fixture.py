"""Authored full inventory source; no database, implicit grant or native claim."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/configuration-inventory-application'
MANIFEST = 'InventoryApplication.xml'
DOC = 'Documents/Receipt.xml'
DOC_FORM = 'Documents/Receipt/Forms/Card/Ext/Form.xml'
DOC_MODULE = 'Documents/Receipt/Forms/Card/Ext/Form/Module.bsl'
CATALOG = 'Catalogs/Products.xml'
CATALOG_FORM = 'Catalogs/Products/Forms/Card/Ext/Form.xml'


def source():
    return {p.relative_to(EXAMPLE).as_posix():p.read_bytes()
            for p in EXAMPLE.rglob('*') if p.is_file()}
