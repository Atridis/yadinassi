"""Reuse pinned native Stock/Receipt/Issue layout, not its old observations."""
from inventory_reference_behavior import fixture as inventory
from . import route
VALIDATION_MODE = 'owned-polymorphic-recorder-material-projection-v1'
OBJECTS = inventory.OBJECTS
MODULES = inventory.MODULES
MAX_FILE = inventory.MAX_FILE
MAX_TOTAL = inventory.MAX_TOTAL
_files = inventory._files

def load_saved():
    setup, assets = inventory.load_saved()
    return setup, {**assets, 'generated/observe.bsl': route.source()}

def prepare(files):
    # Native metadata is deliberately identical; only the separately injected
    # observer differs. No mutation of the shared fixture module or caller map.
    route.source()
    return inventory.prepare(files)

verify_redump = inventory.verify_redump
redump_diagnostic = inventory.redump_diagnostic
valid_diagnostic = inventory.valid_diagnostic
