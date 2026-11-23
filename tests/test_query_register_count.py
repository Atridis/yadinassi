"""Prove the narrow physical COUNT lane against full register reading."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError, FieldSchema
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.query.queries import BSLQuery
from yadinassi.db.query.relational_queries import _Plan
from yadinassi.db.sqlite.sqlite_register_layout import RegisterLayout, register_table
from test_sqlite_register_integration import configuration


COUNT = 'SELECT COUNT(*) AS N FROM InformationRegister.Orders'


class RegisterCountTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'register.sqlite'
        config = configuration(catalogs=False, documents=False)
        source, = config.information_registers
        key, = source.dimensions
        # Include the wide coefficient format as an unprojected payload.
        self.schema = replace(source, dimensions=(key,FieldSchema(uuid4(),'Enabled','boolean')),
            resources=(replace(source.resources[0],qualifiers=(24,2,'Nonnegative')),))
        self.context = SQLiteDBContext.create(self.path, replace(config,information_registers=(self.schema,)))
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)
        self.addCleanup(self.vm.close)

    def sql(self, statement, values=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(statement, values)

    def seed(self, *, unicode=False):
        item = 'Пример' if unicode else 'Item'
        self.vm.execute(f'''
            R=InformationRegisters.Orders.CreateRecordManager();
            R.Item="{item}"; R.Enabled=True; R.Amount=12.50; R.Write();
            R=InformationRegisters.Orders.CreateRecordManager();
            R.Item="{item}"; R.Enabled=False; R.Amount=0.50; R.Write();
        ''')

    def query(self, text=COUNT):
        return BSLQuery(self.vm._catalogs, text, self.vm._documents, self.vm._information_registers)

    def test_actual_bsl_prepared_count_uses_one_statement_for_full_composite_keys(self):
        source = f'Q=New Query("{COUNT}"); S=Q.Execute().Select(); S.Next(); N=S.N;'
        plan = self.vm.prepare(source)
        self.vm.execute_prepared(plan)
        self.assertEqual(self.vm.variables['n'], Decimal(0))
        self.seed()
        # Physical key identity is exact text plus all dimensions, unlike
        # the query language's case-folding comparison for scalar values.
        self.vm.execute('R=InformationRegisters.Orders.CreateRecordManager();'
                        'R.Item="item"; R.Enabled=True; R.Amount=12.50; R.Write();')
        with patch('yadinassi.db.query.register_queries.try_count_register', return_value=None):
            expected = self.query().execute()._rows
        trace = []
        connection = self.context.backend._read_handle.connection
        connection.set_trace_callback(trace.append)
        try:
            with patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
                self.vm.execute_prepared(plan)
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(expected, ((Decimal(3),),))
        self.assertEqual(self.vm.variables['n'], expected[0][0])
        self.assertEqual(len(trace), 1, trace)
        self.assertTrue(trace[0].startswith('SELECT '))
        self.assertIn('GROUP BY', trace[0])

    def test_invalid_hidden_payload_and_duplicate_keys_still_reach_strict_reader(self):
        self.seed()
        layout = RegisterLayout(self.schema)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('PRAGMA ignore_check_constraints=ON')
            connection.execute(f'UPDATE {layout.table} SET {layout.values[0]}=x\'00\'')
        with self.assertRaises(BackendError) as invalid:
            self.query().execute()
        self.assertEqual(invalid.exception.code,'integrity')
        # Put canonical data back and then make a duplicate behind the index.
        self.sql(f'UPDATE {layout.table} SET {layout.values[0]}=?', ((1<<127).to_bytes(16,'big'),))
        self.sql(f'DROP INDEX "{register_table(self.schema)}_dimensions"')
        self.sql(f'INSERT INTO {layout.table} SELECT * FROM {layout.table} LIMIT 1')
        with self.assertRaises(BackendError) as duplicate:
            self.query().execute()
        self.assertEqual(duplicate.exception.code,'integrity')

    def test_unicode_and_filtered_count_keep_full_reader_and_result(self):
        self.seed(unicode=True)
        from yadinassi.db.query.register_queries import load_register
        with patch('yadinassi.db.query.register_queries.load_register', wraps=load_register) as residual:
            self.assertEqual(self.query().execute()._rows, ((Decimal(2),),))
            self.assertEqual(self.query(COUNT+' WHERE Enabled=TRUE').execute()._rows, ((Decimal(1),),))
        self.assertEqual(residual.call_count,2)

    def test_count_preserves_field_and_text_input_limits(self):
        self.seed()
        for name, bound in (('_MAX_CELLS', 5), ('_MAX_RESULT_TEXT', 7)):
            with self.subTest(budget=name):
                with patch('yadinassi.db.query.queries.'+name,bound):
                    with self.assertRaisesRegex(ValueError,'Query input resource limit exceeded'):
                        self.query().execute()
        with self.assertRaisesRegex(ValueError,'TOP outside supported bounds'):
            self.query(COUNT.replace('SELECT','SELECT TOP 0')).execute()

    def test_compact_escaped_dimension_key_keeps_its_separate_budget(self):
        layout = RegisterLayout(self.schema)
        key = '"\\' * 10
        self.sql(f'INSERT INTO {layout.table}({layout.columns}) VALUES({layout.insert_params})',
                 (1,key,1,(1<<127).to_bytes(16,'big')))
        self.assertEqual(self.query().execute()._rows, ((Decimal(1),),))
        with patch('yadinassi.db.sqlite.sqlite_registers.MAX_ROW',45), patch(
                'yadinassi.db.sqlite.sqlite_register_count.fetch_one',
                side_effect=AssertionError('unproved key bound')):
            with self.assertRaises(BackendError) as failure:
                self.query().execute()
        self.assertEqual(failure.exception.code,'invalid_input')

    def test_no_bind_parameters_and_sqlite_errors_keep_storage_boundary(self):
        self.seed()
        self.assertEqual(self.query().execute()._rows, ((Decimal(2),),))
        connection = self.context.backend._read_handle.connection
        if hasattr(connection,'setlimit'):
            old=connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,0)
            try:
                self.assertEqual(self.query().execute()._rows, ((Decimal(2),),))
            finally:
                connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,old)
        self.sql(f'DROP TABLE "{register_table(self.schema)}"')
        with self.assertRaises(BackendError) as failure:
            self.query().execute()
        self.assertEqual(failure.exception.code,'storage_error')

    def test_low_connection_limits_decline_before_first_fused_statement(self):
        self.seed()
        # Open the retained handle via a residual shape, not the fused query.
        self.assertEqual(self.query(COUNT+' WHERE Enabled=TRUE').execute()._rows, ((Decimal(1),),))
        connection = self.context.backend._read_handle.connection
        if not hasattr(connection,'setlimit'):
            self.skipTest('SQLite connection limits unavailable on this Python')
        for limit, value in ((sqlite3.SQLITE_LIMIT_SQL_LENGTH,600),
                             (sqlite3.SQLITE_LIMIT_EXPR_DEPTH,12),
                             (sqlite3.SQLITE_LIMIT_COLUMN,4)):
            with self.subTest(limit=limit):
                old=connection.setlimit(limit,value)
                trace=[]
                connection.set_trace_callback(trace.append)
                try:
                    with patch('yadinassi.db.sqlite.sqlite_register_count.fetch_one',
                               side_effect=AssertionError('fused statement before capability check')):
                        self.assertEqual(self.query().execute()._rows, ((Decimal(2),),))
                finally:
                    connection.set_trace_callback(None)
                    connection.setlimit(limit,old)
                self.assertEqual(len(trace),3,trace)
                self.assertFalse(any('GROUP BY' in sql for sql in trace),trace)
