"""Local catalog editing through managed-form events and real CatalogObject.Write.

This application adapter is not native FormData/standard Write or a remote API.
It owns detached objects and their original optimistic revisions. Fixed references
use a bounded host selection adapter; its scalar selection keys are not native
FormData or managed-form references.
"""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from uuid import UUID, uuid4

from ..catalog_backend import BackendError
from ..catalogs import BSLCatalogs
from ..metadata import BSLCatalogMetadataCollection
from ..unique_identifiers import BSLUUID
from ..dates import BSLDate, _date_from_datetime, _parts, TICKS_PER_SECOND
from ..form_model import BSLFormAttribute
from ..form_runtime import FormApplicationAction, FormActionResult, FormSession
from ..form_event_simulation import VerifiedFormDraftSession
from ..type_descriptions import BSLTypeDescription
from ..type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLAllowedSign
from .catalog_view import CatalogRepository
from .protocol import CatalogRef, UIError, bounded_text, encode_line, encode_value, uuid_text, MAX_LINE_BYTES

# Fixed reviewed application code. Metadata names and user values are host values,
# never interpolated into BSL source or used as renderer-selected handler names.
AUTOFORM_SOURCE = '''
&AtServer
Procedure Create(Cancel, StandardProcessing)
 For Each A In GetAttributes() Do
  If Left(A.Name, 4) = "Data" Then
   F = Items.Add("Input" + A.Name, Type("FormField"));
   F.Title = A.Title;
   If A.Type.ContainsType(Type("Boolean")) Then
    F.Type = FormFieldType.CheckBoxField;
   EndIf;
   F.DataPath = A.Name;
   F.SetAction("OnChange", "Changed");
  EndIf;
 EndDo;
 C = Commands.Add("Save"); C.Action = "SaveCommand";
 B = Items.Add("SaveButton", Type("FormButton")); B.CommandName = "Save"; B.Title = "Save";
 C = Commands.Add("Cancel"); C.Action = "CancelCommand";
 B = Items.Add("CancelButton", Type("FormButton")); B.CommandName = "Cancel"; B.Title = "Cancel";
EndProcedure
&AtClient
Procedure Changed(Element)
 IsDirty = True;
 Status = "";
EndProcedure
&AtClient
Procedure SaveCommand(Command)
EndProcedure
&AtClient
Procedure CancelCommand(Command)
EndProcedure
&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
 If IsDirty And Not DiscardChanges Then Cancel = True; EndIf;
EndProcedure
'''


def _descriptor(kind, qualifiers):
    if kind == 'string':
        return BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(qualifiers[0])))
    if kind == 'number':
        digits, scale, sign = qualifiers
        allowed = BSLAllowedSign.NONNEGATIVE if sign == 'Nonnegative' else BSLAllowedSign.ANY
        return BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(digits), Decimal(scale), allowed))
    return BSLTypeDescription({'boolean': 'Boolean', 'datetime': 'Date'}[kind])


def _input_text(value):
    if type(value) is BSLDate:
        date = _parts(value)
        return f'{date.year:04}-{date.month:02}-{date.day:02}T{date.hour:02}:{date.minute:02}:{date.second:02}'
    return str(value) if type(value) is Decimal else value


def _reference_label(code, description):
    # Presentation is finite even when valid metadata allows 1024 four-byte
    # characters. UUID selection identity never depends on a truncated label.
    def short(value, limit):
        return value if len(value) <= limit else value[:limit] + '…'
    return bounded_text(short(code, 64) + ' · ' + short(description, 512), 4096)


