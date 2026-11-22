"""Logical path/WHERE contract; SQLite lowering is tested independently."""
import unittest
from unittest.mock import patch
from uuid import UUID

import test_main_demo_runtime as demo
from yadinassi import BSLRuntimeError
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.document.document_backend import DocumentKey
from yadinassi.db.query.query_parser import parse_query
from yadinassi.db.query.relational_queries import _Plan
from yadinassi.db.sqlite.sqlite_documents import DocumentView


class QueryDereferenceBindingTests(unittest.TestCase):
    def owner(self):
        case = demo.MainDemoRuntimeTests()
        self.addCleanup(case.doCleanups)
        case.setUp()
        return case.vm

    def test_ordinary_where_binds_document_reference_and_scalar_terms_once(self):
        vm = self.owner()
        manager = vm._documents.get_index('Receipt')
        target = manager._ref(UUID(int=42))
        vm.variables['target'] = target
        calls = []
        def projected(view, source, paths, order, limit, *, predicate=None):
            calls.append((source, paths, order, predicate))
            return (('R1',),)
        with patch.object(DocumentView, 'query_dereference', projected, create=True):
            result = vm.execute('Q=New Query("SELECT D.Ref.Number AS Caption FROM Document.Receipt AS D '
                'WHERE D.Ref=&Target AND (D.Number=&Number OR D.DeletionMark=False)");'
                'Q.SetParameter("Target",Target);Q.SetParameter("Number","R1");Q.Execute()')
        self.assertEqual(result._rows, (('R1',),))
        [(source, paths, order, predicate)] = calls
        self.assertEqual(source, ('document',manager._schema.identity,None))
        self.assertEqual(paths, (('ref','document',manager._schema.identity,'number'),))
        self.assertEqual(order, ())
        self.assertEqual(predicate.kind, 'and')
        key, group = predicate.terms
        self.assertEqual((key.field,key.operator,key.value),('ref','eq',
            DocumentKey(manager._documents._metadata._database_id,manager._schema.identity,UUID(int=42))))
        self.assertEqual(group.kind,'or')
        self.assertEqual(tuple((term.field,term.operator,term.value) for term in group.terms),
                         (('number','eq','R1'),('deletion_mark','eq',False)))

    def test_unowned_and_unsupported_dereference_do_not_reach_provider(self):
        vm = self.owner()
        other = self.owner()
        with patch.object(DocumentView, 'query_dereference',
                          side_effect=AssertionError('physical provider'), create=True):
            for predicate in ('D.Warehouse.Description="x"',
                              'D.Number="x" OR D.Warehouse.Description="y"'):
                with self.subTest(predicate=predicate), self.assertRaisesRegex(BSLRuntimeError,'WHERE'):
                    vm.execute('Q=New Query("SELECT D.Ref.Number AS N FROM Document.Receipt AS D WHERE '
                               + predicate.replace('"','""') + '");Q.Execute()')
            query = parse_query('SELECT D.Ref.Number AS N FROM Document.Receipt AS D')
            with self.assertRaisesRegex(BackendError,'schema_changed'):
                _Plan(query,vm._catalogs,{},documents=other._documents)
