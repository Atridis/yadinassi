"""Verify ValueList probe source and genuine native output bytes."""
from scripts.native_historical_replay import without_value_tree_probes, FILL_EXCLUDE_ORDER_PROBE_BLOCKS, FILL_EXCLUDE_PROBE_BLOCKS, FILL_INCLUDE_PROBE_BLOCKS, DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS
import hashlib
from pathlib import Path
import re
import unittest

from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб списка значений.\n',
           '// Конец компактных проб списка значений.\n\n')
BODY = ('// Начало наблюдений списка значений.\n',
        '// Конец наблюдений списка значений.\n')
EXTRA_HELPERS = ('// Начало уточняющих проб списка значений.\n',
                 '// Конец уточняющих проб списка значений.\n\n')
EXTRA_BODY = ('// Начало уточняющих наблюдений списка значений.\n',
              '// Конец уточняющих наблюдений списка значений.\n')
FINAL = 'table.list.checkpoint.complete: [ok]'


def without_sort_probe(text):
    text = without_value_tree_probes(text)
    # Historical-source integrity only; full native comparators use the file.
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
    ):
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def without_list_probe(text):
    """Historical-source integrity only; never used by a native comparator."""
    for start, end in (EXTRA_HELPERS, HELPERS, BODY):
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


def blob_hash(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class ValueListCheckpointTests(unittest.TestCase):
    def test_owner_source_is_restored_by_only_the_reviewed_supplement_changes(self):
        original = without_sort_probe(source())
        for start, end in (EXTRA_HELPERS, EXTRA_BODY):
            before, rest = original.split(start, 1)
            _, after = rest.split(end, 1)
            original = before + after
        # Reverse precisely the two reviewed identity-dispatch corrections.
        for fixed, historical in (
            ('Если ТипЗнч(Ответ) = Тип("ValueListItem") Тогда',
             'Если Строка(ТипЗнч(Ответ)) = "ЭлементСпискаЗначений" Тогда'),
            ('ИначеЕсли ТипЗнч(Ответ) = Тип("ValueList") Тогда',
             'ИначеЕсли Строка(ТипЗнч(Ответ)) = "СписокЗначений" Тогда'),
        ):
            self.assertEqual(original.count(fixed), 1)
            original = original.replace(fixed, historical)
        self.assertEqual(blob_hash(('\ufeff' + original).encode()),
                         '1c1e516847eca80e53cda3f218c5490418a241bf')

    def test_genuine_owner_addition_preserves_previous_output_and_native_presentations(self):
        data = (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')
        # Isolate the historical core evidence, not the full-native comparator.
        self.assertEqual(blob_hash(data), '97e90791a4011bd7f6ef2922533f92f698557cbd')
        data = data.split(b'table.list.copy.fresh-empty:', 1)[0] + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(blob_hash(data), 'b934bc3fe6d8c8f6b9d4ba23972ccb29bd3d00f6')
        before_sort, sort_tail = data.split(b'table.list.sort.enum.identity:', 1)
        self.assertTrue(sort_tail.endswith(b'table.list.sort.checkpoint.complete: [ok]\n'
                                           b'table.checkpoint.complete: [ok]\n'))
        data = before_sort + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(blob_hash(data), 'c648f0a577aba3cb19c98ad4effaea4088e1ea1e')
        before, tail = data.split(b'table.list.identity:', 1)
        self.assertTrue(tail.endswith(b'table.list.checkpoint.complete: [ok]\n'
                                      b'table.checkpoint.complete: [ok]\n'))
        historical = before + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(blob_hash(historical), 'c3e5ae6e3211b2fb85ba3614cadb764475315ce8')
        self.assertEqual(len(data.splitlines()) - len(historical.splitlines()), 183)
        labels = re.findall(rb'^(table\.list\.[a-z.-]+): \[', data, re.MULTILINE)
        owner_labels = ['table.' + call.arguments[0].value for call in observations()]
        self.assertEqual([label.decode() for label in labels],
                         owner_labels + ['table.list.checkpoint.complete'])
        identity = tail.split(b'\ntable.list.constructor.list:', 1)[0].decode()
        self.assertIn('ListType={"S","' + 'Список значений' + '"}', identity)
        self.assertIn('ItemType={"S","' + 'Элемент списка значений' + '"}', identity)

    def test_original_source_all_goldens_and_environment_are_unchanged(self):
        restored = ('\ufeff' + without_list_probe(without_sort_probe(source()))).encode()
        self.assertEqual(blob_hash(restored), '92ba44889c221de39f8b3ae578f0c1408ccbf0ae')
        hashes = {
            'collections': '97e90791a4011bd7f6ef2922533f92f698557cbd',
            'dates': '05d23c46540b301820f2ac81c8a67fc0e1273dc8',
            'functions': '6df192ac9d10c07755948d7c14cfed9e2311c65f',
            'numbers': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13',
            'strings': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462',
            'values': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27',
        }
        for name, expected in hashes.items():
            data = (ROOT / f'tests/fixtures/native_windows/{name}.out').read_bytes()
            self.assertEqual(blob_hash(data.replace(b'\r\n', b'\n')), expected)
        self.assertEqual((ROOT / 'integrational_tests/meta.md').read_text(encoding='utf-8'),
                         '1c-version: 8.3.27.2342\nos: Windows\ninfobase-mode: файловая база\n'
                         'infobase-locale: русский (Россия)\nsession-locale: русский (Россия)\n'
                         'compatibility-mode: НеУказан\n')

    def test_fixed_unique_bounded_observations_and_full_source_parse(self):
        calls = observations()
        self.assertEqual(len(calls), 38)
        labels = []
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(arg, ast.Literal) and type(arg.value) is str
                                for arg in call.arguments))
            label, expression = (arg.value for arg in call.arguments)
            self.assertRegex(label, r'^list\.[a-z.-]+$')
            self.assertLess(len(expression), 500)
            self.assertNotRegex(expression, r'[\r\n]')
            parse('Result = ' + expression + ';')
            labels.append(label)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(source().count(FINAL), 1)
        self.assertIn('Сообщить("' + FINAL + '");', section(BODY))
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True


if __name__ == '__main__':
    unittest.main()
