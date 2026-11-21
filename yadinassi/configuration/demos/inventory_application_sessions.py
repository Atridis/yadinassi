"""Detached editors admitted only by the explicit inventory forms source grant."""
from types import MappingProxyType

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.configuration.configuration_catalog import CatalogObjectSession
from yadinassi.configuration.configuration_document import require_document_form_schema, _OpenedDocument
from yadinassi.configuration.configuration_posting_document import PostingDocumentSession
from .inventory_host_operations import canonical
from yadinassi.configuration.configuration_inventory_enum_application import InventoryEnumApplicationConfiguration
from .inventory_host_operations import InventoryRootOperations, _source_configuration
from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
from yadinassi.db.document.documents import BSLDocumentObject


class InventoryCatalogSession(CatalogObjectSession):
    def __init__(self, context, schema, configuration, reference=None):
        self.configuration = canonical(configuration)
        if schema not in self.configuration.catalogs:
            raise BackendError('unsupported')
        self._interpreter = None
        is_enum = type(self.configuration) is InventoryEnumApplicationConfiguration
        if is_enum:
            from yadinassi.runtime import Interpreter
            self._interpreter = Interpreter(database_context=context, output=lambda value: None)
        try:
            super().__init__(context, schema, dict(self.configuration.files), reference,
                             enum_fields=is_enum, _interpreter=self._interpreter)
        except BaseException:
            if self._interpreter is not None: self._interpreter.close()
            raise

    def close(self, *, discard_unknown=False):
        if not (discard_unknown is True and self.pending_commit and not self.pending_refresh):
            self.require_discardable()
        if self._interpreter is not None: self._interpreter.close()

    def verify_source(self):
        if _source_configuration(self.context.backend) != self.configuration:
            raise BackendError('schema_changed')
        super().verify_source()


class InventoryDocumentSession(PostingDocumentSession):
    """Typed reference images, but no root authority during form dispatch.

    Inherited execute accepts only a trusted host-owned complete image
    after dispatch. A write with an unknown outcome is never replayed.
    """
    def __init__(self, context, schema, configuration, form, key=None, *, _opened=None):
        configuration = canonical(configuration)
        require_document_form_schema(schema, reference_fields=True,
            enum_fields=type(configuration) in (InventoryEnumApplicationConfiguration, MainDemoConfiguration))
        self.context, self.schema = context, schema
        self.configuration = canonical(configuration)
        if schema not in self.configuration.documents:
            raise BackendError('unsupported')
        self._backend = context.backend
        self._sources = MappingProxyType(dict(self.configuration.files))
        self.form = form
        self.operations = InventoryRootOperations(context, self.configuration)
        # Reuse the root host's canonical family; a bare metadata object has no
        # owned enum namespace and cannot decode persisted enum identities.
        self.manager = self.operations._interpreter._documents.get_index(schema.name)
        self.fields = ('Number', 'Date', 'DeletionMark', 'Posted') + tuple(f.name for f in schema.fields)
        self._saving = False
        self.pending_commit = self.pending_refresh = False
        self.error = None
        self.save_state = 'new'
        self.verify_source()
        if _opened is not None and (type(_opened) is not _OpenedDocument or key is None):
            raise TypeError('owned document opening snapshot required')
        if key is None:
            self.object = self.manager.create_document()
        else:
            from yadinassi.db.document.document_backend import DocumentKey
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
