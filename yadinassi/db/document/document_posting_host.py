"""Source-bound host root posting without operation history.

This API takes plain immutable drafts, not interpreter/form objects. Each
operation constructs a fresh document with empty AdditionalProperties and an
empty movement buffer. Supplemental handler inputs are intentionally excluded.
"""
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from threading import Lock
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError, TabularSectionRows, TabularRow
from yadinassi.configuration.configuration_posting_application import canonical, PROFILE
from yadinassi.db.database_transactions import RootOperation, require_host_root
from .document_backend import DocumentDraft, DocumentKey, DocumentRevision
from .document_posting_values import DocumentWriteMode

@dataclass(frozen=True, slots=True)
class PostingOperationIntent:
    operation_id: UUID
    mode: str
    draft: DocumentDraft
    expected: DocumentRevision | None


def _immutable(value):
    """Copy admitted containers and refuse mutable or disguised scalar values."""
    if value is None or type(value) in (str, bool, int, UUID): return value
    if type(value) is Decimal:
        if not value.is_finite(): raise BackendError('invalid_input')
        return value
    if type(value) is datetime:
        if value.tzinfo is not None or value.microsecond: raise BackendError('invalid_input')
        return value
    if type(value) is tuple: return tuple(_immutable(item) for item in value)
    if type(value) in (DocumentDraft, DocumentKey, DocumentRevision, TabularSectionRows, TabularRow):
        return type(value)(*(_immutable(getattr(value, field.name)) for field in fields(value)))
    raise BackendError('invalid_input')


class RootPostingOperations:
    """Owned by the application host, outside form/server dispatch.

    Results are returned only to the current caller. The host keeps at most
    one operation, and only while its physical SQLite resources need cleanup.
    """
    _operation_type = RootOperation

    def __init__(self, context, configuration):
        self.context = context
        self.backend = context.backend
        require_host_root(self.backend)
        self.configuration = canonical(configuration)
        self._binding = None
        self._operation_lock = Lock()
        self._active_operation = None
        self._closed = False
        self._verify()
        from yadinassi.runtime import Interpreter
        self._interpreter = Interpreter(database_context=context, output=lambda value: None)
        # Eagerly compile bounded handlers before any operation can begin SQL.
        self._interpreter._documents.posting_runtime()

    def _verify(self):
        if self._closed or self.context.backend is not self.backend:
            raise BackendError('schema_changed')
        require_host_root(self.backend)
        self.context.require_active(tabular_sections=True)
        configuration = canonical(self.backend.posting_configuration)
        if (configuration != self.configuration or configuration.profile != PROFILE
                or self.backend.export_configuration() != dict(configuration.files)):
            raise BackendError('schema_changed')
        view = self.backend.begin_document_read()
        try:
            binding = (view.database_id, view.configuration_generation)
            if tuple(sorted(view.documents(), key=lambda s: str(s.identity))) != tuple(sorted(configuration.documents, key=lambda s: str(s.identity))):
                raise BackendError('schema_changed')
        finally: view.close()
        if self._binding is not None and binding != self._binding:
            raise BackendError('schema_changed')
        self._binding = binding

    @contextmanager
    def _exclusive(self):
        if not self._operation_lock.acquire(blocking=False):
            raise BackendError('busy')
        try: yield
        finally: self._operation_lock.release()

    def _release_active(self):
        operation = self._active_operation
        if operation is not None:
            try: operation.release_resources()
            finally:
                if not operation.needs_cleanup:
                    self._active_operation = None

    def _clean_before_read(self):
        if self._active_operation is not None:
            with self._exclusive():
                self._release_active()

    def verify_source(self):
        """Recheck the full exact source/profile/database binding at host root."""
        self._clean_before_read()
        self._verify()

    def _intent(self, operation_id, draft, expected, form, command):
        if type(operation_id) is not UUID or not operation_id.int:
            raise BackendError('invalid_input')
        if type(draft) is not DocumentDraft or (expected is not None and type(expected) is not DocumentRevision):
            raise BackendError('invalid_input')
        if type(form) is not str or type(command) is not str:
            raise BackendError('invalid_input')
        grant = next((g for g in self.configuration.commands if (g.form, g.command) == (form, command)), None)
        if grant is None: raise BackendError('unsupported')
        draft, expected = _immutable(draft), _immutable(expected)
        schema = next((s for s in self.configuration.documents if s.identity == draft.key.document_id), None)
        if (schema is None or draft.key.database_id != self._binding[0]
                or form.split('.')[1:2] != [schema.name] or draft.tabular_sections is None):
            raise BackendError('conflict')
        return PostingOperationIntent(operation_id, grant.mode, draft, expected)

    def _document(self, intent):
        from .documents import BSLDocumentObject
        from .document_lines import BSLDocumentLines
        from yadinassi.temporal.dates import _date_from_datetime
        draft, expected = intent.draft, intent.expected
        schema = next(s for s in self.configuration.documents if s.identity == draft.key.document_id)
        manager = self._interpreter._documents.get_index(schema.name)
        view = self.backend.begin_document_read()
        try: card = view.read_document(draft.key)
        finally: view.close()
        if (None if card is None else card.revision) != expected:
            raise BackendError('conflict')
        document = BSLDocumentObject(manager, card)
        document._key = draft.key
        document._operation_id = intent.operation_id
        if len(draft.values) != len(schema.fields): raise BackendError('invalid_input')
        document.set_member('Number', draft.number)
        document.set_member('Date', _date_from_datetime(draft.date))
        document.set_member('DeletionMark', draft.deletion_mark)
        for field, value in zip(schema.fields, draft.values):
            document.set_member(field.name, manager._logical(field, value))
        if tuple(s.section_id for s in draft.tabular_sections) != tuple(s.identity for s in schema.tabular_sections):
            raise BackendError('invalid_input')
        document._sections = {s.name.casefold(): BSLDocumentLines(document, s, rows.rows)
            for s, rows in zip(schema.tabular_sections, draft.tabular_sections)}
        if document._draft() != draft: raise BackendError('invalid_input')
        return document

    def execute(self, operation_id, draft, expected, *, form, command):
        with self._exclusive():
            if self._active_operation is not None:
                raise BackendError('uncertain_commit')
            self._operation_type._admit_root(self.backend)
            intent = self._intent(operation_id, draft, expected, form, command)
            self._verify()
            if self._interpreter._scheduler.pending or self._interpreter._scheduler._active_task is not None:
                raise BackendError('unsupported')
            document = self._document(intent)
            modes = {'Write': DocumentWriteMode.WRITE, 'Post': DocumentWriteMode.POSTING,
                     'UndoPosting': DocumentWriteMode.UNDO_POSTING}
            # This is the last source/admission check before acquiring the root UoW.
            self._verify()
            operation = self._operation_type(self.backend, operation_id)
            self._active_operation = operation
            try:
                return operation.run(lambda: document.write(modes[intent.mode]))
            except Exception as error:
                # A physical cleanup fault may follow an already published
                # in-memory outcome. Do not tell a caller the write was refused.
                if isinstance(error, MemoryError) or operation.result.state not in ('committed', 'uncertain'):
                    raise
                return operation.result
            finally:
                if not operation.needs_cleanup:
                    self._active_operation = None

    def close(self):
        with self._exclusive():
            self._release_active()
            if not self._closed:
                self._interpreter.close()
                self._closed = True
