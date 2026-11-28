"""Probe instrumentation plus independently supplied native-evidence integrity.

Synthetic sorting deliberately reverses the receiver. No synthetic stream is
saved as native output. Full native gates still read the whole scenario.
"""
from scripts.native_historical_replay import without_value_tree_probes, FILL_EXCLUDE_ORDER_PROBE_BLOCKS, FILL_EXCLUDE_PROBE_BLOCKS, FILL_INCLUDE_PROBE_BLOCKS, DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS
import hashlib
from pathlib import Path
import re
import unittest

from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб сортировки списка.\n', '// Конец компактных проб сортировки списка.\n\n')
BODY = ('// Начало наблюдений сортировки списка.\n', '// Конец наблюдений сортировки списка.\n')
FINAL = 'table.list.sort.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def strip_probe(text):
    text = without_value_tree_probes(text)
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


if __name__ == '__main__':
    unittest.main()
