"""Flat movement TOP uses the same input order on an ordinary managed read."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_movement_layout import references
import test_accumulation_query_runtime as accumulation
import test_document_posting_runtime as recorder


class RawMovementOrderTests(unittest.TestCase):
    def fixture(self, module, case):
        fixture = case()
        self.addCleanup(fixture.doCleanups)
        if module is accumulation:
            fixture.vm, fixture.context = fixture.make()
            fixture.seed(fixture.vm, [('Straße', 1, 5, 8, False, 0),
                                      ('Straße', 2, 5, 2, False, 1),
                                      ('B', 2, 9, 3, False, 2)])
        else:
            fixture.setUp()
            fixture.make('''Procedure Posting(Cancel, Mode)
            Row=RegisterRecords.OwnedPostingRows.Add();
            Row.Key=Number(Number);Row.Amount=5;
            RegisterRecords.OwnedPostingRows.Write=True;
            EndProcedure''')
            for i in (3, 8):
                fixture.new(i)
                fixture.post()
        return fixture

    def query(self, fixture, sql, **parameters):
        fixture.vm.execute('Q=New Query("' + sql.replace('"', '""') + '");')
        query = fixture.vm.execute('Q')
        for name, value in parameters.items():
            query.set_parameter(name, value)
        return query.execute()._rows

    def test_bounded_literal_projection_over_movements(self):
        for module,case,source,field in (
                (accumulation,accumulation.AccumulationQueryRuntimeTests,'AccumulationRegister.OwnedAccumulationRows','Item'),
                (recorder,recorder.PostingRuntimeTests,'InformationRegister.OwnedPostingRows','Key')):
            with self.subTest(source=source):
                fixture=self.fixture(module,case)
                text=f'SELECT TOP 1 {field}, "tag" AS Marker FROM {source} ORDER BY LineNumber'
                with patch('yadinassi.db.query.query_movement_order.try_ordered_movements',return_value=None):
                    expected=self.query(fixture,text)
                self.assertEqual(len(expected),1)
                from yadinassi.db.query.relational_queries import _Plan
                with patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
                    self.assertEqual(self.query(fixture,text),expected)
                    result=fixture.vm.variables['q'].execute()
                self.assertEqual((result._columns[1].name,result._columns[1].kind),('Marker','string'))

    def test_raw_movement_families_share_folded_projection(self):
        from yadinassi.db.query.relational_queries import _Plan
        for module,case,source,field in (
                (accumulation,accumulation.AccumulationQueryRuntimeTests,'AccumulationRegister.OwnedAccumulationRows','Item'),
                (recorder,recorder.PostingRuntimeTests,'InformationRegister.OwnedPostingRows','Key')):
            with self.subTest(source=source):
                fixture=self.fixture(module,case)
                text=f'SELECT TOP 1 {field}, 1.2+0.05 AS Marker FROM {source} ORDER BY LineNumber'
                with patch('yadinassi.db.query.query_movement_order.try_ordered_movements',return_value=None):
                    expected=self.query(fixture,text)
                with patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
                    self.assertEqual(self.query(fixture,text),expected)
                self.assertEqual(expected[0][1].as_tuple(),Decimal('1.25').as_tuple())

    def test_accumulation_ties_filters_and_python_page(self):
        fixture = self.fixture(accumulation, accumulation.AccumulationQueryRuntimeTests)
        sql = ('SELECT TOP 2 Item, Quantity FROM AccumulationRegister.OwnedAccumulationRows '
               'WHERE Item=&K AND Amount>&N ORDER BY Amount DESC')
        values = {'K':'STRASSE', 'N':Decimal('4.999999')}
        with patch('yadinassi.db.query.query_movement_order.try_ordered_movements', return_value=None):
            baseline = self.query(fixture, sql, **values)
        self.assertEqual(baseline, (('Straße',Decimal('8')),('Straße',Decimal('2'))))
        connection = fixture.context.backend._read_handle.connection
        statements = []
        connection.set_trace_callback(statements.append)
        self.addCleanup(connection.set_trace_callback, None)
        self.assertEqual(self.query(fixture, sql, **values), baseline)
        storage = [stmt for stmt in statements if 'amove_' in stmt]
        self.assertEqual(len(storage), 1, storage)
        self.assertIn('ORDER BY', storage[0])
        self.assertIn('m.document_id ASC,m.record_id ASC,m.line_number ASC LIMIT 2', storage[0])

    def test_only_selected_raw_rows_are_decoded_but_all_their_cells_are_checked(self):
        fixture = self.fixture(accumulation, accumulation.AccumulationQueryRuntimeTests)
        source = ' FROM AccumulationRegister.OwnedAccumulationRows '
        self.assertEqual(self.query(fixture, 'SELECT TOP 1 Item'+source+'ORDER BY Amount DESC'), (('B',),))
        table,_ = references('accumulation', fixture.context.backend.accumulation_configuration.registers[0])
        with closing(sqlite3.connect(fixture.context.backend.path)) as db, db:
            db.execute('UPDATE '+table+' SET period=? WHERE line_number=3',('00000000000000',))
        raw = 'SELECT TOP 1 Item'+source+'WHERE Item=&K ORDER BY LineNumber'
        self.assertEqual(self.query(fixture, raw, K='STRASSE'), (('Straße',),))
        with self.assertRaises(BackendError):
            self.query(fixture, raw, K='B') # Same corrupt row is now selected; Period not projected.
        with self.assertRaises(BackendError):
            self.query(fixture, 'SELECT TOP 1 Item'+source+'ORDER BY Amount DESC')

    def test_recorder_ties_and_nonprojected_payload_check(self):
        fixture = self.fixture(recorder, recorder.PostingRuntimeTests)
        sql = ('SELECT TOP 1 Recorder, Key FROM InformationRegister.OwnedPostingRows '
               'WHERE Amount>=&N ORDER BY Amount DESC')
        params = {'N':Decimal(5)}
        with patch('yadinassi.db.query.query_movement_order.try_ordered_movements', return_value=None):
            baseline = self.query(fixture, sql, **params)
        self.assertEqual(len(baseline), 1)
        connection = fixture.context.backend._read_handle.connection
        statements = []
        connection.set_trace_callback(statements.append)
        self.addCleanup(connection.set_trace_callback, None)
        self.assertEqual(self.query(fixture, sql, **params), baseline)
        storage = [stmt for stmt in statements if 'rmove_' in stmt]
        self.assertEqual(len(storage), 1, storage)
        self.assertIn('m.document_id ASC,m.record_id ASC,m.line_number ASC LIMIT 1', storage[0])
        table, _ = references('recorder', fixture.context.backend.posting_configuration.registers[0])
        with closing(sqlite3.connect(fixture.path)) as db, db:
            db.execute('UPDATE '+table+' SET payload_bytes=0 WHERE record_id=?',(str(baseline[0][0].reference_uuid),))
        with self.assertRaises(BackendError):
            self.query(fixture, sql, **params)

    def test_selected_catalog_link_is_checked_even_if_not_projected(self):
        from uuid import uuid4
        from test_inventory_reference_profile import InventoryRuntimeTests
        fixture = InventoryRuntimeTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.seed()
        fixture.document()
        sql = 'SELECT TOP 1 Quantity FROM AccumulationRegister.Stock ORDER BY Product, Quantity DESC'
        self.assertEqual(self.query(fixture, sql), ((Decimal(10),),))
        table, columns = references('accumulation', fixture.config.registers[0])
        # This is a separately committed raw file edit. Same-width UUID keeps
        # the row's valid payload marker unchanged: missing target must fail.
        fixture.sql('UPDATE '+table+' SET '+columns[0]+'=?',(str(uuid4()),))
        with self.assertRaises(BackendError) as error:
            self.query(fixture, sql)
        self.assertEqual(error.exception.code, 'integrity')

    def test_open_writer_stays_on_existing_transaction_view(self):
        from test_inventory_reference_profile import InventoryRuntimeTests
        fixture = InventoryRuntimeTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.seed()
        fixture.document()
        sql = 'SELECT TOP 1 Quantity FROM AccumulationRegister.Stock ORDER BY Quantity DESC'
        before = self.query(fixture, sql)
        fixture.vm.execute('''BeginTransaction();
            T=Documents.Receipt.CreateDocument(); T.Number="staged"; T.Date=Date(2024,1,1);
            T.Warehouse=W.Ref; L=T.Lines.Add(); L.Product=P.Ref; L.Quantity=21; L.Amount=25;
            T.Write(DocumentWriteMode.Posting);
            Q=New Query("SELECT TOP 1 Quantity FROM AccumulationRegister.Stock ORDER BY Quantity DESC");
            S=Q.Execute().Select(); S.Next(); Inside=S.Quantity; RollbackTransaction();''')
        self.assertEqual(fixture.vm.execute('Inside'), Decimal(21))
        self.assertEqual(self.query(fixture, sql), before)
