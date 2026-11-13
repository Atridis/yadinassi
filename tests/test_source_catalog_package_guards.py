"""Independent failure-boundary checks for source package capabilities."""
import unittest
import weakref
from unittest.mock import patch
import test_source_catalog_queries as fixture
from yadinassi.source_query_references import SourcePackageScope
from yadinassi.source_constant_queries import SourceConstantQuery
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi import query_parser as syntax

class SourceCatalogPackageGuardTests(unittest.TestCase):
    setUp=fixture.SourceCatalogQueryTests.setUp
    run_body=fixture.SourceCatalogQueryTests.run_body

    def test_scope_requires_exact_ast(self):
        app,_=self.run_body('')
        statements=syntax.parse_package('SELECT X FROM Saved')
        scope=SourcePackageScope(weakref.ref(app),app.interpreter._catalogs,statements,())
        with self.assertRaises(TypeError):
            scope.require_context(syntax.parse_package('SELECT X FROM Saved'),app.interpreter._catalogs)

    def test_scope_rejects_untranslated_persistent_source(self):
        app,_=self.run_body('')
        statements=syntax.parse_package('SELECT Code FROM Catalog.Items')
        scope=SourcePackageScope(weakref.ref(app),app.interpreter._catalogs,statements,())
        with self.assertRaises(ValueError):scope.require_context(statements,app.interpreter._catalogs)

    def test_final_ownership_failure_does_not_publish(self):
        app,_=self.run_body('')
        query=SourceConstantQuery(app.interpreter,app,'SELECT Ref AS R INTO Saved FROM Catalog.Items')
        manager=BSLTempTablesManager();query._temp_tables_manager=manager
        app.interpreter._context_stack.append('server')
        self.addCleanup(app.interpreter._context_stack.pop)
        original=SourcePackageScope.require_context
        calls=[]
        def guard(scope,statements,catalogs):
            calls.append(1)
            if len(calls)==3:raise ValueError('injected final ownership failure')
            return original(scope,statements,catalogs)
        with patch.object(SourcePackageScope,'require_context',guard):
            with self.assertRaisesRegex(ValueError,'injected final'):
                query.read(app.interpreter)
        self.assertEqual(manager._tables,{})
        self.assertIsNone(manager._owner)
        self.assertFalse(app.constant_store.transaction_active)

    def test_query_keeps_explicit_transaction_on_success(self):
        _,out=self.run_body('BeginTransaction(); Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items; SELECT R FROM Saved"); R=Q.ExecuteBatch(); Message(TransactionActive()); RollbackTransaction();')
        self.assertEqual(out,['Да'])
