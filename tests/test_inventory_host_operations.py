"""Exact inventory forms root grants, typed identities and terminal outcomes."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlite_test_templates import copy_inventory

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogKey, TabularSectionRows, TabularRow
from yadinassi.configuration.configuration_inventory_application import import_inventory_application, PROFILE, validated_core
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.database_transactions import RootOperation, admission, execution
from yadinassi.db.document.document_backend import DocumentDraft, DocumentKey
from yadinassi.configuration.demos.inventory_host_operations import InventoryRootOperations, InventoryRootOperation
from inventory_application_fixture import source, ROOT
from test_document_posting_host import PostingHostTests as _ScalarHostTests

FORM='Document.Receipt.Form.Card'


class InventoryHostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.files=source();self.config=import_inventory_application(self.files,inventory_runtime=PROFILE)
        self.path=Path(self.temp.name)/'inventory.sqlite'
        p,w=copy_inventory(self.path,products=True)
        self.context=SQLiteDBContext(self.path)
        self.addCleanup(self.context.close);self.backend=self.context.backend
        self.product=CatalogKey(self.backend.database_id,*p)
        self.warehouse=CatalogKey(self.backend.database_id,*w)
        self.host=InventoryRootOperations(self.context,self.config);self.addCleanup(self.cleanup_host)
        self.schema=next(s for s in self.config.documents if s.name=='Receipt')
        self.key=DocumentKey(self.backend.database_id,self.schema.identity,uuid4())
        self.draft=DocumentDraft(self.key,'R1',datetime(2024,1,1,12),False,(self.warehouse,),
            (TabularSectionRows(self.schema.tabular_sections[0].identity,
                (TabularRow(uuid4(),(self.product,Decimal(10),Decimal(100))),)),),False)

    cleanup_host=_ScalarHostTests.cleanup_host

    def execute(self,command='DoPost',draft=None,expected=None,operation=None):
        command={'DoPost':'Post','DoWrite':'Write','DoUndo':'UndoPosting'}.get(command,command)
        return self.host.execute(operation or uuid4(),self.draft if draft is None else draft,expected,form=FORM,command=command)

    def card(self):
        with closing(self.backend.begin_document_read()) as view:return view.read_document(self.key)

    def movement(self):return self.backend.read_accumulation(self.config.registers[0].identity,self.key).rows

    def test_atomic_post_contains_exact_catalog_keys_and_movements(self):
        receipt=self.execute();self.assertEqual(receipt.state,'committed');self.assertTrue(receipt.accepted)
        self.assertEqual([r.kind for r in receipt.requests],['document_create','document_set_posted','accumulation_replace'])
        self.assertTrue(self.card().posted);self.assertEqual(self.card().values,(self.warehouse,))
        self.assertEqual(self.card().tabular_sections,self.draft.tabular_sections)
        register=self.config.registers[0];row=self.movement()[0]
        self.assertEqual(dict(zip((f.name for f in register.dimensions),row.dimensions)),
            {'Product':self.product,'Warehouse':self.warehouse})
        self.assertEqual(dict(zip((f.name for f in register.resources),row.resources)),
            {'Quantity':Decimal(10),'Amount':Decimal(100)})

    test_write_is_unposted_and_has_no_movements=_ScalarHostTests.test_write_is_unposted_and_has_no_movements
    test_undo_posting_clears_owned_movements=_ScalarHostTests.test_undo_posting_clears_owned_movements
    test_new_operation_uses_new_empty_movement_buffer=_ScalarHostTests.test_new_operation_uses_new_empty_movement_buffer
    test_stale_revision_refused_before_begin=_ScalarHostTests.test_stale_revision_refused_before_begin
    test_mutable_draft_payload_refused=_ScalarHostTests.test_mutable_draft_payload_refused
    test_uuid_string_and_zero_refused=_ScalarHostTests.test_uuid_string_and_zero_refused
    test_child_admission_cannot_activate_host_operation=_ScalarHostTests.test_child_admission_cannot_activate_host_operation
    test_nested_execution_cannot_activate_host_operation=_ScalarHostTests.test_nested_execution_cannot_activate_host_operation
    test_handler_cancellation_rolls_back_whole_operation=_ScalarHostTests.test_handler_cancellation_rolls_back_whole_operation
    test_known_commit_acceptance_failure_is_not_reported_as_rollback=_ScalarHostTests.test_known_commit_acceptance_failure_is_not_reported_as_rollback
    test_full_source_mismatch_refused_before_begin=_ScalarHostTests.test_full_source_mismatch_refused_before_begin
    test_empty_additional_properties_are_not_external_inputs=_ScalarHostTests.test_empty_additional_properties_are_not_external_inputs
    test_root_entry_failure_is_terminal_not_perpetual_prepared=_ScalarHostTests.test_root_entry_failure_is_terminal_not_perpetual_prepared
    test_second_root_context_token_failure_restores_first_token=_ScalarHostTests.test_second_root_context_token_failure_restores_first_token

    test_failed_rollback_retains_only_physical_cleanup=_ScalarHostTests.test_failed_rollback_retains_only_physical_cleanup
    test_commit_memory_error_does_not_retain_already_closed_operation=_ScalarHostTests.test_commit_memory_error_does_not_retain_already_closed_operation
    test_no_outcome_allocation_is_needed_after_commit=_ScalarHostTests.test_no_outcome_allocation_is_needed_after_commit
    test_lost_reply_and_cleanup_interrupt_do_not_retain_closed_operation=_ScalarHostTests.test_lost_reply_and_cleanup_interrupt_do_not_retain_closed_operation
    test_unknown_before_commit_does_not_claim_success_or_replay=_ScalarHostTests.test_unknown_before_commit_does_not_claim_success_or_replay
    test_lost_commit_reply_stays_unknown_without_lookup_or_replay=_ScalarHostTests.test_lost_commit_reply_stays_unknown_without_lookup_or_replay
    test_final_source_recheck_does_not_retain_operation=_ScalarHostTests.test_final_source_recheck_does_not_retain_operation
    test_reentrant_execute_is_refused_before_effect=_ScalarHostTests.test_reentrant_execute_is_refused_before_effect
    test_correlation_id_is_not_a_persistent_history_key=_ScalarHostTests.test_correlation_id_is_not_a_persistent_history_key
    test_repeated_stale_input_cannot_replay_after_commit=_ScalarHostTests.test_repeated_stale_input_cannot_replay_after_commit
    test_known_commit_with_retained_connection_can_refresh_without_replay=_ScalarHostTests.test_known_commit_with_retained_connection_can_refresh_without_replay

    def test_ungranted_command_refused(self):
        with self.assertRaises(BackendError):self.execute('Unknown')

    def test_wrong_form_refused(self):
        with self.assertRaises(BackendError):
            self.host.execute(uuid4(),self.draft,None,
                form='Document.Other.Form.Card',command='Post')

    def test_old_nonposting_session_still_refuses_backend(self):
        from yadinassi.configuration.configuration_document import DocumentObjectSession
        with self.assertRaises(BackendError):
            DocumentObjectSession(self.context,self.schema,self.files,reference_fields=True)

    def test_wrong_reference_target_refused_before_journal(self):
        with patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('journal')):
            with self.assertRaises(BackendError):self.execute(draft=replace(self.draft,values=(self.product,)))
        self.assertIsNone(self.host._active_operation)

    def test_foreign_database_reference_refused_before_journal(self):
        foreign=replace(self.warehouse,database_id=uuid4())
        with patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('journal')):
            with self.assertRaises(BackendError):self.execute(draft=replace(self.draft,values=(foreign,)))

    def test_expected_revision_generation_is_exact(self):
        self.execute();expected=replace(self.card().revision,configuration_generation=2)
        with self.assertRaises(BackendError):self.execute(expected=expected)

    def test_default_v13_root_still_refuses_full_inventory_forms(self):
        with self.assertRaises(BackendError):RootOperation(self.backend,uuid4())

    def test_core_inventory_profile_has_no_ui_root(self):
        with closing(SQLiteDBContext.create_inventory(Path(self.temp.name)/'core.sqlite',validated_core(self.config))) as context:
            with self.assertRaises(BackendError):InventoryRootOperation(context.backend,uuid4())
            with self.assertRaises(BackendError):InventoryRootOperations(context,self.config)

    def test_core_creator_refuses_full_forms(self):
        path=Path(self.temp.name)/'bad-core.sqlite'
        with self.assertRaises(BackendError):SQLiteDBContext.create_inventory(path,self.config)
        self.assertFalse(path.exists())

    def test_forms_creator_refuses_core_projection(self):
        path=Path(self.temp.name)/'bad-forms.sqlite'
        with self.assertRaises(BackendError):SQLiteDBContext.create_inventory_application(path,validated_core(self.config))
        self.assertFalse(path.exists())

    def test_source_only_verification_inside_child_does_not_grant_root(self):
        with admission(False),execution(self.backend):
            self.host.verify_source()
            with self.assertRaises(BackendError):self.execute()
        self.assertIsNone(self.host._active_operation)

    def test_readonly_child_checks_current_source_without_form_activation(self):
        from yadinassi.db.database_transactions import _execution
        with admission(False),execution(self.backend):
            owner = _execution.get()
            with (
                patch('yadinassi.configuration.demos.inventory_host_operations.canonical',
                      side_effect=AssertionError('validation form')),
                patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('writer')),
            ):
                self.host.verify_source()
                self.assertIs(_execution.get(),owner)
        with closing(sqlite3.connect(self.path)) as db,db:
            raw = self.files['Configuration.xml'] + b'\n'
            db.execute("UPDATE configuration_file SET content=?,sha256=? WHERE path='Configuration.xml'",
                       (raw,sha256(raw).hexdigest()))
        with admission(False),execution(self.backend):
            with self.assertRaisesRegex(BackendError,'schema_changed'):
                self.host.verify_source()
        self.assertIsNone(self.backend._active)

    def test_readonly_child_rejects_matching_mutation_of_both_live_configurations(self):
        configs = (self.backend.accumulation_configuration,self.host.configuration)
        originals = tuple(config.commands for config in configs)
        try:
            for config in configs:object.__setattr__(config,'commands',())
            with admission(False),execution(self.backend):
                with self.assertRaisesRegex(BackendError,'schema_changed'):
                    self.host.verify_source()
        finally:
            for config,commands in zip(configs,originals):object.__setattr__(config,'commands',commands)
        self.assertIsNone(self.backend._active)

    def test_no_lookup_after_reopening_host(self):
        self.assertTrue(self.execute().accepted)
        with closing(InventoryRootOperations(self.context,self.config)) as other:
            for name in ('_operations','receipt','resolve','intent','acknowledge'):
                self.assertFalse(hasattr(other,name))

    def test_full_source_preserved_after_reopen(self):
        with closing(SQLiteDBContext(self.path)) as context:
            self.assertEqual(context.backend.format_version,15)
            self.assertEqual(context.backend.accumulation_configuration,self.config)
            self.assertEqual(context.backend.export_configuration(),self.files)


# Importing shared test methods must not rediscover the scalar test class here.
del _ScalarHostTests
