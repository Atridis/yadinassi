"""Closed Active=true accumulation posting, not a broad native parity claim."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.accumulation_movements import AccumulationDirection, AccumulationReplacement
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import begin, current, execution
from yadinassi.document_posting import PostingLimitError
from yadinassi.document_posting_values import DocumentWriteMode
from yadinassi.transaction_backend import TransactionRequest
from test_configuration_accumulation import source, MODULE, DOC

ROOT = Path(__file__).resolve().parents[1]
SELECTED = b'Procedure Posting(Cancel, PostingMode) RegisterRecords.Rows.Write=True; EndProcedure'


class AccumulationPostingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.counter = 0
        self.make()

    def make(self, module=SELECTED):
        self.counter += 1
        files = source()
        files[MODULE] = module.encode() if type(module) is str else module
        self.config = import_accumulation_configuration(files, accumulation_runtime=PROFILE)
        self.path = Path(self.temp.name) / ('runtime%d.sqlite' % self.counter)
        self.context = SQLiteDBContext.create_accumulation(self.path, self.config)
        self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.lines = []
        self.vm = Interpreter(database_context=self.context, output=self.lines.append)
        self.addCleanup(self.vm.close)

    def new(self, number='1', row=True):
        self.vm.execute('O=Documents.Order.CreateDocument();O.Number="%s";O.Date=Date(2024,1,1);S=O.RegisterRecords.Rows;' % number)
        if row:
            self.vm.execute('R=S.Add();R.Item="A";R.Amount=7.25;R.Period=Date(2024,1,1);R.Note="note";')
        return self.vm.execute('O')

    def post(self):
        self.vm.execute('O.Write(DocumentWriteMode.Posting);')

    def rows(self, obj):
        return self.backend.read_accumulation(self.config.registers[0].identity, obj._key).rows

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(statement, args).fetchall()

    def test_exact_enum_aliases_and_type_identity(self):
        self.assertIs(self.vm.execute('AccumulationRecordType.Receipt'), AccumulationDirection.RECEIPT)
        self.assertIs(self.vm.execute('ВидДвиженияНакопления.Приход'), AccumulationDirection.RECEIPT)
        self.assertIs(self.vm.execute('ВидДвиженияНакопления.Расход'), AccumulationDirection.EXPENSE)
        self.assertTrue(self.vm.execute('(TypeOf(AccumulationRecordType.Expense)=Type("ВидДвиженияНакопления"))'))
        self.assertTrue(self.vm.execute('(Type("AccumulationRecordType")=Type("ВидДвиженияНакопления"))'))
        self.assertFalse(self.vm.execute('(AccumulationRecordType.Receipt=AccumulationRecordType.Expense)'))

    def test_enum_namespace_requires_accumulation_source_grant(self):
        with closing(Interpreter()) as vm:
            with self.assertRaises(BSLRuntimeError):
                vm.execute('AccumulationRecordType.Receipt')

    def test_enum_is_not_a_numeric_flag_or_string(self):
        self.new()
        for value in ('0', '1', 'True', 'False', '"Receipt"', 'Undefined'):
            with self.subTest(value=value), self.assertRaises(BSLRuntimeError):
                self.vm.execute('R.RecordType=' + value)
        self.assertIs(self.vm.execute('R.RecordType'), AccumulationDirection.RECEIPT)

    def test_enum_presentation_and_type_description_are_deferred(self):
        for expression in ('String(AccumulationRecordType.Receipt)',
                           'String(Type("AccumulationRecordType"))',
                           'New TypeDescription("AccumulationRecordType")'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)

    def test_measured_detached_defaults(self):
        self.new(row=False)
        self.vm.execute('R=S.Add();')
        self.assertTrue(self.vm.execute('R.Active'))
        self.assertIs(self.vm.execute('R.RecordType'), AccumulationDirection.RECEIPT)
        self.assertEqual(self.vm.execute('R.Period'), self.vm.execute('Date(1,1,1)'))
        self.assertEqual(self.vm.execute('R.LineNumber'), Decimal(0))
        self.assertEqual(self.vm.execute('R.Amount'), Decimal(0))
        self.post()
        with self.assertRaises(BSLRuntimeError): self.vm.execute('R.LineNumber')

    def test_russian_row_members_and_owned_collection(self):
        obj = self.new(row=False)
        self.vm.execute('R=O.Движения.Rows.Добавить();R.Период=Дата(2024,1,2);R.Активность=Истина;'
                        'R.ВидДвижения=ВидДвиженияНакопления.Расход;R.Amount=-2.50;O.Записать(РежимЗаписиДокумента.Проведение);')
        row, = self.rows(obj)
        self.assertIs(row.direction, AccumulationDirection.EXPENSE)
        self.assertEqual(row.period, datetime(2024,1,2))
        self.assertEqual(row.resources, (Decimal('-2.50'),))

    def test_post_persists_exact_occurrences_and_raw_active(self):
        obj = self.new()
        self.post()
        row, = self.rows(obj)
        self.assertEqual((row.line_number, row.dimensions, row.resources, row.attributes),
                         (1, ('A',), (Decimal('7.25'),), ('note',)))
        self.assertIs(row.active, True)
        self.assertTrue(obj.get_member('Posted'))
        self.assertFalse(obj.is_new())
        self.assertEqual(self.sql('SELECT COUNT(*) FROM unit_of_work_receipt'), [(1,)])

    def test_duplicate_dimensions_period_and_payload_keep_lines(self):
        obj = self.new()
        self.vm.execute('R=S.Add();R.Item="A";R.Amount=7.25;R.Period=Date(2024,1,1);R.Note="note";')
        self.post()
        rows = self.rows(obj)
        self.assertEqual([row.line_number for row in rows], [1,2])
        self.assertEqual(rows[0].dimensions, rows[1].dimensions)
        other = self.new('2')
        self.post()
        self.assertEqual(len(self.rows(obj)), 2)
        self.assertEqual(len(self.rows(other)), 1)

    def test_signed_resources_do_not_coerce_direction(self):
        obj = self.new()
        self.vm.execute('R.Amount=-7.25;R.RecordType=AccumulationRecordType.Expense;')
        self.post()
        row, = self.rows(obj)
        self.assertEqual(row.resources, (Decimal('-7.25'),))
        self.assertIs(row.direction, AccumulationDirection.EXPENSE)

    def test_closed_profile_refuses_any_inactive_row_atomically(self):
        obj = self.new()
        self.vm.execute('R=S.Add();R.Active=False;')
        with self.assertRaises(BSLRuntimeError): self.post()
        self.assertTrue(obj.is_new())
        self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.rows(obj), ())
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'), [(0,)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM accumulation_movement_receipt'), [(0,)])

    def test_all_inactive_is_deferred_not_inferred_native_behavior(self):
        obj = self.new()
        self.vm.execute('R.Active=False;')
        with self.assertRaises(BSLRuntimeError): self.post()
        self.assertEqual(self.rows(obj), ())
        self.vm.execute('R.Active=True;')
        self.post()
        self.assertEqual(len(self.rows(obj)), 1)

    def test_host_journal_cannot_bypass_active_only_profile(self):
        obj = self.new()
        self.post()
        from uuid import uuid4
        with closing(self.backend.begin_unit_of_work(uuid4())) as unit:
            partition = unit.read_accumulation(self.config.registers[0].identity, obj._key)
            request = AccumulationReplacement(partition.register_id, obj._key,
                (replace(partition.rows[0], active=False),), partition.snapshot)
            with self.assertRaises(BackendError):
                unit.stage(TransactionRequest('accumulation_replace', request))
            self.assertEqual(unit.requests, ())
        self.assertTrue(self.rows(obj)[0].active)

    def test_stored_inactive_row_refused_on_open_and_read(self):
        obj = self.new()
        self.post()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('UPDATE accumulation_movement SET active=0')
            connection.commit()
        with self.assertRaises(BackendError): self.rows(obj)
        with self.assertRaises(BackendError): SQLiteDBContext(self.path)

    def test_same_detached_buffer_repost_and_fresh_empty_clear(self):
        obj = self.new()
        self.post()
        self.vm.execute('R=S.Add();R.Amount=3;')
        self.post()
        self.assertEqual(len(self.rows(obj)), 2)
        self.vm.execute('Fresh=O.Ref.GetObject();Fresh.Write(DocumentWriteMode.Posting);')
        self.assertEqual(self.rows(obj), ())
        self.assertTrue(self.vm.execute('Fresh.Posted'))
        self.assertEqual(self.vm.execute('S.Count()'), Decimal(2))

    def test_ordinary_write_preserves_posted_and_movements(self):
        obj = self.new()
        self.post()
        rows = self.rows(obj)
        self.vm.execute('S.Clear();O.Write(DocumentWriteMode.Write);')
        self.assertEqual(self.rows(obj), rows)
        self.assertTrue(obj.get_member('Posted'))

    def test_undo_posting_removes_partition_rows_not_detached_buffer(self):
        obj = self.new()
        self.post()
        self.vm.execute('O.Write(DocumentWriteMode.UndoPosting);')
        self.assertEqual(self.rows(obj), ())
        self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.vm.execute('S.Count()'), Decimal(1))

    def test_explicit_replacement_writes_share_one_root_receipt(self):
        self.make('Procedure Posting(Cancel,Mode) S=RegisterRecords.Rows;S.Write=False;'
                  'S.Write();S.Clear();R=S.Add();R.Amount=9;S.Write();EndProcedure')
        obj = self.new()
        self.post()
        self.assertEqual(self.rows(obj)[0].resources, (Decimal(9),))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM accumulation_movement_receipt'), [(2,)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM unit_of_work_receipt'), [(1,)])

    def test_cancel_after_explicit_write_rolls_back_all_ports(self):
        self.make('Procedure Posting(Cancel,Mode) RegisterRecords.Rows.Write();Cancel=True;EndProcedure')
        obj = self.new()
        with self.assertRaises(BSLRuntimeError): self.post()
        self.assertTrue(obj.is_new())
        self.assertEqual(self.rows(obj), ())
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_posting_state'), [(0,)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM accumulation_movement_receipt'), [(0,)])

    def test_error_after_explicit_write_rolls_back_all_ports(self):
        self.make('Procedure Posting(Cancel,Mode) RegisterRecords.Rows.Write();Raise "cancel";EndProcedure')
        obj = self.new()
        with self.assertRaises(BSLRuntimeError): self.post()
        self.assertEqual(self.rows(obj), ())
        self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'), [(0,)])

    def test_outer_rollback_retains_identity_not_persistence(self):
        obj = self.new()
        self.vm.execute('BeginTransaction();O.Write(DocumentWriteMode.Posting);Saved=O.Ref;RollbackTransaction();')
        self.assertTrue(obj.is_new())
        self.assertFalse(self.vm.execute('(Saved=Documents.Order.EmptyRef())'))
        self.assertTrue(self.vm.execute('(Saved=O.Ref)'))
        self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.rows(obj), ())
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'), [(0,)])

    def test_handler_observes_staged_reference_before_persistence(self):
        self.make('''Procedure Posting(Cancel,Mode)
If Ref=Documents.Order.EmptyRef() Then Raise "empty staged reference";EndIf;
AdditionalProperties.Insert("InsideRef",Ref);
RegisterRecords.Rows.Write=True;
EndProcedure''')
        obj = self.new()
        self.post()
        self.assertEqual(obj.get_member('AdditionalProperties').get_member('InsideRef'),
                         obj.get_member('Ref'))
        self.assertEqual(len(self.rows(obj)), 1)

    def test_two_documents_and_failed_later_write_preserve_earlier_stage(self):
        a = self.new()
        b = self.new('2')
        self.vm.variables.update(a=a,b=b)
        self.vm.execute('B.RegisterRecords.Rows.Get(0).Active=False;BeginTransaction();'
                        'A.Write(DocumentWriteMode.Posting);Try B.Write(DocumentWriteMode.Posting);Except EndTry;CommitTransaction();')
        self.assertFalse(a.is_new())
        self.assertTrue(b.is_new())
        self.assertEqual(len(self.rows(a)), 1)
        self.assertEqual(self.rows(b), ())

    def test_stale_document_conflict_prevents_movement_replacement(self):
        obj = self.new()
        self.post()
        before = self.rows(obj)
        self.vm.execute('A=O.Ref.GetObject();B=O.Ref.GetObject();A.Write();')
        with self.assertRaises(BSLRuntimeError): self.vm.execute('B.Write(DocumentWriteMode.Posting);')
        self.assertEqual(self.rows(obj), before)
        self.assertEqual(self.sql('SELECT revision FROM document_record'), [(2,)])

    def test_receipt_resolution_does_not_reexecute_or_read_current_rows(self):
        obj = self.new()
        with execution(self.backend):
            begin(self.backend)
            obj.write(DocumentWriteMode.POSTING)
            transaction = current(self.backend)
            operation, requests = transaction.unit.operation_id, transaction.unit.requests
            transaction.commit()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE accumulation_movement SET values_json='[]'")
            connection.commit()
        self.assertEqual(len(self.backend.resolve_unit_of_work(operation, requests)), 3)
        with self.assertRaises(BackendError): self.rows(obj)

    def uncertain_posting(self, fault):
        from test_catalog_commit_cleanup_recovery import FaultConnection
        self.make('Procedure Posting(Cancel,Mode) Calls=0;AdditionalProperties.Property("Calls",Calls);'
                  'AdditionalProperties.Insert("Calls",Calls+1);RegisterRecords.Rows.Write=True;EndProcedure')
        obj = self.new()
        self.vm.execute('O.AdditionalProperties.Insert("Calls",0);')
        with execution(self.backend):
            begin(self.backend)
            obj.write(DocumentWriteMode.POSTING)
            transaction = current(self.backend)
            proxy = FaultConnection(transaction.unit._view._connection, commit_fault=fault)
            transaction.unit._view._connection = proxy
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                transaction.commit()
            self.assertTrue(obj.is_new())
            if fault == 'after':
                transaction.commit()
            else:
                with self.assertRaisesRegex(BackendError, 'conflict'):
                    transaction.commit()
        self.assertEqual(proxy.commit_calls, 1)
        self.assertEqual(obj.get_member('AdditionalProperties').get_member('Calls'), Decimal(1))
        self.assertFalse(obj.get_member('Ref').is_empty())
        return obj

    def test_uncertain_after_commit_resolves_all_ports_without_handler_replay(self):
        obj = self.uncertain_posting('after')
        self.assertFalse(obj.is_new())
        self.assertTrue(obj.get_member('Posted'))
        self.assertEqual(len(self.rows(obj)), 1)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM unit_of_work_receipt'), [(1,)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM accumulation_movement_receipt'), [(1,)])

    def test_uncertain_before_commit_does_not_replay_or_persist(self):
        obj = self.uncertain_posting('before')
        self.assertTrue(obj.is_new())
        self.assertFalse(obj.get_member('Posted'))
        self.assertEqual(self.rows(obj), ())
        self.assertEqual(self.sql('SELECT COUNT(*) FROM unit_of_work_receipt'), [(0,)])
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'), [(0,)])

    def test_handler_transaction_controls_are_denied(self):
        for command in ('BeginTransaction();', 'CommitTransaction();', 'RollbackTransaction();'):
            with self.subTest(command=command):
                self.make('Procedure Posting(Cancel,Mode) '+command+' EndProcedure')
                obj = self.new()
                with self.assertRaises(BSLRuntimeError): self.post()
                self.assertEqual(self.rows(obj), ())
                self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'), [(0,)])

    def test_transaction_status_is_read_only_and_aliases_match(self):
        with patch.object(self.backend, 'begin_unit_of_work', wraps=self.backend.begin_unit_of_work) as opened:
            self.assertIs(self.vm.execute('TransactionActive()'), False)
            opened.assert_not_called()
        self.vm.execute('Before=TransactionActive();BeginTransaction();'
                        'Inside=TransactionActive();Russian=ТранзакцияАктивна();'
                        'RollbackTransaction();After=TransactionActive();'
                        'BeginTransaction();CommitTransaction();Committed=TransactionActive();')
        for name in ('before', 'after', 'committed'):
            self.assertIs(self.vm.variables[name], False)
        for name in ('inside', 'russian'):
            self.assertIs(self.vm.variables[name], True)

    def test_transaction_status_preserves_unavailable_contexts(self):
        with closing(Interpreter()) as vm:
            with self.assertRaises(BSLRuntimeError): vm.execute('TransactionActive()')
        self.vm._transaction_activation_allowed = False
        with self.assertRaises(BSLRuntimeError): self.vm.execute('TransactionActive()')
        self.make('Procedure Posting(Cancel,Mode) Value=TransactionActive();EndProcedure')
        obj = self.new()
        with self.assertRaises(BSLRuntimeError): self.post()
        self.assertTrue(obj.is_new())
        self.assertEqual(self.rows(obj), ())

    def test_transaction_status_cannot_inspect_another_execution_backend(self):
        from yadinassi.database_transactions import rollback
        owner = self.backend
        self.make()
        with execution(owner):
            begin(owner)
            try:
                with self.assertRaises(BackendError): self.vm._transaction_active()
                self.assertEqual(current(owner).unit.state, 'open')
            finally:
                rollback(owner)

    def test_transaction_status_does_not_resolve_uncertain_owner(self):
        from yadinassi.database_transactions import rollback
        with execution(self.backend):
            begin(self.backend)
            transaction = current(self.backend)
            transaction.unit.state = 'uncertain'
            try:
                with patch.object(self.backend, 'resolve_unit_of_work') as resolve:
                    with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                        self.vm._transaction_active()
                    resolve.assert_not_called()
                self.assertEqual(transaction.unit.state, 'uncertain')
            finally:
                transaction.unit.state = 'open'
                rollback(self.backend)

    def test_transaction_status_binding_is_owned_by_inherited_activation(self):
        with closing(Interpreter(database_context=self.context)) as child:
            child._inherit_host_bindings(self.vm)
            for name in ('transactionactive', 'транзакцияактивна'):
                self.assertIs(child.functions[name].function.__self__, child)

    def test_unowned_register_and_full_manager_api_are_not_exposed(self):
        self.new()
        for command in ('O.RegisterRecords.Other', 'AccumulationRegisters.Rows.CreateRecordSet()',
                        'S.Read()', 'S.Filter', 'S.Total("Amount")'):
            with self.subTest(command=command), self.assertRaises(BSLRuntimeError):
                self.vm.execute(command)

    def test_detached_write_cannot_create_transaction(self):
        self.new()
        with patch.object(self.backend,'begin_unit_of_work', wraps=self.backend.begin_unit_of_work) as begin_call:
            with self.assertRaises(BSLRuntimeError): self.vm.execute('S.Write();')
            begin_call.assert_not_called()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'), [(0,)])

    def test_period_active_and_write_flag_require_exact_types(self):
        self.new()
        for command in ('R.Period="20240101"', 'R.Period=1', 'R.Active=1', 'S.Write=1'):
            with self.subTest(command=command), self.assertRaises(BSLRuntimeError):
                self.vm.execute(command)

    def test_row_system_fields_remain_read_only(self):
        self.new()
        for command in ('R.LineNumber=10', 'R.Recorder=O.Ref'):
            with self.subTest(command=command), self.assertRaises(BSLRuntimeError):
                self.vm.execute(command)

    def test_clear_detaches_old_row(self):
        self.new()
        self.vm.execute('S.Clear();')
        for command in ('R.Period', 'R.RecordType=AccumulationRecordType.Expense', 'R.Amount=2'):
            with self.subTest(command=command), self.assertRaises(BSLRuntimeError):
                self.vm.execute(command)

    def test_buffer_count_and_bytes_are_checked_before_growth(self):
        self.new(row=False)
        with patch('yadinassi.document_posting_values.MAX_MOVEMENT_ROWS', 1):
            self.vm.execute('S.Add();')
            with self.assertRaises(BSLRuntimeError): self.vm.execute('S.Add();')
        self.vm.execute('S.Clear();')
        with patch('yadinassi.document_posting_values.MAX_BUFFER_BYTES', 1):
            with self.assertRaises(BSLRuntimeError): self.vm.execute('S.Add();')
        self.assertEqual(self.vm.execute('S.Count()'), Decimal(0))

    def test_handler_budget_is_uncatchable_and_atomic(self):
        self.make('Procedure Posting(Cancel,Mode) RegisterRecords.Rows.Write();'
                  'Try While True Do EndDo;Except EndTry;EndProcedure')
        obj = self.new()
        with patch('yadinassi.document_posting.MAX_STEPS', 50):
            with self.assertRaises(PostingLimitError): self.post()
        self.assertTrue(obj.is_new())
        self.assertEqual(self.rows(obj), ())

    def test_invalid_source_handlers_rejected_before_file_allocation(self):
        for module in ('Message("initializer");',
                       'Procedure Posting(Val Cancel,Mode) EndProcedure',
                       'Procedure Posting(Cancel) EndProcedure',
                       'Async Procedure Posting(Cancel,Mode) EndProcedure',
                       'Procedure Posting(Cancel,Mode) EndProcedure Procedure ОбработкаПроведения(Отказ,Режим) EndProcedure'):
            with self.subTest(module=module):
                files = source()
                files[MODULE] = module.encode()
                config = import_accumulation_configuration(files, accumulation_runtime=PROFILE)
                path = Path(self.temp.name) / 'invalid.sqlite'
                with self.assertRaises(BackendError): SQLiteDBContext.create_accumulation(path,config)
                self.assertFalse(path.exists())
        self.assertEqual(self.lines, [])

    def test_posting_object_member_names_cannot_be_metadata_fields(self):
        from test_configuration_accumulation import field
        for name in ('RegisterRecords', 'AdditionalProperties', 'ThisObject'):
            with self.subTest(name=name):
                files = source()
                files[DOC] = files[DOC].replace(b'<ChildObjects>',
                    ('<ChildObjects>'+field('Attribute', 999, name, 'string')).encode())
                with self.assertRaises(ValueError):
                    import_accumulation_configuration(files, accumulation_runtime=PROFILE)

    def test_reopen_and_plain_editor_remains_outside_posting_grant(self):
        from yadinassi.configuration_document import DocumentObjectSession
        obj = self.new()
        self.post()
        with closing(SQLiteDBContext(self.path)) as context:
            with closing(Interpreter(database_context=context)) as vm:
                self.assertTrue(vm.execute('Documents.Order.FindByNumber("1").Posted'))
        with self.assertRaises(BackendError):
            DocumentObjectSession(self.context,self.config.documents[0],dict(self.config.files))
        self.assertEqual(len(self.rows(obj)), 1)
