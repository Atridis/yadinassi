"""Private host primitive tests, not native posting or activated profile tests."""
from decimal import Decimal
import sqlite3
import unittest
from uuid import UUID,uuid4
from yadinassi.catalog_backend import BackendError,FieldSchema
from yadinassi.document_backend import DocumentKey
from yadinassi.document_movements import RecorderRegisterSchema,RecorderReplacement,RecorderMovementRow
from yadinassi.sqlite_recorder_movements import RecorderMovementPort,RECORDER_DDL,schema_data,_json

class RecorderStorageTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:',isolation_level=None);self.addCleanup(self.c.close)
        self.c.execute('PRAGMA foreign_keys=ON')
        self.c.execute('CREATE TABLE document_schema(identity TEXT PRIMARY KEY)')
        self.c.execute('CREATE TABLE document_record(document_id TEXT,record_id TEXT,PRIMARY KEY(document_id,record_id))')
        self.db=uuid4();self.doc=uuid4();self.reg=uuid4()
        self.schema=RecorderRegisterSchema(self.reg,(self.doc,),(FieldSchema(uuid4(),'Amount','number',(10,0,'Any')),))
        for ddl in RECORDER_DDL:self.c.execute(ddl)
        self.c.execute('INSERT INTO document_schema VALUES(?)',(str(self.doc),))
        self.c.execute('INSERT INTO recorder_register_schema VALUES(?,?)',(str(self.reg),_json(schema_data(self.schema,self.db))))
        self.c.execute('INSERT INTO recorder_register_document VALUES(?,?)',(str(self.reg),str(self.doc)))
        self.key=DocumentKey(self.db,self.doc,uuid4())
        self.c.execute('INSERT INTO document_record VALUES(?,?)',(str(self.doc),str(self.key.record_id)))
        self.c.execute('BEGIN')
        self.port=RecorderMovementPort(self.c,self.db,1,(self.schema,))
    def request(self,key=None,rows=None):
        key=key or self.key;snapshot=self.port.read(self.reg,key).snapshot
        return RecorderReplacement(self.reg,key,(RecorderMovementRow(1,True,(Decimal(7),)),) if rows is None else rows,snapshot)
    def test_replace_read_and_immutable_resolve(self):
        req=self.request();op=uuid4();out=self.port.replace(op,req)
        self.assertEqual(self.port.read(self.reg,self.key).rows,req.rows)
        self.assertEqual(self.port.resolve(op,req),out)
        self.port.replace(uuid4(),self.request(rows=()))
        self.assertEqual(self.port.resolve(op,req),out)
    def test_empty_partition_revision_prevents_aba(self):
        before=self.request(rows=());self.port.replace(uuid4(),before)
        after=self.port.read(self.reg,self.key)
        self.assertNotEqual(before.expected_snapshot,after.snapshot)
        with self.assertRaises(BackendError):self.port.replace(uuid4(),before)
    def test_two_recorders_same_register_are_disjoint(self):
        other=DocumentKey(self.db,self.doc,uuid4())
        self.c.execute('INSERT INTO document_record VALUES(?,?)',(str(self.doc),str(other.record_id)))
        left,right=self.request(),self.request(other)
        self.assertNotEqual(self.port.describe(left)[2],self.port.describe(right)[2])
        self.port.replace(uuid4(),left);self.port.replace(uuid4(),right)
        self.assertEqual(len(self.port.read(self.reg,other).rows),1)
    def test_missing_recorder_fk_rolls_back_child_journal(self):
        key=DocumentKey(self.db,self.doc,uuid4());req=self.request(key);op=uuid4()
        with self.assertRaises(sqlite3.IntegrityError):self.port.replace(op,req)
        self.assertEqual(self.port.read(self.reg,key).revision,0)
        self.assertIsNone(self.port.resolve(op,req))
    def test_outer_rollback_removes_rows_and_receipts(self):
        req=self.request();op=uuid4();self.port.replace(op,req)
        self.c.execute('ROLLBACK');self.c.execute('BEGIN')
        self.assertEqual(self.port.read(self.reg,self.key).revision,0)
        self.assertIsNone(self.port.resolve(op,req))
    def test_stale_or_different_request_cannot_resolve_receipt(self):
        req=self.request();op=uuid4();self.port.replace(op,req)
        with self.assertRaises(BackendError):self.port.resolve(op,self.request(rows=()))
    def test_requires_owned_transaction(self):
        self.c.execute('ROLLBACK')
        with self.assertRaises(BackendError):self.port.read(self.reg,self.key)
    def test_corrupt_scalar_never_hidden_by_partition_read(self):
        self.port.replace(uuid4(),self.request())
        self.c.execute("UPDATE recorder_movement SET values_json='[]'")
        with self.assertRaises(BackendError):self.port.read(self.reg,self.key)

