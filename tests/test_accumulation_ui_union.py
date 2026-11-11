"""Union boundaries: forms host authority must not spread to accumulation."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError, serialization
from yadinassi.catalog_backend import BackendError
from yadinassi.values import BSLType
from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE as ACCUMULATION
from yadinassi.configuration_posting import import_posting_configuration, PROFILE as RECORDER
from yadinassi.configuration_posting_application import import_posting_application, PROFILE as FORMS
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import RootOperation, require_host_root
from yadinassi.document_posting_host import RootPostingOperations
from posting_application_fixture import source as form_source
from test_sqlite_accumulation_profile import accumulation_source
from test_configuration_posting import source as recorder_source

ROOT = Path(__file__).resolve().parents[1]


class AccumulationUIUnionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.counter = 0

    def context(self, profile):
        self.counter += 1
        path = Path(self.temp.name) / ('profile%d.sqlite' % self.counter)
        if profile == ACCUMULATION:
            configuration = import_accumulation_configuration(accumulation_source(
                b'Procedure Posting(Cancel, Mode) RegisterRecords.OwnedAccumulationRows.Write=True; EndProcedure'),
                accumulation_runtime=profile)
            context = SQLiteDBContext.create_accumulation(path, configuration)
        else:
            configuration = (import_posting_application(form_source(), posting_runtime=profile)
                if profile == FORMS else import_posting_configuration(recorder_source(), posting_runtime=profile))
            context = SQLiteDBContext.create_posting(path, configuration)
        self.addCleanup(context.close)
        return context, configuration

    def test_v14_rejects_both_host_entrypoints_before_uow(self):
        context, configuration = self.context(ACCUMULATION)
        with patch.object(context.backend, 'begin_unit_of_work', side_effect=AssertionError('unexpected UoW')):
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                RootOperation(context.backend, uuid4())
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                RootPostingOperations(context, configuration)
        self.assertIsNone(getattr(context.backend, '_bsl_transaction', None))

    def test_scalar_v13_does_not_inherit_forms_host_grant(self):
        context, configuration = self.context(RECORDER)
        with patch.object(context.backend, 'begin_unit_of_work', side_effect=AssertionError('unexpected UoW')):
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                RootOperation(context.backend, uuid4())
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                RootPostingOperations(context, configuration)

    def test_exact_forms_v13_admits_host_without_starting_uow(self):
        context, configuration = self.context(FORMS)
        with patch.object(context.backend, 'begin_unit_of_work', side_effect=AssertionError('unexpected UoW')):
            require_host_root(context.backend)
            operation = RootOperation(context.backend, uuid4())
            host = RootPostingOperations(context, configuration)
            host.close()
        self.assertEqual(operation.receipt.state, 'prepared')
        self.assertIsNone(getattr(context.backend, '_bsl_transaction', None))

    def test_forms_configuration_cannot_authorize_v14_backend(self):
        context, _ = self.context(ACCUMULATION)
        _, configuration = self.context(FORMS)
        with patch.object(context.backend, 'posting_configuration', configuration):
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                RootOperation(context.backend, uuid4())

    def test_forged_forms_configuration_is_not_a_source_grant(self):
        context, configuration = self.context(FORMS)
        with patch.object(context.backend, 'posting_configuration', replace(configuration, source_digest='0' * 64)):
            with self.assertRaises(ValueError): RootOperation(context.backend, uuid4())

    def test_forms_root_rechecks_source_before_run_without_callback(self):
        context, _ = self.context(FORMS)
        operation = RootOperation(context.backend, uuid4())
        with patch.object(context.backend, 'export_configuration', return_value={}):
            with patch.object(context.backend, 'begin_unit_of_work', side_effect=AssertionError('unexpected UoW')):
                receipt = operation.run(lambda: self.fail('callback without source grant'))
        self.assertEqual(receipt.state, 'rejected')
        self.assertEqual(receipt.requests, ())

    def test_accumulation_transaction_status_retains_owned_bsl_activation(self):
        context, _ = self.context(ACCUMULATION)
        vm = Interpreter(database_context=context, output=lambda value: None)
        self.addCleanup(vm.close)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            RootOperation(context.backend, uuid4())
        self.assertIs(vm.execute('TransactionActive()'), False)
        vm.execute('BeginTransaction();Inside=TransactionActive();RollbackTransaction();')
        self.assertIs(vm.variables['inside'], True)
        self.assertIs(vm.execute('TransactionActive()'), False)

    def test_accumulation_owned_posting_survives_host_root_refusal(self):
        context, configuration = self.context(ACCUMULATION)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            RootOperation(context.backend, uuid4())
        vm = Interpreter(database_context=context, output=lambda value: None)
        self.addCleanup(vm.close)
        vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();O.Number="1";O.Date=Date(2024,1,1);'
                   'R=O.RegisterRecords.OwnedAccumulationRows.Add();R.Item="A";R.Warehouse=1;'
                   'R.Amount=7.25;R.Quantity=1;R.Note="union";R.Period=Date(2024,1,1);'
                   'BeginTransaction();O.Write(DocumentWriteMode.Posting);'
                   'Inside=TransactionActive();CommitTransaction();')
        self.assertIs(vm.variables['inside'], True)
        self.assertIs(vm.execute('TransactionActive()'), False)
        self.assertIs(context.backend.read_document_posted(vm.variables['o']._key), True)
        rows = context.backend.read_accumulation(configuration.registers[0].identity, vm.variables['o']._key).rows
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resources, (Decimal('7.25'), Decimal(1)))

    def test_accumulation_enum_has_explicit_unsupported_codec_policy(self):
        kind = BSLType.ACCUMULATION_RECORD_TYPE
        self.assertIn(kind, serialization._UNSUPPORTED_CODEC_TYPES)
        self.assertNotIn(kind, serialization._CODECS)
        self.assertNotIn(kind, serialization._TYPE_IDS)
        self.assertNotIn(kind, serialization._TYPES_BY_ID.values())

    def test_accumulation_type_identity_remains_available_without_codec(self):
        context, _ = self.context(ACCUMULATION)
        vm = Interpreter(database_context=context, output=lambda value: None)
        self.addCleanup(vm.close)
        for expression in ('AccumulationRecordType.Receipt', 'AccumulationRecordType.Expense',
                           'ВидДвиженияНакопления.Приход', 'ВидДвиженияНакопления.Расход'):
            self.assertIs(vm.execute('TypeOf(' + expression + ')'), BSLType.ACCUMULATION_RECORD_TYPE)
            with self.assertRaisesRegex(BSLRuntimeError, 'пока не поддерживается'):
                vm.execute('ValueToStringInternal(' + expression + ')')
        for name in ('AccumulationRecordType', 'ВидДвиженияНакопления'):
            self.assertIs(vm.execute('Type("' + name + '")'), BSLType.ACCUMULATION_RECORD_TYPE)
            with self.assertRaisesRegex(BSLRuntimeError, 'пока не поддерживается'):
                vm.execute('ValueToStringInternal(Type("' + name + '"))')

    def test_enum_names_are_not_invented_internal_stream_identifiers(self):
        context, _ = self.context(ACCUMULATION)
        vm = Interpreter(database_context=context, output=lambda value: None)
        self.addCleanup(vm.close)
        # Deliberately synthetic proposals, not native streams or rejection evidence.
        for name in ('AccumulationRecordType', 'ВидДвиженияНакопления', 'ACCUMULATION_RECORD_TYPE'):
            for payload in ('{"T",' + name + '}', '{"#",' + name + ',0}'):
                vm.variables['payload'] = payload
                with self.assertRaises(BSLRuntimeError):
                    vm.execute('ValueFromStringInternal(payload)')
