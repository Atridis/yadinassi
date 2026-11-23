"""Scalar catalog reference access retains full point integrity admission."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_catalog_tabular_runtime as fixtures
from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier


class CatalogPointProjectionTests(unittest.TestCase):
    setUp=fixtures.CatalogTabularRuntimeTests.setUp
    def seed(self):
        self.vm.execute('O=Catalogs.Products.CreateItem();O.Code="1";O.Description="Visible";'
            'O.Text="header";For I=1 To 64 Do L=O.Lines.Add();L.Text="line";EndDo;O.Write();R=O.Ref;')
        return self.vm.execute('R')
    def sql(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as connection,connection:
            return connection.execute(sql,args).fetchall()
    def test_cold_scalar_does_not_materialize_card_and_getobject_still_does(self):
        self.seed()
        with patch.object(_View,'_card',side_effect=AssertionError('full card')):
            self.assertEqual(self.vm.execute('R.Description'),'Visible')
            self.assertEqual(self.vm.execute('R.Text'),'header')
        self.assertEqual(self.vm.execute('R.GetObject().Lines.Count()'),64)
    def test_warm_scalar_does_not_fetch_sections_or_unselected_fields(self):
        self.seed();self.vm.execute('R.Description')
        backend=self.context.backend; trace=[]
        original=backend.begin_read
        def begin():
            view=original();view._connection.set_trace_callback(trace.append);return view
        with patch.object(backend,'begin_read',side_effect=begin), \
                patch.object(_View,'_section_scan',side_effect=AssertionError('warm sections')), \
                patch.object(_View,'_scalar',side_effect=AssertionError('warm full scalar')):
            self.assertEqual(self.vm.execute('R.Наименование'),'Visible')
        reads=[s for s in trace if s.startswith('SELECT record_id,"description"')]
        self.assertEqual(len(reads),1)
        self.assertFalse(any('row_number' in s for s in trace))
    def test_external_section_corruption_invalidates_old_point_proof(self):
        ref=self.seed();self.vm.execute('R.Description')
        schema=self.vm._catalogs.get_index('Products')._schema
        section=schema.tabular_sections[0]
        table=quote_identifier(self.context.backend._section_layout.table_name(schema.identity,section.identity))
        self.sql('UPDATE '+table+' SET row_number=999 WHERE row_number=1')
        with self.assertRaises(BSLRuntimeError):self.vm.execute('R.Description')
    def test_write_commit_invalidates_cached_scalars(self):
        self.seed();self.assertEqual(self.vm.execute('R.Description'),'Visible')
        self.vm.execute('O.Description="Changed";O.Write();')
        self.assertEqual(self.vm.execute('R.Description'),'Changed')

    def test_projected_selection_is_captured_but_ref_reads_see_peer_commit(self):
        self.addCleanup(self.vm.close)
        self.vm.execute('''
            For I=1 To 2 Do
                Item=Catalogs.Products.CreateItem(); Item.Code=String(I);
                Item.Description="Before"+String(I); Item.Write();
            EndDo;
        ''')
        plain = 'SELECT TOP 2 P.Ref, P.Description FROM Catalog.Products AS P ORDER BY P.Code'
        dotted = ('SELECT TOP 2 P.Ref, P.Ref.Description AS Caption '
                  'FROM Catalog.Products AS P ORDER BY P.Code')
        self.vm.execute(f'Q=New Query("{plain}"); Q.Execute();')  # Admit the reusable read handle.
        backend = self.context.backend
        schema = self.vm._catalogs.get_index('Products')._schema
        physical = quote_identifier(backend._layout.table_name(schema.identity))
        trace = []
        connection = backend._read_handle.connection
        connection.set_trace_callback(trace.append)

        def data_reads():
            return [sql for sql in trace if sql.startswith('SELECT ') and f'FROM {physical}' in sql]

        try:
            with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('unbounded query fallback')), \
                    patch.object(_View, '_card', side_effect=AssertionError('whole catalog card')):
                for query, variable in ((plain, 'Snapshot'), (dotted, 'Dotted')):
                    with self.subTest(query=query):
                        trace.clear()
                        self.vm.execute(f'Q=New Query("{query}"); {variable}=Q.Execute();')
                        reads = data_reads()
                        self.assertEqual(len(reads), 1, trace)
                        self.assertTrue(reads[0].endswith('LIMIT 2'), reads)
        finally:
            connection.set_trace_callback(None)

        self.vm.execute('S=Snapshot.Select(); D=Dotted.Select(); L=Snapshot.Select();')
        # An independent SQLite owner commits after Execute and before reading
        # either held selection. No write runs in the reader's BSL program.
        with closing(SQLiteDBContext(self.path)) as peer, \
                closing(Interpreter(database_context=peer)) as writer:
            writer.execute('''
                For I=1 To 2 Do
                    Item=Catalogs.Products.FindByCode(String(I)).GetObject();
                    Item.Description="After"+String(I); Item.Write();
                EndDo;
            ''')

        original = backend.begin_read
        def begin():
            view = original()
            view._connection.set_trace_callback(trace.append)
            return view

        backend._read_handle.connection.set_trace_callback(trace.append)
        try:
            with patch.object(backend, 'begin_read', side_effect=begin):
                trace.clear()
                self.vm.execute('''
                    Captured=New Array; Alias=New Array;
                    While S.Next() Do Captured.Add(S.Description); EndDo;
                    While D.Next() Do Alias.Add(D.Caption); EndDo;
                ''')
                self.assertEqual(self.vm.variables['captured'], ['Before1', 'Before2'])
                self.assertEqual(self.vm.variables['alias'], ['Before1', 'Before2'])
                self.assertEqual(trace, [])

                self.vm.execute('''
                    Current=New Array;
                    While L.Next() Do
                        Current.Add(L.Ref.Description);
                        Current.Add(L.Ref.Description);
                    EndDo;
                ''')
        finally:
            backend._read_handle.connection.set_trace_callback(None)
        self.assertEqual(self.vm.variables['current'], ['After1', 'After1', 'After2', 'After2'])
        points = [sql for sql in data_reads() if sql.startswith('SELECT record_id,"description" ')]
        self.assertEqual(len(points), 4, trace)
        self.assertEqual(points[0], points[1])
        self.assertEqual(points[2], points[3])
        self.assertNotEqual(points[0], points[2])

    def test_repeated_live_member_observes_peer_commit_inside_selection_loop(self):
        self.addCleanup(self.vm.close)
        self.seed()
        self.vm.execute('Q=New Query("SELECT TOP 1 P.Ref, P.Ref.Description AS Caption '
                        'FROM Catalog.Products AS P ORDER BY P.Code"); '
                        'Selection=Q.Execute().Select();')
        with closing(SQLiteDBContext(self.path)) as peer, \
                closing(Interpreter(database_context=peer)) as writer:
            writer.execute('Card=Catalogs.Products.FindByCode("1").GetObject();')

            def commit_between_reads(message):
                self.assertEqual(message, 'commit between reads')
                writer.execute('Card.Description="Changed by peer"; Card.Write();')

            # The actual host output boundary deterministically interleaves
            # a SQLite commit while keeping one BSL iteration and one selection.
            self.vm.output = commit_between_reads
            self.vm.execute_prepared(self.vm.prepare('''
                While Selection.Next() Do
                    Before=Selection.Ref.Description;
                    Message("commit between reads");
                    After=Selection.Ref.Description;
                    Captured=Selection.Caption;
                EndDo;
            '''))
        self.assertEqual(self.vm.variables['before'], 'Visible')
        self.assertEqual(self.vm.variables['after'], 'Changed by peer')
        self.assertEqual(self.vm.variables['captured'], 'Visible')

    def test_unrelated_corrupt_record_does_not_expand_point_validation_scope(self):
        self.seed();self.vm.execute('X=Catalogs.Products.CreateItem();X.Code="2";X.Write();')
        schema=self.vm._catalogs.get_index('Products')._schema
        table=quote_identifier(self.context.backend._layout.table_name(schema.identity))
        self.sql('UPDATE '+table+' SET description=? WHERE code=?',('x'*1000,'2'))
        self.assertEqual(self.vm.execute('R.Description'),'Visible')
    def test_projection_denies_writer_and_closed_view(self):
        ref=self.seed();manager=self.vm._catalogs.get_index('Products')
        key=manager._key(ref.reference_uuid)
        with closing(self.context.backend.begin_write(uuid4())) as view:
            with self.assertRaisesRegex(BackendError,'unsupported'):view.read_catalog_values(key,('description',))
        with self.assertRaisesRegex(BackendError,'closed'):view.read_catalog_values(key,('description',))
    def test_empty_reference_and_bilingual_scalar_defaults_preserved(self):
        self.seed()
        self.assertEqual(self.vm.execute('Catalogs.Products.EmptyRef().Description'),'')
        self.assertFalse(self.vm.execute('Catalogs.Products.EmptyRef().ПометкаУдаления'))


import test_inventory_enum_runtime_binding as enum_fixtures

class EnumCatalogPointProjectionTests(unittest.TestCase):
    setUp=enum_fixtures.InventoryEnumRuntimeBindingTests.setUp
    def test_scalar_and_enum_getters_and_transaction_transfer_boundary(self):
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="P";C.Description="Product";'
                        'C.Unit=Enums.Units.Piece;C.Write();')
        self.assertEqual(self.vm.execute('C.Ref.Description'),'Product')
        self.assertIs(self.vm.execute('C.Ref.Unit'),self.ref)
        for member in ('Description','Unit'):
            with self.assertRaisesRegex(BSLRuntimeError,'unsupported'):
                self.vm.execute('BeginTransaction();V=C.Ref.'+member+';RollbackTransaction();')
    def test_lexical_witness_still_refuses_unregistered_view_subclass(self):
        from yadinassi.configuration.demos.inventory_enum_runtime import read_snapshot
        class ForeignView(_View): pass
        with closing(self.context.backend.begin_read()) as view:
            foreign=object.__new__(ForeignView);foreign.__dict__.update(view.__dict__)
            with self.assertRaisesRegex(BackendError,'unsupported'):
                with read_snapshot(self.vm._metadata,foreign):pass
