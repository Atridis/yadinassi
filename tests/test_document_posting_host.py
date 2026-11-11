"""Trusted-root posting identity, fault recovery and activation boundaries."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import BackendError, TabularSectionRows, TabularRow
from yadinassi.configuration_posting_application import import_posting_application, PROFILE
from yadinassi.configuration_document import DocumentObjectSession
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import admission, execution, RootOperationReceipt, Transaction
from yadinassi.document_backend import DocumentDraft, DocumentKey
from yadinassi.document_posting_host import RootPostingOperations
from yadinassi.sqlite_transactions import UnitOfWork
from posting_application_fixture import source, FORM

ROOT=Path(__file__).resolve().parents[1]


class PostingHostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.files=source();self.config=import_posting_application(self.files,posting_runtime=PROFILE)
        self.context=SQLiteDBContext.create_posting(Path(self.temp.name)/'app.sqlite',self.config)
        self.addCleanup(self.context.close);self.backend=self.context.backend
        self.host=RootPostingOperations(self.context,self.config)
        self.addCleanup(self.cleanup_host)
        self.schema=self.config.documents[0]
        self.key=DocumentKey(self.backend.database_id,self.schema.identity,uuid4())
        self.draft=DocumentDraft(self.key,'1',datetime(2024,1,1),False,(Decimal(7),),
            (TabularSectionRows(self.schema.tabular_sections[0].identity,(TabularRow(uuid4(),(Decimal(2),)),)),),False)

    def cleanup_host(self):
        if self.host._closed:return
        for operation in tuple(self.host._operations):
            self.host.resolve(operation)
        self.host.close()

    def execute(self,command='DoPost',draft=None,expected=None,operation=None):
        return self.host.execute(operation or uuid4(),self.draft if draft is None else draft,expected,form=FORM,command=command)

    def card(self):
        with closing(self.backend.begin_document_read()) as view:return view.read_document(self.key)

    def movement(self):return self.backend.read_recorder(self.config.registers[0].identity,self.key).rows

    def test_atomic_post_contains_document_state_and_movements(self):
        receipt=self.execute()
        self.assertEqual(receipt.state,'committed');self.assertTrue(receipt.accepted)
        self.assertEqual([r.kind for r in receipt.requests],['document_create','document_set_posted','recorder_replace'])
        self.assertTrue(self.card().posted);self.assertEqual(self.movement()[0].values,(Decimal(1),Decimal(7)))
        self.assertEqual(self.card().tabular_sections,self.draft.tabular_sections)

    def test_write_is_unposted_and_has_no_movements(self):
        self.execute('DoWrite');self.assertFalse(self.card().posted);self.assertEqual(self.movement(),())

    def test_undo_posting_clears_owned_movements(self):
        self.execute();card=self.card();self.execute('DoUndo',expected=card.revision)
        self.assertFalse(self.card().posted);self.assertEqual(self.movement(),())

    def test_write_preserves_posted_and_prior_movements(self):
        self.execute();card=self.card();rows=self.movement()
        self.execute('DoWrite',draft=replace(self.draft,values=(Decimal(9),)),expected=card.revision)
        self.assertTrue(self.card().posted);self.assertEqual(self.movement(),rows)

    def test_new_operation_uses_new_empty_movement_buffer(self):
        self.execute();self.execute(expected=self.card().revision)
        self.assertEqual(len(self.movement()),1)

    def test_repeat_uuid_returns_same_receipt_without_handler_replay(self):
        operation=uuid4();first=self.execute(operation=operation)
        with patch('yadinassi.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            self.assertIs(self.execute(operation=operation),first)
        self.assertEqual(self.card().revision.token,'1')

    def test_same_uuid_different_mode_conflicts_before_work(self):
        operation=uuid4();self.execute(operation=operation)
        with patch.object(self.host,'_verify',side_effect=AssertionError('unexpected work')):
            with self.assertRaisesRegex(BackendError,'conflict'):self.execute('DoWrite',operation=operation)

    def test_same_uuid_different_draft_conflicts_before_work(self):
        operation=uuid4();self.execute(operation=operation)
        with self.assertRaisesRegex(BackendError,'conflict'):self.execute(draft=replace(self.draft,number='2'),operation=operation)

    def test_same_uuid_different_revision_conflicts(self):
        operation=uuid4();self.execute(operation=operation)
        with self.assertRaisesRegex(BackendError,'conflict'):self.execute(expected=self.card().revision,operation=operation)

    def test_ungranted_command_refused(self):
        with self.assertRaisesRegex(BackendError,'unsupported'):self.execute('Post')

    def test_wrong_form_refused(self):
        with self.assertRaises(BackendError):self.host.execute(uuid4(),self.draft,None,form='Document.Other.Form.Card',command='DoPost')

    def test_stale_revision_refused_before_begin(self):
        self.execute()
        with patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('begin')):
            with self.assertRaises(BackendError):self.execute()

    def test_mutable_draft_payload_refused(self):
        with self.assertRaises(BackendError):self.execute(draft=replace(self.draft,values=[Decimal(7)]))

    def test_uuid_string_and_zero_refused(self):
        for operation in (str(uuid4()),UUID(int=0)):
            with self.assertRaises(BackendError):self.host.execute(operation,self.draft,None,form=FORM,command='DoPost')

    def test_child_admission_cannot_activate_host_operation(self):
        with admission(False):
            with self.assertRaises(BackendError):self.execute()
        self.assertIsNone(self.card())

    def test_nested_execution_cannot_activate_host_operation(self):
        with execution(self.backend):
            with self.assertRaises(BackendError):self.execute()
        self.assertIsNone(self.card())

    def test_old_nonposting_session_still_refuses_backend(self):
        with self.assertRaises(BackendError):DocumentObjectSession(self.context,self.schema,self.files)

    def test_receipt_unknown_after_host_restart_is_unavailable(self):
        receipt=self.execute();other=RootPostingOperations(self.context,self.config)
        with self.assertRaisesRegex(BackendError,'recovery_unavailable'):other.resolve(receipt.operation_id)
        other.close()

    def test_final_source_recheck_does_not_leave_prepared_ledger(self):
        real=self.host._verify;count=0;operation=uuid4()
        def verify():
            nonlocal count
            count+=1
            if count==2:raise BackendError('schema_changed')
            return real()
        with patch.object(self.host,'_verify',side_effect=verify):
            with self.assertRaises(BackendError):self.execute(operation=operation)
        with self.assertRaisesRegex(BackendError,'recovery_unavailable'):self.host.receipt(operation)
        self.assertIsNone(self.card());self.host.close()

    def test_handler_cancellation_rolls_back_whole_operation(self):
        with patch('yadinassi.document_posting._PostingInterpreter.invoke',side_effect=ValueError('cancelled')):
            receipt=self.execute()
        self.assertEqual(receipt.state,'rejected');self.assertIsNone(self.card());self.assertEqual(self.movement(),())

    def test_uncertain_commit_resolves_exact_requests_without_replay(self):
        real=UnitOfWork.commit
        def lost(unit):real(unit);unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):receipt=self.execute()
        self.assertEqual(receipt.state,'uncertain')
        with patch.object(self.backend,'resolve_unit_of_work',wraps=self.backend.resolve_unit_of_work) as resolve, patch('yadinassi.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            result=self.host.resolve(receipt.operation_id)
        resolve.assert_called_once_with(receipt.operation_id,receipt.requests)
        self.assertEqual(result.state,'committed');self.assertTrue(result.accepted)

    def test_uncertain_without_commit_returns_not_committed_no_replay(self):
        def lost(unit):unit._view.close();unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):receipt=self.execute()
        with patch('yadinassi.document_posting.PostingRuntime.write',side_effect=AssertionError('replay')):
            result=self.host.resolve(receipt.operation_id)
        self.assertEqual(result.state,'not_committed');self.assertIsNone(self.card())

    def test_uncertain_receipt_locks_close(self):
        def lost(unit):unit._view.close();unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):receipt=self.execute()
        with self.assertRaises(BackendError):self.host.close()
        self.host.resolve(receipt.operation_id);self.host.close()

    def test_resolve_mismatched_outcomes_retains_uncertainty(self):
        real=UnitOfWork.commit
        def lost(unit):real(unit);unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost):receipt=self.execute()
        with patch.object(self.backend,'resolve_unit_of_work',return_value=()):
            with self.assertRaisesRegex(BackendError,'integrity'):self.host.resolve(receipt.operation_id)
        self.assertEqual(self.host.receipt(receipt.operation_id).state,'uncertain')

    def test_known_commit_acceptance_failure_is_not_reported_as_rollback(self):
        with patch.object(Transaction,'_install',side_effect=RuntimeError('refresh')):receipt=self.execute()
        self.assertEqual(receipt.state,'committed');self.assertFalse(receipt.accepted);self.assertTrue(self.card().posted)
        result=self.host.resolve(receipt.operation_id);self.assertTrue(result.accepted)

    def test_commit_receipt_survives_cleanup_interruption(self):
        real=UnitOfWork.commit;operation=uuid4()
        def lost(unit):real(unit);unit.state='uncertain';raise BackendError('uncertain_commit')
        with patch.object(UnitOfWork,'commit',lost),patch.object(UnitOfWork,'close',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.execute(operation=operation)
        receipt=self.host.receipt(operation);self.assertEqual(receipt.state,'uncertain');self.assertTrue(receipt.requests)
        with self.assertRaises(BackendError):self.host.close()
        self.assertTrue(self.host.resolve(operation).accepted)

    def test_no_receipt_allocation_is_needed_after_commit(self):
        real=UnitOfWork.commit
        def committed(unit):
            result=real(unit)
            self.allocation_patch=patch('yadinassi.database_transactions.RootOperationReceipt',side_effect=MemoryError)
            self.allocation_patch.start();self.addCleanup(self.allocation_patch.stop)
            return result
        with patch.object(UnitOfWork,'commit',committed):receipt=self.execute()
        self.assertEqual(receipt.state,'committed');self.assertTrue(receipt.accepted)

    def test_commit_memory_error_retains_preallocated_uncertain_receipt(self):
        real=UnitOfWork.commit;operation=uuid4()
        def lost(unit):real(unit);unit.state='uncertain';raise MemoryError
        with patch.object(UnitOfWork,'commit',lost):
            with self.assertRaises(MemoryError):self.execute(operation=operation)
        self.assertEqual(self.host.receipt(operation).state,'uncertain')
        self.assertTrue(self.host.resolve(operation).accepted)

    def test_failed_rollback_cleanup_keeps_host_locked(self):
        operation=uuid4()
        with patch('yadinassi.document_posting.PostingRuntime.write',side_effect=ValueError('fail')),patch.object(UnitOfWork,'rollback',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.execute(operation=operation)
        self.assertEqual(self.host.receipt(operation).error,'cleanup_required')
        with self.assertRaises(BackendError):self.host.close()
        self.assertEqual(self.host.resolve(operation).state,'rejected');self.assertIsNone(self.card())

    def test_full_source_mismatch_refused_before_begin(self):
        with patch.object(self.backend,'export_configuration',return_value={}):
            with patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('begin')):
                with self.assertRaises(BackendError):self.execute()

    def test_empty_additional_properties_are_not_external_inputs(self):
        operation=uuid4();self.execute(operation=operation)
        intent=self.host.intent(operation)
        self.assertEqual(set(intent.__dataclass_fields__),{'operation_id','database_id','generation','source_digest','profile','form','command','mode','draft','expected'})

    def test_max_receipts_never_evicts_recovery_state(self):
        with patch('yadinassi.document_posting_host.MAX_RECEIPTS',1):
            self.execute()
            with self.assertRaises(BackendError):self.execute(expected=self.card().revision)
