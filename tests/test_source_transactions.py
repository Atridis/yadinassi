from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from test_source_constant_store import configuration
from test_source_constants_runtime import package
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


class SourceTransactionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'scratch.sqlite'

    def store(self):
        store = SourceConstantStore.create(self.path, configuration())
        self.addCleanup(store.close)
        return store

    def app(self, body):
        app = SourceApplication(package(body), scratch_database=self.path)
        self.addCleanup(app.close)
        return app

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0]

    def test_multi_constant_commit_and_reopen(self):
        store = self.store(); store.begin_transaction()
        store.set('Flag', True); store.set('Text', 'saved'); store.set('Amount', Decimal('3'))
        self.assertTrue(store.get('Flag')); self.assertEqual(self.count(), 0)
        store.commit_transaction(); self.assertEqual(self.count(), 3)
        store.close()
        reopened = SourceConstantStore.reopen(self.path, configuration()); self.addCleanup(reopened.close)
        self.assertEqual(reopened.get('Text'), 'saved')

    def test_rollback_preserves_previous_values(self):
        store = self.store(); store.set('Flag', False)
        store.begin_transaction(); store.set('Flag', True); store.set('Text', 'temporary')
        store.rollback_transaction(); self.assertFalse(store.get('Flag')); self.assertEqual(self.count(), 1)

    def test_validation_failure_rolls_back_whole_transaction(self):
        store = self.store(); store.begin_transaction(); store.set('Flag', True)
        with self.assertRaises((TypeError, ValueError)): store.set('Text', 1)
        self.assertFalse(store.transaction_active); self.assertEqual(self.count(), 0)

    def test_read_failure_rolls_back_transaction(self):
        store = self.store(); store.begin_transaction(); store.set('Flag', True)
        with self.assertRaises(ValueError): store.get('Text')
        self.assertFalse(store.transaction_active); self.assertEqual(self.count(), 0)

    def test_nested_begin_rejected_without_committing(self):
        store = self.store(); store.begin_transaction(); store.set('Flag', True)
        with self.assertRaisesRegex(ValueError, 'nested'): store.begin_transaction()
        self.assertEqual(self.count(), 0); store.rollback_transaction()

    def test_close_rolls_back(self):
        store = self.store(); store.begin_transaction(); store.set('Flag', True); store.close()
        self.assertEqual(self.count(), 0)

    def test_commit_and_rollback_require_active(self):
        store = self.store()
        for action in (store.commit_transaction, store.rollback_transaction):
            with self.assertRaisesRegex(ValueError, 'no active'): action()

    def test_bsl_commit_aliases(self):
        app = self.app('НачатьТранзакцию(); Constants.Flag.Set(True); ЗафиксироватьТранзакцию();')
        self.assertTrue(app.start()); self.assertEqual(self.count(), 1)

    def test_bsl_rollback_and_status(self):
        app = self.app('If TransactionActive() Then Raise "bad"; EndIf; BeginTransaction(); If Not TransactionActive() Then Raise "bad"; EndIf; Constants.Flag.Set(True); RollbackTransaction();')
        self.assertTrue(app.start()); self.assertEqual(self.count(), 0)

    def test_unhandled_exception_rolls_back(self):
        app = self.app('BeginTransaction(); Constants.Flag.Set(True); Raise "stop";')
        with self.assertRaises(BSLError): app.start()
        self.assertEqual(self.count(), 0)

    def test_unfinished_execution_rolls_back(self):
        app = self.app('BeginTransaction(); Constants.Flag.Set(True);')
        with self.assertRaisesRegex(ValueError, 'boundary|unfinished'): app.start()
        self.assertEqual(self.count(), 0)

    def test_no_implicit_database(self):
        app = SourceApplication(package('BeginTransaction();')); self.addCleanup(app.close)
        with self.assertRaisesRegex(BSLError, 'scratch database'): app.start()

    def test_safe_mode_denied(self):
        app = self.app('SetSafeMode(True); BeginTransaction();')
        with self.assertRaisesRegex(BSLError, 'safe mode'): app.start()
        self.assertEqual(self.count(), 0)

    def test_lock_mode_argument_is_not_silently_ignored(self):
        app = self.app('BeginTransaction(Undefined);')
        with self.assertRaisesRegex(BSLError, 'lock modes unsupported'): app.start()

    def test_foreign_and_client_captured_call_denied(self):
        from yadinassi.source_transactions import SourceTransactionCall
        app = self.app(''); app.start()
        app.interpreter.register_function('Captured', SourceTransactionCall(app, 'begin'), returns_value=False)
        with self.assertRaisesRegex(BSLError, 'owning synchronous server'): app.interpreter.execute('Captured();')

    def test_transfer_guard(self):
        from yadinassi.source_transactions import execution
        from yadinassi.database_transactions import forbid_transfer
        app = self.app(''); app.start()
        with execution(app):
            app.constant_store.begin_transaction()
            with self.assertRaisesRegex(ValueError, 'boundary'): forbid_transfer(None)
            app.constant_store.rollback_transaction()

    def test_extension_registry_read_preserves_transaction(self):
        store = self.store(); store.begin_transaction(); store.set('Flag', True)
        store.require_empty_extension_registry(); store.set('Text', 'temporary')
        self.assertTrue(store.transaction_active); self.assertEqual(self.count(), 0)
        store.rollback_transaction(); self.assertEqual(self.count(), 0)

    def test_bsl_extension_read_and_caught_error_do_not_commit(self):
        app = self.app('BeginTransaction(); Constants.Flag.Set(True); ConfigurationExtensions.Get(); Try Raise "caught"; Except EndTry; Constants.Flag.Set(False); RollbackTransaction();')
        self.assertTrue(app.start()); self.assertEqual(self.count(), 0)
