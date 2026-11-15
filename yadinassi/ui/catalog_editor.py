"""Local catalog editing through managed-form events and real CatalogObject.Write.

This application adapter is not native FormData/standard Write or a remote API.
It owns detached objects and their original optimistic revisions. Fixed references
use a bounded host selection adapter; its scalar selection keys are not native
FormData or managed-form references.
"""
from dataclasses import replace
from copy import copy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from uuid import UUID, uuid4

from ..catalog_backend import (BackendError, CatalogScanRequest, CatalogOrder,
    CatalogValuePage, CatalogValueRow, CatalogKey, CatalogSchema)
from ..catalogs import BSLCatalogs
from ..metadata import BSLCatalogMetadataCollection
from ..unique_identifiers import BSLUUID
from ..dates import BSLDate, _date_from_datetime, _parts, TICKS_PER_SECOND
from ..form_model import BSLFormAttribute
from ..form_runtime import FormApplicationAction, FormActionResult, FormSession
from ..form_event_simulation import VerifiedFormDraftSession, simulate_product_form_event
from ..catalog_object_preparation import CatalogWriteRefused
from ..type_descriptions import BSLTypeDescription
from ..type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLAllowedSign
from .catalog_view import CatalogRepository
from .legacy_reference_choice import LegacyReferenceChooser
from ..catalog_sections import BSLCatalogSection
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


