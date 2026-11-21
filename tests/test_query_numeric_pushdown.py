"""SQL REAL computation is explicit; persisted Decimal bytes stay unchanged."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogNumericAggregateRequest, CatalogNumericAggregateResult
from yadinassi.db.query.queries import BSLQuery
from yadinassi.db.query.relational_queries import _Plan
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier
from yadinassi.types.values import NULL
from yadinassi.db.query import query_pushdown, queries
import test_catalog_queries as fixtures

class NumericAggregateTests(unittest.TestCase):
    setUp=fixtures.CatalogQueryTests.setUp
    tearDown=fixtures.CatalogQueryTests.tearDown
    text='SELECT SUM(Amount) AS S, AVG(Amount) AS A, COUNT(*) AS N FROM Catalog.Products'
    def query(self,text=None):return BSLQuery(self.vm._catalogs,text or self.text).execute()
    def physical(self):
        manager=self.vm._catalogs.get_index('Products');schema=manager._schema
        field=next(f for f in schema.fields if f.name=='Amount')
        return schema,field,quote_identifier(self.context.backend._layout.table_name(schema.identity)),quote_identifier(self.context.backend._layout.field_name(schema.identity,field.identity))
    def sql(self,statement,args=()):
        with closing(sqlite3.connect(self.context.path)) as c,c:return c.execute(statement,args).fetchall()
    def test_combined_projection_no_materialization_matches_exact_simple_values(self):
        with patch.object(query_pushdown,'try_numeric',return_value=None):expected=self.query()
        with patch.object(_Plan,'load',side_effect=AssertionError('materialization')):actual=self.query()
        self.assertEqual(actual._rows,((Decimal(60),Decimal(20),Decimal(3)),))
        self.assertEqual(actual._rows,expected._rows);self.assertEqual(actual._columns,expected._columns)
    def test_empty_and_top_zero(self):
        _,_,table,_=self.physical();self.sql('DELETE FROM '+table)
        self.assertEqual(self.query()._rows,((NULL,NULL,Decimal(0)),))
        with self.assertRaises(ValueError):self.query('SELECT TOP 0 SUM(Amount) AS S FROM Catalog.Products')
    def test_storage_bytes_are_never_rewritten(self):
        _,_,table,column=self.physical();before=self.sql('SELECT record_id,'+column+' FROM '+table+' ORDER BY record_id')
        self.query();self.query()
        self.assertEqual(self.sql('SELECT record_id,'+column+' FROM '+table+' ORDER BY record_id'),before)
    def test_precision_contract_and_scale_independent_of_ambient_context(self):
        from decimal import localcontext
        _,_,table,column=self.physical()
        self.sql('UPDATE '+table+' SET '+column+'=?',('0.10',))
        with localcontext() as ctx:
            ctx.prec=2;result=self.query()
        self.assertEqual(result._rows,((Decimal('0.30'),Decimal('0.1000000000'),Decimal(3)),))
    def test_unprojected_corruption_and_external_epoch_cannot_hide(self):
        self.query();_,_,table,_=self.physical()
        self.sql('UPDATE '+table+' SET description=?',('x'*5000,))
        with self.assertRaises(BackendError):self.query()
    def test_alias_duplicate_ids_rejected(self):
        _,_,table,_=self.physical();ids=self.sql('SELECT record_id FROM '+table)
        self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(ids[0][0].replace('-','').upper(),ids[1][0]))
        with self.assertRaises(BackendError):self.query()
    def test_live_write_invalidates_warm_sum(self):
        self.query();self.vm.execute('P=Catalogs.Products.FindByCode("1").GetObject();P.Amount=40;P.Write();')
        self.assertEqual(self.query()._rows,((Decimal(90),Decimal(30),Decimal(3)),))
    def test_closed_shape_has_no_sql_fragments_or_foreign_field(self):
        schema,field,_,_=self.physical();view=self.context.backend.begin_read()
        try:
            for ops in ((('sum;DROP TABLE x',field.identity),),(('sum',uuid4()),),(),[['sum',field.identity]]):
                with self.assertRaises(BackendError):view.aggregate_catalog(schema.identity,CatalogNumericAggregateRequest(ops))
        finally:view.close()
        with self.assertRaises(BackendError):view.aggregate_catalog(schema.identity,CatalogNumericAggregateRequest((('sum',field.identity),)))
    def test_unsupported_group_where_distinct_and_expressions_stay_residual(self):
        for text in ('SELECT SUM(Amount) AS S FROM Catalog.Products WHERE Active=TRUE',
                     'SELECT Active, SUM(Amount) AS S FROM Catalog.Products GROUP BY Active',
                     'SELECT SUM(DISTINCT Amount) AS S FROM Catalog.Products',
                     'SELECT SUM(Amount+1) AS S FROM Catalog.Products'):
            with self.subTest(text=text),patch.object(_View,'aggregate_catalog',side_effect=AssertionError('unexpected physical plan')):self.query(text)
    def test_budget_and_provider_shape_checks(self):
        with patch.object(queries,'_MAX_CELLS',2),self.assertRaises(ValueError):self.query()
        for result in (CatalogNumericAggregateResult(True,(1,2,3)),CatalogNumericAggregateResult(3,(None,2,3)),CatalogNumericAggregateResult(3,(1,2,True))):
            with patch.object(_View,'aggregate_catalog',return_value=result),self.assertRaises(BackendError):self.query()
    def test_optional_capability_declines_without_changing_results(self):
        expected=self.query()._rows
        with patch.object(_View,'aggregate_catalog',None):self.assertEqual(self.query()._rows,expected)
        with patch.object(_View,'aggregate_catalog',return_value=None):self.assertEqual(self.query()._rows,expected)
    def test_nonfinite_and_out_of_range_numeric_results_fail_explicitly(self):
        for raw in (float('inf'),float('nan'),1e38):
            with self.subTest(raw=raw),patch.object(_View,'aggregate_catalog',return_value=CatalogNumericAggregateResult(3,(raw,20.0,3))):
                with self.assertRaisesRegex(ValueError,'range exceeded'):self.query()
    def test_statement_is_readonly_real_aggregate_after_validation(self):
        schema,field,_,_=self.physical();view=self.context.backend.begin_read();sql=[]
        view._connection.set_trace_callback(sql.append)
        try:
            result=view.aggregate_catalog(schema.identity,CatalogNumericAggregateRequest((('sum',field.identity),('avg',field.identity))))
            self.assertEqual(result.values,(60.0,20.0))
            self.assertTrue(any('SUM(CAST(' in statement and 'AVG(CAST(' in statement for statement in sql))
            self.assertTrue(any('COUNT(DISTINCT' in statement for statement in sql))
            with self.assertRaises(sqlite3.OperationalError):view._connection.execute('DELETE FROM database_info')
        finally:view.close()

    def test_numeric_corruption_cold_and_warm_never_reaches_cast(self):
        _,_,table,column=self.physical()
        for warm in (False,True):
            for value in ('not-decimal','NaN',None):
                self.sql('UPDATE '+table+' SET '+column+'=?',('10.00',))
                if warm:self.query()
                if value is None:
                    with self.assertRaises(sqlite3.IntegrityError):self.sql('UPDATE '+table+' SET '+column+'=?',(value,))
                    continue
                self.sql('UPDATE '+table+' SET '+column+'=?',(value,))
                with self.subTest(warm=warm,value=value),self.assertRaises(BackendError):self.query()
    def test_repeated_fields_charge_input_once_and_result_width_separately(self):
        text='SELECT SUM(Amount) AS S, AVG(Amount) AS A, SUM(Amount) AS T FROM Catalog.Products'
        with patch.object(queries,'_MAX_CELLS',3):
            self.assertEqual(self.query(text)._rows,((Decimal(60),Decimal(20),Decimal(60)),))
        with patch.object(queries,'_MAX_CELLS',2),self.assertRaises(ValueError):self.query(text)

    def test_transactions_remain_residual(self):
        from yadinassi import Interpreter
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.db.sqlite.sqlite_migration_plan import prepare,apply
        path=self.context.path;self.context.close()
        apply(path,prepare(path,maintenance=True),maintenance=True)
        self.context=SQLiteDBContext(path)
        self.vm=Interpreter(database_context=self.context,output=self.output.append, allow_extensions=True)
        with patch.object(query_pushdown,'try_numeric',return_value=None):expected=self.query()._rows
        seen=[];load=_Plan.load
        def capture(plan,*args):seen.append(1);return load(plan,*args)
        self.vm.register_function('RunQuery',lambda:self.assertEqual(self.query()._rows,expected))
        with patch.object(_Plan,'load',capture):self.vm.execute('BeginTransaction();RunQuery();RollbackTransaction();')
        self.assertEqual(seen,[1])


class EnumNumericAggregateTests(unittest.TestCase):
    def setUp(self):
        import tempfile,shutil
        from pathlib import Path
        from yadinassi import Interpreter
        from yadinassi.configuration.configuration_profile_import import create_prepared,prepare_directory
        from test_inventory_enum_relational_reporting import SOURCE,PROFILE
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);source=root/'source';shutil.copytree(SOURCE/'runtime_source',source)
        path=source/'Catalogs/Products.xml'
        field='<Attribute uuid="f6e074bb-2e4b-4e8e-a250-58b47e73bccc"><Properties><Name>Amount</Name><Type><v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>12</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers></Type></Properties></Attribute>'
        path.write_text(path.read_text(encoding='utf-8').replace('</ChildObjects>',field+'</ChildObjects>'),encoding='utf-8')
        self.context=create_prepared(root/'db.sqlite',prepare_directory(source,profile=PROFILE));self.addCleanup(self.context.close)
        self.vm=Interpreter(database_context=self.context);self.addCleanup(self.vm.close)
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="P";P.Amount=12.5;P.Unit=Enums.Units.Piece;P.Write();')
    def query(self):return BSLQuery(self.vm._catalogs,NumericAggregateTests.text).execute()
    def test_format16_real_enum_numeric_query_no_load_cold_and_warm(self):
        with patch.object(_Plan,'load',side_effect=AssertionError('materialization')):
            for _ in range(2):self.assertEqual(self.query()._rows,((Decimal('12.50'),Decimal('12.5'),Decimal(1)),))
        self.assertFalse(any(k[0]=='catalog-count-unique-v1' for k in self.context.backend._read_handle.proofs))
    def test_post_provider_enum_generation_and_mapping_revocation(self):
        original=_View.aggregate_catalog;scope=self.vm._metadata._enum_storage_scope
        for mapping in (False,True):
            old=scope.generation;managers=scope.namespace._managers;key=next(iter(managers));manager=managers[key]
            def revoke(view,*args,**kwargs):
                result=original(view,*args,**kwargs)
                if isinstance(args[1],CatalogNumericAggregateRequest):
                    if mapping:managers.pop(key)
                    else:scope.generation=-1
                return result
            try:
                with patch.object(_View,'aggregate_catalog',revoke),self.assertRaises(BackendError):self.query()
            finally:scope.generation=old;managers[key]=manager
            self.assertIsNone(self.context.backend._active)

if __name__=='__main__':unittest.main()
