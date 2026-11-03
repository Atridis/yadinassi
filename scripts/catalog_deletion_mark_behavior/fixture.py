"""Reuse the frozen owned CatalogObject XML fixture without altering it."""
import hashlib
from catalog_object_behavior import fixture as original
from . import route

MAX_FILE = original.MAX_FILE
MAX_TOTAL = original.MAX_TOTAL
_files = original._files
prepare = original.prepare
verify_redump = original.verify_redump


def load_saved():
    setup, assets = original.load_saved()
    for name, expected in (('generated/setup.json', route.SETUP_SHA256),
                           ('generated/Catalog.xml', route.CATALOG_SHA256)):
        if hashlib.sha256(assets[name]).hexdigest() != expected:
            raise ValueError('fixture changed')
    # The old loader verifies the old frozen packet first; only this returned
    # source witness is substituted, never the old package's files or globals.
    return setup, {**assets, 'generated/observe.bsl': route.source()}
