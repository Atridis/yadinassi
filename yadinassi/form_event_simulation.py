"""Explicit local direct-handler simulation, never configuration activation.

Only exact bytes, identity commitments and immutable scalar inputs cross the host
boundary. No public analysis object, live receiver, backend or callback is accepted.
"""
from dataclasses import dataclass
from uuid import UUID

from .catalog_backend import FieldSchema
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


def simulate_form_event(source, binding, *, catalog_xml, form_xml, definition_xml,
                        event, code, description, deletion_mark=False, cancel=False):
    """Fresh admission and private execution of one original handler per call.

    Caller authenticates storage/provenance. Hash commitments are not authentication.
    Returns a detached candidate even on cancellation; never adopts or writes it.
    Any failure raises, returning neither candidate nor partial messages. No retry.
    """
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
    if type(event) is not str or event not in ('OnChange', 'BeforeWriteAtServer'):
        raise ValueError('form event: unsupported event')
    if type(cancel) is not bool or type(deletion_mark) is not bool:
        raise TypeError('form event: exact Boolean required')
    if event == 'OnChange' and cancel:
        raise ValueError('form event: cancellation belongs to server event')
    # No registered routines, but reject ambiguous symbols as an explicit extra
    # execution admission rule instead of relying on static-description approval.
    reserved = {'объект', 'текущийобъект', 'элемент', 'отказ', 'параметрызаписи',
                'сообщение', 'сокрлп', 'стрдлина', 'сообщениепользователю'}
    names = tuple(e.handler.casefold() for e in admitted.events)
    if len(set(names)) != 2 or any(n in reserved for n in names):
        raise ValueError('form event: handler name collision')
    fields = (
        ScalarFormField(FieldSchema(UUID(int=1), 'Code', 'string',
                                   (admitted.fields[0].maximum_length,)), ('Код',), False),
        ScalarFormField(FieldSchema(UUID(int=2), 'Description', 'string',
                                   (admitted.fields[1].maximum_length,)), ('Наименование',)),
        ScalarFormField(FieldSchema(UUID(int=3), 'DeletionMark', 'boolean', ()),
                        ('ПометкаУдаления',), False))
    receiver = ScalarFormData(fields, (('Code', code), ('Description', description),
        ('DeletionMark', deletion_mark)), root='Объект')
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
