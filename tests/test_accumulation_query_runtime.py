"""Public query replay of the accepted native16 and bounded source contracts."""
from contextlib import closing
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi import query_parser as syntax
from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.dates import _from_parts
from test_sqlite_accumulation_profile import accumulation_source

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/accumulation_register'
ASSETS = ROOT / 'scripts/accumulation_register_behavior'
REG = 'AccumulationRegister.OwnedAccumulationRows'
DATE = _from_parts((2024, 1, 1, 12, 0, 0))
AT = _from_parts((2024, 1, 2, 0, 0, 0))
SELECTED = b'Procedure Posting(Cancel, Mode) RegisterRecords.OwnedAccumulationRows.Write=True; EndProcedure'


class AccumulationQueryRuntimeTests(unittest.TestCase):
    def make(self, module=SELECTED, files=None):
        temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(temp.cleanup)
        config = import_accumulation_configuration(
            accumulation_source(module) if files is None else files, accumulation_runtime=PROFILE)
        context = SQLiteDBContext.create_accumulation(Path(temp.name) / 'query.sqlite', config)
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context, output=lambda line: None)
        self.addCleanup(vm.close)
        return vm, context

    def query(self, vm, text, **parameters):
        vm.execute('Q=New Query("' + text.replace('"', '""') + '");')
        query = vm.execute('Q')
        for name, value in parameters.items():
            query.set_parameter(name, value)
        return query.execute()

    def seed(self, vm, rows, number='1'):
        vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();O.Number="' + number + '";'
                   'O.Date=Date(2024,1,1);Set=O.RegisterRecords.OwnedAccumulationRows;')
        for item, warehouse, amount, quantity, expense, second in rows:
            vm.execute('R=Set.Add();R.Item="' + item + '";R.Warehouse=' + str(warehouse) + ';'
                'R.Amount=' + str(amount) + ';R.Quantity=' + str(quantity) + ';R.Note="note";'
                'R.Period=Date(2024,1,1,12,0,0)+' + str(second) + ';R.RecordType=AccumulationRecordType.' +
                ('Expense' if expense else 'Receipt') + ';')
        vm.execute('O.Write(DocumentWriteMode.Posting);')
        return vm.execute('O')

    def test_unchanged_native16_observer_and_handler_replay(self):
        vm, _ = self.make(module=None)
        observed, diagnostics = [], []
        vm.register_function('ПодробноеПредставлениеОшибки', lambda info: info.get_member('Description'))
        vm.register_function('AccumulationEmit', lambda n, value: observed.append((int(n), value)), returns_value=False)
        vm.register_function('AccumulationDiagnostic', lambda n, stage, error: diagnostics.append((int(n), stage, error)), returns_value=False)
        vm.execute((ASSETS / 'observe.bsl').read_text(encoding='utf-8'), 'accepted-native16-observer')
        self.assertEqual([n for n, _ in observed], list(range(1, 17)), msg=repr(diagnostics)[:8192])
        self.assertEqual([value for _, value in observed], json.loads((FIXTURE / 'observations.out').read_text(encoding='utf-8')))
        self.assertEqual([(n, stage) for n, stage, _ in diagnostics], [(5, 'write'), (14, 'write'), (15, 'write')])

    def test_query_column_actual_is_readable_but_helper_cannot_assign_it(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        vm.execute('Q=New Query("SELECT Amount FROM ' + REG + '");S=Q.Execute().Select();S.Next();'
                   'Function ReadActual(Value) Return Value;EndFunction '
                   'Procedure AssignActual(Value) Value=99;EndProcedure')
        self.assertEqual(vm.execute('ReadActual(S.Amount)'), Decimal(5))
        with self.assertRaisesRegex(BSLRuntimeError, 'read-only property'):
            vm.execute('AssignActual(S.Amount);')
        self.assertEqual(vm.execute('S.Amount'), Decimal(5))

    def test_number_qualifier_actuals_are_bounded_readonly(self):
        vm, _ = self.make()
        vm.execute('N=New NumberQualifiers(38,3);'
                   'Function ReadActual(Value) Return Value;EndFunction '
                   'Procedure AssignActual(Value) Value=1;EndProcedure')
        self.assertEqual(vm.execute('ReadActual(N.Digits)'), Decimal(38))
        self.assertEqual(vm.execute('ReadActual(N.FractionDigits)'), Decimal(3))
        with self.assertRaisesRegex(BSLRuntimeError, 'read-only property'):
            vm.execute('AssignActual(N.Digits);')
        self.assertEqual(vm.execute('N.Digits'), Decimal(38))

    def test_detached_line_number_actual_is_readable_and_not_mutable(self):
        vm, _ = self.make()
        vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();R=O.RegisterRecords.OwnedAccumulationRows.Add();'
                   'Function ReadActual(Value) Return Value;EndFunction '
                   'Procedure AssignActual(Value) Value=1;EndProcedure')
        self.assertEqual(vm.execute('ReadActual(R.LineNumber)'), Decimal(0))
        with self.assertRaisesRegex(BSLRuntimeError, 'read-only property'):
            vm.execute('AssignActual(R.LineNumber);')
        self.assertEqual(vm.execute('R.LineNumber'), Decimal(0))

    def test_readonly_actual_receiver_is_evaluated_once(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        vm.execute('Q=New Query("SELECT Amount FROM ' + REG + '");S=Q.Execute().Select();S.Next();'
                   'Function ReadActual(Value) Return Value;EndFunction')
        selection, calls = vm.execute('S'), []
        def cursor_once():
            calls.append(True)
            return selection
        vm.register_function('CursorOnce', cursor_once)
        self.assertEqual(vm.execute('ReadActual(CursorOnce().Amount)'), Decimal(5))
        self.assertEqual(calls, [True])

    def test_readonly_actual_does_not_grant_generic_object_or_method_reference(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        vm.execute('Q=New Query("SELECT Amount FROM ' + REG + '");S=Q.Execute().Select();S.Next();'
                   'Function ReadActual(Value) Return Value;EndFunction')
        for expression in ('ReadActual(S.Next)', 'ReadActual(R.Amount)', 'ReadActual(O.Number)'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                vm.execute(expression)

    def test_raw_scalars_and_recorder_reference_types(self):
        vm, _ = self.make()
        obj = self.seed(vm, [('A', 2, '1.25', '2.125', False, 0)])
        result = self.query(vm, 'SELECT Period,Active,Recorder,LineNumber,Item,Warehouse,Amount,Quantity,Note FROM ' + REG)
        self.assertEqual(result._rows, ((DATE, True, obj.get_member('Ref'), Decimal(1), 'A', Decimal(2), Decimal('1.25'), Decimal('2.125'), 'note'),))
        self.assertEqual([c.kind for c in result._columns], ['datetime', 'boolean', 'document_ref', 'number', 'string', 'number', 'number', 'number', 'string'])
        self.assertEqual(result._columns[6].qualifiers, (10, 2, 'Any'))
        self.assertEqual(result._columns[7].qualifiers, (10, 3, 'Any'))

    def test_empty_sources_keep_independent_aggregate_qualifiers(self):
        vm, _ = self.make()
        result = self.query(vm, 'SELECT AmountBalance,QuantityBalance FROM ' + REG + '.Balance(&At)', At=AT)
        self.assertEqual(result._rows, ())
        self.assertEqual([c.qualifiers for c in result._columns], [(38, 2, 'Any'), (38, 3, 'Any')])
        result = self.query(vm, 'SELECT AmountTurnover,AmountReceipt,AmountExpense FROM ' + REG + '.Turnovers(&Start,&EndAt)', Start=DATE, EndAt=AT)
        self.assertEqual(result._rows, ())
        self.assertEqual([c.qualifiers for c in result._columns], [(38, 2, 'Any')] * 3)

    def test_duplicate_occurrences_across_recorders_are_aggregated(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 2, 1, False, 0)] * 2)
        self.seed(vm, [('A', 1, 3, 2, False, 0)], '2')
        self.assertEqual(self.query(vm, 'SELECT AmountBalance,QuantityBalance FROM ' + REG + '.Balance(&At)', At=AT)._rows, ((Decimal(7), Decimal(4)),))
        self.assertEqual(self.query(vm, 'SELECT COUNT(*) AS N FROM ' + REG)._rows, ((Decimal(3),),))

    def test_balance_endpoint_is_exclusive(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 1, 1, False, -1), ('A', 1, 10, 10, False, 0), ('A', 1, 100, 100, False, 1)])
        self.assertEqual(self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)', At=DATE)._rows, ((Decimal(1),),))

    def test_turnover_endpoints_are_inclusive_and_equal_interval_is_valid(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 1, 1, False, -1), ('A', 1, 10, 10, False, 0), ('A', 1, 100, 100, False, 1)])
        self.assertEqual(self.query(vm, 'SELECT AmountTurnover FROM ' + REG + '.Turnovers(&Start,&EndAt)', Start=DATE, EndAt=DATE)._rows, ((Decimal(10),),))

    def test_signed_resources_and_expense_subtotals_are_not_absolute_values(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 10, 4, False, 0), ('A', 1, 3, 1, True, 0), ('A', 1, -2, '-0.5', False, 0), ('A', 1, -1, '-0.25', True, 0)])
        self.assertEqual(self.query(vm, 'SELECT AmountTurnover,AmountReceipt,AmountExpense,QuantityTurnover FROM ' + REG + '.Turnovers(&Start,&EndAt)', Start=DATE, EndAt=AT)._rows,
            ((Decimal(6), Decimal(8), Decimal(2), Decimal('2.75')),))

    def test_balance_suppresses_only_all_resource_zero_groups(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 5, False, 0), ('A', 1, 5, 5, True, 0), ('A', 2, 5, 7, False, 0), ('A', 2, 5, 3, True, 0)])
        self.assertEqual(self.query(vm, 'SELECT Warehouse,AmountBalance,QuantityBalance FROM ' + REG + '.Balance(&At)', At=AT)._rows, ((Decimal(2), Decimal(0), Decimal(4)),))

    def test_zero_net_turnovers_with_nonzero_receipts_and_expenses_remain(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 5, False, 0), ('A', 1, 5, 5, True, 0)])
        self.assertEqual(self.query(vm, 'SELECT AmountTurnover,AmountReceipt,AmountExpense FROM ' + REG + '.Turnovers(&Start,&EndAt)', Start=DATE, EndAt=AT)._rows,
                         ((Decimal(0), Decimal(5), Decimal(5)),))

    def test_unmeasured_all_zero_turnover_group_is_explicitly_deferred(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 0, 0, False, 0)])
        with self.assertRaisesRegex(ValueError, 'All-zero turnover group'):
            self.query(vm, 'SELECT AmountTurnover FROM ' + REG + '.Turnovers(&Start,&EndAt)', Start=DATE, EndAt=AT)

    def test_virtual_grouping_uses_existing_uca_not_unicode_casefold(self):
        vm, _ = self.make()
        self.seed(vm, [('Case', 1, 2, 1, False, 0), ('case', 1, 3, 2, False, 0), ('ß', 1, 7, 1, False, 0), ('SS', 1, 11, 1, False, 0)])
        rows = self.query(vm, 'SELECT Item,AmountBalance FROM ' + REG + '.Balance(&At)', At=AT)._rows
        self.assertEqual(dict(rows), {'Case': Decimal(5), 'ß': Decimal(7), 'SS': Decimal(11)})

    def test_resource_width_expands_and_ambient_decimal_precision_is_ignored(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, '60000000.25', '1.111', False, 0), ('A', 1, '60000000.25', '2.222', False, 0)])
        with localcontext() as ctx:
            ctx.prec = 1
            for signal in ctx.traps: ctx.traps[signal] = True
            rows = self.query(vm, 'SELECT AmountBalance,QuantityBalance FROM ' + REG + '.Balance(&At)', At=AT)._rows
        self.assertEqual(rows, ((Decimal('120000000.50'), Decimal('3.333')),))

    def test_exact_aggregate_overflow_is_refused_not_rounded(self):
        files = accumulation_source(SELECTED)
        path = 'AccumulationRegisters/OwnedAccumulationRows.xml'
        files[path] = files[path].replace(b'<v8:Digits>10</v8:Digits>', b'<v8:Digits>38</v8:Digits>', 1)
        vm, _ = self.make(files=files)
        amount = '9' * 36 + '.99'
        self.seed(vm, [('A', 1, amount, 1, False, 0)] * 2)
        with self.assertRaisesRegex(ValueError, 'outside output qualifiers'):
            self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)', At=AT)

    def test_nonnegative_stored_resource_has_signed_any_balance(self):
        files = accumulation_source(SELECTED)
        path = 'AccumulationRegisters/OwnedAccumulationRows.xml'
        files[path] = files[path].replace(b'<v8:AllowedSign>Any</v8:AllowedSign>', b'<v8:AllowedSign>Nonnegative</v8:AllowedSign>', 1)
        vm, _ = self.make(files=files)
        self.seed(vm, [('A', 1, 5, 2, True, 0)])
        result = self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)', At=AT)
        self.assertEqual(result._rows, ((Decimal(-5),),))
        self.assertEqual(result._columns[0].qualifiers, (38, 2, 'Any'))

    def test_register_without_dimensions_has_one_resource_group(self):
        files = accumulation_source(SELECTED)
        path = 'AccumulationRegisters/OwnedAccumulationRows.xml'
        files[path] = re.sub(rb'<Dimension uuid="[^"]+">.*?</Dimension>', b'', files[path], flags=re.S)
        vm, _ = self.make(files=files)
        vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();O.Number="1";'
                   'R=O.RegisterRecords.OwnedAccumulationRows.Add();R.Amount=5;R.Quantity=2;'
                   'R.Period=Date(2024,1,1);O.Write(DocumentWriteMode.Posting);')
        self.assertEqual(self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)', At=AT)._rows, ((Decimal(5),),))
        self.assertEqual(self.query(vm, 'SELECT COUNT(*) AS N FROM ' + REG + '.Balance(&At)', At=AT)._rows, ((Decimal(1),),))

    def test_boolean_and_date_dimensions_are_typed_and_grouped(self):
        files = accumulation_source(SELECTED)
        path = 'AccumulationRegisters/OwnedAccumulationRows.xml'
        raw = files[path]
        for name, value in ((b'Item', b'<v8:Type>xs:boolean</v8:Type>'),
                            (b'Warehouse', b'<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>')):
            pattern = rb'(<Dimension uuid="[^"]+"><Properties><Name>' + name + rb'</Name><Type>).*?(</Type>)'
            raw = re.sub(pattern, lambda match: match[1] + value + match[2], raw, flags=re.S)
        files[path] = raw
        vm, _ = self.make(files=files)
        vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();O.Number="1";'
                   'R=O.RegisterRecords.OwnedAccumulationRows.Add();R.Item=True;R.Warehouse=Date(2024,1,1,12,0,0);'
                   'R.Amount=5;R.Quantity=2;R.Period=Date(2024,1,1);O.Write(DocumentWriteMode.Posting);')
        self.assertEqual(self.query(vm, 'SELECT Item,Warehouse,AmountBalance FROM ' + REG + '.Balance(&At)', At=AT)._rows, ((True, DATE, Decimal(5)),))

    def test_query_exception_and_interruption_release_outer_read_lease(self):
        from yadinassi.database_transactions import execution, current, begin, rollback
        from yadinassi.document_posting_values import DocumentWriteMode
        for error in (ValueError('query stopped'), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                vm, context = self.make()
                vm.execute('A=Documents.OwnedAccumulationDoc.CreateDocument();A.Number="1";'
                    'R=A.RegisterRecords.OwnedAccumulationRows.Add();R.Item="A";R.Amount=5;'
                    'B=Documents.OwnedAccumulationDoc.CreateDocument();B.Number="2";'
                    'R=B.RegisterRecords.OwnedAccumulationRows.Add();R.Item="B";R.Amount=3;'
                    'Q=New Query("SELECT AmountBalance FROM ' + REG + '.Balance(&At)");'
                    'Q.SetParameter("At",Date(2024,1,2));')
                a, b, query = (vm.variables[name] for name in ('a', 'b', 'q'))
                with execution(context.backend):
                    begin(context.backend)
                    a.write(DocumentWriteMode.POSTING)
                    with patch('yadinassi.accumulation_queries._dimension_key', side_effect=error):
                        with self.assertRaises(type(error)):
                            query.execute()
                    self.assertEqual(current(context.backend).leases, 0)
                    b.write(DocumentWriteMode.POSTING)
                    rollback(context.backend)

    def test_russian_family_virtual_names_and_resource_suffixes(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        self.assertEqual(self.query(vm, 'ВЫБРАТЬ AmountОстаток ИЗ РегистрНакопления.OwnedAccumulationRows.Остатки(&At)', At=AT)._rows, ((Decimal(5),),))
        self.assertEqual(self.query(vm, 'SELECT AmountОборот,AmountПриход,AmountРасход FROM РегистрНакопления.OwnedAccumulationRows.Обороты(&Start,&EndAt)', Start=DATE, EndAt=AT)._rows, ((Decimal(5), Decimal(5), Decimal(0)),))

    def test_raw_and_totals_share_one_package_snapshot(self):
        vm, context = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        with patch.object(context.backend, 'begin_query_read', wraps=context.backend.begin_query_read) as opened:
            result = self.query(vm, 'SELECT Item,Amount INTO Raw FROM ' + REG + '; SELECT Item,AmountBalance FROM ' + REG + '.Balance(&At)', At=AT)
        self.assertEqual(result._rows, (('A', Decimal(5)),))
        self.assertEqual(opened.call_count, 1)

    def test_join_raw_document_reference_and_derived_totals(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        result = self.query(vm, 'SELECT R.Item,D.Number FROM ' + REG + ' AS R INNER JOIN Document.OwnedAccumulationDoc AS D ON R.Recorder=D.Ref')
        self.assertEqual(result._rows, (('A', '1'),))
        result = self.query(vm, 'SELECT B.Item,B.Total FROM (SELECT Item,AmountBalance AS Total FROM ' + REG + '.Balance(&At)) AS B', At=AT)
        self.assertEqual(result._rows, (('A', Decimal(5)),))

    def test_union_preserves_independent_total_qualifiers(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        result = self.query(vm, 'SELECT AmountBalance AS Total FROM ' + REG + '.Balance(&At) UNION ALL SELECT Amount FROM ' + REG, At=AT)
        self.assertEqual(result._rows, ((Decimal(5),), (Decimal(5),)))
        self.assertEqual(result._columns[0].qualifiers, (38, 2, 'Any'))

    def test_outer_transaction_staged_query_then_rollback(self):
        vm, _ = self.make()
        vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();O.Number="1";'
            'R=O.RegisterRecords.OwnedAccumulationRows.Add();R.Item="A";R.Amount=5;'
            'BeginTransaction();O.Write(DocumentWriteMode.Posting);'
            'Q=New Query("SELECT AmountBalance FROM ' + REG + '.Balance(&At)");'
            'Q.SetParameter("At",Date(2024,1,2));S=Q.Execute().Select();S.Next();'
            'WasBalance=S.AmountBalance;RollbackTransaction();')
        self.assertEqual(vm.execute('WasBalance'), Decimal(5))
        self.assertEqual(self.query(vm, 'SELECT COUNT(*) AS N FROM ' + REG)._rows, ((Decimal(0),),))

    def test_missing_or_wrong_boundary_rejected_before_database_read(self):
        vm, context = self.make()
        vm.execute('Documents.OwnedAccumulationDoc;')
        with patch.object(context.backend, 'begin_query_read', side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError): self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)')
            for value in (Decimal(1), '20240102', True):
                with self.subTest(value=value), self.assertRaises(TypeError):
                    self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)', At=value)

    def test_fractional_and_reversed_boundaries_are_deferred(self):
        from yadinassi.dates import BSLDate
        vm, _ = self.make()
        with self.assertRaises(TypeError): self.query(vm, 'SELECT AmountBalance FROM ' + REG + '.Balance(&At)', At=BSLDate(DATE.ticks + 1))
        with self.assertRaises(ValueError): self.query(vm, 'SELECT AmountTurnover FROM ' + REG + '.Turnovers(&Start,&EndAt)', Start=AT, EndAt=DATE)

    def test_record_type_projection_and_enum_parameters_are_not_coerced(self):
        vm, _ = self.make()
        with self.assertRaises(ValueError): self.query(vm, 'SELECT RecordType FROM ' + REG)
        with self.assertRaises(TypeError): self.query(vm, 'SELECT Item FROM ' + REG + ' WHERE Item=&T', T=vm.execute('AccumulationRecordType.Receipt'))

    def test_virtual_non_dimension_fields_are_not_exposed(self):
        vm, _ = self.make()
        for field in ('Amount', 'Note', 'Period', 'Recorder', 'Active', 'RecordType', 'LineNumber'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.query(vm, 'SELECT ' + field + ' FROM ' + REG + '.Balance(&At)', At=AT)

    def test_unsupported_virtual_signatures_fail_closed(self):
        for suffix in ('.Balance()', '.Balance(&At,)', '.Balance(&At,&Filter)', '.Turnovers(&A)',
                       '.Turnovers(&A,&B,Month)', '.BalanceAndTurnovers(&A,&B)', '.SliceLast(&At)'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                syntax.parse_package('SELECT Item FROM ' + REG + suffix)

    def test_input_budgets_charge_excluded_and_unprojected_values(self):
        vm, _ = self.make()
        self.seed(vm, [('A', 1, 5, 2, False, 0)])
        with patch('yadinassi.queries._MAX_CELLS', 1):
            with self.assertRaisesRegex(ValueError, 'input resource limit'):
                self.query(vm, 'SELECT COUNT(*) AS N FROM ' + REG + '.Balance(&At)', At=DATE)

    def test_unknown_register_and_wrong_database_profile_rejected(self):
        vm, _ = self.make()
        with self.assertRaises(ValueError): self.query(vm, 'SELECT Period FROM AccumulationRegister.Unknown')
        with closing(Interpreter()) as plain:
            with self.assertRaises(ValueError): self.query(plain, 'SELECT Period FROM ' + REG)


class AccumulationEvidenceTests(unittest.TestCase):
    def test_immutable_output_and_provenance_hashes(self):
        self.assertEqual(sha256((FIXTURE / 'observations.out').read_bytes()).hexdigest(), '1696b237a5912658363738c2603b791540c5f548f83390062e2e1a5cb12b2494')
        self.assertEqual(sha256((FIXTURE / 'provenance.json').read_bytes()).hexdigest(), 'c55aab6c9b49c5007432ed7ba27524a83ff8444f249cd2a58c72a67be29b6034')

    def test_native_measurement_has_exact_sixteen_completed_verified_cases(self):
        evidence = json.loads((FIXTURE / 'provenance.json').read_text(encoding='utf-8'))
        stage = evidence['native_report']['stage3']
        self.assertIs(evidence['native_measurement_accepted'], True)
        self.assertIs(evidence['runtime_parity_accepted'], False)
        self.assertIsNone(evidence['comparison'])
        self.assertEqual(evidence['repository'], dict(commit='38a11ab9fab5822154fa4ea973a35b7dbcb417e9', tree='15bb86ab74d5287b5927c9a870a4d2f42956712a', github_run_attempt='1', github_run_id='42981217995'))
        for field in ('completed', 'config_verified', 'entered', 'process_exited', 'witness_verified'):
            self.assertIs(stage[field], True)
        self.assertEqual((stage['status'], stage['failure_phase'], stage['record_count']), ('ok', 'final', 16))
        self.assertEqual(stage['partial_observations'], list(map(list, enumerate(json.loads((FIXTURE / 'observations.out').read_text(encoding='utf-8')), 1))))

    def test_native_input_and_host_source_hashes_remain_bound(self):
        evidence = json.loads((FIXTURE / 'provenance.json').read_text(encoding='utf-8'))
        stage = evidence['native_report']['stage3']
        self.assertEqual((len(stage['input_sha256']), len(evidence['host_source_sha256'])), (34, 4))
        for path, digest in {**stage['input_sha256'], **evidence['host_source_sha256']}.items():
            self.assertEqual(sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)

    def test_runtime_canonical_wrapper_has_same_material_projection(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from accumulation_register_behavior import fixture
        raw = (FIXTURE / 'RuntimeAccumulationRegister.xml').read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), 'dbc670763140778ea4549a78035b28aaac8fd2215c3aa4d595df5cba1509833a')
        self.assertEqual(fixture._owned_projection(raw, 'AccumulationRegister'),
                         fixture._owned_projection((ASSETS / 'AccumulationRegister.xml').read_bytes(), 'AccumulationRegister'))

    def test_native_24_acquisition_is_not_a_runtime_source_grant(self):
        files = accumulation_source()
        files['AccumulationRegisters/OwnedAccumulationRows.xml'] = (ASSETS / 'AccumulationRegister.xml').read_bytes()
        with self.assertRaises(ValueError): import_accumulation_configuration(files, accumulation_runtime=PROFILE)
