"""Explicit host-only catalog handler preparation and atomic write coordination.

Not configuration activation, a write hook, a transaction, or native parity.
The caller owns source admission and a disposable candidate: errors/cancellation
can leave candidate changes. Receipt recovery does not execute preparation;
only a confirmed absent outcome permits a validated retry. The BSL execution
profile exposes no backend write operation. The host writer owns persistence.
"""

from .catalogs import BSLCatalogObject
from .catalog_backend import BackendError
from yadinassi.runtime import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

_MAX_SOURCE = 16384
_MAX_STEPS = 16384
_SELF = frozenset(('thisobject', 'этотобъект'))
_ALIASES = frozenset(('code', 'код', 'description', 'наименование',
                      'ref', 'ссылка', 'deletionmark', 'пометкаудаления'))
_METHODS = frozenset(('getobject', 'получитьобъект', 'count', 'количество',
                      'get', 'получить', 'insert', 'вставить',
                      'setdata', 'установитьданные', 'message', 'сообщить'))
_REFERENCE_QUERY_METHODS = frozenset(('unloadcolumn', 'выгрузитьколонку', 'setparameter', 'установитьпараметр',
    'execute', 'выполнить', 'select', 'выбрать', 'next', 'следующий'))
_MESSAGE_FIELDS = frozenset(('text', 'текст', 'field', 'поле'))


class CatalogWriteRefused(ValueError):
    """The original object handler refused a host-coordinated write."""
    def __init__(self, messages):
        super().__init__('catalog preparation: write refused')
        self.messages = tuple(messages)


class _ObjectInterpreter(Interpreter):
    def __init__(self, receiver, sink, write_view=None, *, allow_extensions=False):
        def no_output(value):
            raise ValueError('catalog preparation: plain output forbidden')
        super().__init__(output=no_output, user_message_sink=sink, allow_extensions=allow_extensions)
        self.receiver_object = receiver
        self.write_view = write_view
        schema = receiver._manager._schema
        self.object_names = _ALIASES | {f.name.casefold() for f in schema.fields} | {
            s.name.casefold() for s in schema.tabular_sections}
        if self.object_names & (_SELF | {'отказ'}):
            raise ValueError('catalog preparation: reserved object member')
        self.member_names = self.object_names | _MESSAGE_FIELDS | {
            'linenumber', 'номерстроки'} | {
            f.name.casefold() for s in schema.tabular_sections for f in s.fields}
        self.functions = {name: self.functions[name] for name in (
            'сокрлп', 'стрдлина', 'значениезаполнено', 'строка', 'формат')}
        self.types = {name: self.types[name] for name in (
            'соответствие', 'сообщениепользователю')}
        self.remaining = _MAX_STEPS
        self.text_budget = 1048576

    def _object_name(self, name):
        return (self._has_module_context and name in self.object_names
                and not (self.locals is not None and name in self.locals))


    # Legacy extension point keeps superclass visitor instrumentation.

    # Legacy extension point keeps superclass visitor instrumentation.
    def set_variable(self, name, value):
        if self._object_name(name.casefold()):
            self.receiver_object.set_member(name, value)
        else:
            super().set_variable(name, value)


    # Legacy extension point keeps superclass visitor instrumentation.
    def _new_server_activation(self, *args, **kwargs):
        raise ValueError('catalog preparation: context crossing forbidden')


def validate_catalog_object_source(source, schema):
    _admit_catalog_object_source(source,schema)


