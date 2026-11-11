"""Exact full-source inventory UI roots and host-lifetime receipt recovery.

No renderer value, form callback or core inventory profile supplies root
transaction authority. Catalog references in an immutable intent carry database,
metadata and record identity, never a label or a browser capability.
"""
from .sqlite_inventory_source import _UNSPECIFIED
from dataclasses import fields
from uuid import UUID

from .catalog_backend import BackendError, CatalogKey, TabularSectionRows, TabularRow
from .configuration_inventory_application import (
    InventoryApplicationConfiguration, PROFILE,
)
from . import database_transactions as transactions
from .document_backend import DocumentDraft, DocumentKey, DocumentRevision
from .document_posting_host import (
    RootPostingOperations, PostingOperationIntent, MAX_RECEIPTS,
    _immutable as scalar_immutable,
)
from .document_posting_values import DocumentWriteMode


def _source_configuration(backend, *, expected=_UNSPECIFIED):
    """Current read admission, not a root-execution grant for a form VM."""
    from .sqlite_catalog import SQLiteCatalogBackend
    if type(backend) is not SQLiteCatalogBackend or backend.format_version != 15:
        raise BackendError('unsupported')
    view = backend.begin_read()
    try:
        return view.inventory_source(expected=expected)
    finally:
        view.close()


def _require_inventory_host_context(backend):
    # Context authority is independent of the read-only source data port.
    transactions.require_admission()
    if (transactions._execution.get() is not None
            or transactions._execution_backend.get() is not None
            or transactions._registered(backend) is not None):
        raise BackendError('unsupported')


def require_inventory_host_root(backend):
    """Only exact physical15 forms, outside every BSL activation or owner."""
    _require_inventory_host_context(backend)
    _source_configuration(backend)


class InventoryRootOperation(transactions.RootOperation):
    """Same receipt state machine, a different closed trusted-host admission."""
    _admit_root = staticmethod(require_inventory_host_root)


def _immutable(value):
    if type(value) is tuple:
        return tuple(_immutable(item) for item in value)
    if type(value) is CatalogKey:
        if any(type(item) is not UUID for item in (value.database_id, value.catalog_id, value.record_id)):
            raise BackendError('invalid_input')
        if not value.database_id.int or not value.catalog_id.int:
            raise BackendError('invalid_input')
        return CatalogKey(value.database_id, value.catalog_id, value.record_id)
    if type(value) in (DocumentDraft, DocumentKey, DocumentRevision, TabularSectionRows, TabularRow):
        return type(value)(*(_immutable(getattr(value, field.name)) for field in fields(value)))
    return scalar_immutable(value)


class InventoryRootOperations(RootPostingOperations):
    """Exact intents are retained by one application host, not durable after exit.

    Inherited document reconstruction, resolution and close keep the existing
    no-handler-replay and uncertain-outcome semantics. Root entry, source and
    reference admission are explicit here rather than weakening v13.
    """
    def __init__(self, context, configuration):
        self.context = context
        self.backend = context.backend
        self.configuration = configuration
        self._binding = None
        self._operations = {}
        self._closed = False
        self._verify()
        from .runtime import Interpreter
        self._interpreter = Interpreter(database_context=context, output=lambda value: None)
        self._interpreter._documents.posting_runtime()

    def _verify(self, *, require_root=True):
        from .sqlite_catalog import SQLiteCatalogBackend
        if type(self.backend) is not SQLiteCatalogBackend or self.backend.format_version != 15:
            raise BackendError('unsupported')
        if self._closed or self.context.backend is not self.backend:
            raise BackendError('schema_changed')
        if require_root:
            _require_inventory_host_context(self.backend)
        self.context.require_active(tabular_sections=True)
        view = self.backend.begin_document_read()
        try:
            configuration = view.inventory_source(expected=self.configuration)
            binding = (view.database_id, view.configuration_generation)
            if tuple(sorted(view.documents(), key=lambda s: str(s.identity))) != tuple(sorted(configuration.documents, key=lambda s: str(s.identity))):
                raise BackendError('schema_changed')
            for schema in configuration.catalogs:
                if view.catalog_schema(schema.identity) != schema:
                    raise BackendError('schema_changed')
        finally:
            view.close()
        if self._binding is not None and binding != self._binding:
            raise BackendError('schema_changed')
        self._binding = binding
        self.configuration = configuration

    def verify_source(self):
        # Scoped reference normalization needs an integrity read from inside a
        # form activation. It must not install an execution token or journal.
        self._verify(require_root=False)

    def _intent(self, operation_id, draft, expected, form, command):
        if type(operation_id) is not UUID or not operation_id.int:
            raise BackendError('invalid_input')
        if type(draft) is not DocumentDraft or (expected is not None and type(expected) is not DocumentRevision):
            raise BackendError('invalid_input')
        if type(form) is not str or type(command) is not str:
            raise BackendError('invalid_input')
        grant = next((g for g in self.configuration.commands if (g.form, g.command) == (form, command)), None)
        if grant is None:
            raise BackendError('unsupported')
        draft, expected = _immutable(draft), _immutable(expected)
        schema = next((s for s in self.configuration.documents if s.identity == draft.key.document_id), None)
        if (schema is None or draft.key.database_id != self._binding[0]
                or form.split('.')[1:2] != [schema.name] or draft.tabular_sections is None):
            raise BackendError('conflict')
        if expected is not None and (expected.database_id, expected.configuration_generation, expected.document_id, expected.record_id) != (*self._binding, schema.identity, draft.key.record_id):
            raise BackendError('conflict')
        def references(specs, values):
            if len(specs) != len(values):
                raise BackendError('invalid_input')
            for field, value in zip(specs, values):
                if field.kind == 'catalog_ref':
                    if (type(value) is not CatalogKey or value.database_id != self._binding[0]
                            or value.catalog_id != field.target_catalog_id):
                        raise BackendError('conflict')
                elif type(value) is CatalogKey:
                    raise BackendError('invalid_input')
        references(schema.fields, draft.values)
        if tuple(s.section_id for s in draft.tabular_sections) != tuple(s.identity for s in schema.tabular_sections):
            raise BackendError('invalid_input')
        if sum(len(section.rows) for section in draft.tabular_sections) > 1000:
            raise BackendError('invalid_input')
        for definition, section in zip(schema.tabular_sections, draft.tabular_sections):
            for row in section.rows:
                references(definition.fields, row.values)
        return PostingOperationIntent(operation_id, *self._binding,
            self.configuration.source_digest, PROFILE, form, command, grant.mode, draft, expected)

    def execute(self, operation_id, draft, expected, *, form, command):
        require_inventory_host_root(self.backend)
        intent = self._intent(operation_id, draft, expected, form, command)
        previous = self._operations.get(operation_id)
        if previous is not None:
            if previous[0] != intent:
                raise BackendError('conflict')
            return previous[1].receipt
        if len(self._operations) >= MAX_RECEIPTS:
            raise BackendError('unsupported')
        self._verify()
        if self._interpreter._scheduler.pending or self._interpreter._scheduler._active_task is not None:
            raise BackendError('unsupported')
        document = self._document(intent)
        # Verify full source before journal allocation and again at root entry.
        self._verify()
        operation = InventoryRootOperation(self.backend, operation_id)
        modes = {'Write': DocumentWriteMode.WRITE, 'Post': DocumentWriteMode.POSTING,
                 'UndoPosting': DocumentWriteMode.UNDO_POSTING}
        callback = lambda: document.write(modes[intent.mode])
        self._operations[operation_id] = (intent, operation, document)
        return operation.run(callback)
