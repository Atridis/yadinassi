"""Closed host binding/budget contracts; native observations are independent."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from yadinassi import Interpreter
from yadinassi import query_parser as syntax
from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_types import BSLCatalogReference
from yadinassi.configuration_accumulation_references import PROFILE
from yadinassi.configuration_profile_import import prepare_directory, create_prepared
from yadinassi.dates import _from_parts

ROOT = Path(__file__).resolve().parents[1]
REG = 'AccumulationRegister.Stock.'
START = _from_parts((2024, 1, 1))
END = _from_parts((2024, 3, 31, 23, 59, 59))


class DimensionConditionGrammarTests(unittest.TestCase):
    def parse(self, table, args):
        return syntax.parse_package('SELECT COUNT(*) AS N FROM '+REG+table+'('+args+')')[0]

    def test_condition_positions_and_closed_periods(self):
        for table, args in (('Balance', '&At,Product=&P'),
                            ('Turnovers', '&A,&B,,Product=&P'),
                            ('BalanceAndTurnovers', '&A,&B,,,Product=&P')):
            query = self.parse(table, args)
            self.assertEqual(query.virtual_condition,
                syntax.Comparison(syntax.Field(('Product',)), 'eq', syntax.Parameter('P')))
        for table, gap in (('Turnovers', ','), ('BalanceAndTurnovers', ',,')):
            for mode in ('Day', 'Month', 'День', 'Месяц'):
                query = self.parse(table, '&A,&B,'+mode+gap+'Product=&P')
                self.assertIsInstance(query.period_boundary[-1], syntax.Periodicity)

    def test_blank_optional_slots_do_not_change_boundaries(self):
        for table, args, count in (('Balance','&A,',1), ('Turnovers','&A,&B,',2),
                                  ('Turnovers','&A,&B,,',2),
                                  ('BalanceAndTurnovers','&A,&B,',2),
                                  ('BalanceAndTurnovers','&A,&B,,',2),
                                  ('BalanceAndTurnovers','&A,&B,,,',2)):
            query = self.parse(table,args)
            self.assertIsNone(query.virtual_condition)
            self.assertEqual(len(query.period_boundary),count)

    def test_parenthesized_and_bilingual_condition(self):
        query = self.parse('Остатки', '&A,(Product=&P И (Warehouse=&W))')
        self.assertEqual(query.virtual_condition.kind, 'and')
        self.assertEqual(len(query.virtual_condition.terms), 2)
        self.assertEqual(sum(type(n) is syntax.Parameter for n in syntax.walk_nodes(query)),3)

    def test_unsupported_predicates_are_not_general_expressions(self):
        for condition in ('Product=&P OR Warehouse=&W', 'NOT Product=&P',
                          'Product<> &P', 'Product IN &P', 'R.Product=&P',
                          'Product=Warehouse', 'Product="P"', 'Product=&P+1',
                          '&P=Product', 'Product IS NULL', 'Product=&P AND'):
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                self.parse('Balance', '&A,'+condition)

    def test_required_dates_completion_and_slot_misuse_are_refused(self):
        for table,args in (('Balance', ',Product=&P'), ('Balance','&A,,Product=&P'),
                           ('Turnovers','&A,&B,Product=&P'),
                           ('BalanceAndTurnovers','&A,&B,Month,Product=&P'),
                           ('BalanceAndTurnovers','&A,&B,,MovementsAndPeriodBoundaries,Product=&P'),
                           ('BalanceAndTurnovers','&A,&B,,,,Product=&P'),
                           ('Turnovers','&A,&B,Week,Product=&P')):
            with self.subTest(table=table,args=args), self.assertRaises(ValueError):
                self.parse(table,args)

    def test_virtual_predicates_share_existing_query_comparison_budget(self):
        with self.assertRaisesRegex(ValueError,'predicate budget'):
            self.parse('Balance','&A,'+' AND '.join(['Product=&P']*129))

    def test_virtual_nesting_is_bounded(self):
        with self.assertRaisesRegex(ValueError,'nesting'):
            self.parse('Balance','&A,'+'('*18+'Product=&P'+')'*18)

    def test_condition_is_retained_on_join_derived_and_union_sources(self):
        query=syntax.parse_package('SELECT A.QuantityBalance FROM '+REG+'Balance(&At,Product=&P) AS A '
            'LEFT JOIN '+REG+'Turnovers(&A,&B,,Product=&P) AS B ON A.Product=B.Product')[0]
        self.assertIsNotNone(query.virtual_condition)
        self.assertIsNotNone(query.joins[0].source.virtual_condition)
        query=syntax.parse_package('SELECT D.X FROM (SELECT QuantityBalance AS X FROM '+REG+
            'Balance(&At,Product=&P)) AS D UNION ALL SELECT QuantityBalance AS X FROM '+REG+'Balance(&At,Product=&P)')[0]
        self.assertEqual(sum(q.virtual_condition is not None for q in syntax.selects((query,))),2)


SETUP = '''
Function Product(Val Code)
    O=Catalogs.Products.CreateItem(); O.Code=Code; O.Description="same"; O.Write(); Return O.Ref;
EndFunction
Function Warehouse(Val Code)
    O=Catalogs.Warehouses.CreateItem(); O.Code=Code; O.Description="same"; O.Write(); Return O.Ref;
EndFunction
Function Move(Val Code,Val P,Val W,Val At,Val Qty,Val Expense=False)
    If Expense Then O=Documents.Issue.CreateDocument(); Else O=Documents.Receipt.CreateDocument(); EndIf;
    O.Number=Code; O.Date=At; O.Warehouse=W;
    L=O.Lines.Add(); L.Product=P; L.Quantity=Qty; L.Amount=Qty*10;
    O.Write(DocumentWriteMode.Posting); Return O;
EndFunction
P=Product("P"); Other=Product("Other"); W=Warehouse("W"); W2=Warehouse("W2");
'''


class DimensionConditionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'stock.sqlite'
        self.context,self.vm=self.make(self.path)
        self.vm.execute(SETUP)
        self.p,self.w=self.vm.execute('P'),self.vm.execute('W')

    def make(self,path):
        context=create_prepared(path,prepare_directory(ROOT/'scripts/inventory_reference_behavior/runtime_source',profile=PROFILE))
        self.addCleanup(context.close)
        vm=Interpreter(database_context=context,output=lambda text:None);self.addCleanup(vm.close)
        return context,vm

    def seed(self):
        self.vm.execute('Opening=Move("O",P,W,Date(2023,12,31),5);'
            'Receipt=Move("R",P,W,Date(2024,1,15),10);'
            'Issue=Move("I",P,W,Date(2024,1,20),3,True);'
            'OtherWarehouse=Move("W",P,W2,Date(2024,1,15),20);'
            'OtherProduct=Move("P",Other,W,Date(2024,1,15),100);')

    def query(self,text,**params):
        self.vm.execute('Q=New Query("'+text.replace('"','""')+'");')
        query=self.vm.execute('Q')
        for key,value in dict(dict(A=START,B=END,At=END,P=self.p,W=self.w),**params).items():
            query.set_parameter(key,value)
        return query.execute()

    def report(self,table='Balance',condition='Product=&P AND Warehouse=&W',mode='',fields=None,**params):
        if table=='Balance':args='&At,'+condition;fields=fields or 'QuantityBalance'
        else:
            args='&A,&B,'+mode+(',' if table=='Turnovers' else ',,')+condition
            fields=fields or ('QuantityTurnover' if table=='Turnovers' else 'QuantityOpeningBalance,QuantityClosingBalance')
        return self.query('SELECT '+fields+' FROM '+REG+table+'('+args+')',**params)

    def test_selected_balance_and_independent_dimension_axes(self):
        self.seed()
        self.assertEqual(self.report()._rows,((Decimal(12),),))
        self.assertEqual(self.report(condition='Product=&P')._rows,((Decimal(32),),))
        self.assertEqual(self.report(condition='Warehouse=&W')._rows,((Decimal(112),),))

    def test_selected_turnovers_none_day_month(self):
        self.seed()
        self.assertEqual(self.report('Turnovers')._rows,((Decimal(7),),))
        self.assertEqual(sorted(self.report('Turnovers',mode='Day')._rows),[(Decimal(-3),),(Decimal(10),)])
        self.assertEqual(self.report('Turnovers',mode='Month')._rows,((Decimal(7),),))

    def test_combined_condition_keeps_carry_and_closing_boundary(self):
        self.seed()
        self.assertEqual(self.report('BalanceAndTurnovers')._rows,((Decimal(5),Decimal(12)),))
        rows=self.report('BalanceAndTurnovers',mode='Month')._rows
        self.assertEqual(rows,((Decimal(5),Decimal(12)),(Decimal(12),Decimal(12))))

    def test_empty_and_missing_owned_refs_are_no_match_not_all(self):
        empty=self.vm.execute('Catalogs.Products.EmptyRef()')
        missing=self.vm.execute('Catalogs.Products.GetRef(New UUID("00000000-0000-0000-0000-000000009009"))')
        self.seed()
        for value in (empty,missing):
            for table in ('Balance','Turnovers','BalanceAndTurnovers'):
                with self.subTest(table=table),patch('yadinassi.catalogs.BSLCatalogManager._view',side_effect=AssertionError('no existence read')):
                    expected = () if table=='Turnovers' else ((Decimal(0),)*(2 if table=='BalanceAndTurnovers' else 1),)
                    self.assertEqual(self.report(table,P=value)._rows,expected)

    def test_missing_parameter_and_non_dimension_fail_before_query_lease(self):
        with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
            for condition in ('Absent=&P','Quantity=&P','Note=&P','Recorder=&P','Product=&Unset'):
                with self.subTest(condition=condition),self.assertRaises(ValueError):self.report(condition=condition)

    def test_wrong_catalog_and_non_reference_do_not_coerce_to_empty(self):
        with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
            for value in (self.w,'P',Decimal(0),False,UUID(int=1)):
                with self.subTest(kind=type(value).__name__),self.assertRaises(TypeError):self.report(P=value)

    def test_reference_issuer_metadata_and_callbacks_are_exact(self):
        touched=[]
        class HostileCallable:
            def __call__(self,*args):touched.append('call')
            def __eq__(self,other):touched.append('eq');return True
            def __ne__(self,other):touched.append('ne');return False
        for value in (BSLCatalogReference(self.p.value_type,self.p.reference_uuid),
                      replace(self.p,value_type=replace(self.p.value_type)),
                      replace(self.p,metadata=object()),replace(self.p,read_member=lambda ref,name:None),
                      replace(self.p,get_object=None),replace(self.p,read_member=HostileCallable()),
                      replace(self.p,get_object=HostileCallable())):
            with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
                with self.assertRaises(TypeError):self.report(P=value)
        self.assertEqual(touched,[])

    def test_foreign_database_and_vm_family_are_rejected(self):
        _,foreign=self.make(Path(self.temp.name)/'foreign.sqlite')
        with closing(Interpreter(database_context=self.context,output=lambda text:None)) as same_db:
            for other in (foreign,same_db):
                value=other.execute('Catalogs.Products.EmptyRef()')
                with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
                    with self.assertRaises(TypeError):self.report(P=value)

    def test_predicate_term_count_is_not_unbounded(self):
        with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError,'term limit'):
                self.report(condition=' AND '.join(['Product=&P']*17))

    def test_residual_where_grouping_and_joins_stay_after_source_scope(self):
        self.seed()
        result=self.query('SELECT SUM(R.QuantityTurnover) AS N FROM '+REG+
            'Turnovers(&A,&B,,Product=&P) AS R WHERE R.QuantityTurnover>0 GROUP BY R.Product')
        self.assertEqual(result._rows,((Decimal(27),),))
        result=self.query('SELECT A.QuantityBalance,B.QuantityTurnover FROM '+REG+
            'Balance(&At,Product=&P AND Warehouse=&W) AS A LEFT JOIN '+REG+
            'Turnovers(&A,&B,,Product=&P AND Warehouse=&W) AS B ON A.Product=B.Product')
        self.assertEqual(result._rows,((Decimal(12),Decimal(7)),))

    def test_where_and_order_dimensions_are_grouping_dependencies(self):
        self.seed()
        base=' FROM '+REG+'Balance(&At,Product=&P) AS R'
        self.assertEqual(self.query('SELECT R.QuantityBalance'+base+' WHERE R.Warehouse=&W')._rows,
                         ((Decimal(12),),))
        self.assertEqual(sorted(self.query('SELECT R.QuantityBalance'+base+' ORDER BY R.Warehouse')._rows),
                         [(Decimal(12),),(Decimal(20),)])

    def test_having_dimension_dependency_is_not_lost_by_projection(self):
        self.seed()
        self.assertEqual(self.query('SELECT SUM(R.QuantityBalance) AS N FROM '+REG+
            'Balance(&At,Product=&P) AS R GROUP BY R.Warehouse HAVING R.Warehouse=&W')._rows,
            ((Decimal(12),),))

    def test_unselected_dimension_does_not_change_legacy_unconditioned_rows(self):
        self.seed()
        self.assertEqual(sorted(self.query('SELECT QuantityBalance FROM '+REG+'Balance(&At)')._rows),
                         [(Decimal(12),),(Decimal(20),),(Decimal(100),)])
        result=self.report(condition='Product=&P',fields='Warehouse,QuantityBalance')
        self.assertEqual(sorted(row[1] for row in result._rows),[Decimal(12),Decimal(20)])

    def test_zero_aggregate_never_synthesizes_dimensions_or_periods(self):
        self.assertEqual(self.report(fields='Product,QuantityBalance')._rows,())
        for mode in ('Day','Month'):
            for table in ('Turnovers','BalanceAndTurnovers'):
                self.assertEqual(self.report(table,mode=mode)._rows,())
        with patch('yadinassi.queries._MAX_CELLS',1):
            with self.assertRaisesRegex(ValueError,'result resource limit'):self.report()

    def test_derived_and_package_condition_use_single_view(self):
        self.seed()
        queries=('SELECT D.N FROM (SELECT QuantityBalance AS N FROM '+REG+'Balance(&At,Product=&P AND Warehouse=&W)) AS D',
                 'SELECT QuantityBalance AS N INTO T FROM '+REG+'Balance(&At,Product=&P AND Warehouse=&W); SELECT N FROM T')
        original=self.context.backend.begin_query_read
        for text in queries:
            with patch.object(self.context.backend,'begin_query_read',wraps=original) as begin:
                self.assertEqual(self.query(text)._rows,((Decimal(12),),))
            self.assertEqual(begin.call_count,1)
            self.assertIsNone(self.context.backend._active)

    def test_all_rows_charge_input_budget_before_condition(self):
        self.seed()
        with patch.object(syntax,'MAX_ROWS',4):
            with self.assertRaisesRegex(ValueError,'input row limit'):self.report()
        with patch('yadinassi.queries._MAX_CELLS',49):
            with self.assertRaisesRegex(ValueError,'input resource limit'):self.report()

    def test_explicit_condition_avoids_unrequested_generated_groups_but_where_does_not(self):
        self.vm.execute('A=Move("A",P,W,Date(2023,12,31),5);'
            'B=Move("B",Other,W,Date(2023,12,31),10);'
            'C=Move("C",P,W2,Date(2023,12,31),20);')
        with patch.object(syntax,'MAX_ROWS',4):
            self.assertEqual(len(self.report('BalanceAndTurnovers',mode='Month')._rows),2)
            with self.assertRaisesRegex(ValueError,'period result row limit'):
                self.query('SELECT TOP 1 QuantityClosingBalance FROM '+REG+
                    'BalanceAndTurnovers(&A,&B,Month) WHERE Product=&P AND Warehouse=&W')

    def test_unselected_raw_edit_is_still_detected_after_warm_read(self):
        self.seed();self.report()
        key=self.vm.execute('OtherProduct')._key
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE accumulation_movement SET values_json=? WHERE record_id=?',('[]',str(key.record_id)))
        with self.assertRaises((BackendError,ValueError)):self.report()

    def test_unselected_zero_group_does_not_expand_legacy_turnover_admission(self):
        self.vm.execute('A=Move("A",P,W,Date(2024,1,5),5);'
            'B=Move("B",Other,W,Date(2024,1,5),0);')
        self.assertEqual(self.report('Turnovers')._rows,((Decimal(5),),))
        with self.assertRaisesRegex(ValueError,'All-zero turnover group'):
            self.report('Turnovers',P=self.vm.execute('Other'))
        with self.assertRaisesRegex(ValueError,'All-zero turnover group'):
            self.query('SELECT QuantityTurnover FROM '+REG+'Turnovers(&A,&B) WHERE Product=&P')

    def test_query_inside_writer_observes_staging_and_rollback(self):
        seen=[]
        def read():seen.append(self.report()._rows)
        self.vm.register_function('ReadScoped',read,returns_value=False)
        self.vm.execute('BeginTransaction(); D=Move("T",P,W,Date(2024,1,5),7); ReadScoped(); RollbackTransaction();')
        self.assertEqual(seen,[((Decimal(7),),)])
        self.assertEqual(self.report()._rows,((Decimal(0),),))

    def test_reference_results_remain_cursor_typed_without_unload_extension(self):
        self.seed();result=self.report(fields='Product,Warehouse,QuantityBalance')
        self.assertEqual(result._rows,((self.p,self.w,Decimal(12)),))
        self.assertEqual(result._columns[0].reference_identity[1],self.p.value_type.metadata_uuid)
        with self.assertRaisesRegex(ValueError,'Unload'):result.unload()

    def test_scalar_profile_does_not_gain_unmeasured_dimension_predicates(self):
        from test_accumulation_query_runtime import AccumulationQueryRuntimeTests, REG as SCALAR_REG
        vm,_=AccumulationQueryRuntimeTests.make(self)
        with self.assertRaises(ValueError):
            AccumulationQueryRuntimeTests.query(self,vm,'SELECT AmountBalance FROM '+SCALAR_REG+'.Balance(&At,Item=&P)',At=END,P='P')
