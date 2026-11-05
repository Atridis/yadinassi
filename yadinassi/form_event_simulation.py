"""Explicit local direct-handler simulation, never configuration activation.

The offline runner accepts exact bytes, identity commitments and scalar inputs.
The verified consumer obtains its bytes from the host's exact inert backend.
Neither accepts caller analysis, live receivers or execution callbacks.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from .catalog_backend import (BackendError, CatalogFormSource,
                              ConfigurationSourceIdentity, FieldSchema)
from .form_data import ScalarFormData, ScalarFormField, ScalarFormSnapshot
from .form_module_analysis import FormModuleBinding, analyze_form_module, _parse
from .runtime import Interpreter
from .syntax import ast
from .user_messages import UserMessageRecord


@dataclass(frozen=True, slots=True)
class FormEventMessage:
    text: str
    field: str


@dataclass(frozen=True, slots=True)
class FormEventResult:
    snapshot: ScalarFormSnapshot
    cancel: bool
    messages: tuple
    native_parity: bool = False


@dataclass(frozen=True, slots=True)
class FormDraftSnapshot:
    revision: int
    baseline: tuple
    values: tuple
    messages: tuple
    native_parity: bool = False


@dataclass(frozen=True, slots=True)
class FormSavePreparation:
    """Informational detached image, not persistence authority or a commit token."""
    revision: int
    candidate: tuple
    cancel: bool
    messages: tuple
    native_parity: bool = False


class _EventInterpreter(Interpreter):
    """Defense in depth for the closed admitted profile, not a general sandbox."""
    def __init__(self, sink):
        def no_output(value):
            raise ValueError('form event: plain output forbidden')
        super().__init__(output=no_output, user_message_sink=sink)
        self.functions = {name: self.functions[name] for name in ('сокрлп', 'стрдлина')}
        self.types = {'сообщениепользователю': self.types['сообщениепользователю']}
        self._remaining = 256

    def _visit(self, node):
        self._remaining -= 1
        if self._remaining < 0 or type(node) not in (
                ast.Literal, ast.Name, ast.Attribute, ast.Call, ast.New,
                ast.Assign, ast.If, ast.Return, ast.ExpressionStatement, ast.Binary):
            raise ValueError('form event: execution budget or node')
        return (yield from super()._visit(node))

    def visit_Name(self, node):
        name = node.name.casefold()
        if not ((self.locals is not None and name in self.locals)
                or name in self.variables or name in self.functions):
            raise ValueError('form event: unavailable name')
        # Never fall through to Interpreter's built-in global namespaces.
        return super().visit_Name(node)


def _admit(source, binding, catalog_xml, form_xml, definition_xml):
    if type(binding) is not FormModuleBinding:
        raise ValueError('form event: binding required')
    # Check names before constructing canonical inert metadata paths.
    from .form_module_analysis import _name
    _name(binding.catalog_name); _name(binding.form_name)
    base = f'Catalogs/{binding.catalog_name}/Forms/{binding.form_name}'
    admitted = analyze_form_module(source, binding, catalog_xml=catalog_xml,
        form_xml=form_xml, definition_xml=definition_xml,
        catalog_path=f'Catalogs/{binding.catalog_name}.xml', form_path=base + '.xml',
        definition_path=base + '/Ext/Form.xml', module_path=base + '/Ext/Form/Module.bsl')
    # No registered routines, but reject ambiguous symbols as an explicit extra
    # execution admission rule instead of relying on static-description approval.
    reserved = {'объект', 'текущийобъект', 'элемент', 'отказ', 'параметрызаписи',
                'сообщение', 'сокрлп', 'стрдлина', 'сообщениепользователю'}
    names = tuple(e.handler.casefold() for e in admitted.events)
    if len(set(names)) != 2 or any(n in reserved for n in names):
        raise ValueError('form event: handler name collision')
    return admitted


def _receiver(admitted, code, description, deletion_mark):
    fields = (
        ScalarFormField(FieldSchema(UUID(int=1), 'Code', 'string',
                                   (admitted.fields[0].maximum_length,)), ('Код',), False),
        ScalarFormField(FieldSchema(UUID(int=2), 'Description', 'string',
                                   (admitted.fields[1].maximum_length,)), ('Наименование',)),
        ScalarFormField(FieldSchema(UUID(int=3), 'DeletionMark', 'boolean', ()),
                        ('ПометкаУдаления',), False))
    return ScalarFormData(fields, (('Code', code), ('Description', description),
        ('DeletionMark', deletion_mark)), root='Объект')


def simulate_form_event(source, binding, *, catalog_xml, form_xml, definition_xml,
                        event, code, description, deletion_mark=False, cancel=False):
    """Fresh admission and private execution of one original handler per call.

    Caller authenticates storage/provenance. Hash commitments are not authentication.
    Returns a detached candidate even on cancellation; never adopts or writes it.
    Any failure raises, returning neither candidate nor partial messages. No retry.
    """
    admitted = _admit(source, binding, catalog_xml, form_xml, definition_xml)
    if type(event) is not str or event not in ('OnChange', 'BeforeWriteAtServer'):
        raise ValueError('form event: unsupported event')
    if type(cancel) is not bool or type(deletion_mark) is not bool:
        raise TypeError('form event: exact Boolean required')
    if event == 'OnChange' and cancel:
        raise ValueError('form event: cancellation belongs to server event')
    receiver = _receiver(admitted, code, description, deletion_mark)
    # Reparse the same immutable bytes privately; never take an AST from callers.
    program, _ = _parse(source)
    routine = program[0 if event == 'OnChange' else 1]
    messages = []
    def sink(record):
        if (type(record) is not UserMessageRecord or type(record.text) is not str
                or not 1 <= len(record.text) <= 1024 or '\x00' in record.text
                or type(record.field) is not str or record.field != 'Объект.Наименование'
                or type(record.data_path) is not str or record.data_path != '' or record.data_key is not None
                or record.target_id is not None or len(messages) >= 1):
            raise ValueError('form event: message outside scalar profile')
        messages.append(FormEventMessage(record.text, record.field))
    vm = _EventInterpreter(sink)
    try:
        # Same-side direct procedure invocation: no managed-form dispatch and no
        # client/server marshalling. Parameters are private named storage only.
        vm._logical_side = routine.execution_context
        vm._context_stack = [routine.execution_context]
        vm.variables = {'объект': receiver, 'элемент': None, 'отказ': cancel,
                        'текущийобъект': receiver, 'параметрызаписи': None}
        vm.module_names = set(vm.variables)
        arguments = [ast.Name(p.token, p.name) for p in routine.parameters]
        vm._scheduler.run_inline(vm.call_routine(routine, arguments, vm, require_value=False))
        if type(vm.variables['отказ']) is not bool:
            raise ValueError('form event: invalid cancellation')
        return FormEventResult(receiver.snapshot(), vm.variables['отказ'], tuple(messages))
    finally:
        vm.close()


class FormDraftSession:
    """Single-owner local draft over one exact admitted source/metadata binding.

    Construction validates the initial scalar image without running a handler.
    Only successful Description changes replace the complete immutable state.
    Preparation never changes it, even on refusal. There is no persistence API,
    external callback or native managed-form integration. Python hosts are trusted.
    """
    __slots__ = ('_source', '_binding', '_catalog_xml', '_form_xml',
                 '_definition_xml', '_state')

    def __init__(self, source, binding, *, catalog_xml, form_xml, definition_xml,
                 code, description, deletion_mark=False):
        admitted = _admit(source, binding, catalog_xml, form_xml, definition_xml)
        values = _receiver(admitted, code, description, deletion_mark).snapshot().values
        self._source, self._binding = source, binding
        self._catalog_xml, self._form_xml = catalog_xml, form_xml
        self._definition_xml = definition_xml
        self._state = FormDraftSnapshot(0, values, values, ())

    @property
    def binding(self):
        """Identity commitment only; the caller must authenticate its current owner."""
        return self._binding

    def snapshot(self):
        return self._state

    def _require_revision(self, revision):
        if type(revision) is not int or revision != self._state.revision:
            raise ValueError('form draft: stale revision')

    def _run(self, event, description, *, cancel=False):
        values = dict(self._state.values)
        return simulate_form_event(self._source, self._binding,
            catalog_xml=self._catalog_xml, form_xml=self._form_xml,
            definition_xml=self._definition_xml, event=event,
            code=values['Code'], description=description,
            deletion_mark=values['DeletionMark'], cancel=cancel)

    def _change_candidate(self, value, *, revision):
        self._require_revision(revision)
        result = self._run('OnChange', value)
        # Private receiver revisions count BSL setters, not host input events.
        return FormDraftSnapshot(revision + 1, self._state.baseline,
                                 result.snapshot.values, result.messages)

    def change_description(self, value, *, revision):
        state = self._change_candidate(value, revision=revision)
        self._state = state
        return state

    def prepare_save(self, *, revision, cancel=False):
        self._require_revision(revision)
        result = self._run('BeforeWriteAtServer', dict(self._state.values)['Description'],
                           cancel=cancel)
        return FormSavePreparation(revision, result.snapshot.values,
                                   result.cancel, result.messages)


def _stored_binding(record, database_id, catalog_id):
    """Consistency checks, not authentication of arbitrary Python-supplied DTOs."""
    if type(record) is not CatalogFormSource or type(record.identity) is not ConfigurationSourceIdentity:
        raise BackendError('invalid_input')
    identity = record.identity
    ids = (identity.database_id, identity.configuration_id,
           identity.catalog_id, identity.form_id)
    if (any(type(value) is not UUID or not value.int for value in ids)
            or len(set(ids)) != 4 or identity.database_id != database_id
            or identity.catalog_id != catalog_id
            or type(identity.generation) is not int or not 1 <= identity.generation < 2**63
            or type(identity.manifest_sha256) is not str or len(identity.manifest_sha256) != 64
            or any(c not in '0123456789abcdef' for c in identity.manifest_sha256)):
        raise BackendError('invalid_input')
    strings = (record.catalog_name, record.form_name, record.default_object_form,
               record.catalog_path, record.form_path, record.definition_path, record.module_path)
    raw = (record.module_source, record.catalog_xml, record.form_xml, record.definition_xml)
    if (any(type(value) is not str for value in strings)
            or any(type(value) is not bytes for value in (*raw, record.configuration_xml))
            or type(record.module_present) is not bool):
        raise BackendError('invalid_input')
    from .form_module_analysis import _name
    _name(record.catalog_name); _name(record.form_name)
    base = f'Catalogs/{record.catalog_name}/Forms/{record.form_name}'
    if ((record.catalog_path, record.form_path, record.definition_path, record.module_path) != (
            f'Catalogs/{record.catalog_name}.xml', base + '.xml',
            base + '/Ext/Form.xml', base + '/Ext/Form/Module.bsl')
            or record.default_object_form != f'Catalog.{record.catalog_name}.Form.{record.form_name}'):
        raise BackendError('invalid_input')
    if not record.module_present or not record.module_source:
        raise BackendError('unsupported')
    return FormModuleBinding(identity.database_id, identity.configuration_id,
        identity.generation, identity.catalog_id, record.catalog_name,
        identity.form_id, record.form_name, *(sha256(value).hexdigest() for value in raw))


class VerifiedFormDraftSession:
    """Host-only source-bound draft; no renderer, write or persistence authority.

    The host owns the exact inert backend and initial scalar image. Source reads
    close before BSL, and the second read precedes the sole live adoption. A
    schema change permanently locks this consumer without discarding its state.
    Single-owner synchronous use is required; Python hosts remain trusted.
    """
    __slots__ = ('_backend', '_catalog_id', '_record', '_session', '_stale')

    def __init__(self, backend, catalog_id, *, code, description, deletion_mark=False):
        from .sqlite_catalog import SQLiteCatalogBackend
        if type(backend) is not SQLiteCatalogBackend:
            raise TypeError('verified form draft: exact backend required')
        if type(catalog_id) is not UUID or not catalog_id.int:
            raise BackendError('invalid_input')
        if type(code) is not str or type(description) is not str or type(deletion_mark) is not bool:
            raise TypeError('verified form draft: exact scalar types required')
        record = backend.read_form_source(catalog_id)
        binding = _stored_binding(record, backend.database_id, catalog_id)
        session = FormDraftSession(record.module_source, binding,
            catalog_xml=record.catalog_xml, form_xml=record.form_xml,
            definition_xml=record.definition_xml, code=code, description=description,
            deletion_mark=deletion_mark)
        self._backend, self._catalog_id, self._record = backend, catalog_id, record
        self._session, self._stale = session, False

    @property
    def stale(self):
        """Sticky source invalidation; only an explicit new consumer can reopen."""
        return self._stale

    def snapshot(self):
        """Only detached scalars/messages/local revision, never source authority."""
        return self._session.snapshot()

    def _require_revision(self, revision):
        # Reject stale or inexact local revisions without touching storage.
        self._session._require_revision(revision)
        if self._stale:
            raise BackendError('schema_changed')

    def _verify_source(self):
        try:
            record = self._backend.read_form_source(self._catalog_id, expected=self._record.identity)
            _stored_binding(record, self._backend.database_id, self._catalog_id)
            # The full record also catches an inconsistent trusted-host adapter;
            # exact DTO checks above do not authenticate a hostile Python host.
            if record != self._record:
                raise BackendError('schema_changed')
        except BackendError as error:
            if error.code == 'schema_changed':
                self._stale = True
            raise

    def change_description(self, value, *, revision):
        self._require_revision(revision)
        if type(value) is not str:
            raise TypeError('verified form draft: exact string required')
        self._verify_source()
        candidate = self._session._change_candidate(value, revision=revision)
        self._verify_source()
        self._require_revision(revision)
        self._session._state = candidate
        return candidate

    def prepare_save(self, *, revision, cancel=False):
        self._require_revision(revision)
        if type(cancel) is not bool:
            raise TypeError('verified form draft: exact Boolean required')
        self._verify_source()
        candidate = self._session.prepare_save(revision=revision, cancel=cancel)
        self._verify_source()
        self._require_revision(revision)
        return candidate
