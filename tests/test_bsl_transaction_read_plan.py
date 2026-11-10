"""A1 activation bindings and H1-H3 read plans remain closed inside a write lease."""
import unittest
from unittest.mock import patch
import test_bsl_transactions as fixtures
from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.catalog_backend import CatalogScanRequest
from yadinassi.document_backend import DocumentScanRequest
from yadinassi.database_transactions import execution, begin, commit, rollback


class TransactionReadPlanTests(unittest.TestCase):
    setUp = fixtures.BSLTransactionsTests.setUp
    catalog = fixtures.BSLTransactionsTests.catalog

    def test_catalog_write_lease_does_not_cache_integrity(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend);obj.write();view=self.backend.begin_read()
            with patch.object(view,'_preflight_v2',wraps=view._preflight_v2) as check:
                for _ in range(2):view.scan_catalog_values(obj._key.catalog_id,CatalogScanRequest(),('code',))
                self.assertEqual(check.call_count,2)
            self.assertEqual(view._validated_sources,{})
            view.close();commit(self.backend)

    def test_document_write_lease_does_not_cache_integrity(self):
        obj=self.vm.execute('D=Documents.Orders.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);D')
        with execution(self.backend):
            begin(self.backend);obj.write();view=self.backend.begin_document_read()
            with patch.object(view,'_preflight',wraps=view._preflight) as check:
                for _ in range(2):view.scan_document_values(obj._key.document_id,DocumentScanRequest(),('number',))
                self.assertEqual(check.call_count,2)
            self.assertEqual(view._view._validated_sources,{})
            view.close();commit(self.backend)

    def test_import_transaction_globals_bind_to_child(self):
        module=self.path.parent/'Child.bsl';module.write_text('Procedure P() Export EndProcedure',encoding='utf-8')
        self.vm.execute('// #Import Child.bsl\n',source=str(self.path.parent/'main.bsl'))
        child=self.vm.imports['child'].interpreter
        for name in ('begintransaction','committransaction','rollbacktransaction'):
            self.assertIs(child.functions[name].function.__self__,child)

    def test_server_transaction_globals_bind_and_refuse_begin(self):
        server=self.vm._new_server_activation()
        for name in ('begintransaction','committransaction','rollbacktransaction'):
            self.assertIs(server.functions[name].function.__self__,server)
        with self.assertRaises(BSLRuntimeError):server.execute('BeginTransaction();')
        self.assertIsNone(getattr(self.backend,'_bsl_transaction',None))

    def test_host_override_is_not_rebound_by_name(self):
        def host(): return None
        self.vm.register_function('BeginTransaction',host)
        child=Interpreter(database_context=self.context);child._inherit_host_bindings(self.vm)
        self.assertIs(child.functions['begintransaction'].function,host)
