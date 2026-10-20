"""Index codecs grounded in the owner's genuine 1C checkpoint.

The four table.indexes.codec records come from owner commit
3b2fa58484f9dfbd6d296b7f11c373fef184dca5. Native observations are read only.
Defensive/model tests below do not claim additional native stream acceptance.
"""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.native_observations import extract_payload, inverse_stream, read_observation
from yadinassi import Interpreter
from yadinassi.serialization import value_from_string_internal as read
from yadinassi.serialization import value_to_string_internal as write
from yadinassi.structures import BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_tables import BSLCollectionIndex, BSLCollectionIndexes, BSLValueTable
from yadinassi.values import BSLArray, BSLType, equal, to_string


OUTPUT = Path(__file__).resolve().parents[1] / 'integrational_tests/output/collections.out'
COLLECTION_UUID = '3a461c5c-0a17-430a-ae05-90890129a7da'
INDEX_UUID = '4523f487-9cd3-4779-89f5-92023e88037b'
TABLE_UUID = 'acf6192e-81ca-46ef-93a6-5a6968b78663'
FORMAT_ERROR = 'Ошибка формата потока'
D = Decimal


def sample():
    table = BSLValueTable()
    for name in ('Key', 'Second', 'Amount'):
        table.columns.add(name)
    for number in (1, 2):
        row = table.add()
        for column, cell in zip(table.columns, ('a', D(number), D(number))):
            row.cells[column] = cell
    return table


def plain(value):
    if type(value) is BSLArray:
        return [plain(item) for item in value]
    if type(value) is BSLStructure:
        return {key: plain(item) for key, item in value._items.values()}
    return value


def table_view(table):
    return {'Table': {'Count': D(len(table.rows)),
                      'Names': [column.name for column in table.columns],
                      'Rows': [list(row) for row in table.rows]},
            'Indexes': {'Count': D(len(table.indexes.items)),
                        'Items': [list(index) for index in table.indexes]}}


class NativeIndexCodecTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.output = OUTPUT.read_bytes().decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')

    def native(self, name):
        return read_observation(extract_payload(self.output, 'table.indexes.codec.' + name))

    def assert_type_record(self, record, value):
        kind = type_of(value)
        self.assertEqual(write(kind), record.get('TypeWrite'))
        restored = read(record.get('TypeWrite'))
        self.assertIs(restored, kind)
        self.assertEqual(plain(record.get('TypeRead')),
                         {'Type': 'Тип', 'Equal': equal(restored, kind),
                          'Stable': write(restored) == record.get('TypeWrite')})

    def test_all_three_standalone_records_match_exact_native_fields(self):
        table = sample()
        index = table.indexes.add('Key,Second')
        cases = [('empty', BSLValueTable().indexes, COLLECTION_UUID),
                 ('collection', table.indexes, COLLECTION_UUID),
                 ('index', index, INDEX_UUID)]
        for name, value, identifier in cases:
            with self.subTest(name=name):
                native = self.native(name)
                self.assertEqual(set(native._items),
                                 {'type', 'text', 'view', 'typewrite', 'typeread',
                                  'write', 'readtype', 'readwrite', 'readview', 'equal'})
                self.assertEqual(native.get('Type'), str(type_of(value)))
                self.assertEqual(native.get('Text'), to_string(value))
                expected_view = (list(value) if type(value) is BSLCollectionIndex else
                                 {'Count': D(len(value.items)), 'Items': [list(i) for i in value]})
                self.assertEqual(plain(native.get('View')), expected_view)
                self.assertEqual(write(value), '{"#",' + identifier + '}')
                self.assertEqual(write(value), native.get('Write'))
                self.assert_type_record(native, value)
                restored = read(native.get('Write'))
                self.assertIsNone(restored)
                self.assertEqual(native.get('ReadType'), str(type_of(restored)))
                self.assertEqual(native.get('ReadWrite'), write(restored))
                self.assertEqual(native.get('ReadView'), '[error]')
                self.assertIs(native.get('Equal'), equal(value, restored))

    def test_indexed_table_matches_native_bytes_and_complete_inverse(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Amount')
        native = self.native('table')
        self.assertEqual(set(native._items),
                         {'type', 'text', 'view', 'typewrite', 'typeread',
                          'write', 'readtype', 'readwrite', 'readview', 'equal'})
        self.assertEqual(native.get('Type'), str(type_of(table)))
        self.assertEqual(str(type_of(table)), 'Таблица значений')
        self.assertEqual(native.get('Text'), to_string(table))
        self.assertEqual(plain(native.get('View')), table_view(table))
        self.assert_type_record(native, table)
        self.assertEqual(write(table), native.get('Write'))
        self.assertTrue(write(table).endswith(',\n{0,2,\n{0,2,0,1},\n{0,1,2}\n}\n}\n}'))
        restored = read(native.get('Write'))
        self.assertIs(type(restored), BSLValueTable)
        self.assertEqual(native.get('ReadType'), str(type_of(restored)))
        self.assertEqual(write(restored), inverse_stream(native))
        self.assertEqual(plain(native.get('ReadView')), table_view(restored))
        self.assertIs(native.get('Equal'), equal(table, restored))
        self.assertIsNot(restored, table)
        self.assertIs(restored.indexes.table, restored)
        for original, index in zip(table.indexes, restored.indexes):
            self.assertIsNot(index, original)
            self.assertIs(index.table, restored)
            self.assertFalse(index._deleted)
            for column in index.columns:
                self.assertIs(column.table, restored)
                self.assertTrue(any(column is item for item in restored.columns))
        selected = restored.find_rows(BSLStructure('Key,Second', 'a', D(2)))
        self.assertEqual(selected.items, [restored.rows[1]])
        restored.rows[1].set_member('Key', 'changed')
        self.assertEqual(restored.find_rows(BSLStructure('Key,Second', 'a', D(2))).items, [])
        self.assertEqual(table.rows[1].get_member('Key'), 'a')

    def test_observed_bilingual_type_identities_and_unsupported_constructors(self):
        table = sample()
        index = table.indexes.add('Key,Second')
        identity = read_observation(extract_payload(self.output, 'table.indexes.identity'))
        extra = identity.get('Extra')
        for value, names, fields in [
                (table.indexes, ('CollectionIndexes', 'ИндексыКоллекции'),
                 ('CollectionType', 'RussianCollection')),
                (index, ('CollectionIndex', 'ИндексКоллекции'),
                 ('IndexType', 'RussianIndex'))]:
            for name, field in zip(names, fields):
                with self.subTest(name=name):
                    self.assertIs(extra.get(field), True)
                    self.assertIs(type_of(value), type_by_name(name))
                    self.assertIs(type_by_name(name.swapcase()), type_of(value))
        for name in ('collection', 'index'):
            self.assertEqual(extract_payload(self.output, 'table.indexes.constructor.' + name), 'error')
        for name in ('CollectionIndexes', 'CollectionIndex', 'ИндексыКоллекции', 'ИндексКоллекции'):
            with self.subTest(constructor=name):
                output = []
                Interpreter(output.append).execute(
                    'Try value = New ' + name + '(); Except Message("caught"); EndTry;')
                self.assertEqual(output, ['caught'])


class DefensiveIndexCodecTests(unittest.TestCase):
    """Safe canonical models; these are not synthetic native observations."""

    def indexed(self):
        table = sample()
        table.indexes.add('Key,Second')
        table.indexes.add('Amount')
        return table

    def test_general_order_empty_repeated_columns_and_duplicate_definitions(self):
        table = sample()
        for columns in ('', 'Amount,Key', 'Key,Key', 'Key,Key'):
            table.indexes.add(columns)
        restored = read(write(table))
        self.assertEqual([list(index) for index in restored.indexes],
                         [[], ['Amount', 'Key'], ['Key', 'Key'], ['Key', 'Key']])
        self.assertIsNot(restored.indexes.items[2], restored.indexes.items[3])
        self.assertEqual(write(restored), write(table))
        empty = BSLValueTable()
        empty.indexes.add()
        self.assertEqual([list(index) for index in read(write(empty)).indexes], [[]])

    def test_column_identity_survives_names_and_canonical_position_changes(self):
        table = self.indexed()
        key = table.columns.items[0]
        key.set_member('Name', '')
        table.columns.move(key, D(2))
        restored = read(write(table))
        index = restored.indexes.items[0]
        self.assertIs(index.columns[0], restored.columns.items[2])
        self.assertEqual(list(index), ['', 'Second'])
        self.assertEqual(write(restored), write(table))

    def test_nested_children_are_opaque_and_table_snapshots_are_independent(self):
        table = self.indexed()
        graph = BSLArray()
        graph.items = [table, table.indexes, table.indexes.items[0], table]
        restored = read(write(graph))
        self.assertEqual(restored.items[1:3], [None, None])
        left, right = restored.items[0], restored.items[3]
        self.assertIsNot(left, right)
        self.assertIsNot(left.indexes, right.indexes)
        self.assertIsNot(left.indexes.items[0], right.indexes.items[0])
        left.columns.items[0].set_member('Name', 'Changed')
        self.assertEqual(list(right.indexes.items[0]), ['Key', 'Second'])

    def test_unknown_index_record_shapes_and_uuids_are_rejected(self):
        for identifier in (COLLECTION_UUID, INDEX_UUID):
            for payload in ('{"#",' + identifier + ',{0}}',
                            '{"#",' + identifier + ',0}',
                            '{"T",' + identifier + ',0}'):
                with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(payload)
        with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
            read('{"#",00000000-0000-0000-0000-000000000000}')

    def test_malformed_index_metadata_is_rejected_without_partial_results(self):
        stream = write(self.indexed())
        tail = '{0,2,\n{0,2,0,1},\n{0,1,2}\n}'
        self.assertIn(tail, stream)
        bad_tails = [
            '{1,2,{0,2,0,1},{0,1,2}}', '{0}', '{0,-1}', '{0,02}',
            '{0,"2",{0,2,0,1},{0,1,2}}', '{0,1,{0,2,0,1},{0,1,2}}',
            '{0,2,{0,2,0,1}}', '{0,1,{1,2,0,1}}', '{0,1,{0,3,0,1}}',
            '{0,1,{0,1,3}}', '{0,1,{0,1,-1}}', '{0,1,{0,1,1.5}}',
            '{0,1,{0,1,"1"}}', '{0,1,{0,1,01}}', '{0,1,0}',
            '{0,1,{0,0,0}}', '{0,0,{0,0}}',
        ]
        for invalid in bad_tails:
            with self.subTest(tail=invalid), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(stream.replace(tail, invalid))
        self.assertEqual(write(read(stream)), stream)

    def test_oversize_counts_and_total_index_references_are_bounded(self):
        table = BSLValueTable()
        table.columns.add('Key')
        for _ in range(4):
            table.indexes.add('Key,Key')
        stream = write(table)
        with patch('yadinassi.serialization._MAX_NODES', 12):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                write(table)
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read(stream)
        for value in ('{0,10001}', '{0,100000000000000000000000}',
                      '{0,1,{0,10001}}'):
            empty = write(BSLValueTable())
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read(empty.replace('{0,0}', value))

    def test_host_corrupted_index_ownership_is_rejected(self):
        for change in ('collection-owner', 'index-owner', 'foreign-column', 'removed-column',
                       'deleted-index', 'deleted-column', 'non-index'):
            with self.subTest(change=change):
                table = self.indexed()
                foreign = sample()
                index = table.indexes.items[0]
                if change == 'collection-owner':
                    table.indexes = foreign.indexes
                elif change == 'index-owner':
                    index.table = foreign
                elif change == 'foreign-column':
                    index.columns = [foreign.columns.items[0]]
                elif change == 'removed-column':
                    table.columns.items.remove(index.columns[0])
                elif change == 'deleted-index':
                    index._deleted = True
                elif change == 'deleted-column':
                    index.columns[0]._deleted = True
                else:
                    table.indexes.items.append(object())
                with self.assertRaisesRegex(ValueError, 'индекс'):
                    write(table)

    def test_deleted_standalone_children_still_follow_opaque_policy(self):
        table = self.indexed()
        index = table.indexes.items[0]
        table.indexes.clear()
        self.assertEqual(write(index), '{"#",' + INDEX_UUID + '}')
        self.assertIsNone(read(write(index)))
        self.assertEqual(write(table.indexes), '{"#",' + COLLECTION_UUID + '}')


if __name__ == '__main__':
    unittest.main()
