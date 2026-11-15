"""Preserve the exact existing owned baseline; no metadata/security additions."""
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
ASSET_HASHES={}
VALIDATION_MODE='unchanged-owned-temporary-storage-baseline-v1'
def load_saved():
    return original.load_saved()[0],{'generated/observe.bsl':route.source()}
def prepare(files,*,bootstrap_module=None):
    setup,_=load_saved();original._baseline(files,setup)
    original._require(type(bootstrap_module) is bytes)
    original._require(files['Ext/SessionModule.bsl'].decode('utf-8-sig').replace('\r\n','\n')==bootstrap_module.decode('utf-8-sig').replace('\r\n','\n'))
    return setup,dict(files)
def verify_redump(expected,actual):
    return original.verify_redump(expected,actual)
def redump_diagnostic(expected,actual):
    try:verify_redump(expected,actual);return []
    except ValueError:return ['baseline differs']
def valid_diagnostic(value):
    return value in ([],['baseline differs'])
