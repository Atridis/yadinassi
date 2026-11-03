"""Distinct rights-variant identity; observations use exactly the A source."""
from catalog_deletion_mark_behavior.route import (SOURCE_SHA256, SETUP_SHA256,
    CATALOG_SHA256, MAX_OUTPUT, COUNT, source, program, canonical, parse_wire)

PROFILE = 'catalog-deletion-mark-delete-right-v1'
SCHEMA = 'native-1c-catalog-deletion-mark-delete-right-v1'
STAGE_SCHEMA = 'native-1c-catalog-deletion-mark-delete-right-stage-v1'
CATALOG_RIGHTS = ('Read', 'Insert', 'Update', 'Delete')
