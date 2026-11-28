"""SQLite fixture copies keep seed, data variants and test writes separate."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlite_test_templates import copy_inventory
from yadinassi import Interpreter
from yadinassi.db.database_context import SQLiteDBContext


class SQLiteTestTemplatesTests(unittest.TestCase):
    def test_empty_seeded_and_independent_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second, empty = [root / name for name in ('first', 'second', 'empty')]
            keys = copy_inventory(first, products=True)
            self.assertEqual(copy_inventory(second, products=True), keys)
            self.assertIsNone(copy_inventory(empty))
            baseline = first.read_bytes()
            self.assertEqual(second.read_bytes(), baseline)
            self.assertNotEqual(empty.read_bytes(), baseline)
            with SQLiteDBContext(first) as db, closing(Interpreter(database_context=db)) as vm:
                vm.execute('P=Catalogs.Products.CreateItem();P.Code="P2";P.Description="Second";P.Write();')
            self.assertNotEqual(first.read_bytes(), baseline)
            self.assertEqual(second.read_bytes(), baseline)

            third = root / 'third'
            self.assertEqual(copy_inventory(third, products=True), keys)
            self.assertEqual(third.read_bytes(), baseline)
            with self.assertRaises(FileExistsError):
                copy_inventory(second, products=True)
