"""ValueTable streams from the owner's committed collections checkpoint.

Native fixtures are read only. Defensive rejection/resource tests describe
Yadinassi's bounded subset, not additional claims about native 1C behavior.
"""
from tests.native_observations import (read_observation, inverse_stream, assert_snapshot,
                                       assert_type_inverse, assert_nested, extract_payload)

from decimal import Decimal
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi.serialization import value_from_string_internal as read
from yadinassi.serialization import value_to_string_internal as write
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers
from yadinassi.type_values import type_of
from yadinassi.value_tables import BSLValueTable
from yadinassi.values import BSLArray


OUTPUT = Path(__file__).resolve().parents[1] / 'tests/fixtures/native_windows/collections.out'


def array(*items):
    result = BSLArray()
    result.items = list(items)
    return result


def sample():
    table = BSLValueTable()
    name = table.columns.add('Имя')
    number = table.columns.add('Число', BSLTypeDescription('Number'))
    for index in range(1, 4):
        row = table.add()
        row.cells[name] = 'row' + str(index)
        row.cells[number] = Decimal(index)
    return table


class ValueTableNativeCodecTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.output = OUTPUT.read_bytes().decode('utf-8')

    def native(self, label):
        return read_observation(extract_payload(self.output, label))

    def test_four_types_and_standalone_streams(self):
        table = sample()
        for label, value in [('empty', BSLValueTable()), ('table', table),
                             ('columns', table.columns), ('column', table.columns.items[0]),
                             ('row', table.rows[0])]:
            with self.subTest(label=label):
                native = self.native('table.codec.' + label)
                assert_snapshot(self, native, value, table=True)
                restored = read(native.get("Write"))
                if label in ('columns', 'column', 'row'):
                    self.assertIsNone(restored)

    def test_inverse_table_has_fresh_owned_rows_and_columns(self):
        table = sample()
        restored = read(self.native('table.codec.table').get('Write'))
        self.assertIsNot(restored, table)
        self.assertEqual(len(restored.rows), 3)
        self.assertEqual(len(restored.columns.items), 2)
        for index, row in enumerate(restored.rows, 1):
            self.assertIs(row.table, restored)
            self.assertEqual(row.cells[restored.columns.items[0]], 'row' + str(index))
            self.assertEqual(row.cells[restored.columns.items[1]], Decimal(index))
        for column in restored.columns.items:
            self.assertIs(column.table, restored)
        restored.rows[0].cells[restored.columns.items[0]] = 'changed'
        self.assertEqual(table.rows[0].cells[table.columns.items[0]], 'row1')

    def test_native_object_graph_drops_standalone_children(self):
        table = sample()
        graph = array(table, table.rows[0], table.columns, table.columns.items[0])
        record = self.native('table.links.codec-object-graph').get('Extra').get('Codec')
        assert_snapshot(self, record, graph, table=True)
        self.assertEqual(write(graph), record.get('Write'))
        restored = read(record.get('Write'))
        self.assertEqual(restored.items[1:], [None, None, None])
        self.assertIs(restored.items[0].rows[0].table, restored.items[0])
        self.assertEqual(write(restored), inverse_stream(record))
        assert_nested(self, record, graph)


