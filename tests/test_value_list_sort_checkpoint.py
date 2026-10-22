"""Probe instrumentation plus independently supplied native-evidence integrity.

Synthetic sorting deliberately reverses the receiver. No synthetic stream is
saved as native output. Full native gates still read the whole scenario.
"""
from scripts.native_historical_replay import FILL_EXCLUDE_PROBE_BLOCKS, FILL_INCLUDE_PROBE_BLOCKS, DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS
from contextlib import ExitStack
import hashlib
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, ast
from yadinassi.parser import parse
from yadinassi import type_values, serialization, runtime
from yadinassi.search_directions import BSLSearchDirection
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, BSLObject, BSLType, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб сортировки списка.\n', '// Конец компактных проб сортировки списка.\n\n')
BODY = ('// Начало наблюдений сортировки списка.\n', '// Конец наблюдений сортировки списка.\n')
FINAL = 'table.list.sort.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def strip_probe(text):
    for start, end in (
        *FILL_EXCLUDE_PROBE_BLOCKS, *FILL_INCLUDE_PROBE_BLOCKS, *DESCRIPTOR_MAP_PROBE_BLOCKS, *FIELD_REFERENCE_BLOCKS,
        ('// Начало заключительных проб пустой строки кэша списка.\n', '// Конец заключительных проб пустой строки кэша списка.\n\n'),
        ('// Начало заключительных наблюдений пустой строки кэша списка.\n', '// Конец заключительных наблюдений пустой строки кэша списка.\n'),
        ('// Начало уточняющих проб кэша строки списка.\n', '// Конец уточняющих проб кэша строки списка.\n\n'),
        ('// Начало уточняющих наблюдений кэша строки списка.\n', '// Конец уточняющих наблюдений кэша строки списка.\n'),
        ('// Начало компактных проб строкового представления списка.\n', '// Конец компактных проб строкового представления списка.\n\n'),
        ('// Начало наблюдений строкового представления списка.\n', '// Конец наблюдений строкового представления списка.\n'),
        ('// Начало компактных проб копирования списка.\n', '// Конец компактных проб копирования списка.\n\n'),
        ('// Начало наблюдений копирования списка.\n', '// Конец наблюдений копирования списка.\n'),
        HELPERS, BODY,
    ):
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def metadata_blob(data):
    # Checkout transport only, never metadata payload or native comparisons.
    return blob(data.replace(b'\r\n', b'\n'))


class _Namespace(BSLObject):
    def __str__(self):
        return "SYNTHETIC sort namespace"

    def get(self, index):
        raise ValueError("synthetic namespace is not indexable")

    def get_member(self, name):
        if name.casefold() in ('asc', 'возр'):
            return BSLSearchDirection.FROM_BEGIN
        if name.casefold() in ('desc', 'убыв'):
            return BSLSearchDirection.FROM_END
        return super().get_member(name)

    def __iter__(self):
        return iter(BSLSearchDirection)


class Instrumentation:
    def __init__(self):
        self.calls, self.outputs = [], []
        self.fail_after = False
        self.fail_type_codec = False
        self.read_undefined = False
        self.vm = Interpreter(output=self.outputs.append)
        namespace = _Namespace()
        for name in ('sortdirection', 'направлениесортировки'):
            self.vm.variables[name] = namespace
            self.vm.module_names.add(name)
        self.vm.register_function('Тип', self.type_by_name, 'Type')
        self.vm.register_function('ЗначениеВСтрокуВнутр', self.write, 'ValueToStringInternal')
        self.vm.register_function('ЗначениеИзСтрокиВнутр', self.read, 'ValueFromStringInternal')
        self.vm.execute(source().split('#Область МассивыИСтруктуры', 1)[0])

    def type_by_name(self, name):
        if name.casefold() in ('sortdirection', 'направлениесортировки'):
            return BSLType.SEARCH_DIRECTION
        return type_values.type_by_name(name)

    def write(self, value):
        # Only the enum is synthetic. Existing core lists are never serialized.
        if type(value) in (BSLValueList, BSLValueListItem):
            raise AssertionError('raw list/item serialization is forbidden')
        if self.fail_type_codec and value is BSLType.SEARCH_DIRECTION:
            raise ValueError('synthetic type codec failure')
        return serialization.value_to_string_internal(value)

    def read(self, value):
        restored = serialization.value_from_string_internal(value)
        if self.read_undefined and type(restored) is BSLSearchDirection:
            return None
        return restored

    def __enter__(self):
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(runtime, "_COLLECTIONS", runtime._COLLECTIONS + (_Namespace,)))
        original = BSLValueList.get_method
        harness = self
        def get_method(owner, name):
            if name.casefold() in ('sortbyvalue', 'sortbypresentation', 'сортироватьпозначению', 'сортироватьпопредставлению'):
                def reverse(*args):
                    harness.calls.append((name, owner, args))
                    owner.items.reverse()
                    if harness.fail_after:
                        raise ValueError('synthetic mutation before failure')
                return HostFunction(name, reverse, returns_value=False)
            return original(owner, name)
        self.stack.enter_context(patch.object(BSLValueList, 'get_method', get_method))
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)

    def run(self, expression):
        return self.vm.execute(expression)


