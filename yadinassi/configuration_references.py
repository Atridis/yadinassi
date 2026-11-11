"""Trusted bridge between one form's private reference scope and owned storage.

Only explicitly enrolled snapshots of the same open database may normalize into
this coordinator's catalog managers. Browser capabilities never name records.
"""
from weakref import WeakSet

from .catalog_types import BSLCatalogReference
from .form_references import FormReferenceBinding, FormReferenceScope


def owned_reference_scope(owned, targets):
    catalogs = owned.manager._catalogs
    metadata = catalogs._metadata
    metadata._snapshot()
    enrolled = WeakSet((metadata,))
    managers = {}
    bindings = {}
    for target, identity, name in targets:
        manager = catalogs._manager_by_metadata_uuid(identity)
        if manager._schema.name != name:
            raise ValueError('reference target source mismatch')
        managers[target] = manager
        def normalize(value, manager=manager):
            owned.verify_source()
            if (type(value) is not BSLCatalogReference
                    or value.value_type.snapshot not in enrolled
                    or value.value_type.metadata_uuid != manager._schema.identity):
                raise ValueError('reference from another database, target or activation')
            return manager._ref(value.reference_uuid)
        def presentation(value, manager=manager):
            if value.is_empty(): return ''
            card = manager._read(value.reference_uuid)
            return '[Unavailable record]' if card is None or card.deletion_mark else card.description
        bindings[target] = FormReferenceBinding(manager._value_type, manager.empty_ref(), normalize, presentation)
    scope = FormReferenceScope(bindings=bindings)
    def enroll(interpreter):
        other = interpreter._catalogs
        if other is None or other._context.backend is not owned.context.backend:
            raise ValueError('reference activation backend mismatch')
        snapshot = other._metadata
        snapshot._snapshot()
        if (snapshot._database_id != metadata._database_id or snapshot._generation != metadata._generation):
            raise ValueError('reference activation identity mismatch')
        for target, identity, name in targets:
            if other._manager_by_metadata_uuid(identity)._schema != managers[target]._schema:
                raise ValueError('reference activation schema mismatch')
        enrolled.add(snapshot)
    return scope, managers, enroll