class ValueTableDefensiveCodecTests(unittest.TestCase):
    def test_rejects_unknown_layout_and_inconsistent_metadata(self):
        stream = write(sample())
        bad = [stream.replace('{9,', '{8,', 1),
               stream.replace('{2,2,0,0,1,1,', '{2,2,0,0,1,0,', 1),
               stream.replace('{1,3,', '{1,4,', 1),
               stream.replace('{2,0,2,', '{2,9,2,', 1),
               stream.replace('},1,2},', '},1,9},', 1),
               stream.replace('{0,0}\n}', '{0,1}\n}', 1),
               stream.replace('{0,"Имя",', '{1,"Имя",', 1),
               stream.replace('{1,"Число",', '{1,"Имя",', 1)]
        for value in bad:
            with self.subTest(value=value):
                self.assertNotEqual(value, stream)
                with self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                    read(value)

    def test_inverse_rejects_payloads_that_violate_column_schema(self):
        stream = write(sample())
        for payload in ['{"S","1"}', '{"U"}', '{"L"}', '{"B",1}',
                        '{"#",51e7a0d2-530b-11d4-b98a-008048da3034,{0}}']:
            with self.subTest(payload=payload):
                malformed = stream.replace('{"N",1},0}', payload + ',0}', 1)
                self.assertNotEqual(malformed, stream)
                with self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                    read(malformed)

    def test_qualifier_inconsistent_payloads_are_rejected_without_coercion(self):
        cases = [(BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(3), Decimal(1))),
                  Decimal('1.2'), '{"N",1.2}', '{"N",1.23}'),
                 (BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(2))),
                  'ab', '{"S","ab"}', '{"S","abc"}')]
        for description, value, original, invalid in cases:
            with self.subTest(description=description):
                table = BSLValueTable()
                column = table.columns.add('Value', description)
                row = table.add()
                row.cells[column] = value
                stream = write(table)
                malformed = stream.replace(original, invalid, 1)
                self.assertNotEqual(malformed, stream)
                with self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                    read(malformed)
                row.cells[column] = Decimal('1.23') if type(value) is Decimal else 'abc'
                with self.assertRaisesRegex(ValueError, 'не соответствует'):
                    write(table)

    def test_host_mutated_widths_are_bounded_before_formatting(self):
        table = sample()
        column = table.columns.items[0]
        for width in [None, '4', 4, Decimal('NaN'), Decimal('Infinity'),
                      Decimal('-1'), Decimal('1.5'), Decimal(2 ** 32), Decimal('1e1000000')]:
            with self.subTest(width=width):
                column.width = width
                with self.assertRaisesRegex(ValueError, 'ширина'):
                    write(table)
        # Formatting this zero directly would allocate a huge fractional string.
        column.width = Decimal('0e-1000000000')
        self.assertEqual(write(table), write(sample()))

    def test_inverse_rejects_invalid_width_and_keeps_union_defaults(self):
        stream = write(sample())
        for width in ['-1', '1.5', '4294967296']:
            malformed = stream.replace('},"",0}', '},"",' + width + '}', 1)
            self.assertNotEqual(malformed, stream)
            with self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                read(malformed)
        table = BSLValueTable()
        column = table.columns.add('Value', BSLTypeDescription('String,Number'))
        table.add()
        restored = read(write(table))
        self.assertIsNone(restored.rows[0].cells[restored.columns.items[0]])

    def test_cycles_and_resource_budgets(self):
        table = sample()
        table.rows[0].cells[table.columns.items[0]] = table
        with self.assertRaisesRegex(ValueError, 'циклические'):
            write(table)
        table = sample()
        stream = write(table)
        with patch('yadinassi.serialization._MAX_NODES', 4):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                write(table)
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read(stream)

    def test_canonical_snapshot_shapes_and_column_metadata(self):
        # Bounded model checks; only the native fixture tests claim exact 1C bytes.
        for nc, nr in [(0, 2), (1, 0), (1, 1), (3, 2)]:
            with self.subTest(columns=nc, rows=nr):
                table = BSLValueTable()
                for index in range(nc):
                    table.columns.add('Column' + str(index), BSLTypeDescription('String'),
                                      'A "quoted" title', Decimal(14))
                for _ in range(nr):
                    table.add()
                restored = read(write(table))
                self.assertEqual(len(restored.rows), nr)
                self.assertEqual(len(restored.columns.items), nc)
                self.assertEqual(write(restored), write(table))
                for column in restored.columns.items:
                    self.assertEqual(column.title, 'A "quoted" title')
                    self.assertEqual(column.width, Decimal(14))

    def test_repeated_tables_are_separate_snapshots(self):
        table = sample()
        restored = read(write(array(table, table)))
        self.assertIsNot(restored.items[0], restored.items[1])
        self.assertIsNot(restored.items[0].rows[0], restored.items[1].rows[0])

    def test_nested_scalar_collections_are_independent_snapshots(self):
        table = sample()
        table.rows[0].cells[table.columns.items[0]] = array('nested', Decimal(7))
        restored = read(write(table))
        cell = restored.rows[0].cells[restored.columns.items[0]]
        self.assertEqual(cell.items, ['nested', Decimal(7)])
        self.assertIsNot(cell, table.rows[0].cells[table.columns.items[0]])


if __name__ == '__main__':
    unittest.main()
