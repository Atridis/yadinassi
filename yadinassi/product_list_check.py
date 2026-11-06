"""Byte-pinned demo list command over one host-owned read snapshot.

This invokes the original server handler, not native managed-form dispatch.
There is no object-form buffer and no persistence operation in this profile.
"""
from hashlib import sha256
import re

from .catalog_backend import BackendError
from .catalogs import BSLCatalogObject
from .catalog_object_preparation import _ObjectInterpreter
from .form_event_simulation import FormEventMessage
from .configuration_xml import _DEMO_KINDS_SOURCE_SHA256
from .syntax import ast
from .syntax.parser import parse
from .type_values import type_of
from .user_messages import UserMessageRecord
from .values import Reference


def check_product_list(manager, reference, view, list_source, object_source):
    base = 'Catalogs/Номенклатура/'
    for source, path in ((list_source, base + 'Forms/ФормаСписка/Ext/Form/Module.bsl'),
                         (object_source, base + 'Ext/ObjectModule.bsl')):
        if type(source) is not bytes or sha256(source).hexdigest() != _DEMO_KINDS_SOURCE_SHA256[path]:
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

    class ListInterpreter(_ObjectInterpreter):
        def __init__(self):
            super().__init__(receiver, sink, view)
            self.register_function('Тип', manager._catalogs.type_by_name)
            self.register_function('ТипЗнч', type_of)
            self.register_function('Сообщить', message, returns_value=False)

        def _object_name(self, name):
            return False

        def call(self, node, *, require_value):
            callee = self.ungroup(node.callee)
            if type(callee) is ast.Attribute and callee.name.casefold() == 'проверитьданные':
                obj = yield from self.receiver(callee.object)
                if (require_value or len(node.arguments) != 1 or type(obj) is not BSLCatalogObject
                        or obj._manager is not manager or obj.is_new()
                        or sum(len(s._rows) for s in obj._sections.values()) > 32):
                    raise ValueError('product list: saved bounded product required')
                argument = yield from self.argument(node.arguments[0])
                if not isinstance(argument, Reference) or type(argument.get()) is not bool:
                    raise ValueError('product list: Boolean reference required')
                child = _ObjectInterpreter(obj, sink, view)
                try:
                    child.execute_program(parse(object_source.decode('utf-8-sig')))
                    child.variables['отказ'] = argument.get()
                    child.execute('ПроверитьДанные(Отказ);')
                    if type(child.variables['отказ']) is not bool:
                        raise ValueError('product list: Boolean result required')
                    argument.set(child.variables['отказ'])
                finally:
                    child.close()
                return None
            return (yield from super().call(node, require_value=require_value))

    vm = ListInterpreter()
    try:
        program = parse(list_source.decode('utf-8-sig'))
        vm.execute_program(program)
        routine = next(n for n in program if n.name == 'ПроверитьКарточкуНаСервере')
        vm._logical_side = 'server'
        vm._context_stack = ['server']
        vm.variables['выбор'] = reference
        vm.module_names.update(vm.variables)
        vm._scheduler.run_inline(vm.call_routine(routine,
            [ast.Name(routine.parameters[0].token, 'выбор')], vm, require_value=False))
        return tuple(records)
    finally:
        vm.close()