class CatalogEditController:
    """One detached object and scalar selection keys. No persistent read transaction."""
    def __init__(self, manager, schema, obj, *, imported_form=False):
        if type(imported_form) is not bool:
            raise TypeError('exact imported-form flag required')
        self.identity = uuid4().hex
        self.manager, self.schema, self.object = manager, schema, obj
        self.pending_commit = False
        self.pending_refresh = False
        self._refreshed = None
        self.save_state = 'new' if obj.is_new() else 'unchanged'
        self.error = None
        self._source_backend = manager._backend if imported_form else None
        self._source_record = None
        self._source_stale = False
        self._source_messages = ()
        if imported_form:
            if schema.fields or schema.tabular_sections:
                raise BackendError('unsupported')
            self._source_record = manager._backend.read_form_source(schema.identity)
            self._source_draft(obj.get_member('Code'), obj.get_member('Description'))
        self.fields = []
        self.references = []
        self.reference_fields = {}
        definitions = [('Code', 'string', (schema.code_length,)),
                       ('Description', 'string', (schema.description_length,))]
        definitions += [(f.name, f.kind, f.qualifiers) for f in schema.fields if f.kind != 'catalog_ref']
        # Choices are captured through the logical read port, never supplied by
        # the renderer. Overflow and dangling/deleted existing values stay read-only.
        for field in schema.fields:
            if field.kind != 'catalog_ref':
                continue
            value = obj.get_member(field.name)
            repository = CatalogRepository(manager._backend, own_backend=False)
            try:
                target = repository.load(str(field.target_catalog_id))
            except UIError as error:
                if error.code != 'catalog_unavailable':
                    raise
                target = None
            finally:
                repository.close()
            choices = {'00000000-0000-0000-0000-000000000000': 'Empty reference'}
            if target is not None and len(target.cards) <= 64:
                choices.update((card.reference.record, _reference_label(
                    card.value('Code'), card.value('Description')))
                    for card in target.cards if not card.value('DeletionMark'))
            record = str(value.reference_uuid)
            if target is None or len(target.cards) > 64 or record not in choices:
                self.references.append({'name': field.name, 'readOnly': True,
                    'reason': ('reference-options-unavailable' if target is None else
                               'reference-choice-limit' if len(target.cards) > 64 else 'reference-not-selectable'),
                    'value': encode_value(CatalogRef(str(field.target_catalog_id), record)),
                    'presentation': bounded_text(str(value), 4096)})
                continue
            target_manager = manager._catalogs._manager_by_metadata_uuid(field.target_catalog_id)
            self.reference_fields[field.name] = (str(field.target_catalog_id), target_manager, MappingProxyType(choices))
            definitions.append((field.name, 'catalog_ref', (36,)))
        attributes, initial = [], {}
        for index, (field, kind, qualifiers) in enumerate(definitions):
            attribute = 'Data' + str(index)
            descriptor = _descriptor('string' if kind == 'catalog_ref' else kind, qualifiers)
            self.fields.append((field, kind, attribute, descriptor))
            attributes.append(BSLFormAttribute(attribute, descriptor, title=field))
            initial[attribute] = self._field_value(obj, field)
        attributes += [BSLFormAttribute('IsDirty', BSLTypeDescription('Boolean')),
                       BSLFormAttribute('DiscardChanges', BSLTypeDescription('Boolean')),
                       BSLFormAttribute('Status', BSLTypeDescription('String'))]
        names = tuple(field[2] for field in self.fields)
        self.baseline = tuple(initial[key] for key in names)
        self.form = FormSession(AUTOFORM_SOURCE, attributes=tuple(attributes), initial_values=initial,
            bindings={'OnCreateAtServer': 'Create', 'BeforeClose': 'BeforeClose'},
            application_actions=(
                FormApplicationAction('Save', 'SaveCommand', names, names + ('IsDirty', 'Status'), self._save, self._accept_refresh),
                FormApplicationAction('Cancel', 'CancelCommand', (), ('DiscardChanges',), self._cancel)))
        self.form.open()
        self._check_size()

    def _verify_source(self):
        if self.manager._backend is not self._source_backend:
            self._source_stale = True
        if self._source_stale:
            raise BackendError('schema_changed')
        try:
            current = self.manager._backend.read_form_source(
                self.schema.identity, expected=self._source_record.identity)
            if current != self._source_record:
                raise BackendError('schema_changed')
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'):
                self._source_stale = True
            raise

    def _source_draft(self, code, description):
        # Each event starts from the authoritative form buffer, never a second
        # mutable draft. The pinned source is checked around detached execution.
        self._verify_source()
        try:
            draft = VerifiedFormDraftSession(self._source_backend, self.schema.identity,
                code=code, description=description,
                deletion_mark=self.object.get_member('DeletionMark'))
            self._verify_source()
            return draft
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'):
                self._source_stale = True
            raise

    def _field_value(self, obj, field):
        value = obj.get_member(field)
        if field in self.reference_fields:
            value = str(value.reference_uuid)
            if value not in self.reference_fields[field][2]:
                raise UIError('invalid_value')
        return value

    def _values(self, attributes):
        data = dict(attributes)
        return tuple(data[field[2]] for field in self.fields)

    def _saved_reference(self):
        reference = self.object.get_member('Ref')
        return CatalogRef(str(self.schema.identity), str(reference.reference_uuid))

    def _refresh(self):
        reference = self.object.get_member('Ref')
        fresh = reference.get_object(reference)
        if fresh is None:
            raise BackendError('not_found')
        values = tuple(self._field_value(fresh, field[0]) for field in self.fields)
        # Adoption must follow the form's complete result validation/application.
        # A backend-valid value need not be admitted by this bounded scalar form.
        self._refreshed = (fresh, values)
        return FormActionResult(tuple((field[2], value) for field, value in zip(self.fields, values)) +
                                (('IsDirty', False), ('Status', 'Saved')))

    def _accept_refresh(self):
        if self._refreshed is not None:
            self.object, self.baseline = self._refreshed
            self._refreshed = None
            self.pending_refresh = False
            self.pending_commit = False
            self.save_state = 'saved'
            self.error = None

    def _save(self, attributes):
        self._refreshed = None
        values = self._values(attributes)
        self.error = None
        # Recovery may not run BSL or source reads, but it must still use the
        # exact backend which owns the retained intent and refresh obligation.
        if self._source_record is not None and self.manager._backend is not self._source_backend:
            self._source_stale = True
            self.error = 'schema_changed'
            return FormActionResult((('Status', 'Original database session required'),))
        if self.pending_refresh:
            try:
                return self._refresh()
            except Exception as error:
                if self._source_record is not None and isinstance(error, BackendError) and error.code in ('schema_changed', 'integrity'):
                    self._source_stale = True
                self.error = 'refresh_required'
                return FormActionResult((('Status', 'Saved; refresh required'),))
        if self._source_record is None and not self.pending_commit and not self.object.is_new() and values == self.baseline:
            self.save_state = 'unchanged'
            return FormActionResult((('IsDirty', False), ('Status', 'No changes')))
        try:
            if not self.pending_commit:
                if self._source_record is not None:
                    draft = self._source_draft(values[0], values[1])
                    prepared = draft.prepare_save(revision=0)
                    self._verify_source()
                    self._source_messages = prepared.messages
                    if prepared.cancel:
                        self.save_state = 'rejected'
                        self.error = 'form_validation'
                        return FormActionResult((('IsDirty', True), ('Status', 'Save refused by original form handler')))
                    candidate = dict(prepared.candidate)
                    values = (candidate['Code'], candidate['Description'])
                    if not self.object.is_new() and values == self.baseline:
                        self.save_state = 'unchanged'
                        return FormActionResult(tuple((field[2], value) for field, value in zip(self.fields, values)) +
                                                (('IsDirty', False), ('Status', 'No changes')))
                for field, value in zip(self.fields, values):
                    if field[1] == 'catalog_ref':
                        target, manager, choices = self.reference_fields[field[0]]
                        if value not in choices:
                            raise UIError('invalid_value')
                        value = manager.get_ref(BSLUUID(value))
                    self.object.set_member(field[0], value)
            # A retained uncertain object resolves its exact submitted intent before
            # any retry. Never reload latest before Write or allocate another object.
            self.object.write()
        except BackendError as error:
            if self._source_record is not None and error.code in ('schema_changed', 'integrity'):
                self._source_stale = True
            # Resolution failure does not prove the retained intent absent.
            # Keep the existing lock even for transient busy/storage errors.
            self.pending_commit = self.pending_commit or error.code == 'uncertain_commit'
            self.save_state = 'uncertain' if self.pending_commit else 'rejected'
            self.error = error.code
            return FormActionResult((('IsDirty', True), ('Status', 'Save outcome uncertain' if self.pending_commit else 'Save rejected: ' + error.code)))
        except BaseException:
            # An interrupted Write can still have a durable receipt. Keep the
            # editor locked while the exact submitted intent is unresolved.
            if self.object._pending_write is not None:
                self.pending_commit = True
                self.save_state = 'uncertain'
                self.error = 'uncertain_commit'
            raise
        self.pending_commit = False
        self.pending_refresh = True
        self.save_state = 'committed'
        try:
            return self._refresh()
        except Exception as error:
            if self._source_record is not None and isinstance(error, BackendError) and error.code in ('schema_changed', 'integrity'):
                self._source_stale = True
            self.error = 'refresh_required'
            return FormActionResult((('Status', 'Saved; refresh required'),))

    def _cancel(self, unused):
        if self.pending_commit or self.pending_refresh:
            raise UIError('busy')  # Outcome must be resolved, not silently discarded.
        return FormActionResult((('DiscardChanges', True),))

    def _parse_input(self, field, value):
        kind = field[1]
        if kind == 'catalog_ref':
            target, manager, choices = self.reference_fields[field[0]]
            if type(value) is not CatalogRef or value.catalog != target or value.record not in choices:
                raise UIError('invalid_value')
            return value.record
        if kind == 'number' and type(value) is str:
            if len(value) > 144 or not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:E[+-]?[0-9]+)?', value):
                raise UIError('invalid_value')
            try: value = Decimal(value)
            except InvalidOperation: raise UIError('invalid_value') from None
        if kind == 'datetime' and type(value) is str:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}', value):
                raise UIError('invalid_value')
            try: value = _date_from_datetime(datetime.fromisoformat(value))
            except ValueError: raise UIError('invalid_value') from None
        expected = {'string': str, 'number': Decimal, 'boolean': bool, 'datetime': BSLDate}[kind]
        if type(value) is not expected:
            raise UIError('invalid_value')
        encode_value(value)
        if kind == 'datetime' and value.ticks % TICKS_PER_SECOND:
            raise UIError('invalid_value')
        return field[3].adjust_value(value)

    def change(self, control, value):
        if self.pending_commit or self.pending_refresh:
            raise UIError('busy')
        field = next((field for field in self.fields if control == 'Input' + field[2]), None)
        if field is None:
            raise UIError('invalid_value')
        if self._source_record is not None and field[0] != 'Description':
            raise UIError('invalid_value')
        value = self._parse_input(field, value)
        snapshot = self.form.snapshot()
        source_messages = None
        if self._source_record is not None:
            current = dict(snapshot.attributes)
            try:
                draft = self._source_draft(current['Data0'], current['Data1'])
                changed = draft.change_description(value, revision=0)
                self._verify_source()
                value = dict(changed.values)['Description']
                source_messages = changed.messages
            except BackendError as error:
                if error.code in ('schema_changed', 'integrity'):
                    self._source_stale = True
                raise
        attributes = tuple((key, value if key == field[2] else old) for key, old in snapshot.attributes)
        self._check_size(replace(snapshot, attributes=attributes))
        result = self.form.dispatch('change', revision=self.form.revision, control=control, value=value)
        if source_messages is not None:
            self._source_messages = source_messages
        self.error = None
        self.save_state = 'editing'
        return result

    def command(self, control):
        if control not in ('SaveButton', 'CancelButton'):
            raise UIError('invalid_value')
        result = self.form.dispatch('command', revision=self.form.revision, control=control)
        if control == 'CancelButton':
            result = self.form.dispatch('close', revision=self.form.revision)
        return result

    def close(self):
        if self.pending_commit or self.pending_refresh:
            raise UIError('busy')
        return self.form.dispatch('close', revision=self.form.revision)

    def snapshot(self, form_snapshot=None):
        snapshot = self.form.snapshot() if form_snapshot is None else form_snapshot
        values = dict(snapshot.attributes)
        items = {item[0]: item for item in snapshot.items}
        views = dict(snapshot.item_views)
        fields = []
        for field, kind, attribute, unused in self.fields:
            control = 'Input' + attribute
            item = items[control]
            value = values[attribute]
            choices = None
            if kind == 'catalog_ref':
                target, manager, options = self.reference_fields[field]
                choices = [{'value': record, 'label': label} for record, label in options.items()]
                value = CatalogRef(target, value)
            fields.append({'name': field, 'kind': kind, 'control': control,
                'value': encode_value(value), 'inputText': _input_text(values[attribute]),
                'title': item[2], 'visible': item[3], 'enabled': item[4], 'readOnly': item[5] or (self._source_record is not None and field == 'Code'),
                'view': views[control], **({'choices': choices} if choices is not None else {})})
        return {'editorId': self.identity, 'catalog': str(self.schema.identity), 'catalogName': self.schema.name,
            'reference': encode_value(self._saved_reference()), 'isNew': self.object.is_new(),
            'formRevision': snapshot.revision, 'state': snapshot.state,
            'dirty': values['IsDirty'], 'status': values['Status'], 'saveState': self.save_state,
            'error': self.error, 'editingLocked': self.pending_commit or self.pending_refresh,
            'fields': fields, 'references': self.references,
            'commands': [{'control': item[0], 'title': item[2], 'visible': item[3], 'enabled': item[4]}
                         for item in snapshot.items if item[1] == 'button'],
            'messages': list(self.form.messages),
            'originalForm': self._source_record is not None,
            'sourceStale': self._source_stale,
            'fieldMessages': [{'text': message.text, 'field': message.field}
                              for message in self._source_messages]}

    def _check_size(self, snapshot=None):
        # Reserve space for the transport envelope/status/commit identity. No BSL
        # effect or database write is performed to discover an oversized state.
        if len(encode_line(self.snapshot(snapshot))) > MAX_LINE_BYTES - 8192:
            raise UIError('message_limit')


