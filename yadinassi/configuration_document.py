"""Host-owned non-posting document forms over the existing document receipt port.

Images and row UUIDs are trusted host objects, not browser capabilities. Only
DocumentObject.Write persists a complete header and all ordered sections.
"""
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from .catalog_backend import BackendError
from .catalogs import BSLCatalogs
from .database_transactions import forbid_transfer
from .document_backend import DocumentSchema, DocumentKey, DocumentSelection
from .documents import BSLDocuments, BSLDocumentObject
from .metadata import BSLMetadata


@dataclass(frozen=True)
class DocumentRowImage:
    identity: UUID | None
    values: tuple


@dataclass(frozen=True)
class DocumentImage:
    values: tuple
    sections: tuple


@dataclass(frozen=True)
class DocumentSaveResult:
    state: str
    error: str | None = None
    image: DocumentImage | None = None
    key: DocumentKey | None = None
    listing: tuple = ()


def require_document_form_schema(schema):
    if type(schema) is not DocumentSchema:
        raise TypeError('document schema required')
    fields = list(schema.fields)
    for section in schema.tabular_sections:
        fields.extend(section.fields)
    if any(f.kind not in ('string', 'number', 'boolean', 'datetime')
           or f.target_catalog_id is not None for f in fields):
        raise ValueError('scalar document form fields and sections required')


