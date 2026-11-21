"""Legacy receipt rows stay inert; host posting needs no acknowledgement."""
from contextlib import closing
import sqlite3
import unittest
from uuid import uuid4

import test_document_posting_host as posting
import test_inventory_host_operations as inventory
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend


class LegacyPostingReceiptTests(unittest.TestCase):
    setUp=posting.PostingHostTests.setUp
    cleanup_host=posting.PostingHostTests.cleanup_host
    execute=posting.PostingHostTests.execute

    def test_legacy_root_row_does_not_supply_an_outcome_or_block_a_new_write(self):
        operation=uuid4()
        old=(str(operation),'0'*64,'[]')
        with closing(sqlite3.connect(self.context.path)) as db,db:
            db.execute('INSERT INTO unit_of_work_receipt VALUES(?,?,?)',old)
        result=self.execute(operation=operation)
        self.assertEqual(result.state,'committed');self.assertTrue(result.accepted)
        self.assertFalse(hasattr(self.host,'acknowledge'))
        self.assertIsNone(self.host._active_operation)
        with closing(SQLiteCatalogBackend(self.context.path)) as backend:
            self.assertTrue(backend.read_document_posted(self.key))
        with closing(sqlite3.connect(self.context.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM unit_of_work_receipt').fetchall(),[old])
            for table in ('document_commit_receipt','document_posting_receipt','recorder_movement_receipt'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone(),(0,))


class InventoryPostingOutcomeTests(unittest.TestCase):
    setUp=inventory.InventoryHostTests.setUp
    cleanup_host=inventory.InventoryHostTests.cleanup_host
    execute=inventory.InventoryHostTests.execute

    def test_confirmed_posting_is_readable_after_reopen_without_host_history(self):
        result=self.execute()
        self.assertEqual(result.state,'committed');self.assertTrue(result.accepted)
        self.assertIsNone(self.host._active_operation)
        with closing(SQLiteCatalogBackend(self.context.path)) as backend:
            self.assertTrue(backend.read_document_posted(self.key))
            with closing(backend.begin_document_read()) as view:
                self.assertEqual(view.read_document(self.key).revision,result.outcomes[0].result.revision)


class EnumInventoryRootOutcomeTests(unittest.TestCase):
    def test_catalog_write_with_enum_in_host_root_survives_reopen_without_receipts(self):
        import tempfile
        from pathlib import Path
        from inventory_enum_application_fixture import source
        from yadinassi.configuration.configuration_inventory_enum_application import import_inventory_application,PROFILE
        from yadinassi.configuration.demos.inventory_host_operations import InventoryRootOperation
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.runtime import Interpreter
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'enum.sqlite'
            configuration=import_inventory_application(source(),inventory_runtime=PROFILE)
            with SQLiteDBContext.create_inventory_enum_application(path,configuration) as context:
                with closing(Interpreter(database_context=context)) as vm:
                    item=vm.execute('P=Catalogs.Products.CreateItem();P.Code="1";P.Unit=Enums.Units.Piece;P')
                    root=InventoryRootOperation(context.backend,uuid4());result=root.run(item.write)
                    self.assertTrue(result.accepted)
                    self.assertFalse(root.needs_cleanup)
                    key=item._key
            with closing(SQLiteCatalogBackend(path)) as backend, closing(backend.begin_read()) as view:
                card=view.read_catalog(key)
                self.assertEqual(card.revision,result.outcomes[0].result.revision)
                schema=next(c for c in configuration.catalogs if c.identity==key.catalog_id)
                unit=next(i for i,f in enumerate(schema.fields) if f.name=='Unit')
                enum=next(e for e in configuration.enumerations if e.identity==schema.fields[unit].target_enum_id)
                piece=next(v for v in enum.values if v.name=='Piece')
                self.assertEqual(card.values[unit].value_id,piece.identity)
            with closing(sqlite3.connect(path)) as db:
                for table in ('commit_receipt','unit_of_work_receipt'):
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone(),(0,))
