"""Strict Delete-right fixture and a new independently pinned source."""
from catalog_deletion_rights_behavior import fixture as rights
from . import route

MAX_FILE = rights.MAX_FILE
MAX_TOTAL = rights.MAX_TOTAL
_files = rights._files
prepare = rights.prepare
verify_redump = rights.verify_redump


def load_saved():
    setup, assets = rights.load_saved()
    return setup, {**assets, 'generated/observe.bsl': route.source()}
