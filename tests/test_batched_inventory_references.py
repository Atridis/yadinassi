"""Operation-local existence batching preserves snapshot and error contracts."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import json
import sqlite3
import unittest
from uuid import uuid4

import test_inventory_reference_profile as fixtures
from yadinassi.catalog_backend import BackendError, CatalogKey
from yadinassi.document_backend import DocumentSelection, DocumentScanRequest
from yadinassi.sqlite_catalog_layout import reference_presence, quote_identifier
from yadinassi.sqlite_transactions import _accumulation_port


class InventoryReferenceBatchTests(unittest.TestCase):
    setUp = fixtures.InventoryRuntimeTests.setUp
    seed = fixtures.InventoryRuntimeTests.seed
    sql = fixtures.InventoryRuntimeTests.sql

    def document(self, count=64):
        self.seed()
        self.vm.execute('D=Documents.Receipt.CreateDocument(); D.Number="1"; '
            'D.Date=Date(2024,1,1); D.Warehouse=W.Ref; '
            f'For I=1 To {count} Do L=D.Lines.Add(); L.Product=P.Ref; '
            'L.Quantity=1; L.Amount=2; EndDo; D.Write(DocumentWriteMode.Posting);')
        return self.vm.execute('D')._key

    @staticmethod
    def lookups(trace):
        return [sql for sql in trace if sql.startswith(('SELECT 1 FROM "', 'SELECT record_id FROM "'))
                and 'record_id' in sql]

    def test_movement_and_document_read_deduplicate_occurrences(self):
        key = self.document(256)
        with closing(self.backend.begin_read()) as base:
            port = _accumulation_port(base)
            trace = []; base._connection.set_trace_callback(trace.append)
            self.assertEqual(len(port.read(self.config.registers[0].identity,key).rows),256)
            self.assertEqual(len(self.lookups(trace)),2)  # Product + Warehouse, not 512.
        with closing(self.backend.begin_document_read()) as view:
            trace = []; view._connection.set_trace_callback(trace.append)
            self.assertEqual(len(view.read_document(key).tabular_sections[0].rows),256)
            self.assertEqual(len(self.lookups(trace)),2)

    def test_document_section_projection_does_not_reintroduce_per_line_queries(self):
        key = self.document(64)
        schema = next(s for s in self.config.documents if s.identity == key.document_id)
        section = schema.tabular_sections[0]
        with closing(self.backend.begin_document_read()) as view:
            view._validate_query_source(schema)
            trace = []; view._connection.set_trace_callback(trace.append)
            page = view.scan_document_values(schema.identity,DocumentScanRequest(),
                (section.fields[0].identity,),section.identity)
            self.assertEqual(len(page.rows),64)
            self.assertEqual(len(self.lookups(trace)),1)

    def test_document_write_batches_section_values(self):
        key = self.document(128)
        with closing(self.backend.begin_document_read()) as view:
            card = view.read_document(key)
        with closing(self.backend.begin_document_write(uuid4())) as view:
            trace = []; view._connection.set_trace_callback(trace.append)
            view._sections(next(s for s in self.config.documents if s.identity == key.document_id),
                           card.tabular_sections,writing=True)
            self.assertEqual(len(self.lookups(trace)),1)

    def test_no_positive_cache_survives_same_transaction_mutation(self):
        key = self.document(16)
        with closing(self.backend.begin_document_write(uuid4())) as view:
            self.assertIsNotNone(view.read_document(key))
            product = self.vm.execute('P')._key
            table = quote_identifier(self.backend._layout.table_name(product.catalog_id))
            view._connection.execute('DELETE FROM '+table+' WHERE record_id=?',(str(product.record_id),))
            with self.assertRaisesRegex(BackendError,'integrity'): view.read_document(key)
            view.rollback()
        with closing(self.backend.begin_document_read()) as view:
            self.assertIsNotNone(view.read_document(key))

    def test_movement_missing_reference_keeps_read_write_error_codes(self):
        key = self.document(16)
        with closing(self.backend.begin_read()) as base:
            port = _accumulation_port(base)
            rows = port.read(self.config.registers[0].identity,key).rows
            missing = replace(rows[0].dimensions[0], record_id=uuid4())
            bad = (replace(rows[0],dimensions=(missing,rows[0].dimensions[1])),)
            for writing, code in ((True,'not_found'),(False,'integrity')):
                with self.assertRaisesRegex(BackendError,code): port._references(bad,writing=writing)

    def test_missing_reference_precedes_later_malformed_section(self):
        key = self.document(16)
        with closing(self.backend.begin_document_write(uuid4())) as view:
            raw = view._connection.execute('SELECT values_json,sections_json FROM document_record').fetchone()
            values = json.loads(raw[0]); values[0][2] = str(uuid4())
            view._connection.execute('UPDATE document_record SET values_json=?,sections_json=?',
                                    (json.dumps(values),'{}'))
            with self.assertRaisesRegex(BackendError,'integrity'): view.read_document(key)

    def test_selection_limit_precedes_later_deep_json_corruption(self):
        self.seed()
        self.vm.execute('For I=1 To 3 Do D=Documents.Receipt.CreateDocument(); '
            'D.Number=String(I); D.Date=Date(2024,1,1); D.Warehouse=W.Ref; D.Write(); EndDo;')
        schema = next(s for s in self.config.documents if s.name == 'Receipt')
        with closing(self.backend.begin_document_write(uuid4())) as view:
            view._connection.execute("UPDATE document_record SET sections_json=? WHERE number='3'",
                                     ('[' * 20000 + '0' + ']' * 20000,))
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                view.select_documents(schema.identity,DocumentSelection(limit=1))
            with self.assertRaisesRegex(BackendError, 'integrity'):
                view.select_documents(schema.identity,DocumentSelection(limit=3))


class ReferencePresenceChunkTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(sqlite3.Connection, "setlimit"), "Python 3.11+ limit API")
    def test_distinct_keys_chunked_below_connection_limit_and_scoped_by_catalog(self):
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE refs(catalog_id TEXT, record_id TEXT)')
            db, first, second = uuid4(), uuid4(), uuid4()
            ids = [uuid4() for _ in range(600)]
            connection.executemany('INSERT INTO refs VALUES(?,?)',[(str(first),str(v)) for v in ids])
            connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,65)
            keys = [CatalogKey(db,first,v) for v in ids]*2 + [CatalogKey(db,second,ids[0])]
            trace = []; connection.set_trace_callback(trace.append)
            result = reference_presence(connection,keys,lambda cid:('refs','catalog_id=?',(str(cid),)))
            self.assertTrue(all(result[(first,v)] for v in ids))
            self.assertFalse(result[(second,ids[0])])
            self.assertEqual(len(trace),11)  # ceil(600/64) plus a different catalog.
            connection.execute('INSERT INTO refs VALUES(?,?)',(str(second),str(ids[0])))
            result = reference_presence(connection,[keys[-1]],lambda cid:('refs','catalog_id=?',(str(cid),)))
            self.assertTrue(result[(second,ids[0])])