def _admit_catalog_object_source(source, schema):
    """Pure conservative admission for the existing bounded preparation VM.

    Every branch is inspected; validation never runs a handler or writes data.
    Runtime receiver/type and writer validation remain authoritative at each Write.
    Direct preparation has its own opt-in scalar/work budget profile; counters
    are per invocation and are not authority cached in this admitted source.
    """
    from dataclasses import fields
    if type(source) is not str or len(source.encode('utf-8')) > _MAX_SOURCE:
        raise ValueError('catalog preparation: source limit')
    program = parse(source)
    if not program or any(type(n) is not ast.Routine or n.is_async or n.is_dual
            or n.execution_context != 'client' or not n.module_context for n in program):
        raise ValueError('catalog preparation: plain routines required')
    entries = [n for n in program if n.name.casefold() == 'передзаписью']
    if (len(entries) != 1 or entries[0].is_function or len(entries[0].parameters) != 1
            or entries[0].parameters[0].by_value or entries[0].parameters[0].default is not None):
        raise ValueError('catalog preparation: BeforeWrite reference parameter required')
    members = _ALIASES | {f.name.casefold() for f in schema.fields} | {s.name.casefold() for s in schema.tabular_sections}
    readable_members = members | {'linenumber','номерстроки'} | {f.name.casefold() for section in schema.tabular_sections for f in section.fields}
    functions = {'сокрлп', 'стрдлина', 'значениезаполнено', 'строка', 'формат'}
    routines = {n.name.casefold() for n in program}
    if len(routines) != len(program) or routines & (members | _SELF | functions):
        raise ValueError('catalog preparation: routine collision')
    allowed = (ast.Routine, ast.Parameter, ast.Literal, ast.Name, ast.Attribute,
        ast.Call, ast.New, ast.Assign, ast.If, ast.Return, ast.ExpressionStatement,
        ast.Binary, ast.Unary, ast.ForEach, ast.While, ast.Continue)
    def inspect(value):
        if isinstance(value, (list, tuple)):
            for item in value: inspect(item)
        elif isinstance(value, ast.Node):
            if type(value) not in allowed:
                raise ValueError('catalog preparation: unsupported node')
            if type(value) is ast.New and value.name.casefold() not in ('соответствие', 'сообщениепользователю', 'запрос', 'query'):
                raise ValueError('catalog preparation: unsupported constructor')
            if type(value) is ast.Attribute and value.name.casefold() not in readable_members | _MESSAGE_FIELDS | _METHODS | _REFERENCE_QUERY_METHODS:
                raise ValueError('catalog preparation: unavailable member')
            if type(value) is ast.Call:
                callee = value.callee
                if type(callee) is ast.Name and callee.name.casefold() not in functions | routines:
                    raise ValueError('catalog preparation: unavailable call')
                if type(callee) is ast.Attribute and callee.name.casefold() not in _METHODS | _REFERENCE_QUERY_METHODS:
                    raise ValueError('catalog preparation: unavailable method')
                if type(callee) not in (ast.Name, ast.Attribute):
                    raise ValueError('catalog preparation: indirect call forbidden')
            for field in fields(value):
                if field.name != 'token': inspect(getattr(value, field.name))
    inspect(program)
    return program


def prepare_catalog_object(source, receiver, *, cancel=False):
    """Call ПередЗаписью on an explicit disposable object; return (cancel, messages).

    Exact source text is provided by the trusted host, never fetched/activated
    from an archive here. Messages are host UserMessageRecord snapshots, not UI
    navigation authority. A false result alone is NOT permission to persist.
    """
    return _prepare_catalog_object(source, receiver, cancel=cancel)


def _prepare_catalog_object(source, receiver, *, cancel=False, write_view=None, prepared=None, _transaction_scope=None):
    if type(receiver) is not BSLCatalogObject or type(cancel) is not bool:
        raise TypeError('catalog preparation: exact object and Boolean required')
    if receiver._pending_write is not None:
        raise BackendError('uncertain_commit')
    if type(source) is not str or len(source.encode('utf-8')) > _MAX_SOURCE:
        raise ValueError('catalog preparation: source limit')
    from yadinassi.execution.execution_policy import current_backend
    if _transaction_scope is not None:_transaction_scope.check()
    if current_backend() == 'python-direct':
        from yadinassi.execution.direct.python_direct_catalog_preparation import prepared_validator
        prepared=prepared_validator(receiver._manager,source,prepared=prepared)
        program=prepared._program
    else:
        program = parse(source)
        if not program or any(type(n) is not ast.Routine or n.is_async or n.is_dual
                              or n.execution_context != 'client' or not n.module_context
                              for n in program):
            raise ValueError('catalog preparation: plain routines required')
        entries = [n for n in program if n.name.casefold() == 'передзаписью']
        if (len(entries) != 1 or entries[0].is_function
                or len(entries[0].parameters) != 1 or entries[0].parameters[0].by_value
                or entries[0].parameters[0].default is not None):
            raise ValueError('catalog preparation: BeforeWrite reference parameter required')
    records = []
    def sink(record):
        if len(records) >= 128:
            raise ValueError('catalog preparation: message limit')
        records.append(record)
    vm = _ObjectInterpreter(receiver, sink, write_view)
    vm._direct_transaction_preparation_scope=_transaction_scope
    try:
        if _transaction_scope is not None:
            _transaction_scope.check()
        if any(n.name.casefold() in vm.object_names | _SELF | set(vm.functions)
               for n in program):
            raise ValueError('catalog preparation: routine collision')
        from yadinassi.execution.direct.python_direct_catalog_preparation import run_catalog_preparation
        result = run_catalog_preparation(source, program, vm, cancel, prepared=prepared)
        if type(result) is not bool:
            raise ValueError('catalog preparation: Boolean cancellation required')
        return result, tuple(records)
    finally:
        vm.close()


def write_prepared_catalog_object(source, receiver, *, cancel=False):
    """Prepare and durably write one disposable object under the writer lock.

    The host selects the source; this does not activate archived object modules.
    GetObject reads use the same transaction as the write. Refusal/errors can
    leave changes in this disposable receiver, never durable success. A pending
    outcome is resolved first without BSL. Only proven absence permits another
    transaction, which revalidates the frozen intent using its retained source.
    """
    if type(receiver) is not BSLCatalogObject or type(cancel) is not bool:
        raise TypeError('catalog preparation: exact object and Boolean required')
    if type(source) is not str or len(source.encode('utf-8')) > _MAX_SOURCE:
        raise ValueError('catalog preparation: source limit')
    return receiver._write(preparation=(source, cancel))
