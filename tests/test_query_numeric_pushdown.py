"""Exact SQLite aggregate results over scaled numeric storage."""
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
    def sql(self,statement,args=(), *, corrupt=False):
        with closing(sqlite3.connect(self.context.path)) as c,c:
            if corrupt: c.execute('PRAGMA ignore_check_constraints=ON')
            return c.execute(statement,args).fetchall()
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
        self.sql('UPDATE '+table+' SET '+column+'=?',(10,))
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
        for result in (CatalogNumericAggregateResult(True,(1,2,3)),CatalogNumericAggregateResult(3,(None,2,3)),CatalogNumericAggregateResult(3,(Decimal(1),Decimal(2),True)),
                       CatalogNumericAggregateResult(3,(1.0,Decimal(2),3))):
            with patch.object(_View,'aggregate_catalog',return_value=result),self.assertRaises(BackendError):self.query()
    def test_optional_capability_declines_without_changing_results(self):
        expected=self.query()._rows
        with patch.object(_View,'aggregate_catalog',None):self.assertEqual(self.query()._rows,expected)
        with patch.object(_View,'aggregate_catalog',return_value=None):self.assertEqual(self.query()._rows,expected)
    def test_nonfinite_and_out_of_range_numeric_results_fail_explicitly(self):
        for raw in (Decimal('Infinity'),Decimal('NaN'),Decimal('1e38')):
            with self.subTest(raw=raw),patch.object(_View,'aggregate_catalog',return_value=CatalogNumericAggregateResult(3,(raw,Decimal(20),3))):
                with self.assertRaisesRegex(ValueError,'range exceeded'):self.query()
    def test_statement_is_readonly_exact_aggregate_after_validation(self):
        schema,field,_,_=self.physical();view=self.context.backend.begin_read();sql=[]
        view._connection.set_trace_callback(sql.append)
        try:
            result=view.aggregate_catalog(schema.identity,CatalogNumericAggregateRequest((('sum',field.identity),('avg',field.identity))))
            self.assertEqual(tuple(map(type,result.values)),(Decimal,Decimal))
            self.assertEqual(result.values,(Decimal(60),Decimal(20)))
            self.assertEqual(sum('yadinassi_sum_coefficients_v1(' in statement for statement in sql),1)
            self.assertFalse(any(' AS REAL' in statement for statement in sql))
            self.assertTrue(any('COUNT(DISTINCT' in statement for statement in sql))
            with self.assertRaises(sqlite3.OperationalError):view._connection.execute('DELETE FROM database_info')
        finally:view.close()

    def test_numeric_corruption_cold_and_warm_never_reaches_aggregate(self):
        _,_,table,column=self.physical()
        for warm in (False,True):
            for value in ('not-decimal', 'NaN', None, 10**12):
                self.sql('UPDATE '+table+' SET '+column+'=?',(1000,))
                if warm:self.query()
                if value is None:
                    with self.assertRaises(sqlite3.IntegrityError):self.sql('UPDATE '+table+' SET '+column+'=?',(value,))
                    continue
                self.sql('UPDATE '+table+' SET '+column+'=?',(value,),corrupt=True)
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
    def test_numeric_pushdown_rejects_revoked_lexical_owner_before_and_after_provider(self):
        scope = self.vm._metadata._enum_storage_scope
        generation = scope.generation
        try:
            scope.generation = -1
            with patch.object(_View, 'aggregate_catalog') as provider:
                with self.assertRaises(BackendError): self.query()
                provider.assert_not_called()
        finally:
            scope.generation = generation
        self.assertIsNone(self.context.backend._active)

        original = _View.aggregate_catalog
        calls = []
        def revoke(view, identity, request, **kwargs):
            result = original(view, identity, request, **kwargs)
            if type(request) is not CatalogNumericAggregateRequest:
                return result
            calls.append(result)
            scope.generation = -1
            return result
        try:
            with patch.object(_View, 'aggregate_catalog', revoke), self.assertRaises(BackendError):
                self.query()
        finally:
            scope.generation = generation
        self.assertEqual(len(calls), 1)
        self.assertIsNone(self.context.backend._active)

    def test_post_provider_mapping_revocation_only_checks_admitted_enum_dependency(self):
        original = _View.aggregate_catalog
        scope = self.vm._metadata._enum_storage_scope
        managers = scope.namespace._managers
        manager = managers['units']
        piece = self.vm.execute('Enums.Units.Piece')
        expected = ((Decimal('12.50'), Decimal('12.5'), Decimal(1)),)
        for uses_enum in (False, True):
            with self.subTest(uses_enum=uses_enum):
                q = BSLQuery(self.vm._catalogs, NumericAggregateTests.text)
                if uses_enum:
                    # Even an unused SQL parameter is an admitted enum value
                    # at the query boundary; it must retain live authorization.
                    q.set_parameter('ValidateUnit', piece)
                calls = []
                def revoke(view, identity, request, **kwargs):
                    result = original(view, identity, request, **kwargs)
                    if type(request) is not CatalogNumericAggregateRequest:
                        return result
                    calls.append(result)
                    managers.pop('units')
                    return result
                try:
                    with patch.object(_View, 'aggregate_catalog', revoke):
                        if uses_enum:
                            with self.assertRaises(BackendError): q.execute()
                        else:
                            self.assertEqual(q.execute()._rows, expected)
                finally:
                    managers['units'] = manager
                self.assertEqual(len(calls), 1)
                self.assertIsNone(self.context.backend._active)
                self.assertEqual(q.execute()._rows, expected)

if __name__=='__main__':unittest.main()
