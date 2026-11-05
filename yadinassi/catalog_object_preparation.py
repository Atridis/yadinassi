"""Explicit host-only direct catalog handler preparation.

Not configuration activation, a write hook, a transaction, or native parity.
The caller owns source admission and a disposable candidate: errors/cancellation
can leave candidate changes. Never repeat preparation to recover an uncertain
commit. No backend write operation is exposed by this execution profile.
"""
from decimal import Decimal

from .catalogs import BSLCatalogObject
from .catalog_backend import BackendError
from .runtime import Interpreter
from .syntax import ast
from .syntax.parser import parse
from .values import Reference, HostFunction

_MAX_SOURCE = 16384
_MAX_STEPS = 16384
_SELF = frozenset(('thisobject', 'этотобъект'))
_ALIASES = frozenset(('code', 'код', 'description', 'наименование',
                      'ref', 'ссылка', 'deletionmark', 'пометкаудаления'))
_METHODS = frozenset(('getobject', 'получитьобъект', 'count', 'количество',
                      'get', 'получить', 'insert', 'вставить',
                      'setdata', 'установитьданные', 'message', 'сообщить'))
_MESSAGE_FIELDS = frozenset(('text', 'текст', 'field', 'поле'))


class _ObjectInterpreter(Interpreter):
    def __init__(self, receiver, sink):
        def no_output(value):
            raise ValueError('catalog preparation: plain output forbidden')
        super().__init__(output=no_output, user_message_sink=sink)
        self.receiver_object = receiver
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

    def _visit(self, node):
        self.remaining -= 1
        if self.remaining < 0 or type(node) not in (
                ast.Routine, ast.Literal, ast.Name, ast.Attribute, ast.Call,
                ast.New, ast.Assign, ast.If, ast.Return, ast.ExpressionStatement,
                ast.Binary, ast.Unary, ast.ForEach, ast.Continue):
            raise ValueError('catalog preparation: unsupported node or budget')
        result = (yield from super()._visit(node))
        if isinstance(result, HostFunction) and not (
                type(node) is ast.Name
                and self.functions.get(node.name.casefold()) is result):
            raise ValueError('catalog preparation: captured method forbidden')
        if type(result) is Decimal and (not result.is_finite()
                or result.__sizeof__() > 256 or abs(result.adjusted()) > 64):
            raise ValueError('catalog preparation: numeric budget')
        if type(result) is str:
            self.text_budget -= len(result.encode("utf-8"))
            if len(result) > 65536 or self.text_budget < 0:
                raise ValueError("catalog preparation: text budget")
        return result

    def visit_Name(self, node):
        name = node.name.casefold()
        if self._object_name(name):
            return self.receiver_object.get_member(name)
        if name in _SELF:
            return self.receiver_object
        if not ((self.locals is not None and name in self.locals)
                or name in self.variables or name in self.functions):
            raise ValueError('catalog preparation: unavailable name')
        return super().visit_Name(node)

    def call(self, node, *, require_value):
        callee = self.ungroup(node.callee)
        if type(callee) is ast.Attribute and callee.name.casefold() not in _METHODS:
            raise ValueError('catalog preparation: unavailable method')
        return (yield from super().call(node, require_value=require_value))

    def visit_Attribute(self, node):
        if node.name.casefold() not in self.member_names | _METHODS:
            raise ValueError('catalog preparation: unavailable member')
        return (yield from super().visit_Attribute(node))

    def set_variable(self, name, value):
        if self._object_name(name.casefold()):
            self.receiver_object.set_member(name, value)
        else:
            super().set_variable(name, value)

    def argument(self, node):
        target = self.ungroup(node)
        if type(target) is ast.Name and self._object_name(target.name.casefold()):
            return Reference(lambda: self.receiver_object.get_member(target.name),
                             lambda value: self.receiver_object.set_member(target.name, value))
        return (yield from super().argument(node))

    def visit_Assign(self, node):
        if type(node.target) is ast.Attribute and node.target.name.casefold() not in self.member_names:
            raise ValueError('catalog preparation: unavailable assignment')
        return (yield from super().visit_Assign(node))

    def _new_server_activation(self, *args, **kwargs):
        raise ValueError('catalog preparation: context crossing forbidden')


def prepare_catalog_object(source, receiver, *, cancel=False):
    """Call ПередЗаписью on an explicit disposable object; return (cancel, messages).

    Exact source text is provided by the trusted host, never fetched/activated
    from an archive here. Messages are host UserMessageRecord snapshots, not UI
    navigation authority. A false result alone is NOT permission to persist.
    """
    if type(receiver) is not BSLCatalogObject or type(cancel) is not bool:
        raise TypeError('catalog preparation: exact object and Boolean required')
    if receiver._pending_write is not None:
        raise BackendError('uncertain_commit')
    if type(source) is not str or len(source.encode('utf-8')) > _MAX_SOURCE:
        raise ValueError('catalog preparation: source limit')
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
    vm = _ObjectInterpreter(receiver, sink)
    try:
        if any(n.name.casefold() in vm.object_names | _SELF | set(vm.functions)
               for n in program):
            raise ValueError('catalog preparation: routine collision')
        vm.execute_program(program)
        vm.variables['отказ'] = cancel
        vm.execute('ПередЗаписью(Отказ);')
        result = vm.variables['отказ']
        if type(result) is not bool:
            raise ValueError('catalog preparation: Boolean cancellation required')
        return result, tuple(records)
    finally:
        vm.close()
