"""Byte-pinned demo list command over one host-owned read snapshot.

This invokes the original server handler, not native managed-form dispatch.
There is no object-form buffer and no persistence operation in this profile.
"""
from hashlib import sha256
import re

from yadinassi.execution.owned_syntax import syntax_kind
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalogs import BSLCatalogObject
from yadinassi.db.catalog.catalog_object_preparation import _ObjectInterpreter
from yadinassi.forms.form_event_simulation import FormEventMessage
from yadinassi.configuration.demos.main_demo_source import product_event_source_digest
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi.types.type_values import type_of
from yadinassi.application.user_messages import UserMessageRecord
from yadinassi.types.values import Reference


class ListInterpreter(_ObjectInterpreter):
    def __init__(self, receiver, sink, view, manager, message, object_source):
        super().__init__(receiver, sink, view)
        self._list_manager = manager
        self._list_sink = sink
        self._list_view = view
        self._list_object_source = object_source
        self._register_platform_function('Тип', manager._catalogs.type_by_name)
        self._register_platform_function('ТипЗнч', type_of)
        self._register_platform_function('Сообщить', message, returns_value=False)

    def _object_name(self, name):
        return False

    def call(self, node, *, require_value, _evaluation=None):
        callee = self.ungroup(node.callee)
        if syntax_kind(callee) is ast.Attribute and callee.name.casefold() == 'проверитьданные':
            obj = yield from (_evaluation.receiver if _evaluation is not None else self.receiver)(callee.object)
            if (require_value or len(node.arguments) != 1 or type(obj) is not BSLCatalogObject
                    or obj._manager is not self._list_manager or obj.is_new()
                    or sum(len(s._rows) for s in obj._sections.values()) > 32):
                raise ValueError('product list: saved bounded product required')
            argument = yield from (_evaluation.argument if _evaluation is not None else self.argument)(node.arguments[0])
            if not isinstance(argument, Reference) or type(argument.get()) is not bool:
                raise ValueError('product list: Boolean reference required')
            child = _ObjectInterpreter(obj, self._list_sink, self._list_view)
            try:
                child.execute_program(parse(self._list_object_source.decode('utf-8-sig')))
                child.variables['отказ'] = argument.get()
                child.execute('ПроверитьДанные(Отказ);')
                if type(child.variables['отказ']) is not bool:
                    raise ValueError('product list: Boolean result required')
                argument.set(child.variables['отказ'])
            finally:
                child.close()
            return None
        return (yield from super().call(node, require_value=require_value, _evaluation=_evaluation))


def check_product_list(manager, reference, view, list_source, object_source):
    base = 'Catalogs/Номенклатура/'
    for source, path in ((list_source, base + 'Forms/ФормаСписка/Ext/Form/Module.bsl'),
                         (object_source, base + 'Ext/ObjectModule.bsl')):
        if type(source) is not bytes or sha256(source).hexdigest() != product_event_source_digest(manager._backend, path):
            raise BackendError('schema_changed')
    if (manager._schema.name != 'Номенклатура'
            or view.catalog_schema(manager._schema.identity) != manager._schema
            or view.database_id != manager._catalogs._metadata._database_id
            or view.configuration_generation != manager._catalogs._metadata._generation):
        raise BackendError('schema_changed')
    receiver = BSLCatalogObject(manager)
    records = []

    def message(text, field=''):
        if (type(text) is not str or not 1 <= len(text) <= 1024 or '\x00' in text
                or type(field) is not str or len(records) >= 128
                or (field and re.fullmatch(r'Наименование|ВидНоменклатуры|Склады(?:\[(?:[0-9]{1,2})?\]\.Склад)?', field) is None)):
            raise ValueError('product list: bounded diagnostic required')
        records.append(FormEventMessage(text, field))

    def sink(record):
        if type(record) is not UserMessageRecord:
            raise ValueError('product list: diagnostic required')
        message(record.text, record.field)

    vm = ListInterpreter(receiver, sink, view, manager, message, object_source)
    try:
        program = parse(list_source.decode('utf-8-sig'))
        if vm.execution_backend!='python-direct':vm.execute_program(program)
        routine = next(n for n in program if n.name == 'ПроверитьКарточкуНаСервере')
        vm._logical_side = 'server'
        vm._context_stack = ['server']
        vm.variables['выбор'] = reference
        vm.module_names.update(vm.variables)
        if vm.execution_backend=='python-direct':
            from yadinassi.execution.direct.python_direct_form_events import run_event
            vm.variables[routine.parameters[0].name.casefold()]=reference
            run_event(vm,program,routine,list_source.decode('utf-8-sig'),product=True)
        else:
            vm._scheduler.run_inline(vm.call_routine(routine,
                [ast.Name(routine.parameters[0].token, 'выбор')], vm, require_value=False))
        return tuple(records)
    finally:
        vm.close()
