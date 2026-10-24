"""Probe observability only; index behavior and codecs require owner 1C output."""
from scripts.native_historical_replay import FILL_EXCLUDE_ORDER_PROBE_BLOCKS, FILL_EXCLUDE_PROBE_BLOCKS, FILL_INCLUDE_PROBE_BLOCKS, DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS
from decimal import Decimal
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.native_historical_replay import historical_collections_source

from yadinassi import Interpreter, ast, serialization
from yadinassi.parser import parse
from yadinassi.value_tables import (BSLValueTable, BSLValueTableColumn,
                                   BSLValueTableColumnCollection, BSLValueTableRow)
from yadinassi.values import BSLArray, BSLType, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб индексов.\n', '// Конец компактных проб индексов.\n\n')
BODY = ('// Начало наблюдений индексов.\n', '// Конец наблюдений индексов.\n')


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


EXTRA_HELPERS = ('// Начало дополнительных компактных проб индексов.\n', '// Конец дополнительных компактных проб индексов.\n\n')
EXTRA_BODY = ('// Начало дополнительных наблюдений индексов.\n', '// Конец дополнительных наблюдений индексов.\n')


def observations():
    return [node.expression for node in parse(section(BODY) + section(EXTRA_BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


class IndexProbeTests(unittest.TestCase):
    def test_old_source_and_all_owner_goldens_are_byte_exact(self):
        old = source()
        for start, end in (
            *FILL_EXCLUDE_ORDER_PROBE_BLOCKS, *FILL_EXCLUDE_PROBE_BLOCKS, *FILL_INCLUDE_PROBE_BLOCKS, *DESCRIPTOR_MAP_PROBE_BLOCKS, *FIELD_REFERENCE_BLOCKS,
            ('// Начало заключительных проб пустой строки кэша списка.\n', '// Конец заключительных проб пустой строки кэша списка.\n\n'),
            ('// Начало заключительных наблюдений пустой строки кэша списка.\n', '// Конец заключительных наблюдений пустой строки кэша списка.\n'),
            ('// Начало уточняющих проб кэша строки списка.\n', '// Конец уточняющих проб кэша строки списка.\n\n'),
            ('// Начало уточняющих наблюдений кэша строки списка.\n', '// Конец уточняющих наблюдений кэша строки списка.\n'),
            ('// Начало компактных проб строкового представления списка.\n', '// Конец компактных проб строкового представления списка.\n\n'),
            ('// Начало наблюдений строкового представления списка.\n', '// Конец наблюдений строкового представления списка.\n'),
            ('// Начало компактных проб копирования списка.\n', '// Конец компактных проб копирования списка.\n\n'),
            ('// Начало наблюдений копирования списка.\n', '// Конец наблюдений копирования списка.\n'),
            ('// Начало компактных проб сортировки списка.\n', '// Конец компактных проб сортировки списка.\n\n'),
            ('// Начало наблюдений сортировки списка.\n', '// Конец наблюдений сортировки списка.\n'),
            ('// Начало уточняющих проб списка значений.\n', '// Конец уточняющих проб списка значений.\n\n'),
            ('// Начало компактных проб списка значений.\n', '// Конец компактных проб списка значений.\n\n'),
            ('// Начало наблюдений списка значений.\n', '// Конец наблюдений списка значений.\n'),
            HELPERS, BODY, EXTRA_HELPERS, EXTRA_BODY,
        ):
            before, rest = old.split(start, 1)
            _, after = rest.split(end, 1)
            old = before + after
        data = ('\ufeff' + old).encode()
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                         'd6176c44edf9a3d7ad9f8cf7a474a12aca25c809')
        hashes = {'collections': '97e90791a4011bd7f6ef2922533f92f698557cbd',
                  'values': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27',
                  'dates': '05d23c46540b301820f2ac81c8a67fc0e1273dc8',
                  'functions': '6df192ac9d10c07755948d7c14cfed9e2311c65f',
                  'numbers': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13',
                  'strings': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462'}
        for name, expected in hashes.items():
            data = (ROOT / f'tests/fixtures/native_windows/{name}.out').read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), expected)
        self.assertEqual((ROOT / 'integrational_tests/meta.md').read_text(encoding='utf-8'),
                         '1c-version: 8.3.27.2342\nos: Windows\ninfobase-mode: файловая база\n'
                         'infobase-locale: русский (Россия)\nsession-locale: русский (Россия)\n'
                         'compatibility-mode: НеУказан\n')

    def test_owner_addition_preserves_exact_historical_output(self):
        data = (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')
        before, tail = data.split(b'table.indexes.identity:', 1)
        self.assertTrue(tail.endswith(b'table.checkpoint.complete: [ok]\n'))
        before_extra, extra = data.split(b'table.indexes.extra.edit-order:', 1)
        first_run = before_extra + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(first_run)).encode() + b'\0' + first_run).hexdigest(),
                         'dc6c4ab155eb27c49d68ef22f7917d91ff90e876')
        historical = before + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(historical)).encode() + b'\0' + historical).hexdigest(),
                         '1230b2a63eee62f88eee0d8a93cfba15d002f376')

    def test_fixed_bounded_expressions_and_full_source_compile(self):
        calls = observations()
        self.assertEqual(len(calls), 40)
        labels = []
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(arg, ast.Literal) and type(arg.value) is str for arg in call.arguments))
            label, expression = (arg.value for arg in call.arguments)
            self.assertRegex(label, r'^indexes\.[a-z.-]+$')
            self.assertLess(len(expression), 180)
            self.assertNotRegex(expression, r'[\r\n]')
            parse('Result = ' + expression + ';')
            labels.append(label)
        self.assertEqual(len(labels), len(set(labels)))
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True
        for field in ('TypeWrite', 'TypeRead', 'ReadType', 'ReadWrite', 'ReadView', 'SavedIndex'):
            self.assertIn(field, section(HELPERS))
        self.assertNotIn('New CollectionIndex(', section(HELPERS).split('Вычислить')[0])

    def test_current_runtime_matches_full_owner_output_and_completes(self):
        output = []
        Interpreter(output=output.append).execute(historical_collections_source(
            SOURCE.read_bytes(),
            (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes()).decode('utf-8-sig'))
        records = [line for line in output if line.startswith('table.indexes.')
                   and not line.startswith('table.indexes.checkpoint.')]
        self.assertEqual(len(records), 40)
        expected = (ROOT / 'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        self.assertEqual('\n'.join(output) + '\n', expected)
        self.assertEqual([line.split(':', 1)[0] for line in records],
                         ['table.' + call.arguments[0].value for call in observations()])
        self.assertEqual(output[-1], 'table.checkpoint.complete: [ok]')
        self.assertEqual(output.count('table.indexes.checkpoint.complete: [ok]'), 1)

    def test_targets_reached_and_concrete_snapshots_survive(self):
        # Arrays are deliberately used as serializable host instrumentation,
        # not as an implementation or an oracle for native index semantics.
        owners, calls = {}, []
        fail_after_add = [False]
        fail_after_sort = [False]
        original = BSLValueTable.get_member
        original_set = BSLValueTable.set_member
        original_method = BSLValueTable.get_method

        def table_method(table, name):
            method = original_method(table, name)
            def invoke(*args):
                calls.append(("table." + name.casefold(), args))
                result = method(*args)
                if fail_after_sort[0] and name.casefold() == 'sort':
                    raise ValueError('instrumented failure after sort')
                return result
            return HostFunction(name, invoke, returns_value=method.returns_value)

        original_columns_method = BSLValueTableColumnCollection.get_method
        original_column_set = BSLValueTableColumn.set_member
        original_row_set = BSLValueTableRow.set_member

        def columns_method(columns, name):
            method = original_columns_method(columns, name)
            def invoke(*args):
                calls.append(('columns.' + name.casefold(), args))
                return method(*args)
            return HostFunction(name, invoke, returns_value=method.returns_value)

        def column_set(column, name, value):
            calls.append(('column.' + name.casefold(), (value,)))
            return original_column_set(column, name, value)

        def row_set(row, name, value):
            calls.append(('row.' + name.casefold(), (value,)))
            return original_row_set(row, name, value)

        def get_member(table, name):
            if name.casefold() not in ('indexes', 'индексы'):
                return original(table, name)
            if table not in owners:
                collection = BSLArray()
                def method(name):
                    key = name.casefold()
                    key = {'добавить': 'add', 'удалить': 'delete',
                           'очистить': 'clear', 'количество': 'count'}.get(key, key)
                    def invoke(*args):
                        calls.append((key, args))
                        if key in ('add', 'добавить'):
                            item = BSLArray()
                            text = args[0] if args and type(args[0]) is str else ''
                            item.items = [part.strip() for part in text.split(',') if part.strip()]
                            collection.items.append(item)
                            if fail_after_add[0]:
                                raise ValueError("instrumented failure after insertion")
                            return item
                        if key in ('delete', 'удалить'):
                            value, = args
                            if type(value) is Decimal:
                                del collection.items[int(value)]
                            else:
                                collection.items.remove(value)
                            return None
                        if key in ('clear', 'очистить'):
                            collection.items.clear()
                            return None
                        if key in ('count', 'количество'):
                            return Decimal(len(collection.items))
                        if key in ('get', 'получить'):
                            return collection.get(*args)
                        raise ValueError(name)
                    return HostFunction(name, invoke)
                collection.get_method = method
                owners[table] = collection
            return owners[table]

        def set_member(table, name, value):
            if name.casefold() in ('indexes', 'индексы'):
                calls.append(('readonly', (value,)))
            return original_set(table, name, value)

        output = []
        vm = Interpreter(output=output.append)
        vm.execute(source().split('#Область МассивыИСтруктуры', 1)[0])
        with patch.object(BSLValueTable, 'get_member', get_member), patch.object(BSLValueTable, 'set_member', set_member), patch.object(BSLValueTable, 'get_method', table_method), patch.object(BSLValueTableColumnCollection, 'get_method', columns_method), patch.object(BSLValueTableColumn, 'set_member', column_set), patch.object(BSLValueTableRow, 'set_member', row_set):
            for call in observations():
                label, expression = (arg.value for arg in call.arguments)
                if '.constructor.' in label:
                    continue
                calls.clear(); output.clear()
                quoted = expression.replace('"', '""')
                vm.execute('НаблюдатьТаблицы("' + label + '", "' + quoted + '")')
                with self.subTest(label=label):
                    if label != 'indexes.codec.empty':
                        self.assertTrue(any(name == 'add' for name, _ in calls), calls)
                    self.assertEqual(len(output), 1)
                    self.assertNotIn('[serialize-error]', output[0])
                    self.assertNotEqual(output[0], 'table.' + label + ': [error]')
                    if '.codec.' in label:
                        self.assertIn('  Write=', output[0])
                        self.assertIn('  ReadType=', output[0])
                    elif label.endswith('readonly'):
                        self.assertIn('readonly', [name for name, _ in calls])
                    elif '.delete' in label:
                        self.assertIn('delete', [name for name, _ in calls])
                    elif label.endswith('.clear'):
                        self.assertIn('clear', [name for name, _ in calls])
                    target = {'indexes.group': 'table.groupby', 'indexes.sort': 'table.sort',
                              'indexes.copy': 'table.copy', 'indexes.table-clear': 'table.clear',
                              'indexes.search-add-delete': 'table.delete',
                              'indexes.search-bulk': 'table.loadcolumn',
                              'indexes.rename': 'column.name',
                              'indexes.column-delete': 'columns.delete',
                              'indexes.column-move': 'columns.move',
                              'indexes.columns-clear': 'columns.clear'}.get(label)
                    if target:
                        self.assertIn(target, [name for name, _ in calls])
                    if label == 'indexes.copy':
                        self.assertIn('table.copycolumns', [name for name, _ in calls])
                    if label == 'indexes.search-edit':
                        self.assertIn(('row.key', ('b',)), calls)
                        self.assertGreaterEqual(calls.count(('row.key', ('a',))), 3)
                    if label == 'indexes.search-bulk':
                        self.assertIn('table.fillvalues', [name for name, _ in calls])
                    extra_targets = {
                        'indexes.extra.edit-order': ('table.fillvalues', 'table.loadcolumn'),
                        'indexes.extra.reorder': ('table.sort', 'table.move'),
                        'indexes.extra.selection': ('delete', 'table.findrows'),
                        'indexes.extra.copy': ('table.copy', 'table.copycolumns', 'column.name'),
                        'indexes.extra.stale-links': ('delete', 'clear', 'columns.delete', 'column.name'),
                    }.get(label, ())
                    for extra_target in extra_targets:
                        self.assertIn(extra_target, [name for name, _ in calls])
                    if '.search-' in label:
                        self.assertIn('table.findrows', [name for name, _ in calls])

            # Deliberately mutate then fail: the checkpoint must retain both
            # the failure and concrete partial state, rather than an outer error.
            fail_after_add[0] = True
            output.clear()
            vm.execute('НаблюдатьТаблицы("indexes.instrumented", "ИндексыТаблицыПробы(""add"", ""Key"")")')
            self.assertIn('  Status={"S","error"}', output[0])
            self.assertIn('  Indexes.Count={"N",1}', output[0])

            # Supplement stage failures retain earlier and later snapshots.
            fail_after_add[0] = False
            fail_after_sort[0] = True
            output.clear()
            vm.execute('НаблюдатьТаблицы("indexes.instrumented", "ДопПорядокИндексов(""reorder"")")')
            self.assertIn('Sort:error', output[0])
            self.assertIn('  Initial.Order=[{"N",1}; {"N",2}; {"N",3}]', output[0])
            self.assertIn('  Sorted.Order=[{"N",3}; {"N",2}; {"N",1}]', output[0])
            self.assertIn('  Moved.Order=[{"N",2}; {"N",1}; {"N",3}]', output[0])
            fail_after_sort[0] = False

            # A failed view or type codec must not hide the value codec.
            fail_after_add[0] = False
            original_iter = BSLArray.__iter__
            def broken_index_view(value):
                if any(value is collection for collection in owners.values()):
                    raise ValueError('instrumented view failure')
                return original_iter(value)
            def broken_type_write(value):
                if isinstance(value, BSLType):
                    raise ValueError('instrumented type codec failure')
                return serialization.value_to_string_internal(value)
            vm.register_function('ЗначениеВСтрокуВнутр', broken_type_write,
                                 'ValueToStringInternal')
            output.clear()
            with patch.object(BSLArray, '__iter__', broken_index_view):
                vm.execute('НаблюдатьТаблицы("indexes.instrumented", "КодекИндексовПробы(""collection"")")')
            self.assertIn('  View={"S","[error]"}', output[0])
            self.assertIn('  TypeWrite={"S","[error]"}', output[0])
            self.assertIn('  ReadWrite={"S","same-as-Write"}', output[0])
            self.assertNotIn('[serialize-error]', output[0])


if __name__ == '__main__':
    unittest.main()
