"""Closed stock period grammar; native observation determines result semantics."""
import unittest

from yadinassi import query_parser as syntax


class PeriodStatementGrammarTests(unittest.TestCase):
    def test_combined_source_has_bilingual_closed_names(self):
        for family, name in (('AccumulationRegister','BalanceAndTurnovers'),
                             ('РегистрНакопления','ОстаткиИОбороты')):
            statement=syntax.parse_package('SELECT QuantityOpeningBalance FROM '+family+'.Stock.'+name+'(&StartAt,&EndAt) AS S')[0]
            self.assertEqual(statement.section,'balance_and_turnovers')
            self.assertEqual(statement.period_boundary,(syntax.Parameter('StartAt'),syntax.Parameter('EndAt')))
            self.assertEqual(statement.source_alias,'S')

    def test_only_explicit_day_month_tokens_are_normalized(self):
        for source in ('BalanceAndTurnovers','Turnovers','ОстаткиИОбороты','Обороты'):
            for token,kind in (('Day','day'),('День','day'),('Month','month'),('Месяц','month'),('mOnTh','month')):
                with self.subTest(source=source,token=token):
                    statement=syntax.parse_package('SELECT QuantityTurnover FROM AccumulationRegister.Stock.'+source+'(&A,&B,'+token+')')[0]
                    self.assertEqual(statement.period_boundary,(syntax.Parameter('A'),syntax.Parameter('B'),syntax.Periodicity(kind)))

    def test_optional_filters_completion_and_nonliteral_periodicity_remain_closed(self):
        for args in ('', '&A', '&A,', ',&B', '&A,&B,', '&A,&B,Auto', '&A,&B,Recorder',
                     '&A,&B,Week','&A,&B,"Day"','&A,&B,&Mode','&A,&B,Day,','&A,&B,Day,,',
                     '&A,&B,Day,MovementsAndPeriodBoundaries','&A+1,&B','&A,&B+1','&A,&B,Month,Product=&P'):
            with self.subTest(args=args),self.assertRaises(ValueError):
                syntax.parse_package('SELECT QuantityOpeningBalance FROM AccumulationRegister.Stock.BalanceAndTurnovers('+args+')')

    def test_balance_does_not_gain_periodicity_or_interval_arguments(self):
        for args in ('&A,&B','&A,Day','&A,&B,Month'):
            with self.subTest(args=args),self.assertRaises(ValueError):
                syntax.parse_package('SELECT QuantityBalance FROM AccumulationRegister.Stock.Balance('+args+')')


from decimal import Decimal, localcontext
from unittest.mock import patch
from yadinassi.dates import _from_parts, BSLDate
import test_accumulation_query_runtime as fixture

REG = fixture.REG
START = fixture.DATE
END = _from_parts((2024, 1, 3, 12, 0, 0))