def _reference_options(backend, target, current):
    """Bounded compatibility probe; large catalogs retain current/empty only."""
    repository = CatalogRepository(backend, own_backend=False)
    try:
        identity = str(target)
        if not any(item.identity == identity for item in repository.inventory()):
            raise UIError('catalog_unavailable')
        view = repository._read()
        schema = view.catalog_schema(target)
        if type(schema) is not CatalogSchema or schema.identity != target or schema not in repository._schemas:
            raise UIError('metadata_unavailable')
        repository._summary_fields(schema)
        scan = getattr(view, 'scan_catalog_values', None)
        if not callable(scan):
            raise UIError('catalog_unavailable')
        page = scan(target, CatalogScanRequest(order=(CatalogOrder('code'),), page_size=64),
                    ('code', 'description', 'deletion_mark'))
        if type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows) > 64:
            raise UIError('catalog_unavailable')
        if page.continuation is not None and (type(page.continuation) is not str or len(page.continuation) != 32
                or any(c not in '0123456789abcdef' for c in page.continuation) or not page.rows):
            raise UIError('catalog_unavailable')
        options, seen = {str(UUID(int=0)): 'Empty reference'}, set()
        for row in page.rows:
            if (type(row) is not CatalogValueRow or type(row.key) is not CatalogKey
                    or type(row.key.database_id) is not UUID or type(row.key.catalog_id) is not UUID
                    or row.key.database_id != repository._identity[0] or row.key.catalog_id != target):
                raise UIError('catalog_identity')
            record = repository._uuid(row.key.record_id)
            if record in seen or type(row.values) is not tuple or len(row.values) != 3:
                raise UIError('catalog_unavailable')
            seen.add(record)
            code, description, deleted = row.values
            if type(code) is not str or type(description) is not str or type(deleted) is not bool:
                raise UIError('unsupported_value')
            for value, bound in ((code, schema.code_length), (description, schema.description_length)):
                if '\x00' in value or len(value.encode('utf-16-le'))//2 > bound:
                    raise UIError('unsupported_value')
                value.encode('utf-8')
            if page.continuation is None and not deleted:
                options[record] = _reference_label(code, description)
        for record in set(current):
            if record == str(UUID(int=0)) or record in options:
                continue
            cards = repository.load(identity, summary_only=True, record=UUID(record)).cards
            if cards and not cards[0].value('DeletionMark'):
                options[record] = _reference_label(cards[0].value('Code'), cards[0].value('Description'))
        repository.check_source()
        repository._read()
        return options
    except UnicodeError:
        raise UIError('unsupported_value') from None
    finally:
        repository.close()


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
        self._product_source = None
        self._source_stale = False
        self._source_messages = ()
        if imported_form:
            self._source_record = manager._backend.read_form_source(schema.identity)
            self._product_source = manager._backend.catalog_write_preparation(
                schema.identity, expected=self._source_record.identity)
            if self._product_source is None:
                if schema.fields or schema.tabular_sections:
                    raise BackendError('unsupported')
                self._source_draft(obj.get_member('Code'), obj.get_member('Description'))
        self.sections = ReferenceSections(self)
        self.section_baseline = self._section_values(obj)
        self.fields = []
        self.references = []
        self.reference_fields = {}
        definitions = [('Code', 'string', (schema.code_length,)),
                       ('Description', 'string', (schema.description_length,))]
        definitions += [(f.name, f.kind, f.qualifiers) for f in schema.fields if f.kind != 'catalog_ref']
        # A bounded compatibility probe keeps small inline choices. Large targets
        # use the owned pager; missing/deleted current values remain read-only.
        for field in schema.fields:
            if field.kind != 'catalog_ref':
                continue
            value = obj.get_member(field.name)
            record = str(value.reference_uuid)
            try:
                choices = _reference_options(manager._backend, field.target_catalog_id, (record,))
            except (UIError, BackendError):
                choices = None
            if choices is None or record not in choices:
                self.references.append({'name': field.name, 'readOnly': True,
                    'reason': 'reference-options-unavailable' if choices is None else 'reference-not-selectable',
                    'value': encode_value(CatalogRef(str(field.target_catalog_id), record)),
                    'presentation': bounded_text(str(value), 4096)})
                continue
            target_manager = manager._catalogs._manager_by_metadata_uuid(field.target_catalog_id)
            self.reference_fields[field.name] = (str(field.target_catalog_id), target_manager, MappingProxyType(choices))
            definitions.append((field.name, 'catalog_ref', (36,)))
        # A host draft field, not an original form OnChange binding. Append it
        # to preserve existing control identities. Only Save writes this value.
        definitions.append(('DeletionMark', 'boolean', ()))
        attributes, initial = [], {}
        for index, (field, kind, qualifiers) in enumerate(definitions):
            attribute = 'Data' + str(index)
            descriptor = _descriptor('string' if kind == 'catalog_ref' else kind, qualifiers)
            self.fields.append((field, kind, attribute, descriptor))
            attributes.append(BSLFormAttribute(attribute, descriptor,
                title='Пометка удаления' if field == 'DeletionMark' else field))
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
            if self._product_source is not None and self.manager._backend.catalog_write_preparation(
                    self.schema.identity, expected=current.identity) != self._product_source:
                raise BackendError('schema_changed')
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'):
                self._source_stale = True
            raise

    def _source_draft(self, code, description, deletion_mark=None):
        # Each event starts from the authoritative form buffer, never a second
        # mutable draft. The pinned source is checked around detached execution.
        self._verify_source()
        try:
            draft = VerifiedFormDraftSession(self._source_backend, self.schema.identity,
                code=code, description=description,
                deletion_mark=(self.object.get_member('DeletionMark')
                               if deletion_mark is None else deletion_mark))
            self._verify_source()
            return draft
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'):
                self._source_stale = True
            raise

    def _product_candidate(self, values, *, sections=None):
        # Copy the same detached identity/revision, never allocate a replacement
        # new-object key. No mutable field/section aliases escape into execution.
        candidate = copy(self.object)
        candidate._values = dict(self.object._values)
        candidate._sections = {}
        for schema in self.schema.tabular_sections:
            original = (self.object._sections if sections is None else sections)[schema.name.casefold()]
            section = BSLCatalogSection(candidate, schema, original._stored_rows().rows)
            section._dirty = original._dirty
            candidate._sections[schema.name.casefold()] = section
        for field, value in zip(self.fields, values):
            if field[1] == 'catalog_ref':
                target, manager, choices = self.reference_fields[field[0]]
                if value not in choices:
                    raise UIError('invalid_value')
                value = manager.get_ref(BSLUUID(value))
            candidate.set_member(field[0], value)
        return candidate

    def _product_event(self, candidate, event, *, row=None):
        self._verify_source()
        result = simulate_product_form_event(self._source_record.module_source,
            self._product_source.encode('utf-8'), candidate, event=event,
            current_row_id=None if row is None else UUID(row))
        self._verify_source()
        return result

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

    @staticmethod
    def _section_values(obj):
        return tuple(section._stored_rows() for section in obj._sections.values())

    def _refresh(self):
        reference = self.object.get_member('Ref')
        fresh = reference.get_object(reference)
        if fresh is None:
            raise BackendError('not_found')
        values = tuple(self._field_value(fresh, field[0]) for field in self.fields)
        # Adoption must follow the form's complete result validation/application.
        # A backend-valid value need not be admitted by this bounded scalar form.
        patches = dict((field[2], value) for field, value in zip(self.fields, values))
        patches.update(IsDirty=False, Status="Saved")
        current = self._action_snapshot
        prospective = replace(current, attributes=tuple((key, patches.get(key, value))
                                                       for key, value in current.attributes))
        self._check_size(prospective, obj=fresh)
        self._refreshed = (fresh, values)
        return FormActionResult(tuple((field[2], value) for field, value in zip(self.fields, values)) +
                                (('IsDirty', False), ('Status', 'Saved')))

    def _accept_refresh(self):
        if self._refreshed is not None:
            self.object, self.baseline = self._refreshed
            self.section_baseline = self._section_values(self.object)
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
        if self._source_record is None and not self.pending_commit and not self.object.is_new() and values == self.baseline and self._section_values(self.object) == self.section_baseline:
            self.save_state = 'unchanged'
            return FormActionResult((('IsDirty', False), ('Status', 'No changes')))
        try:
            if not self.pending_commit:
                if self._product_source is not None:
                    candidate = self._product_candidate(values)
                    prepared = self._product_event(candidate, 'BeforeWriteAtServer')
                    self._source_messages = prepared.messages
                    if prepared.cancel:
                        self.save_state = 'rejected'
                        self.error = 'form_validation'
                        return FormActionResult((('IsDirty', True), ('Status', 'Save refused by original form handler')))
                    # Only a successfully prepared candidate replaces the writer
                    # receiver. Its own mandatory BeforeWrite runs in transaction.
                    self.object = candidate
                    values = tuple(self._field_value(candidate, f[0]) for f in self.fields)
                elif self._source_record is not None:
                    data = dict((f[0], v) for f, v in zip(self.fields, values))
                    draft = self._source_draft(data['Code'], data['Description'], data['DeletionMark'])
                    prepared = draft.prepare_save(revision=0)
                    self._verify_source()
                    self._source_messages = prepared.messages
                    if prepared.cancel:
                        self.save_state = 'rejected'
                        self.error = 'form_validation'
                        return FormActionResult((('IsDirty', True), ('Status', 'Save refused by original form handler')))
                    candidate = dict(prepared.candidate)
                    values = tuple(candidate[field[0]] for field in self.fields)
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
        except CatalogWriteRefused as error:
            # This rejection happens before commit, including after a proven
            # absent receipt. The writer has released its retained intent.
            self.pending_commit = self.object._pending_write is not None
            self._source_messages = error.messages
            self.save_state = 'rejected'
            self.error = 'object_validation'
            return FormActionResult((('IsDirty', True), ('Status', 'Save refused by original object handler')))
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
        if self._source_record is not None and (field[0] == 'Code' or
                self._product_source is None and field[0] not in ('Description', 'DeletionMark')):
            raise UIError('invalid_value')
        value = self._parse_input(field, value)
        snapshot = self.form.snapshot()
        source_messages = None
        if field[0] == 'DeletionMark':
            # No original deletion-mark change handler exists. Verify its source
            # but leave validation to the original before-save/object handlers.
            if self._source_record is not None:
                self._verify_source()
            source_messages = ()
        elif self._product_source is not None:
            values = tuple(value if f[2] == field[2] else dict(snapshot.attributes)[f[2]] for f in self.fields)
            candidate = self._product_candidate(values)
            event = 'DescriptionOnChange' if field[0] == 'Description' else 'KindOnChange'
            changed = self._product_event(candidate, event)
            value = self._field_value(candidate, field[0])
            source_messages = changed.messages
        elif self._source_record is not None:
            current = dict(snapshot.attributes)
            try:
                data = dict((f[0], current[f[2]]) for f in self.fields)
                draft = self._source_draft(data['Code'], data['Description'], data['DeletionMark'])
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

    def row_event(self, event, section, row=None, value=None):
        if self.pending_commit or self.pending_refresh:
            raise UIError('busy')
        candidate = self.sections.changed(event, section, row, value)
        current = self.form.snapshot()
        source_messages = None
        if self._product_source is not None:
            self._verify_source()
            source_messages = ()  # Structural edits invalidate old positional diagnostics.
            if event == 'changeRow':
                receiver = self._product_candidate(self._values(current.attributes), sections=candidate)
                changed = self._product_event(receiver, 'WarehouseOnChange', row=row)
                candidate = receiver._sections
                source_messages = changed.messages
        prospective = replace(current, attributes=tuple(
            (key, True if key == 'IsDirty' else '' if key == 'Status' else old)
            for key, old in current.attributes))
        self._check_size(prospective, sections=candidate)
        # The reviewed autoform handler owns dirty/close state. No row or save
        # effect is exposed to BSL or selected by renderer-supplied source.
        attribute = self.fields[0][2]
        self.form.dispatch('change', revision=self.form.revision,
                           control='Input' + attribute, value=dict(current.attributes)[attribute])
        self.object._sections = candidate
        # Rebind the adopted detached sections to the live editor receiver.
        for section_value in candidate.values():
            section_value._owner = self.object
        if source_messages is not None:
            self._source_messages = source_messages
        self.error = None
        self.save_state = 'editing'

    def command(self, control):
        if control not in ('SaveButton', 'CancelButton'):
            raise UIError('invalid_value')
        self._action_snapshot = self.form.snapshot()
        try:
            result = self.form.dispatch('command', revision=self.form.revision, control=control)
        finally:
            self._action_snapshot = None
        if control == 'CancelButton':
            result = self.form.dispatch('close', revision=self.form.revision)
        return result

    def close(self):
        if self.pending_commit or self.pending_refresh:
            raise UIError('busy')
        return self.form.dispatch('close', revision=self.form.revision)

    def snapshot(self, form_snapshot=None, *, obj=None, sections=None):
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
                'view': views[control], **({'choices': choices, 'lazyChoice': True} if choices is not None else {})})
        return {'editorId': self.identity, 'catalog': str(self.schema.identity), 'catalogName': self.schema.name,
            'reference': encode_value(self._saved_reference()), 'isNew': self.object.is_new(),
            'formRevision': snapshot.revision, 'state': snapshot.state,
            'dirty': values['IsDirty'], 'status': values['Status'], 'saveState': self.save_state,
            'error': self.error, 'editingLocked': self.pending_commit or self.pending_refresh,
            'fields': fields, 'references': self.references,
            'sections': self.sections.snapshot(obj, sections),
            'commands': [{'control': item[0], 'title': item[2], 'visible': item[3], 'enabled': item[4]}
                         for item in snapshot.items if item[1] == 'button'],
            'messages': list(self.form.messages),
            'originalForm': self._source_record is not None,
            'sourceStale': self._source_stale,
            'fieldMessages': [{'text': message.text, 'field': message.field}
                              for message in self._source_messages]}

    def _check_size(self, snapshot=None, *, obj=None, sections=None):
        # Reserve space for the transport envelope/status/commit identity. No BSL
        # effect or database write is performed to discover an oversized state.
        editor = self.snapshot(snapshot, obj=obj, sections=sections)
        # Exercise the deepest error-envelope shape as well as reserving nodes
        # for the surrounding session/capabilities fields, not bytes alone.
        envelope = {'error': {'data': {'snapshot': {'state': {'editor': editor}}}},
                    'reserved': [None] * 128}
        if len(encode_line(envelope)) > MAX_LINE_BYTES - 8192:
            raise UIError('message_limit')


