"""Periodic database APIs are unsupported in the SQLite catalog MVP."""
from .catalog_backend import BackendError

def get_edge(*args, **kwargs):
    raise BackendError('unsupported')

def select(*args, **kwargs):
    raise BackendError('unsupported')

def slice_edge(*args, **kwargs):
    raise BackendError('unsupported')
