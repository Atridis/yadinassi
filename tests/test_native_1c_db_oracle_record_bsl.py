"""Execute metadata-only BSL against synthetic tables, never native proof.

The actual helper is unmodified. Only the storage API and native ValueTable
column type declarations are controlled inputs. No production runtime support,
row bytes, real database, Docker, native command, or fixture path is involved.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.parser import parse
from yadinassi.structures import BSLStructure
from yadinassi.value_tables import BSLValueTableRow
from yadinassi.values import BSLArray, BSLType, HostFunction
from test_native_async_error_transport import json_subset

MODULES = ROOT / 'scripts/native_1c_db_oracle/modules'
TARGET = 'Справочник.NativeOracleItems'
ROOT_COLUMNS = ('ИмяТаблицыХранения', 'ИмяТаблицы', 'Метаданные', 'Поля')
FIELD_COLUMNS = ('ИмяПоляХранения', 'ИмяПоля', 'Метаданные', 'ТипПоля')
_DEFAULT = object()


def routine(text, name, procedure=False):
    start = ('Процедура ' if procedure else 'Функция ') + name + '('
    end = 'КонецПроцедуры' if procedure else 'КонецФункции'
    assert text.count(start) == 1
    begin = text.index(start)
    return text[begin:text.index(end, begin)] + end


def server():
    return (MODULES / 'NativeOracleServer.bsl').read_text(encoding='utf-8')


def helper_source():
    text = server()
    return (routine(text, 'NativeИменаКолонка', True) + '\n' +
            text[text.index('// Metadata-only observation,'):text.index('// End metadata-only observation.')])


def compact(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def projection():
    return {'schema': 1, 'target': TARGET, 'table': {
        'storage_name': 'Physical', 'logical_name': 'Справочник.NativeOracleItems',
        'metadata_name': 'Справочник.NativeOracleItems', 'fields': [{
            'storage_name': 'Field', 'logical_name': 'Payload',
            'metadata_name': 'Справочник.NativeOracleItems.Реквизит.Payload', 'type_text': 'Строка(32)'}]}}


SETUP = '''
ТестоваяТаблица = Новый ТаблицаЗначений;
ТестоваяТаблица.Колонки.Добавить("ИмяТаблицыХранения", Новый ОписаниеТипов("Строка"));
ТестоваяТаблица.Колонки.Добавить("ИмяТаблицы", Новый ОписаниеТипов("Строка"));
ТестоваяТаблица.Колонки.Добавить("Метаданные", Новый ОписаниеТипов("Строка"));
ТестоваяТаблица.Колонки.Добавить("Поля");
ТестоваяТаблица.Колонки.Добавить("Индексы");
ТестоваяТаблица.Колонки.Добавить("Назначение");
ТестоваяТаблица.Колонки.Добавить("PrivateScalar");
СтрокаТеста = ТестоваяТаблица.Добавить();
СтрокаТеста.ИмяТаблицыХранения = "Physical";
СтрокаТеста.ИмяТаблицы = "Справочник.NativeOracleItems";
СтрокаТеста.Метаданные = "Справочник.NativeOracleItems";
Вложенная = Новый ТаблицаЗначений;
Вложенная.Колонки.Добавить("ИмяПоляХранения", Новый ОписаниеТипов("Строка"));
Вложенная.Колонки.Добавить("ИмяПоля", Новый ОписаниеТипов("Строка"));
Вложенная.Колонки.Добавить("Метаданные", Новый ОписаниеТипов("Строка"));
Вложенная.Колонки.Добавить("ТипПоля", Новый ОписаниеТипов("Строка"));
Вложенная.Колонки.Добавить("PrivateScalar");
ПолеТеста = Вложенная.Добавить();
ПолеТеста.ИмяПоляХранения = "Field";
ПолеТеста.ИмяПоля = "Payload";
ПолеТеста.Метаданные = "Справочник.NativeOracleItems.Реквизит.Payload";
ПолеТеста.ТипПоля = "Строка(32)";
СтрокаТеста.Поля = Вложенная;
'''


class Poison:
    def __str__(self):
        raise AssertionError('Private value must not be rendered')


def set_cell(table, row, column, value):
    # Bypass native-looking typed-column coercion to exercise actual type checks.
    table.rows[row].cells[table.columns.find(column)] = value


class Probe:
    def __init__(self):
        self.vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
        self.vm.execute(SETUP, source='synthetic-UTF-8-value-tables')
        self.root = self.vm.execute('ТестоваяТаблица')
        self.fields = self.vm.execute('Вложенная')
        object.__setattr__(self.root.columns.find('Поля').value_type, 'types', (BSLType.VALUE_TABLE,))
        for name in ('Индексы', 'Назначение', 'PrivateScalar'):
            set_cell(self.root, 0, name, Poison())
        set_cell(self.fields, 0, 'PrivateScalar', Poison())
        self.calls = []; self.reads = []; self.violations = []
        self.vm.execute(helper_source(), source='actual-metadata-only-BSL-helper')
        self.vm.execute('Контекст = Новый Структура("phase", "dispatch");')

    def run(self, *, returned=_DEFAULT, reject=False):
        def get_structure(selector, dbms_names):
            self.calls.append((list(selector), dbms_names))
            if reject:
                raise ValueError('Synthetic private API error, never exported')
            return self.root if returned is _DEFAULT else returned

        original = BSLValueTableRow.get_member
        def guarded(row, name):
            allowed = ROOT_COLUMNS if row.table is self.root else FIELD_COLUMNS
            self.reads.append((row.table is self.root, name))
            if name not in allowed:
                self.violations.append(name)
                raise AssertionError('Private/unreviewed cell access')
            return original(row, name)

        self.vm.register_function('ПолучитьСтруктуруХраненияБазыДанных', get_structure)
        with mock.patch.object(BSLValueTableRow, 'get_member', guarded):
            self.vm.execute('Поймано = Ложь; Попытка Проекция = NativeМетаданныеЗаписи(Контекст); '
                            'Исключение Поймано = Истина; КонецПопытки;', source='synthetic-call')
        assert self.calls == [([TARGET], True)]
        assert self.calls[0][1] is True
        assert not self.violations
        return None if self.vm.execute('Поймано') else json_subset(self.vm.execute('Проекция'))

    @property
    def phase(self):
        return self.vm.execute('Контекст.phase')


class NativeRecordObservationTests(unittest.TestCase):
    def test_actual_helper_returns_only_complete_unchanged_metadata(self):
        p = Probe(); value = p.run()
        self.assertEqual(value, projection())
        self.assertEqual(p.phase, 'record_scan')
        self.assertEqual(p.reads, [(True, 'Поля'), (True, 'ИмяТаблицыХранения'),
            (True, 'ИмяТаблицы'), (True, 'Метаданные')] + [(False, name) for name in FIELD_COLUMNS])
        self.assertNotIn(b'Private', compact(value))

    def test_unknown_empty_qualified_logical_names_and_type_text_are_not_mappings(self):
        for text in ('', 'Unknown', 'Справочник.Other.Реквизит.Custom', 'not a type :!?', '"\\é漢'):
            p = Probe()
            for name in ROOT_COLUMNS[1:3]: set_cell(p.root, 0, name, text)
            for name in FIELD_COLUMNS[1:]: set_cell(p.fields, 0, name, text)
            value = p.run()
            self.assertEqual(value['table']['logical_name'], text)
            self.assertEqual(value['table']['metadata_name'], text)
            for key in ('logical_name', 'metadata_name', 'type_text'):
                self.assertEqual(value['table']['fields'][0][key], text)

    def test_exact_filtered_explicit_true_api_failure_is_never_retried(self):
        p = Probe(); self.assertIsNone(p.run(reject=True)); self.assertEqual(p.phase, 'record_call')
        self.assertEqual(p.reads, [])

    def test_root_runtime_type_rejected_before_any_cell_access(self):
        for value in (None, BSLArray(), BSLStructure(), 'private', False, Decimal(1), Poison()):
            p = Probe(); self.assertIsNone(p.run(returned=value)); self.assertEqual(p.reads, [])
            self.assertEqual(p.phase, 'record_scan')

    def test_all_required_columns_have_exact_single_declared_type_before_cells(self):
        for which, names in (('root', ROOT_COLUMNS), ('fields', FIELD_COLUMNS)):
            for name in names:
                for types in ((), (BSLType.NUMBER,), (BSLType.STRING, BSLType.NUMBER)):
                    p = Probe(); table = getattr(p, which)
                    object.__setattr__(table.columns.find(name).value_type, 'types', types)
                    with self.subTest(table=which, column=name, types=types):
                        self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_scan')
                        self.assertEqual(p.reads, [] if which == 'root' else [(True, 'Поля')])

    def test_every_missing_required_column_rejects(self):
        for which, names in (('root', ROOT_COLUMNS), ('fields', FIELD_COLUMNS)):
            for name in names:
                p = Probe(); getattr(p, which).columns.find(name).name = 'Missing'
                with self.subTest(table=which, name=name): self.assertIsNone(p.run())

    def test_each_accessed_cell_requires_actual_declared_type_no_stringify(self):
        for which, names in (('root', ROOT_COLUMNS[:3]), ('fields', FIELD_COLUMNS)):
            for name in names:
                for value in (None, False, Decimal(1), BSLArray(), BSLStructure(), Poison()):
                    p = Probe(); set_cell(getattr(p, which), 0, name, value)
                    with self.subTest(table=which, name=name, value=type(value).__name__):
                        self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_scan')
        for value in (None, False, 'private', BSLArray(), BSLStructure(), Poison()):
            p = Probe(); set_cell(p.root, 0, 'Поля', value)
            self.assertIsNone(p.run()); self.assertEqual(p.reads, [(True, 'Поля')])

    def test_one_table_and_one_to_sixteen_complete_fields_before_field_access(self):
        for count in (0, 2, 16):
            p = Probe(); p.root.rows[:] = p.root.rows * count
            self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_limit'); self.assertEqual(p.reads, [])
        for count in (0, 17, 32):
            p = Probe(); p.fields.rows[:] = p.fields.rows * count
            self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_limit')
            self.assertEqual(p.reads, [(True, 'Поля')])
        p = self.max_fields(); value = p.run()
        self.assertEqual(len(value['table']['fields']), 16)
        self.assertEqual(len(p.reads), 68)  # 67 scalar cells plus fields-table cell.

    def max_fields(self):
        p = Probe(); p.fields.clear()
        for i in range(16):
            row = p.fields.add(); row.cells[p.fields.columns.find('ИмяПоляХранения')] = 'F' + str(i)
        for name in ROOT_COLUMNS[:3]: set_cell(p.root, 0, name, 'T' if name == ROOT_COLUMNS[0] else '')
        return p

    def test_storage_ascii_grammar_nonempty_no_case_normalization(self):
        for bad in ('', '1F', 'F-', ' F', 'F ', 'F.', 'Ｆ', 'а', 'K', 'İ', 'ı', 'ß', 'ſ', 'e\u0301'):
            for which, name in (('root', ROOT_COLUMNS[0]), ('fields', FIELD_COLUMNS[0])):
                p = Probe(); set_cell(getattr(p, which), 0, name, bad)
                with self.subTest(value=bad, table=which): self.assertIsNone(p.run())
        for valid in ('_', 'a0_', '_123', 'Z' * 64):
            p = Probe(); set_cell(p.root, 0, ROOT_COLUMNS[0], valid); set_cell(p.fields, 0, FIELD_COLUMNS[0], valid)
            value = p.run(); self.assertEqual(value['table']['storage_name'], valid)
            self.assertEqual(value['table']['fields'][0]['storage_name'], valid)

    def test_duplicate_raw_and_ascii_collision_fields_reject_without_reduction(self):
        for names in (('F', 'F'), ('F', 'f'), ('_IDRRef', '_IDRREF')):
            p = Probe(); p.fields.clear()
            for name in names:
                row = p.fields.add(); row.cells[p.fields.columns.find(FIELD_COLUMNS[0])] = name
            self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_scan')

    def test_cell_64_bmp_units_and_768_total_boundaries(self):
        for which, name in (('root', ROOT_COLUMNS[1]), ('fields', FIELD_COLUMNS[3])):
            p = Probe(); set_cell(getattr(p, which), 0, name, 'я' * 64)
            self.assertIsNotNone(p.run())
            p = Probe(); set_cell(getattr(p, which), 0, name, 'я' * 65)
            self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_limit')
        p = self.max_fields()
        # 39 storage units (T and F0..F15), plus 729 unchanged metadata units.
        total = 1 + sum(len('F' + str(i)) for i in range(16))
        left = 768 - total
        for i in range(16):
            for name in FIELD_COLUMNS[1:]:
                length = min(64, left); set_cell(p.fields, i, name, 'я' * length); left -= length
        self.assertEqual(left, 0); value = p.run(); self.assertIsNotNone(value)
        self.assertLessEqual(len(compact(value)), 6144)
        p = self.max_fields(); left = 769 - total
        for i in range(16):
            for name in FIELD_COLUMNS[1:]:
                length = min(64, left); set_cell(p.fields, i, name, 'я' * length); left -= length
        self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_limit')

    def test_controls_surrogates_nonbmp_format_separators_private_unassigned_rejected(self):
        for code in (0, 9, 10, 31, 127, 128, 159, 160, 173, 888, 1564, 6158,
                     8192, 8203, 8232, 8233, 8234, 8239, 8287, 8288, 12288,
                     55296, 56319, 56320, 57343, 57344, 63743, 64976, 65279, 65534, 65535, 0x1f642):
            p = Probe(); set_cell(p.fields, 0, FIELD_COLUMNS[3], chr(code))
            with self.subTest(code=code):
                self.assertIsNone(p.run()); self.assertEqual(p.phase, 'record_scan')

    def test_json_accounting_exact_for_all_accepted_escape_classes(self):
        p = Probe()
        for text in ('', 'abc', '"\\', 'Кириллица', 'é漢\ufffd'):
            p.vm.variables['значение'] = text
            p.vm.execute('Бюджет = Новый Структура("units,bytes,ranges", 0, 0, NativeЗаписьПечатныеГраницы()); '
                         'NativeЗаписьСтрока(Значение, Ложь, Бюджет, Контекст);')
            self.assertEqual(p.vm.execute('Бюджет.bytes'), len(compact(text)) - 2)
            self.assertEqual(p.vm.execute('Бюджет.units'), len(text))
        p.vm.variables['значение'] = 'я'
        p.vm.execute('Бюджет = Новый Структура("units,bytes,ranges", 0, 6138, NativeЗаписьПечатныеГраницы()); '
                     'NativeЗаписьСтрока(Значение, Ложь, Бюджет, Контекст);')
        self.assertEqual(p.vm.execute('Бюджет.bytes'), 6144)
        p.vm.execute('Бюджет.bytes = 6139; Бюджет.units = 0; Поймано = Ложь; '
                     'Попытка NativeЗаписьСтрока(Значение, Ложь, Бюджет, Контекст); '
                     'Исключение Поймано = Истина; КонецПопытки;')
        self.assertTrue(p.vm.execute('Поймано')); self.assertEqual(p.phase, 'record_limit')
        self.assertEqual(p.vm.execute('Бюджет.units'), 0)

    def test_compact_ascii_skeleton_bound_includes_all_keys_and_target(self):
        value = projection(); value['table'].update(storage_name='', logical_name='', metadata_name='', fields=[])
        empty_field = {key: '' for key in ('storage_name', 'logical_name', 'metadata_name', 'type_text')}
        self.assertEqual(len(compact(value)), 179); self.assertEqual(len(compact(empty_field)), 71)
        self.assertEqual(179 + 16 * 71 + 15 + 768 * 6, 5938)
        self.assertLessEqual(5938, 6144)

    def test_frozen_printable_ranges_exhaustively_match_unicode_15_bmp(self):
        p = Probe(); p.vm.execute('Границы = NativeЗаписьПечатныеГраницы();')
        numbers = [int(n) for n in p.vm.execute('Границы')]
        self.assertEqual(len(numbers), 690)
        # Freeze content independently of whichever Unicode database hosts tests.
        self.assertEqual(hashlib.sha256(','.join(map(str, numbers)).encode('ascii')).hexdigest(),
                         '7a038bea3b0d39cffde058419fef674b13bb6e6b8acbb97bb0d18162eed51473')
        accepted = set()
        for first, last in zip(numbers[::2], numbers[1::2]): accepted.update(range(first, last + 1))
        import unicodedata
        if unicodedata.unidata_version == '15.0.0':
            self.assertEqual(accepted, {n for n in range(65536) if chr(n).isprintable()})
        self.assertTrue(all(chr(n).isprintable() for n in accepted))
        # Execute the actual binary search at every frozen range boundary and gap.
        for code in sorted({0, 65535, *numbers, *(n - 1 for n in numbers[::2]), *(n + 1 for n in numbers[1::2])}):
            p.vm.variables['код'] = Decimal(code)
            self.assertEqual(p.vm.execute('NativeЗаписьПечатный(Код, Границы)'), code in accepted, code)


class NativeRecordSourceAndDispatchTests(unittest.TestCase):
    def test_actual_helper_is_native_syntax_one_explicit_filtered_call_no_retry(self):
        source = helper_source(); self.assertTrue(parse(source, source='actual-helper-native-syntax'))
        self.assertEqual(source.count('ПолучитьСтруктуруХраненияБазыДанных('), 1)
        self.assertIn('ПолучитьСтруктуруХраненияБазыДанных(Отбор, Истина)', source)
        self.assertEqual(source.count('Отбор.Добавить('), 1)
        self.assertIn('Отбор.Добавить("Справочник.NativeOracleItems")', source)
        for forbidden in ('Индексы', 'Назначение', 'ТабличноеПространство', 'ОписаниеОшибки',
                          'ПолучитьОбъект', 'Справочники.', 'Запрос', 'Выполнить(', 'НРег(', 'ВРег('):
            self.assertNotIn(forbidden, source)
        self.assertNotRegex(source, r'(?<![\w])Строка\(')
        self.assertNotIn('Попытка', source)

    def test_new_operation_uses_unchanged_setup_identity_and_two_user_checks(self):
        source = server()
        setup_branch = source[source.index('Если Контроль.operation = "audit" Или'):source.index('    Иначе\n        NativeПроверитьПользователя')]
        self.assertIn('Или Контроль.operation = "audit_record_metadata" Тогда', setup_branch)
        self.assertIn('NativeПроверитьПользователя(Текущий, @@SETUP_USER@@, Метаданные.Роли.NativeOracleSetupAdministrator);', setup_branch)
        self.assertIn('NativeПроверитьВсехПользователей();', setup_branch)
        self.assertIn('Если Результат.metadata_version <> 1 Тогда', setup_branch)
        self.assertIn('Результат.Вставить("record_metadata", NativeМетаданныеЗаписи(Контекст));', setup_branch)
        self.assertNotIn('NativeИзмерить(', setup_branch)
        self.assertLess(source.index('NativeПроверитьМетаданные(Результат);', source.index('Результат = NativeНовыйРезультат')),
                        source.index('Или Контроль.operation = "audit_record_metadata" Тогда'))
        for name, expected in ORIGINAL_HASHES.items():
            self.assertEqual(hashlib.sha256(routine(source, name, name not in ('NativeИменаХранения', 'NativeНовыйРезультат', 'NativeСостояние', 'NativeСохраненнаяСсылка', 'NativeПрочитатьJSON')).encode('utf-8')).hexdigest(), expected)

    def test_managed_client_accepts_new_success_errors_and_keeps_old_admission(self):
        source = (MODULES / 'ManagedApplicationModule.bsl').read_text(encoding='utf-8')
        vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
        vm.execute(routine(source, 'NativeПроверитьОтвет', True))
        for operation in ('bootstrap', 'audit', 'audit_contract', 'observe', 'create', 'update', 'delete', 'audit_record_metadata'):
            vm.variables['ответ'] = BSLStructure('status,operation,phase', 'ok', operation, 'complete')
            vm.execute('NativeПроверитьОтвет(Ответ);')
        for phase in ('record_call', 'record_scan', 'record_limit'):
            vm.variables['ответ'] = BSLStructure('status,operation,phase', 'error', 'audit_record_metadata', phase)
            vm.execute('NativeПроверитьОтвет(Ответ);')
            for operation in ('dispatch', 'bootstrap', 'audit', 'audit_contract', 'observe', 'create', 'update', 'delete'):
                vm.variables['ответ'] = BSLStructure('status,operation,phase', 'error', operation, phase)
                vm.execute('Поймано = Ложь; Попытка NativeПроверитьОтвет(Ответ); Исключение Поймано = Истина; КонецПопытки;')
                self.assertTrue(vm.execute('Поймано'))
        for status, operation, phase in (('ok', 'audit_record_metadata', 'record_scan'),
                                        ('error', 'audit_record_metadata', 'complete'),
                                        ('ok', 'audit_record_metadata_other', 'complete'),
                                        ('error', 'audit_record_metadata', 'record_other')):
            vm.variables['ответ'] = BSLStructure('status,operation,phase', status, operation, phase)
            vm.execute('Поймано = Ложь; Попытка NativeПроверитьОтвет(Ответ); Исключение Поймано = Истина; КонецПопытки;')
            self.assertTrue(vm.execute('Поймано'))

    def test_actual_dispatcher_binds_new_lane_runs_setup_checks_and_never_crud(self):
        from test_native_1c_db_oracle_metadata import ControlledMembers, rendered_module
        for version in (1, 2):
            p = Probe(); vm = p.vm; events = []; writes = []
            setup_role = object(); current_user = object(); token = 'b' * 32
            control = BSLStructure('schema,nonce,token,operation', Decimal(1),
                                   '0123456789abcdef' * 2, token, 'audit_record_metadata')
            vm.register_function('ПривилегированныйРежим', lambda: False)
            vm.register_function('NativeПрочитатьJSON', lambda path: control)
            vm.register_type('Файл', lambda path: ControlledMembers(Существует=HostFunction('Существует', lambda: False)))
            vm.register_type('СистемнаяИнформация', lambda: ControlledMembers(ВерсияПриложения='8.3.27.1508'))
            def metadata(result):
                events.append('metadata')
                result.insert('metadata_version', Decimal(version))
                result.insert('payload_length', Decimal(32 if version == 1 else 64))
                result.insert('amount_digits', Decimal(9)); result.insert('amount_scale', Decimal(2))
            def identity(user, name, role):
                self.assertIs(user, current_user); self.assertEqual(name, 'NativeOracleSetup')
                self.assertIs(role, setup_role); events.append('identity')
            vm.register_function('NativeПроверитьМетаданные', metadata, returns_value=False)
            vm.register_function('NativeПроверитьПользователя', identity, returns_value=False)
            vm.register_function('NativeПроверитьВсехПользователей', lambda: events.append('two_users'), returns_value=False)
            def storage(selector, dbms_names):
                self.assertEqual(list(selector), [TARGET]); self.assertIs(dbms_names, True)
                events.append('storage'); return p.root
            vm.register_function('ПолучитьСтруктуруХраненияБазыДанных', storage)
            vm.register_function('NativeЗаписатьJSON', lambda path, value: writes.append(json_subset(value)), returns_value=False)
            vm.execute('Перем ПользователиИнформационнойБазы, Метаданные;')
            vm.variables['пользователиинформационнойбазы'] = ControlledMembers(
                ТекущийПользователь=HostFunction('ТекущийПользователь', lambda: current_user))
            vm.variables['метаданные'] = ControlledMembers(Роли=ControlledMembers(NativeOracleSetupAdministrator=setup_role))
            source = rendered_module('NativeOracleServer.bsl')
            vm.execute('\n'.join((routine(source, 'NativeВыполнить'),
                                  routine(source, 'NativeВыполнитьПроверенный', True),
                                  routine(source, 'NativeНовыйРезультат'))))
            vm.execute('Ответ = NativeВыполнить("' + token + '");')
            reply = json_subset(vm.execute('Ответ'))
            if version == 1:
                self.assertEqual(events, ['metadata', 'identity', 'two_users', 'storage'])
                self.assertEqual(reply, {'status': 'ok', 'operation': 'audit_record_metadata', 'phase': 'complete'})
                self.assertEqual(len(writes), 1); value = writes[0]
                self.assertEqual(value['record_metadata'], projection())
                self.assertNotIn('storage_names', value)
                self.assertTrue(value['role_verified']); self.assertTrue(value['users_verified'])
                self.assertTrue(value['nonprivileged'])
                self.assertTrue(all(value[k] is None for k in ('count', 'code', 'payload', 'amount', 'deletion_mark', 'same_reference')))
            else:
                self.assertEqual(events, ['metadata', 'identity', 'two_users'])
                self.assertEqual(writes, [])
                self.assertEqual(reply, {'status': 'error', 'operation': 'audit_record_metadata', 'phase': 'identity'})

    def test_actual_client_publishes_new_success_and_finite_errors_then_stops(self):
        from test_native_1c_db_oracle_metadata import completion_vm, finite_reply, COMPLETION_PATH, PENDING_PATH
        for status, phase in (('ok', 'complete'), ('error', 'record_call'), ('error', 'record_scan'), ('error', 'record_limit')):
            vm, events, files = completion_vm(finite_reply(status, 'audit_record_metadata', phase))
            vm.execute('ПриНачалеРаботыСистемы();')
            self.assertEqual(events, ['server', 'open', 'write', 'close', 'move', 'shutdown'])
            self.assertNotIn(PENDING_PATH, files)
            value = json.loads(files[COMPLETION_PATH])
            self.assertEqual((value['status'], value['operation'], value['phase']), (status, 'audit_record_metadata', phase))
            self.assertEqual(set(value), {'schema', 'nonce', 'token', 'operation', 'phase', 'status'})

    def test_all_changed_modules_render_parse_native_only(self):
        replacements = {'@@NONCE@@': '"' + 'a' * 32 + '"', '@@EVIDENCE@@': '"/offline-controlled"',
                        '@@SETUP_USER@@': '"NativeOracleSetup"', '@@CRUD_USER@@': '"NativeOracleCRUD"'}
        for name in ('NativeOracleServer.bsl', 'ManagedApplicationModule.bsl'):
            source = (MODULES / name).read_text(encoding='utf-8')
            for before, after in replacements.items(): source = source.replace(before, after)
            self.assertNotIn('@@', source)
            self.assertTrue(parse(source, source=name))


ORIGINAL_HASHES = {'NativeИменаХранения': 'f5c27c531995a94663e6620eba0735e13d0db307f6c2317292ed7ab5e74a4eac', 'NativeИменаКолонка': '70eff2bd30d3c66d032fa5a396344113f2c06a413a9209c9519a38c2052ad04a', 'NativeИменаЛимит': '2b1b81f5d95a85a8bb0c005eb3311970abc5050d172d3c7fac0a83b71e960032', 'NativeИменаСтрока': '7ca09903758d8e342d668c6c241051f89b6a8f45734075b648a52d15ef825775', 'NativeНовыйРезультат': 'd19e5403a1593a64041ffb369cd5f4fa7e9959be50ae1ba8e22557bcbbce7249', 'NativeПроверитьПользователя': 'f4aaeb50ff93efa1e78d6ace8b300530cf3fa00db49d38cd2d397d6f3dd33459', 'NativeПроверитьВсехПользователей': '3674aa9ba0c59a5ccbd9d2222ae39fdb7da0e134bb044421b91f454511b44281', 'NativeПроверитьМетаданные': '8332fb214bf353ac697b97e7bbdd24802436ae6b59a598157d34fa3de58ec268', 'NativeИзмерить': 'c4435ee509da8e57a50beea70e722f03053477800fc8bf8696468e7cfb15671d', 'NativeСостояние': 'e899a9c74f35ab964b85a4d5c59564ebc90eeb0011e78a892ef3b4d2d3d2fabd', 'NativeСохраненнаяСсылка': '7cb57746852d9b507a2fe720d52c1969510ba8513d747e13e80cbe2f3f63ac04', 'NativeПрочитатьJSON': 'b85328bbd4f6be0dbfb4185af9fbc3807e109bd3f495716e26d2c8cdfa96b5ea', 'NativeЗаписатьJSON': '3b58488da8193a296db76ba040655f4c7c33b92cffbf147bab2de4df8db03cfb'}

if __name__ == '__main__': unittest.main()
