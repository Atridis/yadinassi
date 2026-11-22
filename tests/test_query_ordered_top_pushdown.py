"""ORDER/TOP keeps query-language comparison semantics, not SQLite defaults."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import datetime
import sqlite3
import unittest
from unittest.mock import patch
from uuid import UUID

import test_main_demo_runtime as main
import test_sqlite_catalog_sections as generic
from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import CatalogKey
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_documents import DocumentView
from yadinassi.db.sqlite.sqlite_query_indexes import register_query_collations


class OrderedTopMainDemoTests(unittest.TestCase):
    setUp = main.MainDemoRuntimeTests.setUp

    def query(self, text):
        quoted = text.replace('"', '""')
        return self.vm.execute('Q=New Query("' + quoted + '"); Q.Execute()')._rows

    def seed(self):
        manager = self.vm._catalogs.get_member('Склады')
        self.manager = manager
        entries = (('1','Straße'), ('2','STRASSE'), ('3','Ёж'), ('4','ёж'),
                   ('5','a\0A'), ('6','a\0z'), ('7','Я'))
        identities = {}
        for code, description in entries:
            saved = manager.create_item()
            saved.set_member('Code',code)
            saved.set_member('Description',description)
            saved.write()
            identities[code] = saved._key.record_id.int
        return entries, identities

    def actual_trace(self):
        backend = self.context.backend
        connect = backend._connect
        statements = []
        def traced_connect(**kwargs):
            connection = connect(**kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        if backend._read_handle is not None:
            backend._read_handle.connection.set_trace_callback(statements.append)
        return statements, patch.object(backend,'_connect',side_effect=traced_connect)

    def test_literal_projection_and_unordered_point_query_select_one_page(self):
        self.seed()
        texts = (
            ('SELECT TOP 1 Description, "literal" AS Marker FROM Catalog.Склады ORDER BY Code', ('Straße','literal')),
            ('SELECT TOP 1 Description, &Marker AS Mark FROM Catalog.Склады WHERE Code=&Key', ('STRASSE','param')),
            ('SELECT TOP 1 Description FROM Catalog.Склады WHERE Code=&Key', ('STRASSE',)),
            ('SELECT TOP 1 "constant" AS Marker FROM Catalog.Склады ORDER BY Code', ('constant',)),
            ('SELECT TOP 1 "constant" AS Marker FROM Catalog.Склады WHERE Code="missing"', None),
        )
        from yadinassi.db.query.relational_queries import _Plan
        for text, expected in texts:
            with self.subTest(text=text):
                self.vm.execute('Q=New Query("' + text.replace('"','""') + '");')
                query=self.vm.variables['q']
                if '&Key' in text:query.set_parameter('Key','2')
                if '&Marker' in text:query.set_parameter('Marker','param')
                trace,traced=self.actual_trace()
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('materialized input')), \
                        patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    result=query.execute()
                self.assertEqual(result._rows,() if expected is None else (expected,))
                if '&Marker' in text:
                    self.assertEqual((result._columns[1].name,result._columns[1].kind),('Mark','string'))
                self.assertEqual(len(trace),1,trace)
                self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
                self.assertNotIn('literal',trace[0])
                self.assertNotIn('constant',trace[0])

    def test_distinct_top_one_preserves_concrete_casefold_representative(self):
        self.seed()
        for suffix in (' ORDER BY Description ASC', ' ORDER BY Description DESC'):
            with self.subTest(suffix=suffix):
                text=('SELECT DISTINCT TOP 1 Description, "tag" AS Marker FROM Catalog.Склады '
                      'WHERE Code<="2"'+suffix)
                with patch.object(DocumentView,'ordered_catalog_values',return_value=None) as decline:
                    expected=self.query(text)
                decline.assert_called_once()
                self.assertIn(expected,((('Straße','tag'),),(('STRASSE','tag'),)))
                trace,traced=self.actual_trace()
                with traced, patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    self.assertEqual(self.query(text),expected)
                self.assertEqual(len(trace),1,trace)
                self.assertNotIn('DISTINCT',trace[0])

    def test_distinct_hidden_order_and_throwing_expression_stay_residual(self):
        self.seed()
        with patch.object(DocumentView,'ordered_catalog_values',side_effect=AssertionError('unsupported pushdown')):
            with self.assertRaisesRegex(Exception,'DISTINCT ordering must use projected expressions'):
                self.query('SELECT DISTINCT TOP 1 Description FROM Catalog.Склады ORDER BY Code')
            self.assertEqual(len(self.query('SELECT DISTINCT TOP 2 Description FROM Catalog.Склады ORDER BY Description')),2)
            with self.assertRaisesRegex(Exception,'division by zero'):
                self.query('SELECT TOP 1 Code, CASE WHEN Code="1" THEN 1 ELSE 1/0 END AS Marker '
                           'FROM Catalog.Склады ORDER BY Code')

    def test_qualified_multiple_keys_filter_and_top_in_one_query(self):
        self.seed()
        trace, traced = self.actual_trace()
        with traced, patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
            result = self.query('SELECT TOP 4 W.Code AS C FROM Catalog.Склады AS W '
                                'WHERE W.Code > "1" AND W.DeletionMark = FALSE '
                                'ORDER BY W.Description DESC, C DESC')
        self.assertEqual(result,(('4',),('3',),('7',),('2',)))
        self.assertEqual(len(trace),1,trace)
        self.assertIn('ORDER BY "description" COLLATE yadinassi_casefold_v1 DESC',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 4'),trace)

    def test_casefold_ties_are_ascending_uuid_even_on_descending_order(self):
        entries, identities = self.seed()
        for descending in (False,True):
            with self.subTest(descending=descending):
                expected = sorted(entries,key=lambda item:identities[item[0]])
                expected.sort(key=lambda item:item[1].casefold(),reverse=descending)
                self.assertEqual(self.query('SELECT TOP 7 W.Code FROM Catalog.Склады AS W '
                                            'ORDER BY W.Description '+('DESC' if descending else 'ASC')),
                                 tuple((code,) for code,_ in expected))

    def test_provider_decline_keeps_exact_order_and_empty_result(self):
        self.seed()
        text = 'SELECT TOP 4 W.Code FROM Catalog.Склады AS W ORDER BY W.Description, W.Code DESC'
        expected = self.query(text)
        with patch.object(DocumentView,'ordered_catalog_values',return_value=None) as decline:
            self.assertEqual(self.query(text),expected)
        decline.assert_called_once()
        self.assertEqual(self.query('SELECT TOP 2 Code FROM Catalog.Склады WHERE Code = "missing" ORDER BY Description'),())

    def test_selected_corrupt_sort_field_rejected_without_materialization(self):
        self.seed()
        table = self.context.backend._layout.table_name(self.manager._schema.identity)
        with closing(sqlite3.connect(self.path)) as connection:
            register_query_collations(connection)
            connection.execute(f'UPDATE "{table}" SET description=? WHERE code=?',('Z'*1000,'1'))
            connection.commit()
        with self.assertRaisesRegex(Exception,'integrity'):
            self.query('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = "1" ORDER BY Description')
        self.assertEqual(self.query('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = "2" ORDER BY Description'),(('2',),))

    def test_explicit_transaction_keeps_existing_scan_and_sees_own_write(self):
        self.seed()
        with patch.object(_View,'_validate_scan_scalars',autospec=True,side_effect=_View._validate_scan_scalars) as validate:
            self.vm.execute('BeginTransaction(); W=Catalogs.Склады.CreateItem(); W.Code="99"; '
                            'W.Description="transaction"; W.Write(); '
                            'Q=New Query("SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = ""99"" ORDER BY Description");'
                            'R=Q.Execute(); RollbackTransaction();')
        self.assertEqual(self.vm.variables['r']._rows,(('99',),))
        self.assertTrue(validate.called)
        self.assertEqual(self.query('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = "99" ORDER BY Description'),())


class OrderedTopGenericTests(unittest.TestCase):
    setUp = generic.CatalogSectionTests.setUp
    values = generic.CatalogSectionTests.values
    draft = generic.CatalogSectionTests.draft
    create = generic.CatalogSectionTests.create

    def test_unordered_point_on_non_enum_fast_catalog_path(self):
        card = self.draft(code='1')
        self.create(card)
        self.create(self.draft(code='2'))
        db = SQLiteDBContext(self.path)
        self.addCleanup(db.close)
        vm = Interpreter(database_context=db)
        self.addCleanup(vm.close)
        for key,text in (
            ('1','SELECT TOP 1 Code FROM Catalog.Products WHERE Code=&Key'),
            (vm._catalogs.get_index('Products')._ref(card.key.record_id),
             'SELECT TOP 1 Code FROM Catalog.Products WHERE Ref=&Key'),
        ):
            with self.subTest(text=text):
                vm.execute('Q=New Query("' + text + '");')
                query=vm.variables['q'];query.set_parameter('Key',key)
                with patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    self.assertEqual(query.execute()._rows,(('1',),))

    def test_exact_numbers_dates_and_empty_reference_order(self):
        # Direct non-enum path, with custom physical columns and a reference.
        first = self.backend.begin_write(UUID(int=100))
        try:
            category_key = CatalogKey(self.backend.database_id,self.category.identity,UUID(int=1))
            from yadinassi.db.catalog.catalog_backend import CatalogDraft
            first.create(CatalogDraft(category_key,'C1','Category',False,()))
            first.commit()
        finally: first.close()
        for code, amount, day, ref in (('1','10',2,category_key), ('2','2',2,category_key),
                                       ('3','2',1,None), ('4','-1',2,None)):
            draft = self.draft(code=code)
            values = self.values(amount=amount)
            values = (*values[:3],datetime.datetime(2024,1,day),values[-1] if ref is None else ref)
            self.create(replace(draft,values=values))
        db = SQLiteDBContext(self.path)
        self.addCleanup(db.close)
        vm = Interpreter(database_context=db)
        self.addCleanup(vm.close)
        with patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
            rows = vm.execute('Q=New Query("SELECT TOP 3 P.Code AS C, P.Amount '
                              'FROM Catalog.Products AS P ORDER BY P.Amount, P.Date DESC, P.Category"); Q.Execute()')._rows
            self.assertEqual(rows,(('4',Decimal('-1.00')),('2',Decimal('2.00')),('3',Decimal('2.00'))))
            rows = vm.execute('Q=New Query("SELECT TOP 2 P.Code AS C FROM Catalog.Products AS P '
                              'ORDER BY P.Category, C"); Q.Execute()')._rows
            self.assertEqual(rows,(('3',),('4',)))


class OrderedTopDocumentTests(unittest.TestCase):
    setUp = main.MainDemoRuntimeTests.setUp
    query = OrderedTopMainDemoTests.query
    actual_trace = OrderedTopMainDemoTests.actual_trace

    def seed(self):
        source = '''
For N=1 To 5 Do
 D=Documents.Receipt.CreateDocument();
 If N=1 Then D.Number="Straße"; D.Date=Date(2024,1,2);
 ElsIf N=2 Then D.Number="STRASSE"; D.Date=Date(2024,1,2);
 ElsIf N=3 Then D.Number="straße"; D.Date=Date(2024,1,1);
 ElsIf N=4 Then D.Number="Я"; D.Date=Date(2024,1,2);
 Else D.Number="ignored"; D.Date=Date(2024,1,1); D.DeletionMark=True;
 EndIf;
 D.Write();
EndDo;
'''
        self.vm.execute(source)

    def test_ordered_document_with_literal_matches_residual(self):
        self.seed()
        text='SELECT TOP 1 Number, "tag" AS Marker FROM Document.Receipt WHERE DeletionMark=FALSE ORDER BY Date,Number'
        with patch.object(DocumentView,'ordered_document_values',return_value=None) as decline:
            expected=self.query(text)
        decline.assert_called_once()
        trace,traced=self.actual_trace()
        from yadinassi.db.query.relational_queries import _Plan
        with traced, patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
            self.assertEqual(self.query(text),expected)
        self.assertEqual(len(trace),1,trace)
        self.assertTrue(trace[0].endswith('LIMIT 1'),trace)

    def test_document_top_ref_matches_indexed_point_with_or_without_order(self):
        from yadinassi.db.query.relational_queries import _Plan
        self.seed()
        self.vm.execute('R=Documents.Receipt.FindByNumber("Straße");')
        for suffix in ('',' ORDER BY D.Date'):
            with self.subTest(order=suffix):
                text=('SELECT TOP 1 D.Number,1 AS Marker FROM Document.Receipt AS D WHERE D.Ref=&Key'+suffix)
                self.vm.execute('Q=New Query("'+text+'"); Q.SetParameter("Key",R);')
                with patch.object(DocumentView,'ordered_document_values',return_value=None) as decline:
                    self.assertEqual(self.vm.execute('Q.Execute()')._rows,(('Straße',Decimal(1)),))
                decline.assert_called_once()
                trace,traced = self.actual_trace()
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
                    self.assertEqual(self.vm.execute('Q.Execute()')._rows,(('Straße',Decimal(1)),))
                self.assertEqual(len(trace),1,trace)
                self.assertIn('r.record_id COLLATE BINARY =',trace[0])
                self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
                with closing(sqlite3.connect(self.path)) as raw:
                    register_query_collations(raw)
                    plan = tuple(row[-1] for row in raw.execute('EXPLAIN QUERY PLAN '+trace[0]))
                    self.assertTrue(any('SEARCH r' in operation and 'record_id=?' in operation
                                        for operation in plan),plan)
                self.vm.execute('Q.SetParameter("Key", Documents.Receipt.EmptyRef());')
                self.assertEqual(self.vm.execute('Q.Execute()')._rows,())

    def test_document_top_ref_still_sees_owned_staged_record_and_rollback(self):
        self.vm.execute('''BeginTransaction();
K=Documents.Receipt.GetRef(New UUID());
D=Documents.Receipt.CreateDocument();D.SetNewObjectRef(K);
D.Number="pending";D.Date=Date(2024,1,1);D.Write();
Q=New Query("SELECT TOP 1 D.Number,1 AS Mark FROM Document.Receipt AS D WHERE D.Ref=&Key");
Q.SetParameter("Key",K);Result=Q.Execute();RollbackTransaction();
''')
        self.assertEqual(self.vm.variables['result']._rows,(('pending',Decimal(1)),))
        self.assertEqual(self.vm.execute('Q.Execute()')._rows,())

    def test_number_date_and_ref_same_as_residual_with_stable_ties(self):
        self.seed()
        text = ('SELECT TOP 4 D.Ref AS R, D.Number AS N, D.Date FROM Document.Receipt AS D '
                'WHERE D.DeletionMark = FALSE ORDER BY N DESC, D.Date ASC')
        with patch.object(DocumentView,'ordered_document_values',return_value=None) as decline:
            expected = self.query(text)
        decline.assert_called_once()
        self.assertEqual(tuple(row[1] for row in expected),('Я','straße','STRASSE','Straße'))
        trace, traced = self.actual_trace()
        with traced, patch.object(DocumentView,'_validate_query_source',side_effect=AssertionError('full source')):
            self.assertEqual(self.query(text),expected)
        self.assertEqual(len(trace),1,trace)
        self.assertIn('ORDER BY r.number COLLATE yadinassi_casefold_v1 DESC,r.date COLLATE BINARY ASC',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 4'),trace)
        text = ('SELECT TOP 3 D.Ref AS R, D.Number FROM Document.Receipt AS D ORDER BY R DESC')
        with patch.object(DocumentView,'ordered_document_values',return_value=None):
            expected = self.query(text)
        self.assertEqual(self.query(text),expected)

    def test_physical_custom_projection_uses_only_used_column(self):
        self.seed()
        trace, traced = self.actual_trace()
        with traced, patch.object(DocumentView,'_validate_query_source',side_effect=AssertionError('full source')):
            rows = self.query('SELECT TOP 2 D.Number, D.State FROM Document.Receipt AS D ORDER BY D.Number')
        self.assertEqual(tuple(number for number,_ in rows),('ignored','straße'))
        self.assertEqual(len(trace),1,trace)
        self.assertIn('LEFT JOIN "document_data_',trace[0])
        self.assertEqual(trace[0].count('a."attr_'),1)
        self.assertNotIn('json_',trace[0])

    def test_document_top_inside_transaction_sees_write_then_rollback(self):
        with patch.object(DocumentView,'_validate_query_source',autospec=True,
                          side_effect=DocumentView._validate_query_source) as validate:
            self.vm.execute('BeginTransaction(); D=Documents.Receipt.CreateDocument(); D.Number="pending"; '
                            'D.Date=Date(2024,1,1); D.Write(); '
                            'Q=New Query("SELECT TOP 1 Number FROM Document.Receipt ORDER BY Date"); '
                            'R=Q.Execute(); RollbackTransaction();')
        self.assertEqual(self.vm.variables['r']._rows,(('pending',),))
        self.assertTrue(validate.called)
        self.assertEqual(self.query('SELECT TOP 1 Number FROM Document.Receipt ORDER BY Date'),())
