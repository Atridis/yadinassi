"""Standalone BSL writes use SQLite once, without an automatic replay."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_documents import DocumentView
from yadinassi.db.sqlite.sqlite_registers import RegisterView
from test_document_configuration_xml import document_files
from test_information_registers import register_files


class StandaloneDocumentRegisterNoReceiptTests(unittest.TestCase):
    def database(self, files):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path=Path(folder.name)/'db.sqlite'
        context=SQLiteDBContext.create(path, import_configuration(files))
        self.addCleanup(context.close)
        vm=Interpreter(database_context=context)
        self.addCleanup(vm.close)
        return vm, path, context.backend

    def sql(self, path, code):
        with closing(sqlite3.connect(path)) as db:
            return db.execute(code).fetchall()

    def trace_writes(self, backend):
        statements=[]
        connect=backend._connect
        def traced(*args, **kwargs):
            db=connect(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db
        patcher=patch.object(backend,'_connect',side_effect=traced)
        patcher.start()
        self.addCleanup(patcher.stop)
        return statements

    def assert_no_receipt_access(self, statements, commits):
        self.assertEqual(sum(sql == 'COMMIT' for sql in statements), commits)
        write_receipts=('COMMIT_RECEIPT','INFORMATION_REGISTER_RECEIPT','UNIT_OF_WORK_RECEIPT')
        for sql in map(str.upper, statements):
            if sql.startswith('INSERT INTO') or 'WHERE OPERATION_ID=' in sql:
                self.assertFalse(any(name in sql for name in write_receipts),sql)

    @staticmethod
    def lose_reply(commit):
        def lost(view):
            commit(view)
            raise OSError('commit acknowledgement lost')
        return lost

    def test_document_does_not_write_receipt_and_lost_reply_cannot_replay(self):
        vm,path,backend=self.database(document_files(catalogs=False, fields=False))
        statements=self.trace_writes(backend)
        vm.execute('D=Documents.Orders.CreateDocument();D.Date=Date(2026,11,9);D.Write();')
        self.assertEqual(vm.execute('D.Number'),'000000001')
        vm.execute('X=Documents.Orders.CreateDocument();X.Date=Date(2026,11,9);')
        with patch.object(DocumentView,'_confirm_commit',self.lose_reply(DocumentView._confirm_commit)):
            with self.assertRaises(BSLRuntimeError):
                vm.execute('X.Write();')
        with patch.object(backend,'begin_document_write') as begin, \
             patch.object(backend,'resolve_document_write',create=True) as resolve:
            with self.assertRaises(BSLRuntimeError):
                vm.execute('X.Write();')
            begin.assert_not_called()
            resolve.assert_not_called()
        self.assertEqual(self.sql(path,'SELECT number FROM document_record ORDER BY number'),
                         [('000000001',),('000000002',)])
        self.assertEqual(self.sql(path,'SELECT COUNT(*) FROM document_commit_receipt'),[(0,)])
        self.assertFalse(vm.execute('Documents.Orders.FindByNumber("000000002").IsEmpty()'))
        self.assert_no_receipt_access(statements,2)

    def test_unconfirmed_document_transaction_rolls_back_number_and_row(self):
        vm,path,backend=self.database(document_files(catalogs=False, fields=False))
        vm.execute('D=Documents.Orders.CreateDocument();D.Date=Date(2026,11,9);')
        with patch.object(DocumentView,'_confirm_commit',side_effect=OSError('commit not acknowledged')):
            with self.assertRaises(BSLRuntimeError):
                vm.execute('D.Write();')
        self.assertEqual(self.sql(path,'SELECT COUNT(*) FROM document_record'),[(0,)])
        with patch.object(backend,'begin_document_write') as begin:
            with self.assertRaises(BSLRuntimeError):
                vm.execute('D.Write();')
            begin.assert_not_called()
        vm.execute('NewDoc=Documents.Orders.CreateDocument();NewDoc.Date=Date(2026,11,9);NewDoc.Write();')
        self.assertEqual(vm.execute('NewDoc.Number'),'000000001')

    def test_records_and_sets_freeze_until_explicit_fresh_read(self):
        vm,path,backend=self.database(register_files())
        statements=self.trace_writes(backend)
        # Plain python-direct does not currently expose the InformationRegisters
        # global; exercise the existing language objects against the same SQLite.
        manager=vm._information_registers.get_member('Prices')
        record=manager.create_record_manager()
        record.set_member('Item','A')
        record.set_member('Region','North')
        record.set_member('Price',Decimal(3))
        records=manager.create_record_set()
        records.get_member('Filter').get_member('Region').get_member('Set')('South')
        row=records.add()
        row.set_member('Item','B')
        row.set_member('Price',Decimal(5))
        for target,resolve_method in ((record,'resolve_register_write'),(records,'resolve_register_set')):
            with self.subTest(target=type(target).__name__):
                with patch.object(RegisterView,'_confirm_commit',self.lose_reply(RegisterView._confirm_commit)):
                    with self.assertRaisesRegex(BackendError,'uncertain_commit'):
                        target.write()
                with patch.object(backend,'begin_register_write') as begin, \
                     patch.object(backend,resolve_method,create=True) as resolve:
                    with self.assertRaisesRegex(BackendError,'uncertain_commit'):
                        target.write()
                    begin.assert_not_called()
                    resolve.assert_not_called()
                target.read()
        self.assertEqual(record.get_member('Price'),3)
        self.assertEqual(records.get(Decimal(0)).get_member('Price'),5)
        record.set_member('Price',Decimal(6))
        record.write()
        record.delete()
        self.assertEqual(self.sql(path,'SELECT COUNT(*) FROM information_register_record'),[(1,)])
        self.assertEqual(self.sql(path,'SELECT COUNT(*) FROM information_register_receipt'),[(0,)])
        self.assert_no_receipt_access(statements,4)