class CatalogEditorApplication:
    """Host-owned local application service. Renderer never chooses its database."""
    def __init__(self, context):
        context.require_active(tabular_sections=True)
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
        self.list_messages = ()
        self.summary = None
        self.query, self.order = '', 'code'
        self.list_notice = ''
        self._reference_chooser = None
        self._reference_projection = None

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
        try:
            summary = repository.load_summary(self.selected)
            candidate = summary.select(query=self.query, order=self.order)
            self.summary = summary
            return candidate
        finally: repository.close()

    def _list_state(self):
        return self.selected, self.summary, self.view, self.page, self.query, self.order, self.list_notice

    def _restore_list(self, state):
        self.selected, self.summary, self.view, self.page, self.query, self.order, self.list_notice = state

    def _preflight_list(self):
        encode_line({'error': {'data': {'snapshot': self.snapshot()}}})

    def _refresh_saved_list(self):
        """Authoritative read after confirmed Save, never another Write.

        Keep the selected card open and locate its persisted identity in the
        newly read ordering. A failed projection retains a refresh obligation;
        the next Save resolves that obligation without resubmitting the write.
        """
        editor = self.editor
        if editor is None or editor.error or editor.save_state not in ('saved', 'unchanged'):
            return
        previous = self._list_state()
        try:
            candidate = self._load()
            reference = editor._saved_reference()
            position = next((i for i, card in enumerate(candidate.cards) if card.reference == reference), None)
            limit = self.page[1]
            # A confirmed write may legitimately move outside the current filter.
            # It must not become a pending write or be injected into the result.
            page = (((position // limit) * limit) if position is not None else min(self.page[0], max(0, ((len(candidate.cards)-1)//limit)*limit)), limit)
            present = any(card.reference == reference for card in self.summary.cards)
            self.list_notice = (('Saved record is outside the current filter' if present else 'Saved record is no longer available') if position is None else '')
            self.view, self.page = candidate, page
            self._preflight_list()
        except Exception:
            self._restore_list(previous)
            self.view = None
            editor.pending_refresh = True
            editor.save_state = 'committed'
            editor.error = 'refresh_required'
            editor.form.form._data['status'] = 'Saved; list refresh required'

    def select(self, identity):
        if self.editor is not None: raise UIError('busy')
        self._schema(identity)
        previous = self._list_state()
        self.selected, self.query, self.order = identity, '', 'code'
        try:
            self.view = self._load()
            self.page, self.list_notice = (0, 8), ''
            self._preflight_list()
        except BaseException:
            self._restore_list(previous); raise

    def filter_records(self, query, order):
        if self.editor is not None or self.summary is None: raise UIError('busy')
        candidate = self.summary.select(query=query, order=order)
        previous = self._list_state()
        try:
            self.view, self.query, self.order = candidate, query, order
            self.page, self.list_notice = (0, self.page[1]), ''
            self._preflight_list()
        except BaseException:
            self._restore_list(previous); raise

    def refresh_records(self):
        if self.editor is not None or self.selected is None: raise UIError('busy')
        previous = self._list_state()
        try:
            candidate = self._load()
            limit = self.page[1]
            offset = min(self.page[0], max(0, ((len(candidate.cards)-1)//limit)*limit))
            self.view, self.page = candidate, (offset, limit)
            self.list_notice = ''
            self._preflight_list()
        except BaseException:
            self._restore_list(previous); raise

    def check_card(self, reference):
        self.list_messages = ()
        if self.editor is not None or self.view is None:
            raise UIError('busy')
        schema = self._schema(self.selected)
        if schema.identity not in self._active_forms or schema.name != 'Номенклатура':
            raise UIError('invalid_message')
        manager = self.catalogs.get_index(schema.name)
        if reference is None:
            selected = manager.empty_ref()
        else:
            if type(reference) is not CatalogRef or reference.catalog != self.selected:
                raise UIError('catalog_identity')
            selected = manager.get_ref(BSLUUID(reference.record))
        from ..product_list_check import check_product_list
        view = self.backend.begin_read()
        try:
            sources = view.product_list_sources(schema.identity)
            self.list_messages = check_product_list(manager, selected, view, *sources)
        finally:
            view.close()

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

    def _close_reference_choice(self):
        if self._reference_chooser is not None:
            self._reference_chooser.cancel()
        self._reference_chooser = self._reference_projection = None

    def reference_choice(self, action):
        try:
            return self._reference_choice(action)
        except BaseException:
            if self._reference_chooser is not None and self._reference_chooser._ticket is None:
                self._close_reference_choice()
            raise

    def _reference_choice(self, action):
        if type(action) is not dict or type(action.get('action')) is not str:
            raise UIError('invalid_value')
        name = action['action']
        expected = {'begin': {'action','control','section','row'},
            'search': {'action','ticket','query'}, 'page': {'action','ticket','cursor'},
            'apply': {'action','ticket','choice'}, 'clear': {'action','ticket'},
            'cancel': {'action','ticket'}, 'refresh': {'action','ticket'}}
        if name not in expected or set(action) != expected[name]:
            raise UIError('invalid_value')
        editor = self.editor
        if editor is None or editor.pending_commit or editor.pending_refresh or editor.form.closed:
            raise UIError('busy')
        if name == 'begin':
            control, section, row_id = action['control'], action['section'], action['row']
            scalar = type(control) is str and section is None and row_id is None
            sectional = control is None and type(section) is str and type(row_id) is str
            if not scalar and not sectional:
                raise UIError('invalid_value')
            if sectional: uuid_text(row_id, nonzero=True)
            binding = None
            def witness():
                if self.editor is not editor or editor.pending_commit or editor.pending_refresh or editor.form.closed:
                    raise UIError('busy')
                if self.backend is not editor.manager._backend:
                    raise UIError('catalog_unavailable')
                if editor._source_record is not None: editor._verify_source()
                view = self.backend.begin_read()
                try:
                    actual_binding = (view.database_id, view.configuration_generation)
                    schemas = view.catalogs()
                    if type(schemas) is not tuple or any(type(s) is not CatalogSchema for s in schemas) or editor.schema not in schemas:
                        raise UIError('metadata_unavailable')
                finally:
                    view.close()
                if binding is not None and actual_binding != binding:
                    raise UIError('catalog_unavailable')
                snap = editor.snapshot()
                if scalar:
                    field = next((f for f in snap['fields'] if f['control'] == control), None)
                    if field is None or not field.get('lazyChoice') or field['readOnly'] or not field['enabled'] or not field['visible']:
                        raise UIError('invalid_value')
                    target = editor.reference_fields[field['name']][0]
                    current = field['inputText']
                else:
                    item = next((s for s in snap['sections'] if s['name'] == section), None)
                    row = None if item is None else next((r for r in item['rows'] if r['id'] == row_id), None)
                    if item is None or item['readOnly'] or row is None or row['field']['readOnly']:
                        raise UIError('invalid_value')
                    schema = next(s for s in editor.schema.tabular_sections if s.name == section)
                    target = str(schema.fields[0].target_catalog_id)
                    current = row['field']['inputText']
                return (editor.identity, control, section, row_id, target, current, snap['formRevision'], actual_binding)
            pin = witness()
            binding = pin[-1]
            self._close_reference_choice()
            def preflight(projection):
                previous = self._reference_projection
                try:
                    self._reference_projection = projection
                    encode_line({'error': {'data': {'snapshot': self.snapshot()}}})
                finally:
                    self._reference_projection = previous
            chooser = LegacyReferenceChooser(self.backend, UUID(pin[4]), witness, preflight=preflight)
            projection = chooser.begin()
            self._reference_chooser, self._reference_projection = chooser, projection
            self._reference_destination = (control, section, row_id)
            return
        chooser = self._reference_chooser
        if chooser is None:
            raise UIError('invalid_value')
        ticket = action['ticket']
        if name == 'cancel':
            chooser._check(ticket)
            self._close_reference_choice()
        elif name in ('search', 'page', 'refresh'):
            projection = (chooser.search(ticket, action['query']) if name == 'search' else
                          chooser.page(ticket, action['cursor']) if name == 'page' else chooser.refresh(ticket))
            self._reference_projection = projection
        else:
            label = 'Empty reference'
            if name == 'apply':
                selected = next((r for r in self._reference_projection['rows'] if r['choice'] == action['choice']), None)
                if selected is None: raise UIError('invalid_value')
                label = _reference_label(selected['code'], selected['description'])
            reference = chooser.clear(ticket) if name == 'clear' else chooser.apply(ticket, action['choice'])
            control, section, row_id = self._reference_destination
            self._close_reference_choice()
            if control is not None:
                field = next(f for f in editor.fields if 'Input'+f[2] == control)
                target, manager, options = editor.reference_fields[field[0]]
                updated = dict(options); updated[reference.record] = label
                editor.reference_fields[field[0]] = (target, manager, MappingProxyType(updated))
                try: editor.change(control, reference)
                except BaseException:
                    editor.reference_fields[field[0]] = (target, manager, options)
                    raise
            else:
                options = editor.sections.options[section]
                updated = dict(options); updated[reference.record] = label
                editor.sections.options[section] = updated
                try: editor.row_event('changeRow', section, row_id, reference)
                except BaseException:
                    editor.sections.options[section] = options
                    raise

    def event(self, event, **values):
        if self.closed: raise UIError('closed')
        if event != 'referenceChoice': self._close_reference_choice()
        if event != 'checkCard': self.list_messages = ()
        if event == 'referenceChoice': self.reference_choice(values['action'])
        elif event == 'checkCard': self.check_card(values['reference'])
        elif event == 'selectCatalog': self.select(values['catalog'])
        elif event == 'filterRecords': self.filter_records(values['query'], values['order'])
        elif event == 'refreshRecords': self.refresh_records()
        elif event == 'create': self.open()
        elif event == 'openCard': self.open(values['reference'])
        elif event == 'page':
            if self.editor is not None or self.view is None: raise UIError('busy')
            self.view.page(values['offset'], values['limit'])
            self.page = (values['offset'], values['limit'])
        elif event in ('change', 'command', 'closeCard', 'addRow', 'deleteRow', 'changeRow'):
            if self.editor is None: raise UIError('closed')
            if event == 'change': self.editor.change(values['control'], values['value'])
            elif event == 'command':
                self.editor.command(values['control'])
                if values['control'] == 'SaveButton':
                    self._refresh_saved_list()
            elif event in ('addRow', 'deleteRow', 'changeRow'): self.editor.row_event(event, **values)
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
                    self.refresh_records()
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
                 'list': self.view.page(*self.page) if self.view is not None and not self.closed else None,
                 'editor': self.editor.snapshot() if self.editor is not None else None,
                 'referenceChoice': self._reference_projection,
                 'listQuery': {'query': self.query, 'order': self.order, 'notice': self.list_notice},
                 'listCheck': {'available': bool(not self.closed and self.editor is None and self.view is not None
                     and any(str(s.identity) == self.selected and s.identity in self._active_forms
                             and s.name == 'Номенклатура' for s in self._inventory())),
                     'messages': [{'text': m.text, 'field': m.field} for m in self.list_messages]}}
        return {'capabilities': {'canCreate': writable, 'canEdit': writable, 'canWrite': writable,
                'referenceEditing': True, 'referenceChoiceLimit': 64, 'referencePickerLimit': 8192, 'lazyReferenceChoice': True, 'referenceRowEditing': True, 'sectionRowLimit': 32, 'actual1CForms': False, 'autoform': True,
                'standardFormWrite': False, 'remoteService': False,
                'importedNameValidation': bool(self._active_forms)}, 'state': state}

    def close(self):
        self._close_reference_choice()
        if not self.closed:
            self.closed = True
            self.context.close()


MAX_SECTION_ROWS = 32


class ReferenceSections:
    """Captured choices; detached runtime rows retain their opaque identities."""
    def __init__(self, owner):
        self.owner = owner
        self.options = {}
        for schema in owner.schema.tabular_sections:
            if len(schema.fields) != 1 or schema.fields[0].kind != 'catalog_ref':
                continue
            field = schema.fields[0]
            current = tuple(str(row.get_member(field.name).reference_uuid)
                for row in owner.object._sections[schema.name.casefold()]._rows)
            try:
                choices = _reference_options(owner.manager._backend, field.target_catalog_id, current)
            except (UIError, BackendError):
                continue
            self.options[schema.name] = choices

    def snapshot(self, obj=None, replacement=None):
        obj = self.owner.object if obj is None else obj
        sections = obj._sections if replacement is None else replacement
        total = sum(len(section._rows) for section in sections.values())
        result = []
        for schema in self.owner.schema.tabular_sections:
            section = sections[schema.name.casefold()]
            choices = self.options.get(schema.name)
            reason = ('section-profile-unsupported' if len(schema.fields) != 1 or schema.fields[0].kind != 'catalog_ref'
                      else 'reference-options-unavailable' if choices is None
                      else 'section-row-limit' if total > MAX_SECTION_ROWS else None)
            item = {'name': schema.name, 'title': schema.name, 'readOnly': reason is not None,
                    'reason': reason, 'rowCount': len(section._rows), 'rows': [],
                    'canAdd': reason is None and total < MAX_SECTION_ROWS}
            if reason is None:
                field = schema.fields[0]
                for index, row in enumerate(section._rows):
                    value = row.get_member(field.name)
                    record = str(value.reference_uuid)
                    item['rows'].append({'id': str(row._identity), 'number': index + 1,
                        'field': {'name': field.name, 'kind': 'catalog_ref',
                            'value': encode_value(CatalogRef(str(field.target_catalog_id), record)),
                            'inputText': record, 'choices': [{'value': key, 'label': label} for key, label in choices.items()],
                            'readOnly': record not in choices, 'lazyChoice': record in choices}})
            result.append(item)
        return result

    def changed(self, event, name, row=None, value=None):
        owner = self.owner
        state = next((item for item in self.snapshot() if item['name'] == name), None)
        if state is None or state['readOnly']:
            raise UIError('invalid_value')
        schema = next(s for s in owner.schema.tabular_sections if s.name == name)
        original = owner.object._sections[name.casefold()]
        candidate = BSLCatalogSection(owner.object, schema, original._stored_rows().rows)
        if event == 'addRow':
            if not state['canAdd']:
                raise UIError('invalid_value')
            candidate.add()
        else:
            current = next((r for r in candidate._rows if str(r._identity) == row), None)
            if current is None:
                raise UIError('invalid_value')
            if event == 'deleteRow':
                candidate.delete(current)
            elif event == 'changeRow':
                field = schema.fields[0]
                choices = self.options[name]
                if (str(current.get_member(field.name).reference_uuid) not in choices
                        or type(value) is not CatalogRef or value.catalog != str(field.target_catalog_id)
                        or value.record not in choices):
                    raise UIError('invalid_value')
                manager = owner.manager._catalogs._manager_by_metadata_uuid(field.target_catalog_id)
                current.set_member(field.name, manager.get_ref(BSLUUID(value.record)))
            else:
                raise UIError('invalid_value')
        sections = dict(owner.object._sections)
        sections[name.casefold()] = candidate
        return sections
