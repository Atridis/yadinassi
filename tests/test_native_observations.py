"""Synthetic parser/schema fixtures; none are additional native evidence."""
import unittest
from decimal import Decimal

from tests.native_observations import (read_observation, extract_payload,
                                       inverse_stream, assert_snapshot)
from yadinassi.serialization import value_to_string_internal as write
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray


def encoded(value):
    # Mirrors documented presentation escaping, only for synthetic parser tests.
    return write(value).replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t')


class SyntheticObservationReaderTests(unittest.TestCase):
    def test_legacy_string_preserves_intrinsic_crlf_and_literal_escapes(self):
        value = 'left\r\nright\\n\\r;="quoted"🙂'
        self.assertEqual(read_observation(write(value)), value)
        self.assertEqual(extract_payload('sample: [' + write(value) + ']\n', 'sample'), write(value))

    def test_type_paths_preserve_container_kind_count_and_exact_escaped_scalar(self):
        value = 'first\r\nlast\\n;value.Fake={"B",1};"quote"\t🙂'
        payload = ('value=structure(3);value.Text=' + encoded(value) +
                   ';value.Items=array(2);value.Items.0={"U"};value.Items.1=structure(0)'
                   ';value.Count={"N",7}')
        result = read_observation(payload)
        self.assertIs(type(result), BSLStructure)
        self.assertEqual(result.get('Text'), value)
        self.assertIs(type(result.get('Items')), BSLArray)
        self.assertIsNone(result.get('Items').items[0])
        self.assertIs(type(result.get('Items').items[1]), BSLStructure)
        self.assertEqual(result.get('Count'), Decimal(7))
        self.assertIs(type(read_observation('value=array(0)')), BSLArray)
        self.assertIs(type(read_observation('value=structure(0)')), BSLStructure)

    def test_table_flat_paths_and_inline_containers_preserve_all_fields(self):
        raw = 'raw\r\nstream\\n;=[]\t\u2028"'
        payload = ('\n  TypeRead.Equal={"B",1}\n  TypeRead.Stable={"B",0}\n'
                   '  View.Rows=[[{"N",1}; ' + encoded(raw) + ']; []]\n'
                   '  View.Columns=[{{"S","Name"}={"S","A"}; {"S","Empty"}={}}]\n'
                   '  Write=' + encoded(raw) + '\n')
        value = read_observation(payload)
        self.assertIs(value.get('TypeRead').get('Equal'), True)
        self.assertIs(value.get('TypeRead').get('Stable'), False)
        self.assertEqual(value.get('Write'), raw)
        self.assertEqual(value.get('View').get('Rows').items[0].items[1], raw)
        self.assertEqual(value.get('View').get('Columns').items[0].get('Name'), 'A')

    def test_inline_compact_scalar_requires_explicit_escape_mode(self):
        value = '\\n\r\n'
        self.assertEqual(read_observation(encoded(value), compact=True), value)

    def test_rejects_malformed_paths_counts_escapes_and_trailing_data(self):
        cases = [
            'value=structure(1);value.A={"N",1};value.A={"N",2}',
            'value=structure(2);value.A={"N",1};value.a={"N",2}',
            'value=structure(1)', 'value=structure(0);value.A={"N",1}',
            'value=array(2);value.0={"N",1}',
            'value=array(1);value.1={"N",1}',
            'value=array(1);value.01={"N",1}',
            'value=structure(1);value.A.B={"N",1}',
            'value={"N",1};value.A={"N",2}',
            'value={"S","bad\\q"}', 'value={"S","truncated\\',
            'value={"N",1}junk', '{"N",1}junk',
            '\n A={"N",1}\n A={"N",2}\n',
            '\n A={"N",1}\n a={"N",2}\n',
            '\n A={"N",1}\n A.B={"N",2}\n',
            '[{"N",1};]', '[{"N",1}]junk',
            '{{"S","A"}={"N",1}; {"S","a"}={"N",2}}',
            'value=array(10001)', '[' * 66 + ']' * 66,
        ]
        for payload in cases:
            with self.subTest(payload=payload[:90]), self.assertRaises(ValueError):
                read_observation(payload)

    def test_aggregate_declared_elements_rejected_before_large_allocations(self):
        payload = ('value=structure(2);value.A=array(6000);value.B=array(6000)')
        with self.assertRaisesRegex(ValueError, 'aggregate container limit'):
            read_observation(payload)

    def test_implicit_path_ancestors_share_the_observation_budget(self):
        payload = '\n'.join('Root' + str(index) + '.Child' * 60 + '={"N",1}'
                            for index in range(170))
        with self.assertRaisesRegex(ValueError, 'aggregate path limit'):
            read_observation(payload)

    def test_table_snapshot_requires_both_view_fields(self):
        # Deliberately synthetic incomplete snapshot, never a native fixture.
        from yadinassi.value_tables import BSLValueTable
        from yadinassi.type_values import type_of
        table = BSLValueTable()
        nested = BSLArray(); nested.add(table)
        record = BSLStructure('Type,Text,Write,TypeWrite,ReadType,ReadWrite,TypeRead,Equal,Nested',
            type_of(table), str(table), write(table), write(type_of(table)),
            type_of(table), write(table), write(type_of(table)), False, write(nested))
        with self.assertRaises(AssertionError):
            assert_snapshot(self, record, table, table=True)
        record.insert('View', BSLStructure())
        with self.assertRaises(AssertionError):
            assert_snapshot(self, record, table, table=True)

    def test_missing_and_duplicate_labels_rejected(self):
        with self.assertRaises(ValueError):
            extract_payload('other: [{"N",1}]\n', 'sample')
        with self.assertRaises(ValueError):
            extract_payload('sample: [{"N",1}]\nsample: [{"N",2}]\n', 'sample')

    def test_inverse_contract_keeps_different_stream_exact_and_flags_typed(self):
        raw = '{"S","a\r\nb"}'
        record = BSLStructure('Write,ReadWriteEqual,ReadWrite', 'original', False, raw)
        self.assertEqual(inverse_stream(record), raw)
        equal_record = BSLStructure('Write,ReadWriteEqual', raw, True)
        self.assertEqual(inverse_stream(equal_record), raw)
        table_record = BSLStructure('Write,ReadWrite', raw, 'same-as-Write')
        self.assertEqual(inverse_stream(table_record), raw)
        for record in [BSLStructure('Write,ReadWriteEqual', raw, 'True'),
                       BSLStructure('Write,ReadWriteEqual', raw, False),
                       BSLStructure('Write,ReadWriteEqual,ReadWrite', raw, False, raw),
                       BSLStructure('Write,ReadWriteEqual,ReadWrite', raw, True, raw)]:
            with self.assertRaises(AssertionError):
                inverse_stream(record)


if __name__ == '__main__':
    unittest.main()
