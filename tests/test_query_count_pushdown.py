"""COUNT physical plan equivalence, not performance or new native evidence."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch
from yadinassi import query_pushdown, relational_queries, queries, query_parser
from yadinassi.catalog_backend import BackendError, CatalogAggregateRequest, CatalogAggregateResult
from yadinassi.queries import BSLQuery
from yadinassi.sqlite_catalog import _View
from yadinassi.sqlite_catalog_layout import quote_identifier
import test_catalog_queries as fixtures

class CountPushdownTests(unittest.TestCase):
    setUp=fixtures.CatalogQueryTests.setUp
    tearDown=fixtures.CatalogQueryTests.tearDown
    def query(self,text='SELECT COUNT(*) AS N FROM Catalog.Products'):
        return BSLQuery(self.vm._catalogs,text).execute()
    def sql(self,statement,args=()):
        with closing(sqlite3.connect(self.context.path)) as c,c:return c.execute(statement,args).fetchall()
    def table(self):
        self.manager=self.vm._catalogs.get_index('Products')
        return quote_identifier(self.context.backend._layout.table_name(self.manager._schema.identity))
    def test_no_materialization_and_result_metadata_equivalence(self):
        with patch.object(query_pushdown,'count_eligible',return_value=False):expected=self.query()
        with patch.object(relational_queries._Plan,'load',side_effect=AssertionError('materialization')):actual=self.query()
        self.assertEqual(actual._rows,((Decimal(3),),));self.assertEqual(actual._rows,expected._rows)
        self.assertEqual(actual._columns,expected._columns)
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Products");S=Q.Execute().Select();S.Next();Message(S.N);')
        self.assertEqual(self.output,['3'])
    def test_empty_and_duplicate_payload_values(self):
        table=self.table();self.sql('UPDATE '+table+' SET description=?',('same',))
        self.assertEqual(self.query()._rows,((Decimal(3),),))
        self.sql('DELETE FROM '+table)
        self.assertEqual(self.query()._rows,((Decimal(0),),))
    def test_alias_duplicate_logical_ids_fail_in_both_paths(self):
        table=self.table();ids=self.sql('SELECT record_id FROM '+table)
        alias=ids[0][0].replace('-','').upper()
        self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(alias,ids[1][0]))
        for enabled in (False,True):
            with patch.object(query_pushdown,'count_eligible',wraps=query_pushdown.count_eligible) as eligible:
                if not enabled:eligible.return_value=False
                with self.assertRaises(BackendError):self.query()
    def test_unique_uuid_alias_and_null_reference_remain_valid(self):
        table=self.table();record=self.sql('SELECT record_id FROM '+table)[0][0]
        self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(record.replace('-','').upper(),record))
        field=next(f for f in self.manager._schema.fields if f.name=='Category')
        column=quote_identifier(self.context.backend._layout.field_name(self.manager._schema.identity,field.identity))
        self.sql('UPDATE '+table+' SET '+column+'=NULL')
        for enabled in (False,True):
            with patch.object(query_pushdown,'count_eligible',wraps=query_pushdown.count_eligible) as eligible:
                if not enabled:eligible.return_value=False
                self.assertEqual(self.query()._rows,((Decimal(3),),))
    def test_corrupt_unprojected_field_cannot_hide_behind_count(self):
        table=self.table();field=next(f for f in self.manager._schema.fields if f.name=='Amount')
        column=quote_identifier(self.context.backend._layout.field_name(self.manager._schema.identity,field.identity))
        self.query() # populate immutable validation proof first
        self.sql('UPDATE '+table+' SET '+column+'=?',('not-a-number',))
        with self.assertRaises(BackendError):self.query()
    def test_input_and_result_limits_preserved(self):
        for module,name in ((query_parser,'MAX_ROWS'),(queries,'_MAX_CELLS')):
            with patch.object(module,name,2),self.assertRaises(ValueError):self.query()
    def test_out_of_shape_declines_and_capability_optional(self):
        for suffix in (' WHERE Active=TRUE',' GROUP BY Active',' ORDER BY N'):
            with patch.object(_View,'aggregate_catalog',side_effect=AssertionError('unexpected pushdown')):
                self.query('SELECT COUNT(*) AS N FROM Catalog.Products'+suffix)
        with patch.object(_View,'aggregate_catalog',None):self.assertEqual(self.query()._rows,((Decimal(3),),))
        with patch.object(_View,'aggregate_catalog',return_value=None):self.assertEqual(self.query()._rows,((Decimal(3),),))
        with patch.object(_View,'aggregate_catalog',return_value=CatalogAggregateResult(True)),self.assertRaises(BackendError):self.query()
    def test_warm_proof_no_revalidation_and_external_epoch_invalidation(self):
        original=_View._scalar;seen=[]
        def scalar(owner,*args,**kwargs):seen.append(1);return original(owner,*args,**kwargs)
        with patch.object(_View,'_scalar',scalar):
            self.query();seen.clear();self.query();self.assertEqual(seen,[])
            table=self.table();self.sql('UPDATE '+table+' SET description=?',('changed',))
            self.query();self.assertGreater(len(seen),0)

    def test_malformed_zero_and_braced_id_match_canonical_rejection(self):
        table=self.table();record=self.sql('SELECT record_id FROM '+table)[0][0]
        for invalid in ('not-a-uuid','00000000-0000-0000-0000-000000000000','{'+record+'}'):
            self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(invalid,record))
            try:
                for enabled in (False,True):
                    with patch.object(query_pushdown,'count_eligible',wraps=query_pushdown.count_eligible) as eligible:
                        if not enabled:eligible.return_value=False
                        with self.assertRaises(BackendError):self.query()
            finally:self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(record,invalid))
    def test_internal_writer_invalidates_unique_proof_and_closed_view_rejects(self):
        self.query()
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="4";P.Write();')
        self.assertEqual(self.query()._rows,((Decimal(4),),))
        manager=self.vm._catalogs.get_index('Products');view=self.context.backend.begin_read()
        try:self.assertEqual(view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest()).count,4)
        finally:view.close()
        with self.assertRaisesRegex(BackendError,'closed'):view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
    def test_readonly_sql_and_warm_distinct_proof_are_separate(self):
        manager=self.vm._catalogs.get_index('Products');backend=self.context.backend
        view=backend.begin_read();sql=[];view._connection.set_trace_callback(sql.append)
        try:
            view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
            self.assertTrue(any('COUNT(DISTINCT' in line for line in sql));sql.clear()
            view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
            self.assertFalse(any('COUNT(DISTINCT' in line for line in sql))
            self.assertTrue(any('SELECT COUNT(*) FROM' in line for line in sql))
            with self.assertRaises(sqlite3.OperationalError):view._connection.execute('DELETE FROM database_info')
        finally:view.close()
    def test_count_proof_external_commit_before_read_and_after_rollback(self):
        from yadinassi.sqlite_read_handles import ReadHandle
        table=self.table();self.query();backend=self.context.backend
        real=backend._check_file;calls=[]
        def check():
            calls.append(1)
            if len(calls)==1:self.sql('DELETE FROM '+table+' WHERE code=?',('1',))
            return real()
        with patch.object(backend,'_check_file',side_effect=check):self.assertEqual(self.query()._rows,((Decimal(2),),))
        complete=ReadHandle.complete
        def after_rollback(handle,proofs):
            self.sql('DELETE FROM '+table+' WHERE code=?',('2',))
            return complete(handle,proofs)
        with patch.object(ReadHandle,'complete',after_rollback):self.assertEqual(self.query()._rows,((Decimal(2),),))
        self.assertEqual(self.query()._rows,((Decimal(1),),))
    def test_wal_storage_is_still_explicitly_unsupported(self):
        self.table();backend=self.context.backend
        backend._close_idle_read_handle();self.sql('PRAGMA journal_mode=WAL')
        with self.assertRaisesRegex(BackendError,'unsupported'):self.query()

    def test_top_zero_is_existing_parser_rejection_empty_or_nonempty(self):
        for empty in (False,True):
            if empty:self.sql('DELETE FROM '+self.table())
            with patch.object(_View,'aggregate_catalog',side_effect=AssertionError('not reached')):
                with self.assertRaisesRegex(ValueError,'TOP outside supported bounds'):
                    self.query('SELECT TOP 0 COUNT(*) AS N FROM Catalog.Products')
    def test_invalid_provider_results_and_operation_fail_closed(self):
        for value in (-1,'3',True,10**30):
            with patch.object(_View,'aggregate_catalog',return_value=CatalogAggregateResult(value)):
                with self.assertRaises((BackendError,ValueError)):self.query()
        with closing(self.context.backend.begin_read()) as view:
            manager=self.vm._catalogs.get_index('Products')
            for request in (object(),CatalogAggregateRequest('raw SQL')):
                with self.assertRaisesRegex(BackendError,'invalid_input'):
                    view.aggregate_catalog(manager._schema.identity,request)
    def test_active_transaction_staged_write_declines_to_current_executor(self):
        from yadinassi import Interpreter
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi.sqlite_migration_plan import prepare,apply
        path=self.context.path;self.context.close()
        apply(path,prepare(path,maintenance=True),maintenance=True)
        self.context=SQLiteDBContext(path)
        self.vm=Interpreter(database_context=self.context,output=self.output.append)
        original=_View.aggregate_catalog;declines=[]
        def observe(view,*args):
            result=original(view,*args)
            if not view._cache_validation_allowed():declines.append(result)
            return result
        load=relational_queries._Plan.load;loads=[]
        def observed_load(plan,*args):
            loads.append(1);return load(plan,*args)
        with patch.object(_View,'aggregate_catalog',observe),patch.object(relational_queries._Plan,'load',observed_load):
            self.vm.execute('''BeginTransaction();P=Catalogs.Products.CreateItem();P.Code="4";P.Write();
Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Products");S=Q.Execute().Select();S.Next();Message(S.N);
RollbackTransaction();''')
        self.assertEqual(self.output,['4']);self.assertEqual(loads,[1]);self.assertTrue(all(item is None for item in declines))
        self.assertEqual(self.query()._rows,((Decimal(3),),))
    def test_failed_close_retires_new_count_proof(self):
        from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
        backend=self.context.backend;manager=self.vm._catalogs.get_index('Products')
        view=backend.begin_read();view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
        self.assertTrue(any(key[0]=='catalog-count-unique-v1' for key in view._validated_sources))
        proxy=AdmissionFaultConnection(view._connection,rollback_error=sqlite3.OperationalError('rollback'),close_error=sqlite3.OperationalError('close'))
        view._connection=proxy;backend._read_handle.connection=proxy
        try:
            with self.assertRaisesRegex(BackendError,'storage_error'):view.close()
            self.assertIsNone(backend._read_handle)
            with self.assertRaisesRegex(BackendError,'busy'):backend.begin_read()
        finally:proxy.disable_faults();view.close()
        with closing(backend.begin_read()) as fresh:
            self.assertFalse(any(key[0]=='catalog-count-unique-v1' for key in fresh._validated_sources))
            self.assertEqual(fresh.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest()).count,3)
