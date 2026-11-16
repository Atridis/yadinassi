"""Informational object preparation owns one fresh read snapshot, not a writer."""
from unittest import TestCase
from unittest.mock import patch
import test_product_form_events as fixture
from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import _View


class PreparationViewTests(TestCase):
    def setUp(self):
        self.fixture=fixture.ProductFormEventTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_all_references_share_one_fresh_snapshot_and_close_it(self):
        f=self.fixture; reads=[]; original=_View.read_catalog
        def read(view,key):
            reads.append(view)
            return original(view,key)
        with patch.object(_View,'read_catalog',read), patch.object(f.context.backend,'begin_write',side_effect=AssertionError('write')):
            self.assertFalse(f.run_event('BeforeWriteAtServer').cancel)
        self.assertEqual(len(reads),2)
        self.assertIs(reads[0],reads[1])
        self.assertIsNone(f.context.backend._active)
        f.vm.execute('Склад.ПометкаУдаления=Истина; Склад.Записать();')
        # No snapshot/row cache crosses operations.
        self.assertTrue(f.run_event('BeforeWriteAtServer').cancel)
        self.assertIsNone(f.context.backend._active)

    def test_read_failure_closes_snapshot_without_write(self):
        f=self.fixture
        with patch.object(_View,'read_catalog',side_effect=BackendError('schema_changed')), patch.object(f.context.backend,'begin_write',side_effect=AssertionError('write')):
            with self.assertRaises(Exception):f.run_event('BeforeWriteAtServer')
        self.assertIsNone(f.context.backend._active)
        self.assertFalse(f.run_event('BeforeWriteAtServer').cancel)

    def test_constructor_failure_also_closes_owned_snapshot(self):
        f=self.fixture
        with patch('yadinassi.catalog_object_preparation._ObjectInterpreter',side_effect=ValueError('constructor failed')):
            with self.assertRaises(Exception):f.run_event('BeforeWriteAtServer')
        self.assertIsNone(f.context.backend._active)