class ValueListSortCheckpointTests(unittest.TestCase):
    def test_exact_base_and_protected_files(self):
        self.assertEqual(blob(('\ufeff' + strip_probe(source())).encode()), '922aafef9f03dce85f1fa5149af9f4c615356661')
        expected = {
            'collections.out': '97e90791a4011bd7f6ef2922533f92f698557cbd',
            'dates.out': '05d23c46540b301820f2ac81c8a67fc0e1273dc8',
            'functions.out': '6df192ac9d10c07755948d7c14cfed9e2311c65f',
            'numbers.out': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13',
            'strings.out': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462',
            'values.out': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27',
        }
        for name, expected_hash in expected.items():
            self.assertEqual(blob((ROOT / 'tests/fixtures/native_windows' / name).read_bytes().replace(b'\r\n', b'\n')), expected_hash)
        # Git's Windows checkout may transport text with CRLF. Only line
        # endings are normalized; metadata field content remains exact.
        self.assertEqual(metadata_blob((ROOT / 'integrational_tests/meta.md').read_bytes()),
                         'f76530bce7bd3b8a54055b2390ec7551024c62e2')
        self.assertIn('__version__ = "0.3.2"', (ROOT / 'yadinassi/__init__.py').read_text())

    def test_complete_owner_evidence_preserves_every_prior_byte(self):
        # Owner Atridis commit 317262725bf3507a6b66dd1f2d962d822806d338.
        # Only Git checkout line-ending transport is normalized.
        data = (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(blob(data), '97e90791a4011bd7f6ef2922533f92f698557cbd')
        # Isolate the historical sort block; full-native comparisons remain exact.
        data = data.split(b'table.list.copy.fresh-empty:', 1)[0] + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(blob(data), 'b934bc3fe6d8c8f6b9d4ba23972ccb29bd3d00f6')
        before, added = data.split(b'table.list.sort.enum.identity:', 1)
        self.assertEqual(len(before), 134955)
        self.assertEqual(blob(before + b'table.checkpoint.complete: [ok]\n'),
                         'c648f0a577aba3cb19c98ad4effaea4088e1ea1e')
        tail = b'table.list.sort.enum.identity:' + added
        labels = re.findall(rb'^(table\.list\.sort\.[a-z.-]+): \[', tail, re.MULTILINE)
        self.assertEqual([label.decode() for label in labels],
                         ['table.' + c.arguments[0].value for c in observations()]
                         + ['table.list.sort.checkpoint.complete'])
        self.assertEqual(len(data.splitlines()), 3631)
        self.assertEqual(len(tail.splitlines()), 52)
        self.assertTrue(data.endswith(b'table.list.sort.checkpoint.complete: [ok]\n'
                                     b'table.checkpoint.complete: [ok]\n'))
        for marker in (b'[iteration-error]', b'[serialize-error]', b'[limit]', b'[result-error]'):
            self.assertNotIn(marker, tail)
        self.assertEqual(list((ROOT / 'tests/fixtures/native_windows').glob('*.err')), [])

    def test_metadata_transport_preserves_content_check(self):
        data = (ROOT / 'integrational_tests/meta.md').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(metadata_blob(data.replace(b'\n', b'\r\n')),
                         'f76530bce7bd3b8a54055b2390ec7551024c62e2')
        self.assertNotEqual(metadata_blob(data.replace(b'8.3.27.2342', b'8.3.27.2343')),
                            'f76530bce7bd3b8a54055b2390ec7551024c62e2')

    def test_bounded_unique_records_and_full_source_parse(self):
        calls = observations()
        self.assertEqual(len(calls), 27)
        labels = []
        for call in calls:
            label, expression = [a.value for a in call.arguments]
            self.assertRegex(label, r'^list\.sort\.[a-z.-]+$')
            self.assertLess(len(expression), 500)
            parse('Result = ' + expression)
            labels.append(label)
        self.assertEqual(len(set(labels)), 27)
        self.assertEqual(source().count(FINAL), 1)
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_every_record_reaches_sort_or_enum_and_serializes(self):
        with Instrumentation() as h:
            for call in observations():
                label, expression = [a.value for a in call.arguments]
                h.calls.clear()
                with self.subTest(label=label):
                    result = h.run(expression)
                    self.assertIsNotNone(result)
                    if not label.startswith('list.sort.enum.'):
                        # Procedure-in-expression arity controls may reject
                        # before dispatch; every record still has a statement.
                        self.assertEqual(len(result.items), expression.count('|') + 1)
                        command_count = expression.count('|') + 1
                        if label == 'list.sort.arity':
                            command_count = 2  # procedure-as-expression stops before dispatch
                        if label == 'list.sort.repeat':
                            command_count = 4  # two sorts in each fresh receiver
                        self.assertEqual(len(h.calls), command_count)
                        for case in result.items:
                            self.assertNotEqual(case.get_member('After'), None)
                            if label != 'list.sort.arity':
                                self.assertEqual(case.get_member('Status'), 'ok')
                    text = serialization.value_to_string_internal(result)
                    self.assertNotIn('[iteration-error]', text)
                    self.assertNotIn('[limit]', text)
                    self.assertNotIn('raw list/item serialization is forbidden', text)

    def test_enum_identity_uses_types_and_members_not_presentations(self):
        with Instrumentation() as h:
            result = h.run('ТипНаправленияСортировкиПробы()')
            for key in ('TypeRU', 'TypeEN', 'AscAlias', 'DescAlias', 'Distinct'):
                self.assertIs(result.get_member(key), True)
            self.assertEqual(len(result.get_member('Iteration').items), 2)

    def test_ordered_framing_and_completion(self):
        with Instrumentation() as h:
            h.vm.execute(section(BODY))
            self.assertEqual([m.split(': [', 1)[0] for m in h.outputs],
                             ['table.' + c.arguments[0].value for c in observations()] + [FINAL.split(':')[0]])
            self.assertTrue(all('[serialize-error]' not in m for m in h.outputs))
            self.assertTrue(all(not m.endswith(': [error]') for m in h.outputs))

    def test_equal_values_remain_distinguishable_by_item_identity(self):
        with Instrumentation() as h:
            result = h.run('ДействиеСортировкиСписка("numeric", "Список.SortByValue();")')
            self.assertEqual(result.get_member('Status'), 'ok')
            self.assertEqual(result.get_member('After').get_member('Order').items, [4, 3, 2, 1, 0])

    def test_post_error_order_and_saved_ids_are_observable(self):
        with Instrumentation() as h:
            h.fail_after = True
            result = h.run('ДействиеСортировкиСписка("history", "Список.SortByValue();")')
            self.assertEqual(result.get_member('Status'), 'error')
            self.assertEqual(result.get_member('After').get_member('Order').items, [3, 2, 1, 0])
            self.assertEqual([r.get_member('ID') for r in result.get_member('BeforeIDs').items], [4, 0, 2, 3])
            self.assertEqual([r.get_member('ID') for r in result.get_member('AfterIDs').items], [3, 2, 0, 4])
            self.assertTrue(all(r.get_member('Same') for r in result.get_member('Saved').items))
            self.assertIsNotNone(result.get_member('Fields'))

    def test_each_series_has_fresh_receiver(self):
        with Instrumentation() as h:
            h.run('СерияСортировкиСписка("numeric", "Список.SortByValue();|Список.SortByValue();")')
            self.assertEqual(len(h.calls), 2)
            self.assertIsNot(h.calls[0][1], h.calls[1][1])

    def test_count_and_iteration_fail_independently(self):
        with Instrumentation() as h:
            owner = BSLValueList(); items = BSLArray()
            items.items = [owner.add(None), owner.add(None)]
            h.vm.variables.update(owner=owner, saved=items)
            h.vm.module_names.update(('owner', 'saved'))
            with patch.object(BSLValueList, 'count', side_effect=ValueError('synthetic')):
                result = h.run('ПорядокСортировкиСписка(owner, saved)')
                self.assertEqual(result.get_member('Count'), '[error]')
                self.assertEqual(result.get_member('Order').items, [0, 1])
            with patch.object(BSLValueList, '__iter__', side_effect=ValueError('synthetic')):
                result = h.run('ПорядокСортировкиСписка(owner, saved)')
                self.assertEqual(result.get_member('Count'), 2)
                self.assertEqual(result.get_member('Order').items, ['[iteration-error]'])

    def test_id_failure_does_not_hide_order_or_fields(self):
        with Instrumentation() as h, patch.object(BSLValueListItem, 'get_id', side_effect=ValueError('synthetic')):
            result = h.run('ДействиеСортировкиСписка("history", "Список.SortByValue();")')
            self.assertEqual(result.get_member('After').get_member('Order').items, [3, 2, 1, 0])
            self.assertEqual(result.get_member('Saved').items[0].get_member('ID'), '[error]')
            self.assertIsNotNone(result.get_member('Fields'))

    def test_enum_type_codec_failure_preserves_value_and_readback(self):
        with Instrumentation() as h:
            h.fail_type_codec = True
            result = h.run('КодекНаправленияСортировкиПробы(SortDirection.Asc, Истина)')
            self.assertEqual(result.get_member('TypeWrite'), '[error]')
            self.assertNotEqual(result.get_member('Write'), '[error]')
            self.assertTrue(result.get_member('ReadEqual'))

    def test_enum_successful_undefined_read_is_not_hidden(self):
        with Instrumentation() as h:
            h.read_undefined = True
            result = h.run('КодекНаправленияСортировкиПробы(SortDirection.Desc)')
            self.assertFalse(result.get_member('ReadType'))
            self.assertFalse(result.get_member('ReadEqual'))
            self.assertEqual(result.get_member('ReadWrite'), '{"U"}')


if __name__ == '__main__':
    unittest.main()
