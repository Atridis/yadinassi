"""Differential coverage for physical filtering over owned flat sources."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch

import test_information_register_queries as register_fixtures
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.query import query_pushdown
from yadinassi.db.query.relational_queries import _Plan
from yadinassi.db.sqlite.sqlite_document_layout import data_table
from yadinassi.db.sqlite.sqlite_register_layout import register_table
from yadinassi.db.sqlite.sqlite_typed_rows import attribute_column


class FlatWhereTests(unittest.TestCase):
    setUp = register_fixtures.InformationRegisterQueryTests.setUp
    query = register_fixtures.InformationRegisterQueryTests.query
    rows = register_fixtures.InformationRegisterQueryTests.rows

    def seed(self):
        self.vm.execute("""For I=1 To 4 Do
          D=Documents.Orders.CreateDocument();D.Number=String(I);D.Date=Date(2024,1,1);
          D.Amount=I*10; D.Stamp=Date(2024,1,I); D.Active=I<>3;
          R=InformationRegisters.Rates.CreateRecordManager();R.Key=String(I);
          R.Amount=I*10; R.Stamp=Date(2024,1,I); R.Enabled=I<>3;
          If I=1 Then D.Text="O'Reilly"; R.Key="O'Reilly";
          ElsIf I=2 Then D.Text="Straße"; R.Key="Straße";
          ElsIf I=4 Then D.Text="STRASSE"; R.Key="STRASSE"; EndIf;
          D.Write();R.Write();
        EndDo;""")

    def bound(self, text, **parameters):
        q = self.query(text)
        for key,value in parameters.items(): q.set_parameter(key,value)
        return q.execute()._rows

    def trace(self):
        backend = self.context.backend
        connect = backend._connect
        statements = []
        if backend._read_handle is not None:
            backend._read_handle.connection.set_trace_callback(statements.append)
        def open_traced(**kwargs):
            connection = connect(**kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        return statements, patch.object(backend,'_connect',side_effect=open_traced)

    def verify(self, text, expected, **parameters):
        with patch.object(query_pushdown,'try_ordered_select',return_value=None):
            self.assertEqual(self.bound(text,**parameters),expected)
        trace, traced = self.trace()
        with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual load')):
            self.assertEqual(self.bound(text,**parameters),expected)
        result_sql = [s for s in trace if ' WHERE ' in s and ' ORDER BY ' in s and s.endswith('LIMIT 2')]
        self.assertEqual(len(result_sql),1,trace)
        self.assertNotIn('AS REAL',result_sql[0])
        self.assertEqual(trace,result_sql)
        self.assertIsNone(self.context.backend._active)
        return result_sql[0]

    def test_document_where_custom_exact_number_unicode_and_header(self):
        self.seed()
        text = ('SELECT TOP 2 Number,Amount FROM Document.Orders WHERE '
                '(Amount>&Min AND Active=TRUE AND Text=&Folded) OR '
                '(Stamp=&Start AND Text=&Quoted AND DeletionMark=FALSE) '
                'ORDER BY Text,Number')
        sql = self.verify(text,(('1',Decimal(10)),('2',Decimal(20))),
                          Min=Decimal('19.995'),Folded='strasse',Quoted="O'Reilly",Start=self.vm.execute('Date(2024,1,1)'))
        self.assertIn('COLLATE yadinassi_casefold_v1',sql)
        self.assertIn("O''Reilly",sql)

    def test_document_header_disjunction_uses_the_same_scalar_path(self):
        self.seed()
        text = ('SELECT TOP 2 Number FROM Document.Orders '
                'WHERE Number=&First OR Number=&Last ORDER BY Number DESC')
        self.verify(text,(('4',),('1',)),First='1',Last='4')

    def test_register_where_exact_number_folded_ties_and_decline(self):
        self.seed()
        text = ('SELECT TOP 2 Key,Amount FROM InformationRegister.Rates '
                'WHERE Enabled=TRUE AND (Amount>&Min OR Stamp=&Start) ORDER BY Key')
        sql = self.verify(text,(("O'Reilly",Decimal(10)),('STRASSE',Decimal(40))),Min=Decimal('19.995'),Start=self.vm.execute('Date(2024,1,1)'))
        self.assertIn('COLLATE yadinassi_casefold_v1',sql)
        # A reference comparison is still residual: not a scalar SQL operand.
        from yadinassi.db.sqlite.sqlite_registers import RegisterView
        with patch.object(RegisterView,'ordered_register_records',side_effect=AssertionError('reference predicate')):
            expected = self.rows('SELECT TOP 2 Key FROM InformationRegister.Rates '
                                 'WHERE Category IS NOT NULL ORDER BY Key')
        self.assertEqual(len(expected),2)
        too_precise = self.vm.execute('Date(2024,1,1)+0.5')
        with patch.object(RegisterView,'ordered_register_records',side_effect=AssertionError('fractional Date predicate')):
            self.assertEqual(self.bound('SELECT TOP 2 Key FROM InformationRegister.Rates '
                                        'WHERE Stamp=&Moment ORDER BY Key',Moment=too_precise),())

    def test_independent_register_uses_same_exact_constant_projection(self):
        self.seed()
        text=('SELECT TOP 2 Key, 1/3 AS Marker FROM InformationRegister.Rates '
              'WHERE Enabled=TRUE ORDER BY Key')
        self.verify(text,(("O'Reilly",Decimal('0.3333333333')),
                          ('STRASSE',Decimal('0.3333333333'))))
        from yadinassi.db.sqlite.sqlite_registers import RegisterView
        with patch.object(RegisterView,'ordered_register_records',side_effect=AssertionError('row-dependent expression')):
            self.assertEqual(self.rows('SELECT TOP 1 Amount+0 AS Marker FROM InformationRegister.Rates ORDER BY Amount'),
                             ((Decimal(10),),))

    def test_selected_rows_are_validated_and_residual_keeps_its_own_checks(self):
        self.seed()
        backend = self.context.backend
        specs = (
            (data_table(backend._document_schemas[0]), backend._document_schemas[0].fields, 'Text',
             'SELECT TOP 1 Number FROM Document.Orders WHERE Amount < 20 ORDER BY Text', (('1',),)),
            (register_table(backend._register_schemas[0]), backend._register_schemas[0].fields, 'Key',
             'SELECT TOP 1 Amount FROM InformationRegister.Rates WHERE Amount < 20 ORDER BY Amount',
             ((Decimal(10),),)),
        )
        for table, definitions, corrupt_name, text, expected in specs:
            column = {f.name:attribute_column(f) for f in definitions}
            def corrupt(amount, value):
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(f'UPDATE "{table}" SET "{column[corrupt_name]}"=? WHERE "{column["Amount"]}"=?',
                               (value, amount))
            corrupt(4000, 'oversize'*20)
            try:
                self.assertEqual(self.rows(text),expected)
                # The ordinary unbounded path still refuses whole-source damage.
                with self.assertRaisesRegex(BackendError,'integrity'):
                    self.rows(text.replace('TOP 1 ',''))
            finally:
                corrupt(4000, 'STRASSE')
            corrupt(1000, 'oversize'*20)
            try:
                with self.assertRaisesRegex(BackendError,'integrity'):
                    self.rows(text)
                self.assertIsNone(backend._active)
                self.assertFalse(backend._read_handle.connection.in_transaction)
            finally:
                corrupt(1000, "O'Reilly")

    def test_no_partial_where_for_expression_or_explicit_transaction(self):
        self.seed()
        from yadinassi.db.sqlite.sqlite_documents import DocumentView
        from yadinassi.db.sqlite.sqlite_registers import RegisterView
        with patch.object(RegisterView,'ordered_register_records',side_effect=AssertionError('partial predicate')):
            self.assertEqual(self.rows('SELECT TOP 1 Key FROM InformationRegister.Rates '
                                       'WHERE Amount+1>10 AND Enabled=TRUE ORDER BY Amount'),(("O'Reilly",),))
        from uuid import uuid4
        from yadinassi.db.query import query_parser
        document = _Plan(query_parser.parse_package('SELECT TOP 1 Number FROM Document.Orders WHERE Amount>=10 ORDER BY Number')[0],
                         self.vm._catalogs, {}, documents=self.vm._documents)
        register = _Plan(query_parser.parse_package('SELECT TOP 1 Key FROM InformationRegister.Rates '
                                           'WHERE Amount>=10 ORDER BY Key')[0],
                         self.vm._catalogs, {}, information_registers=self.vm._information_registers)
        with closing(self.context.backend.begin_document_write(uuid4())) as writer, \
             patch.object(DocumentView,'ordered_document_values',side_effect=AssertionError('writer document route')), \
             patch.object(RegisterView,'ordered_register_records',side_effect=AssertionError('writer register route')):
            self.assertIsNone(query_pushdown.try_ordered_select(document,writer))
            self.assertIsNone(query_pushdown.try_ordered_select(register,writer))


if __name__ == '__main__':
    unittest.main()
