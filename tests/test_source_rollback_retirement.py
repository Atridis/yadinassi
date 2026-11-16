"""SQLite rollback failure must retire source handles, not reopen authority."""
import sqlite3
import unittest
from unittest.mock import patch
import test_source_document_sections as fixture
from uuid import uuid4

class FailingConnection:
    def __init__(self,connection,fail_rollback=True,fail_commit=False,fail_close=False):
        self.connection=connection;self.fail_rollback=fail_rollback
        self.fail_commit=fail_commit;self.fail_close=fail_close;self.closed=False
    def __getattr__(self,name):return getattr(self.connection,name)
    def execute(self,sql,*args):
        if sql=='ROLLBACK' and self.fail_rollback:raise sqlite3.OperationalError('injected rollback failure')
        if sql=='COMMIT' and self.fail_commit:raise sqlite3.OperationalError('injected commit failure')
        return self.connection.execute(sql,*args)
    def close(self):
        self.closed=True
        if self.fail_close:raise sqlite3.OperationalError('injected close failure')
        self.connection.close()

class SourceRollbackRetirementTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store
    def wrapper(self,s,**kwargs):
        original=s._connection;self.addCleanup(original.close)
        s._connection=FailingConnection(original,**kwargs);return s._connection
    def retired(self,s):
        self.assertTrue(s._closed);self.assertFalse(s.transaction_active)
        self.assertFalse(s._explicit_transaction)
        with self.assertRaisesRegex(ValueError,'closed'):s._open()
    def test_explicit_rollback_failure_retires(self):
        s=self.store();s.begin_transaction();w=self.wrapper(s)
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.rollback_transaction()
        self.assertTrue(w.closed);self.retired(s)
    def test_commit_and_rollback_failure_retires(self):
        s=self.store();s.begin_transaction();self.wrapper(s,fail_commit=True)
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.commit_transaction()
        self.retired(s)
    def test_commit_failure_successful_rollback_keeps_handle(self):
        s=self.store();s.begin_transaction();self.wrapper(s,fail_commit=True,fail_rollback=False)
        with self.assertRaises(sqlite3.OperationalError):s.commit_transaction()
        self.assertFalse(s._closed);self.assertFalse(s.transaction_active);s._open()
    def test_begin_validation_and_rollback_failure_retires(self):
        s=self.store();self.wrapper(s)
        real=s._open;calls=[]
        def check():
            calls.append(1)
            if len(calls)==2:raise ValueError('injected validation failure')
            return real()
        with patch.object(s,'_open',side_effect=check):
            with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.begin_transaction()
        self.retired(s)
    def test_record_abort_rollback_failure_retires(self):
        s=self.store();s.begin_transaction();self.wrapper(s)
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):
            s.write_document_bundle('Invoice',uuid4(),0,self.values(),{})
        self.retired(s)
    def test_close_failure_still_retires(self):
        s=self.store();s.begin_transaction();self.wrapper(s,fail_close=True)
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.rollback_transaction()
        self.retired(s)
    def test_abort_closed_handle_is_idempotent(self):
        s=self.store();s.begin_transaction();s.close();s._abort();s._abort()
        self.retired(s)
    def test_closed_section_read_preserves_closed_error(self):
        s=self.store();s.close()
        with self.assertRaisesRegex(ValueError,'store is closed'):s.read_documents('Invoice')
        with self.assertRaisesRegex(ValueError,'store is closed'):s.read_document_bundle('Invoice',uuid4())
    def test_constant_owned_read_cleanup_failure_retires(self):
        s=self.store();self.wrapper(s)
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.get_many(())
        self.retired(s)
    def test_constant_set_error_cleanup_failure_retires(self):
        s=self.store();s.begin_transaction();self.wrapper(s)
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.set('UnknownConstant',None)
        self.retired(s)
    def test_explicit_flag_without_sql_transaction_retires(self):
        s=self.store();s._explicit_transaction=True
        with self.assertRaisesRegex(ValueError,'rollback failed; store closed'):s.rollback_transaction()
        self.retired(s)
