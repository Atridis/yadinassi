"""The query port validates the complete bounded source before projection."""
import unittest
from uuid import uuid4
from yadinassi.catalog_backend import BackendError
import test_recorder_movement_storage as fixtures

class RecorderQueryPortTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.RecorderStorageTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups);self.f=fixture
    def test_scan_reads_staged_partition(self):
        f=self.f;req=f.request();f.port.replace(uuid4(),req)
        result=f.port.scan(f.reg)
        self.assertEqual(len(result),1);self.assertEqual(result[0][0],f.key)
        self.assertEqual(result[0][1].rows,req.rows)
    def test_empty_source(self):
        self.assertEqual(self.f.port.scan(self.f.reg),())
    def test_unknown_register_refused(self):
        with self.assertRaises(BackendError):self.f.port.scan(uuid4())
    def test_schema_tamper_even_empty_source_refused(self):
        f=self.f;f.c.execute("UPDATE recorder_register_schema SET definition='{}'")
        with self.assertRaises(BackendError):f.port.scan(f.reg)
    def test_nonprojected_corrupt_cell_refused(self):
        f=self.f;f.port.replace(uuid4(),f.request())
        f.c.execute("UPDATE recorder_movement SET values_json='[]'")
        with self.assertRaises(BackendError):f.port.scan(f.reg)
    def test_source_after_close_refused(self):
        f=self.f;f.c.execute('ROLLBACK')
        with self.assertRaises(BackendError):f.port.scan(f.reg)