class RecorderJournalTests(RecorderStorageTests):
    def setUp(self):
        super().setUp()
        from types import SimpleNamespace
        from contextlib import contextmanager
        self.c.execute('CREATE TABLE commit_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT, revisions_json TEXT)')
        self.c.execute('CREATE TABLE document_commit_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT, document_id TEXT, record_id TEXT, revision INTEGER, number TEXT)')
        self.c.execute('CREATE TABLE information_register_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT, outcome_json TEXT)')
        self.c.execute('CREATE TABLE unit_of_work_receipt(operation_id TEXT PRIMARY KEY,request_hash TEXT,outcomes_json TEXT)')
        owner=self
        class View:
            _backend=SimpleNamespace(storage_version=8,format_version=13,_recorder_schemas=(owner.schema,))
            database_id=owner.db;configuration_generation=1
            _connection=owner.c
            def __init__(self,operation):self._operation_id=operation;self.closed=False
            def _require(self,write=False):
                if self.closed or not self._connection.in_transaction:raise BackendError('closed')
            @contextmanager
            def _atomic_record(self):
                self._connection.execute('SAVEPOINT root_stage')
                try:
                    yield
                    self._connection.execute('RELEASE root_stage')
                except BaseException:
                    self._connection.execute('ROLLBACK TO root_stage');self._connection.execute('RELEASE root_stage');raise
            def close(self):
                if self._connection.in_transaction:self._connection.execute('ROLLBACK')
                self.closed=True
        self.View=View
    def test_root_batch_assigns_distinct_existing_child_ids(self):
        from yadinassi.sqlite_transactions import UnitOfWork,_child
        from yadinassi.transaction_backend import TransactionRequest
        other=DocumentKey(self.db,self.doc,uuid4())
        self.c.execute('INSERT INTO document_record VALUES(?,?)',(str(self.doc),str(other.record_id)))
        op=uuid4();tx=UnitOfWork(self.View(op))
        tx.stage(TransactionRequest('recorder_replace',self.request()))
        tx.stage(TransactionRequest('recorder_replace',self.request(other)))
        outcomes=tx.commit()
        self.assertEqual(len(outcomes),2)
        child_ids={r[0] for r in self.c.execute('SELECT operation_id FROM recorder_movement_receipt')}
        self.assertEqual(child_ids,{str(_child(op,0)),str(_child(op,1))})
        self.assertIsNotNone(self.c.execute('SELECT 1 FROM unit_of_work_receipt WHERE operation_id=?',(str(op),)).fetchone())
    def test_outer_stage_failure_keeps_other_partition_and_root_bookkeeping(self):
        from yadinassi.sqlite_transactions import UnitOfWork
        from yadinassi.transaction_backend import TransactionRequest
        tx=UnitOfWork(self.View(uuid4()));tx.stage(TransactionRequest('recorder_replace',self.request()))
        missing=DocumentKey(self.db,self.doc,uuid4())
        with self.assertRaises(BackendError):tx.stage(TransactionRequest('recorder_replace',self.request(missing)))
        self.assertEqual(len(tx.requests),1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM recorder_movement_receipt').fetchone()[0],1)
        tx.rollback()
        self.c.execute('BEGIN');self.assertEqual(self.port.read(self.reg,self.key).revision,0)
    def test_same_partition_twice_in_root_is_explicitly_refused(self):
        from yadinassi.sqlite_transactions import UnitOfWork
        from yadinassi.transaction_backend import TransactionRequest
        tx=UnitOfWork(self.View(uuid4()));tx.stage(TransactionRequest('recorder_replace',self.request()))
        with self.assertRaises(BackendError):tx.stage(TransactionRequest('recorder_replace',self.request(rows=())))
        tx.rollback()
    def test_unactivated_backend_refuses_before_recorder_table_access(self):
        from types import SimpleNamespace
        from yadinassi.sqlite_transactions import _recorder_port
        with self.assertRaises(BackendError):_recorder_port(SimpleNamespace(_backend=SimpleNamespace()))
    def test_root_recovery_uses_immutable_child_receipt_after_later_replace(self):
        from types import SimpleNamespace
        from yadinassi.sqlite_transactions import UnitOfWork,resolve
        from yadinassi.transaction_backend import TransactionRequest
        operation=uuid4();request=TransactionRequest('recorder_replace',self.request())
        tx=UnitOfWork(self.View(operation));tx.stage(request);expected=tx.commit()
        self.c.execute('BEGIN');self.port.replace(uuid4(),self.request(rows=()));self.c.execute('COMMIT')
        def begin_read():
            self.c.execute('BEGIN');return self.View(None)
        backend=SimpleNamespace(begin_read=begin_read,storage_version=8)
        self.assertEqual(resolve(backend,operation,(request,)),expected)
        self.assertEqual(resolve(backend,operation,(request,)),expected)
    def test_root_recovery_rejects_missing_child_without_replay(self):
        from types import SimpleNamespace
        from yadinassi.sqlite_transactions import UnitOfWork,resolve
        from yadinassi.transaction_backend import TransactionRequest
        op=uuid4();request=TransactionRequest('recorder_replace',self.request());tx=UnitOfWork(self.View(op));tx.stage(request);tx.commit()
        self.c.execute('DELETE FROM recorder_movement_receipt')
        def begin_read():
            self.c.execute('BEGIN');return self.View(None)
        with self.assertRaises(BackendError):resolve(SimpleNamespace(begin_read=begin_read),op,(request,))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM recorder_movement_receipt').fetchone()[0],0)
    def test_fresh_only_profile_cannot_enter_additive_update_planner(self):
        from unittest.mock import patch,Mock
        from yadinassi.sqlite_configuration_update import prepare
        backend=Mock(format_version=13,activated=True)
        with patch('yadinassi.configuration_evolution.canonical',return_value=object()), patch('yadinassi.sqlite_catalog.SQLiteCatalogBackend',return_value=backend), patch('yadinassi.sqlite_migration_plan._open') as writer:
            with self.assertRaises(BackendError):prepare('unused',object(),maintenance=True)
            backend.begin_read.assert_not_called();writer.assert_not_called()
            backend.close.assert_called_once()
