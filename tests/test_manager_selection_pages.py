"""Actual BSL manager cursors, not Query result selections or raw DB ports."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_documents import DocumentView
from yadinassi.db.sqlite.sqlite_document_layout import section_table
from yadinassi.db.sqlite.sqlite_typed_rows import attribute_column
from catalog_sections_fixture import configuration_files_with_sections as catalog_files
from test_document_configuration_xml import document_files
from yadinassi.db.sqlite.sqlite_migration_plan import apply, prepare


class ManagerSelectionPagesTests(unittest.TestCase):
    def database(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'select.sqlite'
        db = SQLiteDBContext.create(path, import_configuration(files))
        self.addCleanup(db.close)
        messages = []
        vm = Interpreter(database_context=db, output=messages.append)
        self.addCleanup(vm.close)
        return db, vm, path, messages

    def test_catalog_pages_only_headers_and_get_object_still_reads_latest_parts(self):
        db, vm, _, messages = self.database(catalog_files())
        vm.execute('''For I=1 To 35 Do
O=Catalogs.Products.CreateItem(); O.Code=String(136-I); O.Description="old";
L=O.Lines.Add(); L.Text="old"; O.Write();
EndDo;''')
        calls = []
        scalar = _View._scalar
        def count(view, identity, row, *, schema):
            calls.append(row[2])
            return scalar(view, identity, row, schema=schema)

        with patch.object(_View, '_scalar', count), patch.object(_View, '_section_scan',
                side_effect=AssertionError('catalog selection fetched unused parts')):
            vm.execute('S=Catalogs.Products.Select(); S.Next();')
            self.assertEqual(calls, [str(101+i) for i in range(16)])
            self.assertIsNone(db.backend._active)
            vm.execute('While S.Next() Do Message(S.Code); EndDo; Message(S.Code);')
            self.assertEqual(calls, [str(101+i) for i in range(35)])
        self.assertEqual(messages, [str(102+i) for i in range(34)] + ['135'])
        self.assertTrue(vm.execute('S.Next()'))  # Existing catalog rewind.
        vm.execute('O.Description="new"; O.Lines[0].Text="new"; O.Write();')
        self.assertEqual(vm.execute('S.Description'), 'old')
        self.assertEqual(vm.execute('S.GetObject().Lines[0].Text'), 'new')

    def seed_documents(self, vm, count=35):
        vm.execute(f'''For I=1 To {count} Do
D=Documents.Orders.CreateDocument(); D.Number=String(100+I);
D.Date=Date(2026,11,9); D.Text="old";
L=D.Lines.Add(); L.Flag=True; D.Write();
EndDo;''')

    def test_document_pages_have_detached_current_parts_and_consistent_date_order(self):
        db, vm, _, messages = self.database(document_files())
        self.seed_documents(vm)
        cards = []
        read_card = DocumentView._card
        def count(view, schema, row, *, presence=None):
            result = read_card(view,schema,row,presence=presence)
            cards.append(result.number)
            return result

        with patch.object(DocumentView,'_card',count):
            vm.execute('S=Documents.Orders.Select(Date(2026,11,9),Date(2026,11,9));S.Next();')
            self.assertEqual(cards,[str(101+i) for i in range(16)])
            self.assertIsNone(db.backend._active)
            self.assertTrue(vm.execute('S.GetObject().Lines[0].Flag'))
            vm.execute('While S.Next() Do Message(S.Number); EndDo;')
            self.assertEqual(cards,[str(101+i) for i in range(35)])
        self.assertEqual(messages,[str(102+i) for i in range(34)])
        self.assertIsNone(vm.execute('S.GetObject()'))
        self.assertFalse(vm.execute('S.Next()'))

    def test_exact_full_page_has_normal_terminal_state_and_selected_part_bounds(self):
        db, vm, path, _ = self.database(document_files())
        self.seed_documents(vm,16)
        vm.execute('S=Documents.Orders.Select();For I=1 To 16 Do S.Next();EndDo;')
        self.assertEqual(vm.execute('S.Number'),'116')
        self.assertFalse(vm.execute('S.Next()'))
        self.assertIsNone(vm.execute('S.GetObject()'))
        manager = vm._documents.get_index('Orders')
        # The headers fit, but the selected physical part row pushes the page
        # over the configured bound. No DB-wide scan is needed to prove this.
        with patch('yadinassi.db.sqlite.sqlite_documents._MAX_TOTAL', 16*147):
            with self.assertRaisesRegex(BackendError,'unsupported'): manager.select()
        document = manager._schema
        section, = document.tabular_sections
        flag, = section.fields
        table = section_table(document,section)
        with closing(sqlite3.connect(path)) as c, c:
            c.execute('''WITH RECURSIVE line(n) AS (VALUES (2) UNION ALL SELECT n+1 FROM line WHERE n<1001)
                INSERT INTO "{table}" (document_id,record_id,row_id,row_number,"{flag}")
                SELECT r.document_id,r.record_id,printf('%08x-0000-4000-8000-000000000000',n),n,1
                FROM document_record r,line WHERE r.number='101'
            '''.format(table=table,flag=attribute_column(flag)))
        with self.assertRaisesRegex(BackendError,'unsupported'): manager.select()
        self.assertIsNone(db.backend._active)

    def test_explicit_transaction_neither_acquires_nor_is_held_by_selection(self):
        original, vm, path, _ = self.database(document_files())
        self.seed_documents(vm)
        vm.close()
        original.close()
        apply(path,prepare(path,maintenance=True),maintenance=True)
        with SQLiteDBContext(path) as db, closing(Interpreter(database_context=db)) as vm:
            vm.execute('S=Documents.Orders.Select();')
            vm.execute('''BeginTransaction(); Denied=False; BoundaryDenied=False;
Try X=Documents.Orders.Select(); Except Denied=True; EndTry;
For I=1 To 16 Do S.Next(); EndDo;
Try S.Next(); Except BoundaryDenied=True; EndTry;
D=Documents.Orders.CreateDocument();D.Number="200";D.Date=Date(2026,11,9);D.Write();
CommitTransaction();''')
            self.assertIsNone(db.backend._active)
            self.assertTrue(vm.execute('Denied And BoundaryDenied'))
            self.assertTrue(vm.execute('S.Next()'))
            self.assertEqual(vm.execute('S.Number'),'117')
            self.assertFalse(vm.execute('D.IsNew()'))

    def test_later_document_corruption_is_reported_when_its_page_is_reached(self):
        db, vm, path, _ = self.database(document_files())
        self.seed_documents(vm)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE document_record SET date='99999999999999' WHERE number='135'")
        vm.execute('S=Documents.Orders.Select();For I=1 To 32 Do S.Next();EndDo;')
        self.assertEqual(vm.execute('S.Number'),'132')
        with self.assertRaises((BackendError,BSLRuntimeError)):
            vm.execute('S.Next();')
        self.assertIsNone(db.backend._active)
