"""Detached editors admitted only by the explicit inventory forms source grant."""
from types import MappingProxyType

from .catalog_backend import BackendError
from .configuration_catalog import CatalogObjectSession
from .configuration_document import require_document_form_schema, _OpenedDocument
from .configuration_posting_document import PostingDocumentSession
from .configuration_inventory_application import canonical
from .inventory_host_operations import InventoryRootOperations, _source_configuration
from .documents import BSLDocumentObject


class InventoryCatalogSession(CatalogObjectSession):
    def __init__(self, context, schema, configuration, reference=None):
        self.configuration = canonical(configuration)
        if schema not in self.configuration.catalogs:
            raise BackendError('unsupported')
        super().__init__(context, schema, dict(self.configuration.files), reference)

    def verify_source(self):
        if _source_configuration(self.context.backend) != self.configuration:
            raise BackendError('schema_changed')
        super().verify_source()


class InventoryDocumentSession(PostingDocumentSession):
    """Typed reference images, but no root authority during form dispatch.

    Inherited execute/recover accepts only a trusted host-owned complete image
    after dispatch. Live opaque receipts retain the exact immutable request.
    """
    def __init__(self, context, schema, configuration, form, key=None, *, _opened=None):
        require_document_form_schema(schema, reference_fields=True)
        self.context, self.schema = context, schema
        self.configuration = canonical(configuration)
        if schema not in self.configuration.documents:
            raise BackendError('unsupported')
        self._backend = context.backend
        self._sources = MappingProxyType(dict(self.configuration.files))
        self.form = form
        self.operations = InventoryRootOperations(context, self.configuration)
        from .metadata import BSLMetadata
        from .catalogs import BSLCatalogs
        from .documents import BSLDocuments
        metadata = BSLMetadata(context)
        catalogs = BSLCatalogs(metadata._catalogs, context)
        self.manager = BSLDocuments(metadata._documents, context, catalogs).get_index(schema.name)
        self.fields = ('Number', 'Date', 'DeletionMark', 'Posted') + tuple(f.name for f in schema.fields)
        self._saving = False
        self.pending_commit = self.pending_refresh = False
        self.error = None
        self.save_state = 'new'
        self._operation_id = None
        self.receipt_token = None
        self.verify_source()
        if _opened is not None and (type(_opened) is not _OpenedDocument or key is None):
            raise TypeError('owned document opening snapshot required')
        if key is None:
            self.object = self.manager.create_document()
        else:
            from .document_backend import DocumentKey
            if type(key) is not DocumentKey or key.database_id != self._backend.database_id or key.document_id != schema.identity:
                raise BackendError('invalid_input')
            if _opened is not None:
                card = _opened.take(context, schema, key)
            else:
                view = self._backend.begin_document_read()
                try:
                    card = view.read_document(key)
                finally:
                    view.close()
            if card is None:
                raise BackendError('not_found')
            self.object = BSLDocumentObject(self.manager, card)
            self.save_state = 'unchanged'
        self.baseline = self.image()
        self.listing = ()
