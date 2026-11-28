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
from yadinassi.formats.storage.serialization import value_from_string_internal as read
from yadinassi.formats.storage.serialization import value_to_string_internal as write
from yadinassi.formats.storage.value_storage_table import TableSnapshotError
from yadinassi.collections.structures import BSLStructure
from yadinassi.types.type_values import type_by_name, type_of
from yadinassi.collections.value_tables import BSLCollectionIndex, BSLCollectionIndexes, BSLValueTable
from yadinassi.types.values import BSLArray, BSLType, equal, to_string


OUTPUT = Path(__file__).resolve().parents[1] / 'tests/fixtures/native_windows/collections.out'
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
        for position, cell in enumerate(('a', D(number), D(number))):
            row.set(position, cell)
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
                        'Items': [[table.columns.items[i].name for i in signature]
                                  for signature in table.indexes.items]}}


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
        self.assertEqual(restored.indexes.items, table.indexes.items)
        self.assertEqual(restored._search.declarations, {(0, 1), (2,)})
        self.assertEqual(restored._search.cache, {})
        for signature in restored.indexes.items:
            for position in signature:
                self.assertIs(restored.columns.items[position].table, restored)
                self.assertIsNot(restored.columns.items[position], table.columns.items[position])
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

    def test_canonical_composites_and_declaration_order(self):
        table = sample()
        handle = table.indexes.add('Key,Amount')
        table.indexes.add('Second')
        self.assertEqual(list(handle), ['Key', 'Amount'])
        restored = read(write(table))
        self.assertEqual(restored.indexes.items, [(0, 2), (1,)])
        self.assertEqual([list(index) for index in restored.indexes],
                         [['Key', 'Amount'], ['Second']])
        self.assertEqual(write(restored), write(table))
        for unsupported in ('', 'Key,Key', 'Key,Amount'):
            with self.subTest(unsupported=unsupported):
                table = sample()
                table.indexes.add('Key,Amount')
                added = table.indexes.add(unsupported)
                self.assertIs(table.indexes.get_index(1), added)
                with self.assertRaisesRegex(TableSnapshotError, 'unsupported index declaration'):
                    write(table)

    def test_column_identity_survives_rename(self):
        table = self.indexed()
        table.columns.items[0].set_member('Name', '')
        restored = read(write(table))
        self.assertEqual(restored.indexes.items[0], (0, 1))
        self.assertEqual([restored.columns.items[position].name
                          for position in restored.indexes.items[0]], ['', 'Second'])
        self.assertEqual(write(restored), write(table))

    def test_nested_index_collection_is_opaque_and_table_snapshots_are_independent(self):
        table = self.indexed()
        graph = BSLArray()
        graph.items = [table, table.indexes, table]
        restored = read(write(graph))
        self.assertIsNone(restored.items[1])
        left, right = restored.items[0], restored.items[2]
        self.assertIsNot(left, right)
        self.assertIsNot(left.indexes, right.indexes)
        self.assertIsNot(left._search.declarations, right._search.declarations)
        left.indexes.clear()
        left.columns.items[0].set_member('Name', 'Changed')
        self.assertEqual(right.indexes.items, [(0, 1), (2,)])
        self.assertEqual(right.columns.items[0].name, 'Key')

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
            '{0,1,{0,0,0}}', '{0,0,{0,0}}', '{0,1,{0,0}}',
            '{0,1,{0,2,1,0}}', '{0,1,{0,2,0,0}}', '{0,2,{0,1,0},{0,1,0}}',
        ]
        for invalid in bad_tails:
            with self.subTest(tail=invalid), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(stream.replace(tail, invalid))
        self.assertEqual(write(read(stream)), stream)

    def test_oversize_counts_and_total_index_references_are_bounded(self):
        table = BSLValueTable()
        for name in ('Key', 'Second', 'Amount'):
            table.columns.add(name)
        for definition in ('Key,Second', 'Key,Amount', 'Second,Amount', 'Key,Second,Amount'):
            table.indexes.add(definition)
        stream = write(table)
        with patch('yadinassi.formats.storage.serialization._MAX_NODES', 12):
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
        for change in ('collection-owner', 'foreign-column', 'removed-position',
                       'declaration-mismatch', 'duplicate', 'non-index'):
            with self.subTest(change=change):
                table = self.indexed()
                if change == 'collection-owner':
                    table.indexes = sample().indexes
                elif change == 'foreign-column':
                    handle = table.indexes.get_index(0)
                    handle._columns = (sample().columns.items[0], table.columns.items[1])
                elif change == 'removed-position':
                    table.indexes.items[0] = (3,)
                elif change == 'declaration-mismatch':
                    table._search.declarations.remove((0, 1))
                elif change == 'duplicate':
                    table.indexes.items[1] = (0, 1)
                else:
                    table.indexes.items[0] = object()
                # Container/search ownership errors originate in the wire
                # writer; bad declarations are rejected by its shared snapshot
                # validator before they reach the serialized stream.
                if change in ('collection-owner', 'declaration-mismatch'):
                    with self.assertRaisesRegex(ValueError, 'недопустимая коллекция индексов'):
                        write(table)
                else:
                    with self.assertRaises(TableSnapshotError):
                        write(table)

    def test_direct_bsl_typed_index_roundtrip_and_live_write(self):
        vm = Interpreter()
        try:
            vm.execute('T=New ValueTable; T.Columns.Add("Key", New TypeDescription("String")); '
                       'R=T.Add(); R.Key="x"; T.Indexes.Add("Key"); '
                       'S=ValueToStringInternal(T); C=ValueFromStringInternal(S);')
            self.assertEqual(vm.variables['c']._search.cache, {})
            vm.execute('M=C.FindRows(New Structure("Key","x")); Before=M.Count(); '
                       'M[0].Key="y"; After=C.FindRows(New Structure("Key","x")).Count(); '
                       'Original=T.FindRows(New Structure("Key","x")).Count();')
            self.assertEqual((vm.variables['before'], vm.variables['after'], vm.variables['original']),
                             (D(1), D(0), D(1)))
        finally:
            vm.close()

    def test_live_cache_is_not_part_of_the_stream(self):
        table = self.indexed()
        stream = write(table)
        table.find_rows(BSLStructure('Key,Second', 'a', D(2)))
        self.assertTrue(table._search.cache)
        self.assertEqual(write(table), stream)
        self.assertEqual(read(stream)._search.cache, {})

    def test_deleted_standalone_children_still_follow_opaque_policy(self):
        table = self.indexed()
        index = table.indexes.get_index(0)
        table.indexes.clear()
        self.assertEqual(write(index), '{"#",' + INDEX_UUID + '}')
        self.assertIsNone(read(write(index)))
        self.assertEqual(write(table.indexes), '{"#",' + COLLECTION_UUID + '}')


if __name__ == '__main__':
    unittest.main()
