"""Unindexed version-9 internal strings over positional tables."""
from decimal import Decimal
import unittest

from tests.native_observations import extract_payload, read_observation
from tests.test_value_table_serialization import OUTPUT
from yadinassi import Interpreter
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.formats.storage.serialization import value_from_string_internal as read
from yadinassi.formats.storage.serialization import value_to_string_internal as write
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.types.type_qualifiers import BSLNumberQualifiers


class PlainTableInternalCodecTests(unittest.TestCase):
    def test_frozen_native_unindexed_bytes_in_both_directions(self):
        native = read_observation(extract_payload(OUTPUT.read_bytes().decode('utf-8'), 'table.codec.table'))
        text = native.get('Write')
        table = BSLValueTable()
        table.columns.add('Имя')
        table.columns.add('Число', BSLTypeDescription('Number'))
        for i in range(1, 4):
            row = table.add()
            row.set_member('Имя', f'row{i}')
            row.set_member('Число', Decimal(i))
        self.assertEqual(write(table), text)
        inverse = read(text)
        self.assertEqual(write(inverse), text)
        self.assertEqual(tuple(inverse.rows[0]), ('row1', Decimal(1)))
        self.assertIs(inverse.rows[0].table, inverse)
        self.assertIs(inverse.columns.items[0].table, inverse)
        inverse.rows[0].set_member('Имя', 'changed')
        self.assertEqual(table.rows[0].get_member('Имя'), 'row1')

    def test_direct_bsl_integer_serializes_as_number_and_restores_decimal(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable;T.Columns.Add("N");'
                   'For I=7 To 8 Do R=T.Add();R.N=I+0;EndDo;')
        self.assertIs(type(list.__getitem__(vm.variables['t'].rows[0], 0)), int)
        vm.execute('Text=ValueToStringInternal(T);Restored=ValueFromStringInternal(Text);')
        self.assertIn('{"N",7}', vm.variables['text'])
        value = vm.variables['restored'].rows[0][0]
        self.assertIs(type(value), Decimal)
        self.assertEqual(value, Decimal(7))
        self.assertEqual(write(vm.variables['restored']), vm.variables['text'])

    def test_qualified_cells_are_validated_without_coercing_snapshot(self):
        table = BSLValueTable()
        table.columns.add('N', BSLTypeDescription('Number', BSLNumberQualifiers(3, 1)))
        row = table.add()
        row.set_member('N', Decimal('1.2'))
        text = write(table)
        self.assertEqual(read(text).rows[0].get_member('N'), Decimal('1.2'))
        with self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
            read(text.replace('{"N",1.2}', '{"N",1.23}', 1))
        list.__setitem__(row, 0, Decimal('1.23'))  # Deliberately malformed host input.
        with self.assertRaisesRegex(ValueError, 'не соответствует'):
            write(table)

    def test_writer_refuses_bad_positional_row_width_and_foreign_owner(self):
        for mutate in (lambda row: list.clear(row), lambda row: setattr(row, 'table', BSLValueTable())):
            table = BSLValueTable()
            table.columns.add('N')
            row = table.add()
            mutate(row)
            with self.assertRaises(ValueError):
                write(table)