class PeriodStatementRuntimeTests(unittest.TestCase):
    make = fixture.AccumulationQueryRuntimeTests.make
    seed = fixture.AccumulationQueryRuntimeTests.seed
    query = fixture.AccumulationQueryRuntimeTests.query

    def report(self, vm, fields='AmountOpeningBalance,AmountReceipt,AmountExpense,AmountTurnover,AmountClosingBalance',
               start=START, end=END, periodicity=None, table='BalanceAndTurnovers'):
        mode = ',' + periodicity if periodicity else ''
        return self.query(vm, 'SELECT ' + fields + ' FROM ' + REG + '.' + table + '(&A,&B' + mode + ')', A=start, B=end)

    def test_empty_results_keep_numeric_qualifiers(self):
        vm, _ = self.make()
        result = self.report(vm, 'AmountOpeningBalance,AmountClosingBalance,QuantityOpeningBalance,QuantityClosingBalance')
        self.assertEqual(result._rows, ())
        self.assertEqual([column.qualifiers for column in result._columns], [(38, 2, 'Any')]*2 + [(38, 3, 'Any')]*2)

    def test_opening_is_before_start_and_flows_include_both_endpoints(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 3, 3, False, -1), ('A', 1, 5, 5, False, 0),
                       ('A', 1, 2, 2, True, 1), ('A', 1, 100, 100, False, 2)])
        result = self.report(vm, end=BSLDate(START.ticks+10000))
        self.assertEqual(result._rows, ((Decimal(3), Decimal(5), Decimal(2), Decimal(3), Decimal(6)),))
        self.assertEqual(self.report(vm,end=START)._rows, ((Decimal(3),Decimal(5),Decimal(0),Decimal(5),Decimal(8)),))

    def test_carry_only_and_balanced_flows_are_retained(self):
        vm, _ = self.make()
        self.seed(vm, [('Carry', 1, 3, 3, False, -1), ('Flows', 1, 5, 5, False, 0),
                       ('Flows', 1, 5, 5, True, 0), ('Zero', 1, 0, 0, False, 0)])
        rows = self.report(vm, 'Item,AmountOpeningBalance,AmountReceipt,AmountExpense,AmountClosingBalance')._rows
        self.assertEqual(rows, (('Carry',Decimal(3),Decimal(0),Decimal(0),Decimal(3)),
                                ('Flows',Decimal(0),Decimal(5),Decimal(5),Decimal(0))))

    def test_partial_days_clip_first_label_and_do_not_fill_gaps(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,3,3,False,-1),('A',1,5,5,False,0),('A',1,2,2,True,21600),('A',1,1,1,True,172800)])
        rows=self.report(vm,'Period,AmountOpeningBalance,AmountReceipt,AmountExpense,AmountClosingBalance',periodicity='Day')._rows
        self.assertEqual(rows,((START,Decimal(3),Decimal(5),Decimal(2),Decimal(6)),
                              (_from_parts((2024,1,3)),Decimal(6),Decimal(0),Decimal(1),Decimal(5))))
        turnover=self.report(vm,'Period,AmountTurnover',periodicity='День',table='Turnovers')._rows
        self.assertEqual(turnover,((START,Decimal(3)),(_from_parts((2024,1,3)),Decimal(-1))))

    def test_carry_adds_only_start_and_end_boundary_rows(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,7,7,False,-1)])
        rows=self.report(vm,'Period,AmountOpeningBalance,AmountClosingBalance',periodicity='Day')._rows
        self.assertEqual(rows,((START,Decimal(7),Decimal(7)),(_from_parts((2024,1,3)),Decimal(7),Decimal(7))))
        self.assertEqual(self.report(vm,'Period,AmountTurnover',periodicity='Day',table='Turnovers')._rows,())

    def test_wide_day_interval_is_sparse_not_an_unbounded_calendar_expansion(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,7,7,False,-1)])
        rows=self.report(vm,'Period,AmountOpeningBalance,AmountClosingBalance',
                         end=_from_parts((2099,12,31)),periodicity='Day')._rows
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1][0],_from_parts((2099,12,31)))

    def test_russian_fields_and_virtual_name(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,3,3,False,-1),('A',1,5,5,False,0)])
        self.assertEqual(self.report(vm,'AmountНачальныйОстаток,AmountПриход,AmountРасход,AmountОборот,AmountКонечныйОстаток',
                                     table='ОстаткиИОбороты')._rows,
                         ((Decimal(3),Decimal(5),Decimal(0),Decimal(5),Decimal(8)),))

    def test_hostile_decimal_context_does_not_round_vector_totals(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,'1234.56','1.125',False,-1),('A',1,'12.34','0.125',False,0),('A',1,'0.01','0.001',True,0)])
        with localcontext() as context:
            context.prec=2
            for signal in context.traps: context.traps[signal]=True
            self.assertEqual(self.report(vm,'AmountClosingBalance,QuantityClosingBalance')._rows,
                             ((Decimal('1246.89'),Decimal('1.249')),))

    def test_period_row_limit_is_charged_before_top_and_projection(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,7,7,False,-1)])
        with patch.object(syntax,'MAX_ROWS',1):
            with self.assertRaisesRegex(ValueError,'period result row limit'):
                self.report(vm,'COUNT(*) AS N',periodicity='Day')

    def test_period_cells_are_charged_before_materialization(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,7,7,False,-1)])
        # One input row costs ten cells; the first generated boundary carries
        # all dimensions and resource totals even with COUNT(*) projection.
        with patch('yadinassi.queries._MAX_CELLS',11):
            with self.assertRaisesRegex(ValueError,'period result resource limit'):
                self.report(vm,'COUNT(*) AS N',periodicity='Day')

    def test_missing_or_invalid_period_parameters_fail_before_lease(self):
        vm, context = self.make()
        vm.execute('Documents.OwnedAccumulationDoc;')
        with patch.object(context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
            for value in (None,False,Decimal(1),BSLDate(START.ticks+1)):
                with self.subTest(value=value),self.assertRaises(TypeError):
                    self.report(vm,start=value)
            with self.assertRaises(ValueError):self.report(vm,start=END,end=START)

    def test_statement_uses_one_actual_read_lease(self):
        vm, context = self.make()
        self.seed(vm,[('A',1,7,7,False,-1)])
        original=context.backend.begin_query_read
        with patch.object(context.backend,'begin_query_read',wraps=original) as begin:
            self.report(vm,periodicity='Day')
            self.assertEqual(begin.call_count,1)
        self.assertIsNone(context.backend._active)

    def test_nonperiodic_source_does_not_expose_period_or_raw_fields(self):
        vm, _ = self.make()
        for field in ('Period','Recorder','LineNumber','Active','RecordType','Amount','Note'):
            with self.subTest(field=field),self.assertRaises(ValueError):self.report(vm,field)

    def test_periodic_zero_groups_do_not_poison_unrelated_results(self):
        vm, _ = self.make()
        self.seed(vm,[('A',1,0,0,False,0),('B',1,5,5,False,0)])
        self.assertEqual(self.report(vm,'Item,AmountTurnover',periodicity='Day',table='Turnovers')._rows,
                         (('B',Decimal(5)),))
        with self.assertRaisesRegex(ValueError,'All-zero turnover group'):
            self.report(vm,'AmountTurnover',table='Turnovers')

    def test_new_date_range_is_an_explicit_host_guard_not_a_writer_or_legacy_change(self):
        vm, context = self.make()
        vm.execute('Documents.OwnedAccumulationDoc;')
        with patch.object(context.backend,'begin_query_read',side_effect=AssertionError('must not read')):
            for value in (_from_parts((1899,12,31)),_from_parts((2100,1,1)),_from_parts((9999,12,31,23,59,59))):
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,'1900 through 2099'):
                    self.report(vm,start=value,end=value)
        for value in (_from_parts((1900,1,1)),_from_parts((2099,12,31,23,59,59))):
            self.assertEqual(self.report(vm,start=value,end=value)._rows,())
        self.assertEqual(self.query(vm,'SELECT AmountBalance FROM '+REG+'.Balance(&At)',
                                   At=_from_parts((9999,12,31,23,59,59)))._rows,())