class CatalogEditorApplication:
    """Host-owned local application service. Renderer never chooses its database."""
    def __init__(self, context):
        context.require_active()
        self.context = context
        self.backend = context.backend
        self._active_forms = self.backend.active_form_catalogs()
        if (type(self._active_forms) is not tuple or
                any(type(identity) is not UUID or not identity.int for identity in self._active_forms)):
            raise BackendError('unsupported')
        self.metadata = BSLCatalogMetadataCollection(context)
        self.catalogs = BSLCatalogs(self.metadata, context)
        self.selected = None
        self.view = None
        self.page = (0, 8)
        self.editor = None
        self.closed = False

    def _inventory(self):
        view = self.backend.begin_read()
        try: return view.catalogs()
        finally: view.close()

    def _schema(self, identity):
        uuid_text(identity, nonzero=True)
        schema = next((schema for schema in self._inventory() if str(schema.identity) == identity), None)
        if schema is None: raise UIError('catalog_not_found')
        return schema

    def _load(self):
        repository = CatalogRepository(self.backend, own_backend=False)
        try: return repository.load(self.selected)
        finally: repository.close()

    def select(self, identity):
        if self.editor is not None: raise UIError('busy')
        self._schema(identity)
        old = self.selected
        self.selected = identity
        try: self.view = self._load()
        except BaseException:
            self.selected = old; raise
        self.page = (0, 8)

    def open(self, reference=None):
        if self.editor is not None: raise UIError('busy')
        schema = self._schema(self.selected)
        manager = self.catalogs.get_index(schema.name)
        if reference is None:
            obj = manager.create_item()
        else:
            if type(reference) is not CatalogRef or reference.catalog != self.selected or UUID(reference.record).int == 0:
                raise UIError('catalog_identity')
            ref = manager.get_ref(BSLUUID(reference.record))
            obj = ref.get_object(ref)
            if obj is None: raise UIError('record_not_found')
        editor = CatalogEditController(manager, schema, obj,
            imported_form=schema.identity in self._active_forms)
        self.editor = editor

    def event(self, event, **values):
        if self.closed: raise UIError('closed')
        if event == 'selectCatalog': self.select(values['catalog'])
        elif event == 'create': self.open()
        elif event == 'openCard': self.open(values['reference'])
        elif event == 'page':
            if self.editor is not None or self.view is None: raise UIError('busy')
            self.view.page(values['offset'], values['limit'])
            self.page = (values['offset'], values['limit'])
        elif event in ('change', 'command', 'closeCard'):
            if self.editor is None: raise UIError('closed')
            if event == 'change': self.editor.change(values['control'], values['value'])
            elif event == 'command': self.editor.command(values['control'])
            else: self.editor.close()
            if self.editor.form.closed:
                source_stale = self.editor._source_stale
                self.editor = None
                if source_stale:
                    # Discard must leave a usable terminal snapshot, not attempt
                    # fresh catalog reads against a permanently invalidated pin.
                    self.view = None
                    self.close()
                else:
                    self.view = self._load()
        elif event == 'close':
            if self.editor is not None:
                self.editor.close()
                if not self.editor.form.closed: return
            self.close()
        else: raise UIError('invalid_message')

    def snapshot(self):
        capabilities = self.backend.capabilities()
        writable = not self.closed and capabilities.atomic_transactions and capabilities.catalog_create and capabilities.catalog_update
        state = {'kind': 'closed' if self.closed else 'editor' if self.editor else 'list' if self.view else 'catalogs',
                 'catalogs': [] if self.closed or self.editor is not None else [{'id': str(schema.identity), 'name': schema.name} for schema in self._inventory()],
                 'list': self.view.page(*self.page) if self.view is not None and self.editor is None else None,
                 'editor': self.editor.snapshot() if self.editor is not None else None}
        return {'capabilities': {'canCreate': writable, 'canEdit': writable, 'canWrite': writable,
                'referenceEditing': True, 'referenceChoiceLimit': 64, 'actual1CForms': False, 'autoform': True,
                'standardFormWrite': False, 'remoteService': False,
                'importedNameValidation': bool(self._active_forms)}, 'state': state}

    def close(self):
        if not self.closed:
            self.closed = True
            self.context.close()
