"""Unchanged fresh owned baseline for in-memory regex extension observations."""
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
VALIDATION_MODE='owned-regex-extensions-load-update-observation-v1'
ASSET_HASHES={}
RESOURCES={}


def load_saved():
    return original.load_saved()[0],{'generated/observe.bsl':route.source()}


def _files(files):
    return original._files(files)


def prepare(files,*,bootstrap_module=None):
    setup,_=load_saved()
    original._baseline(files,setup)
    original._require(type(bootstrap_module) is bytes and 0<len(bootstrap_module)<=MAX_FILE)
    original._require(files['Ext/SessionModule.bsl'].decode('utf-8-sig').replace('\r\n','\n')==bootstrap_module.decode('utf-8-sig').replace('\r\n','\n'))
    _files(files)
    return setup,dict(files)


def verify_prepared(expected,actual):
    _files(expected);_files(actual)
    original._require(expected==actual)
    return True


def valid_diagnostic(value):
    return type(value) is list and not value
