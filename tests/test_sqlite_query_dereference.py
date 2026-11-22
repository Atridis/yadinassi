"""Verify the physical provider independently of query AST binding."""
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from test_main_demo_configuration import source
from yadinassi import Interpreter
from yadinassi.configuration.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.database_transactions import begin, execution, rollback
from yadinassi.db.sqlite.sqlite_document_layout import data_table
from yadinassi.db.sqlite.sqlite_typed_rows import attribute_column


class SQLiteDereferenceProviderTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)/'query.sqlite'
        self.context = SQLiteDBContext.create_main_demo(self.path,
            import_main_demo_configuration(source(),profile=PROFILE))
        self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.vm = Interpreter(database_context=self.context)
        self.addCleanup(self.vm.close)
        self.manager = self.vm._documents.get_index('Receipt')
        self.schema = self.manager._schema
        self.field = next(field for field in self.schema.fields if field.name=='Warehouse')
        self.source = ('document',self.schema.identity,None)
        self.paths = ((self.field.identity,'catalog',self.field.target_catalog_id,'description'),
                      ('ref','document',self.schema.identity,'number'))
        with closing(self.backend.begin_query_read(query_language=True)):
            pass

    def seed(self):
        self.vm.execute('''W=Catalogs.Склады.CreateItem();W.Description="Warehouse";W.Write();
D=Documents.Receipt.CreateDocument();D.Number="A";D.Warehouse=W.Ref;D.Date=Date(2024,1,1);D.Write();
E=Documents.Receipt.CreateDocument();E.Number="B";E.Date=Date(2024,1,1);E.Write();''')

    def test_one_select_shared_paths_and_missing_is_not_empty_string(self):
        self.seed()
        trace=[]
        with closing(self.backend.begin_query_read(query_language=True)) as view:
            view._connection.set_trace_callback(trace.append)
            try:
                self.assertEqual(view.query_dereference(self.source,self.paths,(),10001),
                                 (('Warehouse','A'),(None,'B')))
                self.assertEqual(view.query_dereference(self.source,(self.paths[1],),(),10001),
                                 (('A',),('B',)))
            finally: view._connection.set_trace_callback(None)
        self.assertEqual(len(trace),2)
        self.assertEqual(trace[0].count('LEFT JOIN'),2)
        self.assertNotIn('LEFT JOIN',trace[1])
        self.assertIsNone(self.backend._active)

    def test_nonempty_selected_dangling_target_is_integrity_not_missing(self):
        self.seed()
        table = data_table(self.schema)
        column = attribute_column(self.field)
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute(f'UPDATE "{table}" SET "{column}"=? WHERE record_id='
                           '(SELECT record_id FROM document_record WHERE number=?)',(str(uuid4()),'A'))
        with closing(self.backend.begin_query_read(query_language=True)) as view:
            with self.assertRaisesRegex(BackendError,'integrity'):
                view.query_dereference(self.source,self.paths,(),10001)

    def test_registered_transaction_lease_reads_own_writer(self):
        with execution(self.backend):
            begin(self.backend)
            try:
                with closing(self.backend.begin_query_read(query_language=True)) as view:
                    self.assertEqual(view.query_dereference(self.source,self.paths,(),10001),())
            finally:
                rollback(self.backend)

    def test_nullable_boolean_and_number_order_matches_equivalent_explicit_join(self):
        from dataclasses import replace

        from sqlite_catalog_fixture import configuration_files
        from yadinassi.configuration.configuration_xml import import_configuration
        from yadinassi.db.catalog.catalog_backend import FieldSchema
        from yadinassi.types.values import NULL

        cfg = import_configuration(configuration_files())
        category = next(schema for schema in cfg.catalogs if schema.name=='Categories')
        weight = FieldSchema(uuid4(),'Weight','number',(10,2,'Any'))
        cfg = replace(cfg,catalogs=tuple(replace(schema,fields=(*schema.fields,weight))
            if schema is category else schema for schema in cfg.catalogs))
        with SQLiteDBContext.create(self.path.with_name('order.sqlite'),cfg) as db,                 closing(Interpreter(database_context=db)) as vm:
            vm.execute('''C=Catalogs.Categories.CreateItem(); C.Code="target"; C.Weight=1.5; C.Write();
P=Catalogs.Products.CreateItem(); P.Code="A"; P.Category=C.Ref; P.Write();
Q=Catalogs.Products.CreateItem(); Q.Code="B"; Q.Write();''')
            schema = vm._catalogs.get_index('Products')._schema
            reference = next(field for field in schema.fields if field.name=='Category')
            for field,name in (('deletion_mark','DeletionMark'),(weight.identity,'Weight')):
                for descending in (False,True):
                    with self.subTest(field=name,descending=descending):
                        direction = 'DESC' if descending else 'ASC'
                        joined = (f'SELECT P.Code AS Code,C.{name} AS Value FROM Catalog.Products AS P '
                            'LEFT JOIN Catalog.Categories AS C ON C.Ref=P.Category '
                            f'ORDER BY Value {direction}')
                        vm.variables['sql'] = joined
                        expected = vm.execute('Q=New Query(Sql); Q.Execute()')._rows
                        with closing(db.backend.begin_query_read(query_language=True)) as view:
                            actual = view.query_dereference(('catalog',schema.identity,None),
                                (('code',None,None,None),(reference.identity,'catalog',category.identity,field)),
                                ((1,descending),),10001)
                        self.assertEqual(actual,tuple((code,None if value is NULL else value)
                                                      for code,value in expected))

    def test_simple_source_conjunction_and_exact_document_ref_remain_one_select(self):
        from yadinassi.db.catalog.catalog_backend import CatalogComparison, CatalogPredicate
        self.seed()
        ident = self.vm.execute('D.Ref').reference_uuid
        requested = self.manager._key(ident)
        pred = CatalogPredicate('and',(CatalogComparison('ref','eq',requested),
                                       CatalogComparison('number','eq','a')))
        with closing(self.backend.begin_query_read(query_language=True)) as view:
            trace=[]
            view._connection.set_trace_callback(trace.append)
            try:
                self.assertEqual(view.query_dereference(self.source,self.paths,(),10001,predicate=pred),
                                 (('Warehouse','A'),))
            finally: view._connection.set_trace_callback(None)
            self.assertEqual(len(trace),1)
            plan = view._connection.execute('EXPLAIN QUERY PLAN '+trace[0]).fetchall()
            self.assertTrue(any('SEARCH s' in item[-1] and 'record_id=?' in item[-1] for item in plan),plan)


    def test_or_across_typed_source_fields_matches_explicit_join_and_uses_one_sql(self):
        from yadinassi.types.values import NULL
        self.seed()
        vm = self.vm
        predicate = ('(D.Warehouse=&Warehouse AND D.Number="a") OR '
                     '(D.Number="B" AND D.DeletionMark=False)')
        dotted = ('SELECT D.Number, D.Warehouse.Description AS Caption FROM Document.Receipt AS D '
                  'WHERE '+predicate+' ORDER BY D.Number')
        joined = ('SELECT D.Number, W.Description AS Caption FROM Document.Receipt AS D '
                  'LEFT JOIN Catalog.Склады AS W ON D.Warehouse=W.Ref '
                  'WHERE '+predicate+' ORDER BY D.Number')
        vm.variables['sql'] = joined
        expected = vm.execute('Q=New Query(Sql);Q.SetParameter("Warehouse",W.Ref);Q.Execute()')._rows
        self.assertEqual(expected,(('A','Warehouse'),('B',NULL)))
        vm.variables['sql'] = dotted
        vm.execute('Q=New Query(Sql);Q.SetParameter("Warehouse",W.Ref);')
        trace=[]
        connection = self.backend._read_handle.connection
        connection.set_trace_callback(trace.append)
        try:
            self.assertEqual(vm.execute('Q.Execute()')._rows,expected)
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(len(trace),1,trace)
        self.assertIn(' OR ',trace[0])
        self.assertEqual(trace[0].count('LEFT JOIN "catalog_Склады"'),1)

    def test_audit_catalog_self_path_duplicate_or_with_top1_and_distinct(self):
        self.seed()
        self.vm.execute('Key=W.Code;')
        for distinct in ('','DISTINCT '):
            with self.subTest(distinct=distinct):
                self.vm.variables['sql'] = (
                    f'SELECT {distinct}TOP 1 W.Ref.Description AS Caption FROM Catalog.Склады AS W '
                    'WHERE W.Code=&Key OR W.Code=&Key')
                self.vm.execute('Q=New Query(Sql);Q.SetParameter("Key",Key);')
                trace=[]
                connection = self.backend._read_handle.connection
                connection.set_trace_callback(trace.append)
                try:
                    self.assertEqual(self.vm.execute('Q.Execute()')._rows,(('Warehouse',),))
                finally:
                    connection.set_trace_callback(None)
                self.assertEqual(len(trace),1,trace)
                self.assertIn(' OR ',trace[0])
                self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
                self.assertNotIn('LEFT JOIN',trace[0])

    def test_distinct_preserves_first_spelling_null_and_top_against_join(self):
        from yadinassi.types.values import NULL
        self.vm.execute('''W=Catalogs.Склады.CreateItem();W.Description="Straße";W.Write();
W2=Catalogs.Склады.CreateItem();W2.Description="STRASSE";W2.Write();
W3=Catalogs.Склады.CreateItem();W3.Description="";W3.Write();
D=Documents.Receipt.CreateDocument();D.Number="A";D.Date=Date(2024,1,1);D.Warehouse=W.Ref;D.Write();
D=Documents.Receipt.CreateDocument();D.Number="B";D.Date=Date(2024,1,1);D.Warehouse=W2.Ref;D.Write();
D=Documents.Receipt.CreateDocument();D.Number="C";D.Date=Date(2024,1,1);D.Warehouse=W3.Ref;D.Write();
D=Documents.Receipt.CreateDocument();D.Number="D";D.Date=Date(2024,1,1);D.Write();
D=Documents.Receipt.CreateDocument();D.Number="E";D.Date=Date(2024,1,1);D.Write();''')
        for top, order, wanted in (
                ('','',(('Straße',),('',),(NULL,))),
                ('',' ORDER BY Caption',((NULL,),('',),('Straße',))),
                ('TOP 1 ',' ORDER BY Caption DESC',(('Straße',),)),
                ('TOP 2 ',' ORDER BY Caption DESC',(('Straße',),('',))),
                ('TOP 2 ','',(('Straße',),('',)))):
            with self.subTest(top=top,order=order):
                select = 'SELECT DISTINCT '+top
                predicate = ' WHERE D.DeletionMark=False OR D.Number="unknown"'+order
                self.vm.variables['sql'] = (select+'W.Description AS Caption FROM Document.Receipt AS D '
                    'LEFT JOIN Catalog.Склады AS W ON D.Warehouse=W.Ref'+predicate)
                expected = self.vm.execute('Q=New Query(Sql);Q.Execute()')._rows
                self.assertEqual(expected,wanted)
                self.vm.variables['sql'] = (select+'D.Warehouse.Description AS Caption '
                    'FROM Document.Receipt AS D'+predicate)
                self.vm.execute('Q=New Query(Sql);')
                trace=[]
                connection = self.backend._read_handle.connection
                connection.set_trace_callback(trace.append)
                try:
                    self.assertEqual(self.vm.execute('Q.Execute()')._rows,expected)
                finally:
                    connection.set_trace_callback(None)
                self.assertEqual(len(trace),1,trace)
                self.assertTrue(trace[0].endswith('LIMIT 1' if top=='TOP 1 ' else 'LIMIT 10001'),trace)

    def test_distinct_does_not_hide_an_invalid_duplicate_reference(self):
        from yadinassi import BSLRuntimeError
        self.seed()
        table, column = data_table(self.schema), attribute_column(self.field)
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute(f'UPDATE "{table}" SET "{column}"=? WHERE record_id='
                           '(SELECT record_id FROM document_record WHERE number=?)',(str(uuid4()),'B'))
        self.vm.variables['sql'] = ('SELECT DISTINCT D.Warehouse.Description AS Caption '
                                    'FROM Document.Receipt AS D')
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('Q=New Query(Sql);Q.Execute()')
        self.assertIsNone(self.backend._active)

    def test_or_dereference_reads_staged_owner_and_never_escapes_rollback(self):
        self.seed()
        self.vm.variables['sql'] = (
            'SELECT D.Warehouse.Description AS Caption FROM Document.Receipt AS D '
            'WHERE D.Number="inside" OR D.Number="missing"')
        self.vm.execute('''Q=New Query(Sql);
BeginTransaction();
Inside=Documents.Receipt.CreateDocument();Inside.Number="inside";Inside.Date=Date(2024,1,1);
Inside.Warehouse=W.Ref;Inside.Write();
Captured=Q.Execute();RollbackTransaction();
''')
        self.assertEqual(self.vm.variables['captured']._rows,(('Warehouse',),))
        self.assertEqual(self.vm.execute('Q.Execute()')._rows,())
        self.assertIsNone(self.backend._active)

    def test_distinct_does_not_charge_only_unique_rows_to_input_budget(self):
        from unittest.mock import patch
        from yadinassi import BSLRuntimeError
        self.vm.execute('''W=Catalogs.Склады.CreateItem();W.Description="Same";W.Write();
For I=1 To 2 Do
 D=Documents.Receipt.CreateDocument();D.Number=String(I);D.Date=Date(2024,1,1);D.Warehouse=W.Ref;D.Write();
EndDo;''')
        self.vm.variables['sql'] = ('SELECT DISTINCT D.Warehouse.Description AS Caption '
                                    'FROM Document.Receipt AS D')
        with patch('yadinassi.db.query.queries._MAX_CELLS',1):
            with self.assertRaises(BSLRuntimeError):
                self.vm.execute('Q=New Query(Sql);Q.Execute()')
        self.assertIsNone(self.backend._active)
