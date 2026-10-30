"""Synthetic observations only; no native support evidence."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'),
                str(ROOT / 'yadinassi/storage'), str(ROOT / 'tests')]
import params_slot_observer as o
import test_filedb_named_file as f

c = o.loader.catalog_module


def link(marker=1, following=0):
    return bytes((marker,)) + following.to_bytes(4, 'little') + bytes(296)


def source(rows=(), head=0, marker=1, **kwargs):
    return f.named_source(list(rows), reserved=link(marker, head), **kwargs)


def observe(value, **kwargs):
    return o.observe(value.read_at, value.size, **kwargs)


class ParamsSlotTests(unittest.TestCase):
    def test_every_marker_and_unlinked(self):
        value = source([f.named_row('dBnAmEs'), f.named_row(''), link(1), link(255)], head=4)
        result = observe(value)
        self.assertEqual((result['later_zero_count'], result['later_one_count'],
                          result['later_other_count']), (2, 1, 1))
        self.assertEqual((result['filename_zero_count'], result['filename_empty_count'],
                          result['filename_nonempty_count'], result['dbnames_match_count']), (2, 1, 1, 1))
        self.assertEqual((result['linked_nonzero_count'], result['unlinked_nonzero_count']), (1, 1))
        self.assertEqual(result['runtime_support'], 'not_claimed')
        self.assertEqual(result['recipe_sha256'], o.RECIPE_SHA256)
        # Blob body page eight and index page seven must remain unopened.
        self.assertFalse(any(offset // f.P in (7, 8) for offset, _ in value.calls))

    def test_reserved_marker_classes_single_slot(self):
        for marker, expected in ((0, 'zero'), (1, 'one'), (2, 'other'), (255, 'other')):
            result = observe(source(marker=marker))
            self.assertEqual(result['first_marker_class'], expected)
            self.assertEqual(result['chain_outcome'], 'terminated')
            self.assertEqual(result['filename_zero_count'], 0)

    def test_chain_outcomes(self):
        cases = [([link(1, 2), link(2, 0)], 1, 'terminated', 2),
                 ([link(1, 1)], 1, 'cycle', 1),
                 ([link(1, 2), link(2, 1)], 1, 'cycle', 2),
                 ([link(1, 99)], 1, 'out_of_range', 1),
                 ([link()], 0xffffffff, 'out_of_range', 0),
                 ([f.named_row()], 1, 'zero_marker_target', 0)]
        for rows, head, outcome, count in cases:
            with self.subTest(outcome=outcome, count=count):
                result = observe(source(rows, head=head))
                self.assertEqual(result['chain_outcome'], outcome)
                self.assertEqual(result['linked_nonzero_count'], count)

    def test_no_transport_interpretation_duplicates_allowed_ascii_only(self):
        result = observe(source([f.named_row('DBNames'), f.named_row('dbnames'),
                                 f.named_row('ＤＢＮＡＭＥＳ'), f.named_row('DBNames ')]))
        self.assertEqual(result['dbnames_match_count'], 2)

    def test_fullscan_tail_failure_not_early_match(self):
        bad = bytearray(f.named_row(''))
        bad[1:3] = (129).to_bytes(2, 'little')
        with self.assertRaisesRegex(c.InvalidStructure, 'dbnames_filename_length'):
            observe(source([f.named_row(), bytes(bad)]))
        bad[1:5] = b'\x01\x00\x00\xd8'
        with self.assertRaisesRegex(c.UnsupportedLayout, 'dbnames_filename_encoding'):
            observe(source([bytes(bad)]))

    def test_nonzero_does_not_decode_filename(self):
        result = observe(source([b'\x02' + b'\xff' * 300]))
        self.assertEqual(result['later_other_count'], 1)
        self.assertEqual(result['filename_zero_count'], 0)

    def test_schema_empty_geometry_limits(self):
        cases = [(source(lock='1'), c.UnsupportedLayout, 'dbnames_profile_mismatch'),
                 (source(name='PARAMSX'), c.UnsupportedLayout, 'dbnames_table_missing'),
                 (source(data_length=0), c.UnsupportedLayout, 'params_slot_empty_data'),
                 (source(data_length=302), c.InvalidStructure, 'dbnames_record_length'),
                 (source([link()] * 4096), c.ResourceLimit, 'dbnames_slots')]
        for value, error, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(error, code):
                observe(value)

    def test_cross_page_and_maximum_complete_scan(self):
        result = observe(source([f.named_row('DBNames')] * 4095))
        self.assertEqual(result['candidate_slots'], 4096)
        self.assertEqual(result['dbnames_match_count'], 4095)
        # Slot 27 filename straddles the first data-page boundary.
        result = observe(source([f.named_row('x' * 128)] * 28))
        self.assertEqual(result['filename_nonempty_count'], 28)

    def test_mapping_alias_rejected_before_body(self):
        value = source([f.named_row()])
        f.internal(value, 6, f.P, (20,))
        with self.assertRaises(c.UnsupportedSharing):
            observe(value)
        self.assertFalse(any(offset // f.P == 20 for offset, _ in value.calls))

    def test_tail_io_failure_never_returns_partial_counts(self):
        value = source([f.named_row()] * 40)
        def read(offset, length):
            if offset // f.P == 21:
                return b''
            return value.read_at(offset, length)
        with self.assertRaises(c.CatalogError):
            o.observe(read, value.size)

    def test_link_width_endianness_and_no_alternate_probe(self):
        value = source([link()] * 256, head=256)
        result = observe(value)
        self.assertEqual(result['linked_nonzero_count'], 1)
        self.assertEqual(result['chain_outcome'], 'terminated')
        body_calls = [(offset, length) for offset, length in value.calls
                      if offset // f.P >= 20]
        self.assertEqual(len(body_calls), 2 * 257)
        self.assertTrue(all(length in (1, 4) for _, length in body_calls))

    def test_cumulative_budget_exact_boundary_and_consumption(self):
        readers = []
        original = c.CatalogReader
        def capture(*args, **kwargs):
            reader = original(*args, **kwargs)
            readers.append(reader)
            return reader
        with mock.patch.object(c, 'CatalogReader', side_effect=capture):
            result = observe(source([f.named_row(), link()]))
        usage = readers[-1].usage
        for field, count in vars(usage).items():
            if field not in ('output_bytes', 'bytes_processed', 'read_bytes', 'page_reads'):
                continue
            limits = replace(c.CatalogLimits(), **{'max_' + field: count})
            self.assertEqual(observe(source([f.named_row(), link()]), limits=limits), result)
            limits = replace(limits, **{'max_' + field: count - 1})
            with self.assertRaises(c.ResourceLimit):
                observe(source([f.named_row(), link()]), limits=limits)
        bad = bytearray(f.named_row()); bad[1:3] = b'\xff\xff'
        with mock.patch.object(c, 'CatalogReader', side_effect=capture):
            with self.assertRaises(c.InvalidStructure):
                observe(source([bytes(bad)]))
        reader = readers[-1]
        count = reader.usage.read_bytes
        with self.assertRaises(ValueError):
            reader.read_catalog()
        with self.assertRaises(ValueError):
            reader._open_table_data(reader._catalog.tables[0])
        self.assertEqual(reader.usage.read_bytes, count)


if __name__ == '__main__':
    unittest.main()
