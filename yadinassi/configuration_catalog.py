"""Host-owned scalar catalog form persistence, independent of form layout.

The owner admits the configuration profile and binds this coordinator to one
form. No BSL object, SQL handle, callback, or revision is a renderer capability.
This is not an implementation of native standard FormWrite semantics.
"""
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from .catalog_backend import BackendError, CatalogSchema
from .catalog_object_preparation import CatalogWriteRefused
from .catalogs import BSLCatalogs, BSLCatalogObject
from .metadata import BSLCatalogMetadataCollection
from .unique_identifiers import BSLUUID
from .ui.catalog_view import CatalogRepository
from .ui.protocol import CatalogRef, encode_line


@dataclass(frozen=True)
class CatalogSaveResult:
    state: str
    error: str | None = None
    values: tuple = ()
    reference: CatalogRef | None = None
    listing: object = None


class CatalogObjectSession:
    """One detached writer with retained uncertain intent and refresh obligation.

    ``before_write`` receives a detached complete scalar dictionary and returns
    the prepared complete dictionary, or None to refuse. It is never called
    while resolving a retained write or retrying a postcommit refresh.
    ``validate_result`` must preflight, not mutate external form state; adoption
    occurs only after it accepts the refreshed record and authoritative list.
    """
    def __init__(self, context, schema, source_files, reference=None, *, reference_fields=False, enum_fields=False, _interpreter=None):
        if type(reference_fields) is not bool or type(enum_fields) is not bool:
            raise TypeError("explicit reference field admission required")
        allowed = ('string', 'number', 'boolean', 'datetime') + (('catalog_ref',) if reference_fields else ()) + (('enum_ref',) if enum_fields else ())
        if (type(schema) is not CatalogSchema or schema.hierarchy != 'none' or schema.tabular_sections
                or any(f.kind not in allowed or (f.target_catalog_id is not None and
                       not (reference_fields and f.kind == 'catalog_ref')) or (f.target_enum_id is not None and
                       not (enum_fields and f.kind == 'enum_ref')) for f in schema.fields)):
            raise ValueError('scalar catalog object form required')
        if (type(source_files) is not dict or not source_files
                or any(type(k) is not str or type(v) is not bytes for k, v in source_files.items())):
            raise TypeError('exact configuration source bytes required')
        context.require_active(tabular_sections=True)
        self.context, self.schema = context, schema
        self._backend = context.backend
        self._sources = MappingProxyType(dict(source_files))
        self._identity = None
        self._stale = False
        self.fields = ('Code', 'Description', 'DeletionMark') + tuple(f.name for f in schema.fields)
        self.pending_commit = self.pending_refresh = False
        self.error = None
        self.listing = None
        self._saving = False
        self.verify_source()
        if enum_fields:
            from .runtime import Interpreter
            from .inventory_enum_runtime import binding
            from .inventory_host_operations import _source_configuration
            from .configuration_inventory_enum_application import InventoryEnumApplicationConfiguration
            if type(_source_configuration(context.backend)) is not InventoryEnumApplicationConfiguration:
                raise BackendError('unsupported')
            if type(_interpreter) is not Interpreter or _interpreter.database_context is not context:
                raise BackendError('unsupported')
            binding(_interpreter._metadata)
            self.metadata = _interpreter._metadata._catalogs
            self.manager = _interpreter._catalogs.get_index(schema.name)
        else:
            if _interpreter is not None:
                raise BackendError('unsupported')
            self.metadata = BSLCatalogMetadataCollection(context)
            self.manager = BSLCatalogs(self.metadata, context).get_index(schema.name)
        if reference is None:
            self.object = self.manager.create_item()
        else:
            if (type(reference) is not CatalogRef or reference.catalog != str(schema.identity)
                    or type(reference.record) is not str):
                raise ValueError('same-catalog host reference required')
            try:
                identity = UUID(reference.record)
            except (ValueError, AttributeError):
                raise ValueError('canonical record identity required') from None
            if not identity.int or str(identity) != reference.record:
                raise ValueError('canonical nonempty record identity required')
            ref = self.manager.get_ref(BSLUUID(reference.record))
            self.object = ref.get_object(ref)
            if self.object is None:
                raise BackendError('not_found')
        self.baseline = tuple(self.values().items())
        self.save_state = 'new' if self.object.is_new() else 'unchanged'

    def verify_source(self):
        if self._stale or self.context.backend is not self._backend:
            self._stale = True
            raise BackendError('schema_changed')
        try:
            self.context.require_active(tabular_sections=True)
            if self._backend.export_configuration() != dict(self._sources):
                raise BackendError('schema_changed')
            view = self._backend.begin_read()
            try:
                identity = (view.database_id, view.configuration_generation)
                if view.catalog_schema(self.schema.identity) != self.schema:
                    raise BackendError('schema_changed')
                if self._identity is not None and identity != self._identity:
                    raise BackendError('schema_changed')
                self._identity = identity
            finally:
                view.close()
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'):
                self._stale = True
            raise

    def values(self):
        return {field: self.object.get_member(field) for field in self.fields}

    def _candidate(self, values):
        if type(values) is not dict or set(values) != set(self.fields):
            raise ValueError('complete canonical scalar object image required')
        # Preserve the originally opened revision: a fresh read here would hide
        # a concurrent writer and turn a stale editor into a lost update.
        candidate = BSLCatalogObject(self.manager)
        candidate._key = self.object._key
        candidate._revision = self.object._revision
        candidate._values = dict(self.object._values)
        candidate._operation_id = self.object._operation_id
        for name in self.fields:
            candidate.set_member(name, values[name])
        return candidate

    def _result(self):
        return CatalogSaveResult(self.save_state, self.error)

    def _refresh(self, validate_result):
        self.verify_source()
        ref = self.object.get_member('Ref')
        fresh = ref.get_object(ref)
        if fresh is None:
            raise BackendError('not_found')
        values = tuple((name, fresh.get_member(name)) for name in self.fields)
        reference = CatalogRef(str(self.schema.identity), str(ref.reference_uuid))
        repository = CatalogRepository(self._backend, own_backend=False)
        try:
            listing = repository.load(str(self.schema.identity))
        finally:
            repository.close()
        listing.card(reference)  # No success if the confirmed record is absent.
        # Validate the bounded list projection before publishing success.
        position = next(i for i, card in enumerate(listing.cards) if card.reference == reference)
        encode_line(listing.page(position // 8 * 8, 8))
        result = CatalogSaveResult('saved', None, values, reference, listing)
        if validate_result is not None:
            validate_result(result)
        self.object = fresh
        self.baseline = values
        self.listing = listing
        self.pending_refresh = self.pending_commit = False
        self.save_state, self.error = 'saved', None
        return result

    def _try_refresh(self, validate_result):
        try:
            return self._refresh(validate_result)
        except Exception:
            # Write is already confirmed. This is neither rejection nor a reason
            # to replay form preparation or Write. The next save only refreshes.
            self.pending_refresh = True
            self.listing = None
            self.save_state, self.error = 'committed', 'refresh_required'
            return self._result()

    def save(self, values, *, before_write=None, validate_result=None):
        if self._saving:
            raise BackendError('busy')
        self._saving = True
        try:
            return self._save(values, before_write=before_write, validate_result=validate_result)
        finally:
            self._saving = False

    def _save(self, values, *, before_write=None, validate_result=None):
        if before_write is not None and not callable(before_write):
            raise TypeError('trusted form preparation callback required')
        if validate_result is not None and not callable(validate_result):
            raise TypeError('trusted result validator required')
        if self.context.backend is not self._backend:
            self._stale = True
            self.error = 'schema_changed'
            return self._result()
        if self.pending_refresh:
            return self._try_refresh(validate_result)
        self.error = None
        try:
            if not self.pending_commit:
                self.verify_source()
                candidate = self._candidate(values)
                if before_write is not None:
                    try:
                        prepared = before_write({name: candidate.get_member(name) for name in self.fields})
                    except Exception:
                        self.save_state, self.error = 'rejected', 'form_validation'
                        return self._result()
                    # The callback may execute form code but cannot change which
                    # database/source owns this write.
                    self.verify_source()
                    if prepared is None:
                        self.save_state, self.error = 'rejected', 'form_validation'
                        return self._result()
                    candidate = self._candidate(prepared)
                self.object = candidate
            # On retry this exact object retains operation/draft/receipt. Its own
            # mandatory preparation contract is enforced by CatalogObject.Write.
            self.object.write()
        except CatalogWriteRefused:
            self.pending_commit = self.object._pending_write is not None
            self.save_state, self.error = 'rejected', 'object_validation'
            return self._result()
        except BackendError as error:
            self.pending_commit = self.pending_commit or self.object._pending_write is not None or error.code == 'uncertain_commit'
            self.save_state = 'uncertain' if self.pending_commit else 'rejected'
            self.error = error.code
            return self._result()
        except BaseException:
            if self.object._pending_write is not None:
                self.pending_commit = True
                self.save_state, self.error = 'uncertain', 'uncertain_commit'
            raise
        self.pending_commit = False
        self.pending_refresh = True
        self.save_state = 'committed'
        return self._try_refresh(validate_result)

    def require_discardable(self):
        if self.pending_commit or self.pending_refresh:
            raise BackendError('uncertain_commit' if self.pending_commit else 'busy')
