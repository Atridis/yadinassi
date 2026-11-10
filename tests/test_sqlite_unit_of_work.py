"""Host transactions are distinct from standalone BSL object Write semantics."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4, uuid5
from unittest.mock import patch
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey, FieldSchema
from yadinassi.document_backend import DocumentDraft, DocumentKey
from yadinassi.register_backend import RegisterDraft, RegisterKey, RegisterSetDraft
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_migration_plan import prepare, apply, resolve, transition_status
from yadinassi.transaction_backend import TransactionRequest, StagedTicket
from test_sqlite_catalog_hierarchy import configuration
from test_catalog_commit_cleanup_recovery import FaultConnection


class UnitOfWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'mixed.sqlite'
        self.config = configuration(mixed=True)
        backend = SQLiteCatalogBackend.create(self.path,self.config); backend.close()
        self.plan = prepare(self.path,maintenance=True)
        apply(self.path,self.plan,maintenance=True)
        self.backend = SQLiteCatalogBackend(self.path); self.addCleanup(self.backend.close)

    def catalog(self, code='item'):
        return CatalogDraft(CatalogKey(self.backend.database_id,self.config.catalogs[0].identity,uuid4()),code,'item',False,())

    def document(self, number='A'):
        return DocumentDraft(DocumentKey(self.backend.database_id,self.config.documents[0].identity,uuid4()),number,datetime(2026,1,1),False,())

    def register(self):
        return RegisterDraft(RegisterKey(self.backend.database_id,self.config.information_registers[0].identity,(datetime(2026,1,1),'item')),(Decimal('2.50'),))

    def trio(self):
        return (TransactionRequest('catalog_create',self.catalog()),TransactionRequest('document_create',self.document()),TransactionRequest('register_write',self.register()))

    def test_profile_preserves_base_and_index(self):
        self.assertEqual((self.backend.format_version,self.backend.storage_version),(11,10))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT sql FROM sqlite_master WHERE name='document_query_order_v1'").fetchone()[0], 'CREATE INDEX document_query_order_v1 ON document_record(document_id,date,number,record_id)')

    def test_catalog_order_index_is_available_on_every_connection(self):
        schema=self.config.catalogs[0]
        connection=self.backend._connect()
        try:
            name='query_catalog_'+schema.identity.hex+'_v1'
            table=self.backend._layout.table_name(schema.identity)
            plan=connection.execute('EXPLAIN QUERY PLAN SELECT record_id FROM "'+table+'" ORDER BY record_id COLLATE yadinassi_uuid_v1').fetchall()
            self.assertTrue(any(name in row[3] for row in plan))
        finally:connection.close()

    def test_mixed_stage_reads_and_commit(self):
        requests=self.trio(); operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            tickets=tuple(tx.stage(r) for r in requests)
            self.assertTrue(all(type(t) is StagedTicket for t in tickets))
            self.assertEqual(tx.read_catalog(requests[0].draft.key).code,'item')
            self.assertEqual(tx.read_document(requests[1].draft.key).number,'A')
            self.assertEqual(tx.read_register(requests[2].draft.key).values,(Decimal('2.50'),))
            results=tx.commit()
        self.assertEqual(self.backend.resolve_unit_of_work(operation,requests),results)

    def test_uncommitted_context_rolls_back_every_port(self):
        requests=self.trio(); operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            for r in requests: tx.stage(r)
        self.assertEqual(tx.state,'aborted')
        self.assertIsNone(self.backend.resolve_unit_of_work(operation,requests))
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            self.assertIsNone(tx.read_catalog(requests[0].draft.key))
            self.assertIsNone(tx.read_document(requests[1].draft.key))
            self.assertIsNone(tx.read_register(requests[2].draft.key))

    def test_second_failed_stage_preserves_first_until_explicit_commit(self):
        first=TransactionRequest('catalog_create',self.catalog())
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            tx.stage(first)
            with self.assertRaises(BackendError): tx.stage(TransactionRequest('catalog_create',self.catalog()))
            self.assertEqual(tx.requests,(first,))
            self.assertEqual(len(tx.commit()),1)

    def test_multiple_documents_are_supported(self):
        requests=(TransactionRequest('document_create',self.document('A')),TransactionRequest('document_create',self.document('B')))
        operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            for r in requests: tx.stage(r)
            results=tx.commit()
        self.assertEqual(self.backend.resolve_unit_of_work(operation,requests),results)

    def test_repeat_object_is_explicitly_unsupported(self):
        request=TransactionRequest('catalog_create',self.catalog())
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            tx.stage(request)
            with self.assertRaisesRegex(BackendError,'unsupported'): tx.stage(request)

    def test_backend_cannot_start_second_owner(self):
        with self.backend.begin_unit_of_work(uuid4()):
            with self.assertRaisesRegex(BackendError,'busy'): self.backend.begin_read()

    def test_empty_commit_refuses(self):
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            with self.assertRaisesRegex(BackendError,'invalid_input'): tx.commit()

    def test_rollback_and_commit_are_terminal(self):
        tx=self.backend.begin_unit_of_work(uuid4());tx.rollback()
        with self.assertRaisesRegex(BackendError,'closed'): tx.stage(self.trio()[0])

    def test_changed_request_and_order_refuse_resolution(self):
        operation=uuid4(); requests=self.trio()
        with self.backend.begin_unit_of_work(operation) as tx:
            for r in requests: tx.stage(r)
            tx.commit()
        with self.assertRaisesRegex(BackendError,'conflict'): self.backend.resolve_unit_of_work(operation,requests[::-1])
        changed=(replace(requests[0],draft=replace(requests[0].draft,description='changed')),*requests[1:])
        with self.assertRaisesRegex(BackendError,'conflict'): self.backend.resolve_unit_of_work(operation,changed)

    def test_operation_reuse_refuses_before_write(self):
        operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            tx.stage(self.trio()[0]);tx.commit()
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.begin_unit_of_work(operation)

    def test_readonly_cannot_begin_unit(self):
        other=SQLiteCatalogBackend(self.path,read_only=True)
        try:
            with self.assertRaisesRegex(BackendError,'unsupported'):other.begin_unit_of_work(uuid4())
        finally:other.close()

    def test_uncertain_commit_resolves_whole_batch(self):
        operation=uuid4();requests=self.trio();tx=self.backend.begin_unit_of_work(operation)
        for r in requests:tx.stage(r)
        tx._view._connection=FaultConnection(tx._view._connection,commit_fault='after')
        with self.assertRaisesRegex(BackendError,'uncertain_commit'):tx.commit()
        self.assertEqual(tx.state,'uncertain')
        self.assertEqual(len(self.backend.resolve_unit_of_work(operation,requests)),3)

    def test_legacy_standalone_write_still_works(self):
        draft=self.catalog();view=self.backend.begin_write(uuid4())
        try:view.create(draft);self.assertEqual(len(view.commit_outcomes()),1)
        finally:view.close()


    def test_commit_failure_before_sql_is_not_durable(self):
        requests=self.trio();operation=uuid4();tx=self.backend.begin_unit_of_work(operation)
        for request in requests:tx.stage(request)
        tx._view._connection=FaultConnection(tx._view._connection,commit_fault='before')
        with self.assertRaisesRegex(BackendError,'uncertain_commit'):tx.commit()
        self.assertIsNone(self.backend.resolve_unit_of_work(operation,requests))

    def test_interrupt_after_commit_is_resolvable(self):
        request=self.trio()[0];operation=uuid4();tx=self.backend.begin_unit_of_work(operation);tx.stage(request)
        tx._view._connection=FaultConnection(tx._view._connection,commit_fault='interrupt')
        with self.assertRaises(KeyboardInterrupt):tx.commit()
        self.assertEqual(len(self.backend.resolve_unit_of_work(operation,(request,))),1)

    def test_stage_memory_error_restores_sql_and_journal(self):
        request=self.trio()[0]
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            with patch.object(tx._view,'_record_change',side_effect=MemoryError):
                with self.assertRaises(MemoryError):tx.stage(request)
            self.assertEqual(tx.requests,())
            self.assertIsNone(tx.read_catalog(request.draft.key))
            tx.stage(request);self.assertEqual(len(tx.commit()),1)

    def test_child_receipt_failure_rolls_back_document(self):
        request=self.trio()[1]
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            with patch('yadinassi.sqlite_transactions._receipt_hash',side_effect=MemoryError):
                with self.assertRaises(MemoryError):tx.stage(request)
            self.assertIsNone(tx.read_document(request.draft.key));self.assertEqual(tx.requests,())
            tx.stage(request);tx.commit()

    def test_missing_child_receipt_cannot_confirm_batch(self):
        requests=self.trio();operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            for request in requests:tx.stage(request)
            tx.commit()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('DELETE FROM document_commit_receipt')
        with self.assertRaisesRegex(BackendError,'integrity'):self.backend.resolve_unit_of_work(operation,requests)

    def test_changed_child_outcome_cannot_confirm_batch(self):
        request=self.trio()[1];operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:tx.stage(request);tx.commit()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE document_commit_receipt SET number='B'")
        with self.assertRaisesRegex(BackendError,'integrity'):self.backend.resolve_unit_of_work(operation,(request,))

    def test_root_binding_corruption_refuses(self):
        request=self.trio()[0];operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:tx.stage(request);tx.commit()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE unit_of_work_receipt SET request_hash=?",('0'*64,))
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.resolve_unit_of_work(operation,(request,))

    def test_overlapping_register_operations_refuse(self):
        request=self.trio()[2]
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            tx.stage(request)
            with self.assertRaisesRegex(BackendError,'unsupported'):tx.stage(TransactionRequest('register_set',RegisterSetDraft(request.draft.key.register_id,(),(),replace=False)))

    def test_register_set_can_share_catalog_document_commit(self):
        requests=self.trio();draft=requests[2].draft
        requests=(*requests[:2],TransactionRequest('register_set',RegisterSetDraft(draft.key.register_id,(),(draft,),replace=False)))
        operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            for request in requests:tx.stage(request)
            results=tx.commit()
        self.assertEqual(self.backend.resolve_unit_of_work(operation,requests),results)

    def test_updates_and_delete_share_second_transaction(self):
        requests=self.trio()
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            for request in requests:tx.stage(request)
            results=tx.commit()
        updates=(TransactionRequest('catalog_update',replace(requests[0].draft,description='new'),results[0].result.revision),
                 TransactionRequest('document_update',replace(requests[1].draft,number='B'),results[1].result.revision),
                 TransactionRequest('register_delete',requests[2].draft,results[2].result.revision))
        operation=uuid4()
        with self.backend.begin_unit_of_work(operation) as tx:
            for request in updates:tx.stage(request)
            outcomes=tx.commit()
        self.assertEqual(self.backend.resolve_unit_of_work(operation,updates),outcomes)

    def test_operation_budget_is_global(self):
        with self.backend.begin_unit_of_work(uuid4()) as tx,patch('yadinassi.sqlite_transactions.MAX_OPERATIONS',1):
            tx.stage(self.trio()[0])
            with self.assertRaisesRegex(BackendError,'unsupported'):tx.stage(self.trio()[1])

    def test_payload_budget_is_global(self):
        with self.backend.begin_unit_of_work(uuid4()) as tx,patch('yadinassi.sqlite_transactions.MAX_BYTES',1):
            with self.assertRaisesRegex(BackendError,'unsupported'):tx.stage(self.trio()[0])
            self.assertEqual(tx.requests,())

    def test_child_operation_collision_is_rejected(self):
        operation=uuid4();child=uuid5(operation,'unit-of-work-v1:0')
        view=self.backend.begin_write(child)
        try:view.create(self.catalog('old'));view.commit()
        finally:view.close()
        with self.backend.begin_unit_of_work(operation) as tx:
            with self.assertRaisesRegex(BackendError,'conflict'):tx.stage(self.trio()[0])

    def test_staging_is_not_frontend_write_success(self):
        request=self.trio()[0]
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            ticket=tx.stage(request)
            self.assertFalse(hasattr(ticket,'revision'))
            self.assertEqual(tx.state,'open')


class MigrationPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'source.sqlite'
        self.config=configuration()
        backend=SQLiteCatalogBackend.create(self.path,self.config);backend.close()

    def test_dry_run_deterministic_and_readonly(self):
        before=self.path.read_bytes();a=prepare(self.path,maintenance=True);b=prepare(self.path,maintenance=True)
        self.assertEqual(a.plan_hash,b.plan_hash);self.assertEqual(a.steps,b.steps)
        self.assertEqual(before,self.path.read_bytes())

    def test_explicit_transition_matrix(self):
        self.assertEqual(transition_status(10,11),'additive_transaction_profile')
        self.assertEqual(transition_status(1,2),'legacy_prepare_v1_required')
        self.assertEqual(transition_status(6,11),'source_activation_profile_not_supported')
        self.assertEqual(transition_status(9,10),'transition_not_supported')

    def test_maintenance_required(self):
        with self.assertRaisesRegex(BackendError,'invalid_input'):prepare(self.path)

    def test_stale_plan_refuses_without_mutation(self):
        plan=prepare(self.path,maintenance=True)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE database_info SET name='changed'")
        before=self.path.read_bytes()
        with self.assertRaisesRegex(BackendError,'conflict'):apply(self.path,plan,maintenance=True)
        self.assertEqual(before,self.path.read_bytes())

    def test_apply_resolve_and_reopen(self):
        plan=prepare(self.path,maintenance=True)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'not_committed')
        apply(self.path,plan,maintenance=True)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'committed')
        backend=SQLiteCatalogBackend(self.path)
        try:self.assertEqual(backend.format_version,11)
        finally:backend.close()

    def test_forged_plan_refuses(self):
        plan=prepare(self.path,maintenance=True)
        with self.assertRaisesRegex(BackendError,'invalid_input'):apply(self.path,replace(plan,target_version=12),maintenance=True)

    def test_old_format_does_not_implicitly_upgrade(self):
        backend=SQLiteCatalogBackend(self.path)
        try:
            self.assertEqual(backend.format_version,10)
            with self.assertRaisesRegex(BackendError,'unsupported'):backend.begin_unit_of_work(uuid4())
        finally:backend.close()

    def test_changed_marker_remains_uncertain(self):
        plan=prepare(self.path,maintenance=True);apply(self.path,plan,maintenance=True)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE transaction_migration SET migration_id=?",(str(uuid4()),))
        self.assertEqual(resolve(self.path,plan,maintenance=True),'uncertain')

    def test_all_supported_base_profiles_preserved(self):
        for version in (2,3,4,7,8,9,10):
            with self.subTest(version=version):
                path=Path(self.temp.name)/('v%d.sqlite'%version)
                config=configuration(mixed=version>=7,numbered=version==4)
                catalogs=tuple(replace(c,hierarchy='none',tabular_sections=c.tabular_sections if version in (3,4) else ()) for c in config.catalogs)
                if version==10:catalogs=config.catalogs
                documents=config.documents if version>=7 else ()
                registers=config.information_registers if version>=8 else ()
                if version==8:registers=tuple(replace(r,periodicity='Nonperiodical') for r in registers)
                config=replace(config,catalogs=catalogs,documents=documents,information_registers=registers)
                backend=SQLiteCatalogBackend.create(path,config)
                self.assertEqual(backend.format_version,version);backend.close()
                plan=prepare(path,maintenance=True);apply(path,plan,maintenance=True)
                backend=SQLiteCatalogBackend(path)
                try:
                    self.assertEqual((backend.format_version,backend.storage_version),(11,version))
                    draft=CatalogDraft(CatalogKey(backend.database_id,catalogs[0].identity,uuid4()),'long-code-truncated','x',False,())
                    request=TransactionRequest('catalog_create',draft);operation=uuid4()
                    with backend.begin_unit_of_work(operation) as tx:tx.stage(request);outcomes=tx.commit()
                    self.assertEqual(backend.resolve_unit_of_work(operation,(request,)),outcomes)
                finally:backend.close()

    def test_rollback_during_migration_leaves_source(self):
        plan=prepare(self.path,maintenance=True)
        import yadinassi.sqlite_migration_plan as migration
        original=migration._fingerprint;count=0
        def fail(db,**kwargs):
            nonlocal count
            count+=1
            if kwargs.get('upgraded'):raise MemoryError()
            return original(db,**kwargs)
        with patch.object(migration,'_fingerprint',side_effect=fail):
            with self.assertRaises(MemoryError):apply(self.path,plan,maintenance=True)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'not_committed')

    def test_cli_plan_roundtrip_apply_resolve(self):
        from yadinassi.storage_migration_cli import main
        saved=Path(self.temp.name)/'plan.json'
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(main(['plan',str(self.path),'--maintenance','--plan-file',str(saved)]),0)
            self.assertEqual(main(['apply',str(self.path),'--maintenance','--plan-file',str(saved)]),0)
            self.assertEqual(main(['resolve',str(self.path),'--maintenance','--plan-file',str(saved)]),0)
        self.assertEqual(out.getvalue(),'plan_saved\ncommitted\ncommitted\n')

    def test_cli_does_not_overwrite_saved_plan(self):
        from yadinassi.storage_migration_cli import main
        saved=Path(self.temp.name)/'plan.json';saved.write_text('retained',encoding='utf-8')
        with redirect_stderr(StringIO()):self.assertEqual(main(['plan',str(self.path),'--maintenance','--plan-file',str(saved)]),2)
        self.assertEqual(saved.read_text(),'retained')

    def test_profile_marker_is_admitted_strictly(self):
        plan=prepare(self.path,maintenance=True);apply(self.path,plan,maintenance=True)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('DELETE FROM transaction_migration')
        with self.assertRaisesRegex(BackendError,'integrity'):SQLiteCatalogBackend(self.path)

    def test_unexpected_index_is_not_admitted(self):
        plan=prepare(self.path,maintenance=True);apply(self.path,plan,maintenance=True)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('CREATE INDEX unexpected_idx ON database_info(name)')
        with self.assertRaisesRegex(BackendError,'unsupported'):SQLiteCatalogBackend(self.path)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'uncertain')
