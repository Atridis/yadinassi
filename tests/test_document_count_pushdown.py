"""Document COUNT keeps the whole logical input budget without loading cards."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch

import test_document_query_port as fixture
import test_main_demo_runtime as main_demo
from yadinassi import BSLRuntimeError
from yadinassi.db.query import queries, query_pushdown, relational_queries
from yadinassi.db.sqlite import sqlite_documents
from yadinassi.db.sqlite.sqlite_document_layout import data_table, section_table
from yadinassi.db.sqlite.sqlite_typed_rows import attribute_column


class _Queries:
    def query(self, text):
        return self.vm.execute('Q=New Query("'+text.replace('"','""')+'"); Q.Execute()')

    def compare_one_statement(self, text, rows):
        with patch.object(query_pushdown, 'count_eligible', return_value=False):
            previous = self.query(text)
        trace = []
        conn = self.context.backend._read_handle.connection
        conn.set_trace_callback(trace.append)
        try:
            with patch.object(relational_queries._Plan,'load',side_effect=AssertionError('full load')):
                result = self.query(text)
        finally:
            conn.set_trace_callback(None)
        self.assertFalse(conn.in_transaction)
        self.assertEqual(result._rows, rows)
        self.assertEqual(result._rows, previous._rows)
        self.assertEqual(result._columns, previous._columns)
        self.assertEqual(len(trace), 1, trace)
        self.assertIn('COUNT(*)', trace[0])


class DocumentCountTests(_Queries,unittest.TestCase):
    setUp = fixture.DocumentQueryPortTests.setUp
    tearDown = fixture.DocumentQueryPortTests.tearDown
    object = fixture.DocumentQueryPortTests.object
    seed = fixture.DocumentQueryPortTests.seed
    sql = fixture.DocumentQueryPortTests.sql

    def test_configured_document_and_parts_count_variants_and_empty(self):
        for count in (0, 4):
            if count: self.seed(count)
            for source in ('Document.Orders','Document.Orders.Lines'):
                for expression,suffix in (
                    ('COUNT(*) AS N',''),
                    ('COUNT(D.Ref)+0.00 AS N,"constant" AS Marker','WHERE 1=1 ORDER BY N'),
                    ('COUNT(*) AS N','WHERE NULL=1'),
                ):
                    with self.subTest(count=count,source=source,expression=expression):
                        expected = ((Decimal(count).quantize(Decimal('0.00')),'constant'),) if 'Marker' in expression else (
                            (Decimal(0 if suffix else count),),)
                        self.compare_one_statement(f'SELECT {expression} FROM {source} AS D {suffix}',expected)

    def test_hidden_values_and_parts_remain_counted_toward_limits(self):
        self.seed(3)
        # Whole cards contain more cells than either this header or empty
        # result projects. Three 9-character Numbers are also charged.
        text = 'SELECT COUNT(*) FROM Document.Orders WHERE 1=0'
        for name,limit in (('_MAX_CELLS',4),('_MAX_RESULT_TEXT',26)):
            with self.subTest(limit=name),patch.object(queries,name,limit):
                with patch.object(relational_queries._Plan,'load',side_effect=AssertionError('full load')):
                    with self.assertRaisesRegex(BSLRuntimeError,'Query input resource limit exceeded'):
                        self.query(text)
        with patch.object(sqlite_documents,'_MAX_TOTAL',128):
            with self.assertRaisesRegex(BSLRuntimeError,'unsupported'): self.query(text)

    def test_damaged_hidden_values_fail_even_in_false_count(self):
        self.seed(3)
        headers = 'document_record'
        attributes = data_table(self.schema)
        part = section_table(self.schema,self.schema.tabular_sections[0])
        amount = attribute_column(next(f for f in self.schema.fields if f.name=='Amount'))
        cases = (
            (headers,'record_id','not-a-uuid'),
            (headers,'date','20230229000000'),
            (headers,'date','20240229240000'),
            (headers,'number','x'*10),
            (attributes,amount,10**12),
            (part,'row_id','00000000-0000-0000-0000-000000000000'),
            (part,'row_number',2),
        )
        for table,column,invalid in cases:
            with self.subTest(table=table,column=column,value=invalid):
                with closing(sqlite3.connect(self.path)) as conn,conn:
                    row,previous = conn.execute(f'SELECT rowid,"{column}" FROM "{table}" LIMIT 1').fetchone()
                    conn.execute('PRAGMA ignore_check_constraints=ON')
                    conn.execute(f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',(invalid,row))
                try:
                    sql = 'SELECT COUNT(*) FROM Document.Orders WHERE 1=0'
                    with patch.object(query_pushdown,'count_eligible',return_value=False):
                        with self.assertRaises(BSLRuntimeError) as old:
                            self.query(sql)
                    with self.assertRaises(type(old.exception)) as new:
                        self.query(sql)
                    self.assertEqual(str(old.exception),str(new.exception))
                finally:
                    self.sql(f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',(previous,row))

    def test_unicode_and_embedded_nul_use_the_existing_decoder(self):
        obj = self.object()
        obj.set_member('Text','Буква\0😀')
        obj.set_member('Number','Ю😀')
        obj.write()
        sql = 'SELECT COUNT(Ref) FROM Document.Orders'
        with patch.object(query_pushdown,'count_eligible',return_value=False):
            old = self.query(sql)
        self.assertEqual(old._rows,((Decimal(1),),))
        self.assertEqual(self.query(sql)._rows,old._rows)

    def test_statement_error_uses_owned_storage_error_translation(self):
        self.seed()
        with patch('yadinassi.db.sqlite.sqlite_document_count.fetch_one',
                   side_effect=sqlite3.OperationalError('driver error')):
            with self.assertRaisesRegex(BSLRuntimeError,'storage_error'):
                self.query('SELECT COUNT(*) FROM Document.Orders')
        self.assertIsNone(self.context.backend._active)
        self.assertEqual(self.query('SELECT COUNT(*) FROM Document.Orders')._rows,((Decimal(3),),))

    def test_nonconstant_document_filter_keeps_original_provider(self):
        self.seed(3)
        with patch('yadinassi.db.sqlite.sqlite_document_count.count',
                   side_effect=AssertionError('unexpected count witness')):
            result = self.query('SELECT COUNT(*) FROM Document.Orders WHERE Number="000000001"')
        self.assertEqual(result._rows,((Decimal(1),),))

    def test_cold_part_count_declines_unsupported_prepare_capabilities(self):
        self.seed()
        sql = 'SELECT COUNT(Ref) FROM Document.Orders.Lines'
        with closing(self.context.backend.begin_query_read(query_language=True)):
            pass
        connection = self.context.backend._read_handle.connection
        setlimit = getattr(connection,'setlimit',None)
        if setlimit is not None:
            for category,cap in ((sqlite3.SQLITE_LIMIT_COMPOUND_SELECT,1),
                                 (sqlite3.SQLITE_LIMIT_EXPR_DEPTH,20),
                                 (sqlite3.SQLITE_LIMIT_FUNCTION_ARG,2),
                                 (sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH,32),
                                 (sqlite3.SQLITE_LIMIT_VDBE_OP,256)):
                with self.subTest(category=category,cap=cap):
                    self.context.backend._close_idle_read_handle()
                    with closing(self.context.backend.begin_query_read(query_language=True)):
                        pass
                    setlimit = self.context.backend._read_handle.connection.setlimit
                    previous = setlimit(category,cap)
                    try:
                        with patch('yadinassi.db.sqlite.sqlite_document_count.fetch_one',
                                   side_effect=AssertionError('unsupported proof was prepared')):
                            self.assertEqual(self.query(sql)._rows,((Decimal(3),),))
                    finally:
                        setlimit(category,previous)
        self.compare_one_statement(sql,((Decimal(3),),))

    def test_header_only_source_uses_one_statement_as_well(self):
        from pathlib import Path
        import tempfile
        from yadinassi import Interpreter
        from yadinassi.configuration.configuration_xml import import_configuration
        from yadinassi.db.database_context import SQLiteDBContext
        from test_document_configuration_xml import document_files

        # Use an actual fresh document type with no physical attribute or part tables.
        from xml.etree import ElementTree as ET
        files = document_files()
        path = next(p for p in files if p=='Documents/Orders.xml')
        root = ET.fromstring(files[path])
        children = next(node for node in root.iter() if node.tag.endswith('}ChildObjects'))
        children.clear()
        files[path] = ET.tostring(root, encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            with closing(SQLiteDBContext.create(Path(directory)/'test.sqlite',import_configuration(files))) as context:
                self.context.close()
                self.context=context
                self.vm=Interpreter(database_context=context)
                self.vm.execute('D=Documents.Orders.CreateDocument();D.Date=Date(2024,2,29);D.Write();')
                sql = 'SELECT COUNT(*) FROM Document.Orders'
                # Open the live read connection, but do not prepare the fused
                # SQL before lowering its cap (SQLite can reuse cached SQL).
                with closing(context.backend.begin_query_read(query_language=True)):
                    pass
                connection = context.backend._read_handle.connection
                length_limit = getattr(connection,'setlimit',None)
                if length_limit is not None:
                    for category,cap in ((sqlite3.SQLITE_LIMIT_SQL_LENGTH,650),
                                         (sqlite3.SQLITE_LIMIT_COLUMN,7)):
                        with self.subTest(category=category,cap=cap):
                            context.backend._close_idle_read_handle()
                            with closing(context.backend.begin_query_read(query_language=True)):
                                pass
                            connection = context.backend._read_handle.connection
                            length_limit = connection.setlimit
                            previous = length_limit(category,cap)
                            try:
                                with patch('yadinassi.db.sqlite.sqlite_document_count.fetch_one',
                                           side_effect=AssertionError('oversized SQL was prepared')):
                                    self.assertEqual(self.query(sql)._rows,((Decimal(1),),))
                            finally:
                                length_limit(category,previous)
                    # Document residual SQL must be prepared at stock length.
                    # The optional witness itself is still cold at this cap.
                    with patch.object(query_pushdown,'count_eligible',return_value=False):
                        self.assertEqual(self.query(sql)._rows,((Decimal(1),),))
                    category = sqlite3.SQLITE_LIMIT_LENGTH
                    previous = length_limit(category,200)
                    try:
                        with patch('yadinassi.db.sqlite.sqlite_document_count.fetch_one',
                                   side_effect=AssertionError('oversized GLOB parameter was bound')):
                            self.assertEqual(self.query(sql)._rows,((Decimal(1),),))
                    finally:
                        length_limit(category,previous)
                self.compare_one_statement(sql,((Decimal(1),),))
                set_limit = getattr(connection, 'setlimit', None)
                if set_limit is not None:
                    original = set_limit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 1)
                from contextlib import nullcontext
                old_python = (patch('yadinassi.db.sqlite.sqlite_section_delta._limit',return_value=1)
                              if set_limit is None else nullcontext())
                calls = []
                connection.set_trace_callback(calls.append)
                try:
                    with old_python, patch('yadinassi.db.sqlite.sqlite_document_count.fetch_one',
                                           side_effect=AssertionError('too many SQL arguments')):
                        self.assertEqual(self.query(sql)._rows,((Decimal(1),),))
                finally:
                    connection.set_trace_callback(None)
                    if set_limit is not None:
                        set_limit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, original)
                self.assertTrue(any('SELECT r.record_id,' in statement for statement in calls))


class DocumentCountMainDemoTests(_Queries,unittest.TestCase):
    setUp = main_demo.MainDemoRuntimeTests.setUp

    def test_shipped_receipt_checks_enum_reference_and_posted_inputs(self):
        self.vm.execute(main_demo.SEED+'''D=Documents.Receipt.CreateDocument();D.Number="r1";D.Date=Date(2024,1,1);
            D.Warehouse=Склад.Ref;D.State=Enums.States.Draft;R=D.Lines.Add();
            R.Product=Карточка.Ref;R.Unit=Enums.Units.Piece;R.Quantity=1;R.Amount=0;D.Write();''')
        self.compare_one_statement('SELECT COUNT(Ref) FROM Document.Receipt',((Decimal(1),),))
        self.compare_one_statement('SELECT COUNT(*) FROM Document.Receipt.Lines',((Decimal(1),),))
        ident = self.vm.variables['d']._key.document_id
        record = self.vm.variables['d']._key.record_id
        path = self.context.path
        schema = self.vm.variables['d']._manager._schema
        table = data_table(schema)
        warehouse = attribute_column(next(f for f in schema.fields if f.name=='Warehouse'))
        state = attribute_column(next(f for f in schema.fields if f.name=='State'))
        for name,column,bad in (('document_posting_state','document_revision',1000),
                                (table,warehouse,'00000000-0000-0000-0000-000000000001'),
                                (table,state,'00000000-0000-0000-0000-000000000001')):
            with self.subTest(column=column):
                predicate = ' WHERE document_id=? AND record_id=?'
                keys = (str(ident),str(record))
                with closing(sqlite3.connect(path)) as conn,conn:
                    (prior,) = conn.execute(f'SELECT "{column}" FROM "{name}"'+predicate,keys).fetchone()
                    statement = f'UPDATE "{name}" SET "{column}"=?'+predicate
                    conn.execute(statement,(bad,*keys))
                try:
                    with self.assertRaisesRegex(BSLRuntimeError,'integrity'):
                        self.query('SELECT COUNT(*) FROM Document.Receipt')
                finally:
                    with closing(sqlite3.connect(path)) as conn,conn:
                        conn.execute(statement,(prior,*keys))

    def test_explicit_writer_sees_staged_rows_and_rollback_unchanged(self):
        self.vm.execute(main_demo.SEED+'''D=Documents.Receipt.CreateDocument();D.Number="r1";
            D.Date=Date(2024,1,1);D.Warehouse=Склад.Ref;D.State=Enums.States.Draft;''')
        with patch('yadinassi.db.sqlite.sqlite_document_count.count',
                   side_effect=AssertionError('detached proof for explicit writer')):
            result = self.vm.execute('''BeginTransaction();D.Write();
                Q=New Query("SELECT COUNT(Ref) FROM Document.Receipt");
                Result=Q.Execute();RollbackTransaction();Result''')
        self.assertEqual(result._rows,((Decimal(1),),))
        self.assertEqual(self.query('SELECT COUNT(*) FROM Document.Receipt')._rows,((Decimal(0),),))
