"""Byte-pinned demo list command over one host-owned read snapshot.

This invokes the original server handler, not native managed-form dispatch.
There is no object-form buffer and no persistence operation in this profile.
"""
from hashlib import sha256
import re

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalogs import BSLCatalogObject
from yadinassi.db.catalog.catalog_object_preparation import _ObjectInterpreter
from yadinassi.forms.form_event_simulation import FormEventMessage
from yadinassi.configuration.demos.main_demo_source import product_event_source_digest
from yadinassi.syntax.parser import parse
from yadinassi.types.type_values import type_of
from yadinassi.application.user_messages import UserMessageRecord


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
        routine = next(n for n in program if n.name == 'ПроверитьКарточкуНаСервере')
        vm._logical_side = 'server'
        vm._context_stack = ['server']
        vm.variables['выбор'] = reference
        vm.module_names.update(vm.variables)
        from yadinassi.execution.direct.python_direct_form_events import run_event
        vm.variables[routine.parameters[0].name.casefold()]=reference
        run_event(vm,program,routine,list_source.decode('utf-8-sig'),product=True)
        return tuple(records)
    finally:
        vm.close()