class DocumentObjectSession:
    """One detached editor; retain uncertain intent rather than replaying edits."""
    def __init__(self, context, schema, source_files, key=None):
        require_document_form_schema(schema)
        if (type(source_files) is not dict or not source_files or
                any(type(k) is not str or type(v) is not bytes for k, v in source_files.items())):
            raise TypeError('exact configuration source bytes required')
        context.require_active(tabular_sections=True)
        self.context, self.schema = context, schema
        self._backend, self._sources = context.backend, MappingProxyType(dict(source_files))
        self._identity = None
        self._stale = self._saving = False
        self.pending_commit = self.pending_refresh = False
        self.error = None
        self.fields = ('Number', 'Date', 'DeletionMark') + tuple(f.name for f in schema.fields)
        self.verify_source()
        self.metadata = BSLMetadata(context)
        catalogs = BSLCatalogs(self.metadata._catalogs, context)
        self.manager = BSLDocuments(self.metadata._documents, context, catalogs).get_index(schema.name)
        if key is None:
            self.object = self.manager.create_document()
        else:
            if (type(key) is not DocumentKey or key.database_id != self._identity[0]
                    or key.document_id != schema.identity or type(key.record_id) is not UUID
                    or not key.record_id.int):
                raise ValueError('same-document host key required')
            view = self.manager._view()
            try: card = view.read_document(key)
            finally: view.close()
            if card is None: raise BackendError('not_found')
            self.object = BSLDocumentObject(self.manager, card)
        self.baseline = self.image()
        self.listing = ()
        self.save_state = 'new' if self.object.is_new() else 'unchanged'

    def verify_source(self):
        if self._stale or self.context.backend is not self._backend:
            self._stale = True
            raise BackendError('schema_changed')
        try:
            self.context.require_active(tabular_sections=True)
            # This host editor owns ordinary, unposted document writes only.
            # A separate posting source grant must not activate its callbacks.
            if (getattr(self._backend, 'posting_configuration', None) is not None
                    or getattr(self._backend, 'accumulation_configuration', None) is not None):
                raise BackendError('unsupported')
            if self._backend.export_configuration() != dict(self._sources):
                raise BackendError('schema_changed')
            view = self._backend.begin_document_read()
            try:
                identity = (view.database_id, view.configuration_generation)
                if view.document_schema(self.schema.identity) != self.schema:
                    raise BackendError('schema_changed')
                if self._identity is not None and identity != self._identity:
                    raise BackendError('schema_changed')
                self._identity = identity
            finally: view.close()
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'): self._stale = True
            raise

    def image(self, obj=None):
        obj = self.object if obj is None else obj
        values = tuple((name, obj.get_member(name)) for name in self.fields)
        sections = tuple((schema.name, tuple(DocumentRowImage(row._identity,
            tuple((f.name, row.get_member(f.name)) for f in schema.fields))
            for row in obj._sections[schema.name.casefold()]))
            for schema in self.schema.tabular_sections)
        return DocumentImage(values, sections)

    @staticmethod
    def _members(values, names):
        if (type(values) is not tuple or len(values) != len(names) or
                any(type(pair) is not tuple or len(pair) != 2 for pair in values) or
                tuple(pair[0] for pair in values) != names):
            raise ValueError('complete ordered document image required')
        return dict(values)

    def _candidate(self, image):
        if type(image) is not DocumentImage: raise TypeError('document image required')
        values = self._members(image.values, self.fields)
        names = tuple(s.name for s in self.schema.tabular_sections)
        sections = self._members(image.sections, names)
        if (any(type(rows) is not tuple for rows in sections.values())
                or sum(len(rows) for rows in sections.values()) > 1000):
            raise ValueError('document form row limit')
        candidate = BSLDocumentObject(self.manager)
        candidate._key = self.object._key
        candidate._revision = self.object._revision
        candidate._operation_id = self.object._operation_id
        for name, value in values.items(): candidate.set_member(name, value)
        seen = set()
        for schema in self.schema.tabular_sections:
            original = self.object._sections[schema.name.casefold()]
            allowed = {row._identity for row in original}
            target = candidate._sections[schema.name.casefold()]
            for row in sections[schema.name]:
                if type(row) is not DocumentRowImage: raise TypeError('document row image required')
                if row.identity is not None:
                    if type(row.identity) is not UUID or row.identity not in allowed or row.identity in seen:
                        raise ValueError('document row belongs to another editor or section')
                    seen.add(row.identity)
                fields = self._members(row.values, tuple(f.name for f in schema.fields))
                added = target.add()
                if row.identity is not None: added._identity = row.identity
                for name, value in fields.items(): added.set_member(name, value)
        return candidate

    def _result(self):
        return DocumentSaveResult(self.save_state, self.error)

    def _refresh(self, validate_result):
        self.verify_source()
        view = self.manager._view()
        try:
            card = view.read_document(self.object._key)
            if card is None: raise BackendError('not_found')
            listing = view.select_documents(self.schema.identity, DocumentSelection())
            if not any(row.key == card.key for row in listing): raise BackendError('not_found')
        finally: view.close()
        fresh = BSLDocumentObject(self.manager, card)
        image = self.image(fresh)
        result = DocumentSaveResult('saved', None, image, card.key, listing)
        if validate_result is not None: validate_result(result)
        self.object, self.baseline, self.listing = fresh, image, listing
        self.pending_commit = self.pending_refresh = False
        self.save_state, self.error = 'saved', None
        return result

    def _try_refresh(self, validate_result):
        try: return self._refresh(validate_result)
        except Exception:
            self.pending_refresh = True
            self.listing = ()
            self.save_state, self.error = 'committed', 'refresh_required'
            return self._result()

    def save(self, image, *, validate_result=None):
        if self._saving: raise BackendError('busy')
        if validate_result is not None and not callable(validate_result):
            raise TypeError('trusted result validator required')
        forbid_transfer(self._backend)
        self._saving = True
        try:
            if self.context.backend is not self._backend:
                self._stale = True; self.error = 'schema_changed'; return self._result()
            if self.pending_refresh: return self._try_refresh(validate_result)
            self.error = None
            try:
                if not self.pending_commit:
                    self.verify_source()
                    self.object = self._candidate(image)
                self.object.write()
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
        finally: self._saving = False

    def require_discardable(self):
        if self.pending_commit or self.pending_refresh:
            raise BackendError('uncertain_commit' if self.pending_commit else 'busy')
