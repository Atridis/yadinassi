"""Synthetic same-reader seam regression, not native content evidence."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'),
                str(ROOT / 'yadinassi/storage'), str(ROOT / 'tests')]
import filedb_catalog as c
import params_extraction as old
import test_native_1c_db_oracle_extraction as fixtures


class SharedDBNamesReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = old.load_reader(ROOT / 'yadinassi/storage/filedb_named_file.py')

    def profile(self):
        return self.module.DBNamesProfile(declarations=old.DECLARATIONS,
                                         recordlock='0', format_item=0)

    def reader(self, value, *, limits=None):
        reader = c.CatalogReader(value.read_at, value.size, limits=limits)
        return reader, reader.read_catalog()

    def extract(self, reader, catalog, **changes):
        return self.module._read_dbnames_from_catalog(reader, catalog,
            profile=changes.pop('profile', self.profile()), **changes)

    def test_same_result_and_usage_as_unchanged_public_api(self):
        value = fixtures.source()
        expected = self.module.read_dbnames(value.read_at, value.size, profile=self.profile())
        reader, catalog = self.reader(fixtures.source())
        before = reader.usage
        with mock.patch.object(c.CatalogReader, 'read_catalog', side_effect=AssertionError('second scan')):
            actual = self.extract(reader, catalog)
        self.assertEqual(actual, expected)
        self.assertIs(reader._catalog, catalog)
        self.assertGreater(reader.usage.output_bytes, before.output_bytes)
        self.assertEqual(actual.usage.catalog, reader.usage)

    def test_equal_copy_foreign_and_incomplete_catalog_never_read(self):
        value = fixtures.source(); reader, catalog = self.reader(value)
        other, other_catalog = self.reader(fixtures.source())
        before = len(value.calls)
        for candidate in (replace(catalog), other_catalog, None):
            with self.assertRaises(ValueError): self.extract(reader, candidate)
        self.assertEqual(len(value.calls), before)
        fresh = c.CatalogReader(value.read_at, value.size)
        with self.assertRaises(ValueError): self.extract(fresh, catalog)
        self.assertIsNone(fresh._catalog)
        self.assertIsNot(other._catalog, catalog)

    def test_success_and_preopen_are_single_use(self):
        value = fixtures.source(); reader, catalog = self.reader(value)
        self.extract(reader, catalog); before = len(value.calls)
        with self.assertRaises(ValueError): self.extract(reader, catalog)
        self.assertEqual(len(value.calls), before)
        reader, catalog = self.reader(fixtures.source())
        reader._open_table_data(catalog.tables[0])
        with self.assertRaises(ValueError): self.extract(reader, catalog)

    def test_failed_profile_or_argument_consumes_identical_reader(self):
        for mismatch in (False, True):
            value = fixtures.source(lock='1' if mismatch else '0')
            bad = self.profile() if mismatch else object()
            reader, catalog = self.reader(value)
            with self.assertRaises((c.UnsupportedLayout, ValueError)):
                self.extract(reader, catalog, profile=bad)
            before = len(value.calls)
            self.assertTrue(reader._dbnames_attempted)
            with self.assertRaises(ValueError): self.extract(reader, catalog)
            self.assertEqual(len(value.calls), before)

    def test_cumulative_catalog_budget_is_not_reset_and_failure_is_consumed(self):
        value = fixtures.source()
        complete = self.module.read_dbnames(value.read_at, value.size, profile=self.profile())
        total = complete.usage.catalog.output_bytes
        value = fixtures.source()
        reader, catalog = self.reader(value, limits=c.CatalogLimits(max_output_bytes=total - 1))
        before = reader.usage.output_bytes
        self.assertGreater(before, 0)
        with self.assertRaises(c.ResourceLimit) as caught:
            self.extract(reader, catalog)
        self.assertEqual(caught.exception.code, 'output_bytes')
        self.assertGreaterEqual(reader.usage.output_bytes, before)
        count = len(value.calls)
        with self.assertRaises(ValueError): self.extract(reader, catalog)
        self.assertEqual(len(value.calls), count)

    def test_selected_blob_cannot_overlap_reserved_catalog_pages(self):
        value = fixtures.source(); reader, catalog = self.reader(value)
        # The existing ownership graph owns descriptor/root pages before the seam.
        original_roles = dict(reader._source.roles)
        self.assertTrue(original_roles)
        # Table BLOB page 11 is replaced by root-data page 3 in its FAT0 header.
        value.page(8)[24:28] = (3).to_bytes(4, 'little')
        with self.assertRaises(c.UnsupportedSharing):
            self.extract(reader, catalog)
        self.assertTrue(all(reader._source.roles.get(k) == v for k, v in original_roles.items()))
        before = len(value.calls)
        with self.assertRaises(ValueError): self.extract(reader, catalog)
        self.assertEqual(len(value.calls), before)


if __name__ == '__main__':
    unittest.main()
