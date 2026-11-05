"""Backend-neutral typed scan contract exercised on owned SQLite only."""
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4
import unittest

import test_sqlite_catalog_backend as fixtures
from yadinassi.catalog_backend import (BackendError, CatalogComparison,
    CatalogPredicate, CatalogOrder, CatalogScanRequest, CatalogKey)


class ScanTests(unittest.TestCase):
    setUp=fixtures.BackendTests.setUp
    tearDown=fixtures.BackendTests.tearDown
    draft=fixtures.BackendTests.draft
    def seed(self, count=5):
        tx=self.backend.begin_write(uuid4())
        for i in range(count):
            tx.create(replace(self.draft(code=str(i).zfill(4),amount=Decimal(i)),
                description='same' if i < 2 else 'row'+str(i)))
        tx.commit()

    def test_pages_complete_order_and_consumed_tokens(self):
        self.seed();view=self.backend.begin_read()
        request=CatalogScanRequest(order=(CatalogOrder('code',True),),page_size=2)
        first=view.scan_catalog(self.product.identity,request)
        self.assertEqual([c.code for c in first.cards],['0004','0003'])
        token=first.continuation
        second=view.scan_catalog(self.product.identity,replace(request,continuation=token))
        self.assertEqual([c.code for c in second.cards],['0002','0001'])
        with self.assertRaisesRegex(BackendError,'invalid_input'):
            view.scan_catalog(self.product.identity,replace(request,continuation=token))
        last=view.scan_catalog(self.product.identity,replace(request,continuation=second.continuation))
        self.assertEqual([c.code for c in last.cards],['0000']);self.assertIsNone(last.continuation)
        view.close()
        with self.assertRaisesRegex(BackendError,'closed'):view.scan_catalog(self.product.identity,request)

    def test_card_reads_reuse_one_schema_per_operation(self):
        from unittest.mock import patch
        import yadinassi.sqlite_catalog as storage
        self.seed(20)
        view = self.backend.begin_read()
        self.addCleanup(view.close)
        queries = []
        view._connection.set_trace_callback(queries.append)
        with patch.object(storage, '_schema', wraps=storage._schema) as parse_schema:
            def schema_reads():
                return [query for query in queries
                        if query.startswith('SELECT definition FROM catalog_schema')]
            cards = view.select_catalog(self.product.identity)
            self.assertEqual(len(cards), 20)
            self.assertEqual(len(schema_reads()), 1)
            self.assertEqual(parse_schema.call_count, 1)
            queries.clear(); parse_schema.reset_mock()
            page = view.scan_catalog(self.product.identity, CatalogScanRequest(
                CatalogComparison('code', 'eq', '0019'), page_size=1))
            self.assertEqual(page.cards, (cards[-1],))
            self.assertIsNone(page.continuation)
            self.assertEqual(len(schema_reads()), 1)
            self.assertEqual(parse_schema.call_count, 1)
            queries.clear(); parse_schema.reset_mock()
            self.assertEqual(view.read_catalog(cards[-1].key), cards[-1])
            self.assertEqual(len(schema_reads()), 1)
            self.assertEqual(parse_schema.call_count, 1)

    def test_scan_schema_reuse_keeps_continuation_order_and_validation(self):
        self.seed()
        view = self.backend.begin_read()
        self.addCleanup(view.close)
        queries = []
        view._connection.set_trace_callback(queries.append)
        request = CatalogScanRequest(order=(CatalogOrder('code'),), page_size=2)
        codes = []
        for expected_length in (2, 2, 1):
            queries.clear()
            page = view.scan_catalog(self.product.identity, request)
            self.assertEqual(len(page.cards), expected_length)
            codes.extend(card.code for card in page.cards)
            self.assertEqual(sum(query.startswith('SELECT definition FROM catalog_schema')
                                 for query in queries), 1)
            request = replace(request, continuation=page.continuation)
        self.assertEqual(codes, ['0000', '0001', '0002', '0003', '0004'])
        self.assertIsNone(page.continuation)

    def test_predicates_exact_typed_and_boolean_composition(self):
        self.seed();view=self.backend.begin_read();amount=self.product.fields[1].identity
        predicate=CatalogPredicate('and',(CatalogComparison(amount,'ge',Decimal(2)),
            CatalogPredicate('or',(CatalogComparison('code','eq','0002'),CatalogComparison('code','eq','0004')))))
        page=view.scan_catalog(self.product.identity,CatalogScanRequest(predicate,(CatalogOrder(amount,True),)))
        self.assertEqual([c.values[1] for c in page.cards],[Decimal(4),Decimal(2)])
        for bad in (2,2.0,True,Decimal('NaN'),Decimal('1e99999')):
            with self.subTest(bad=type(bad).__name__),self.assertRaises(BackendError):
                view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogComparison(amount,'eq',bad)))
        view.close()

    def test_empty_catalog_still_validates_complete_request(self):
        view=self.backend.begin_read()
        bads=(CatalogScanRequest(CatalogComparison('not_a_field','eq','x')),
              CatalogScanRequest(CatalogPredicate('or',())),CatalogScanRequest(page_size=True),
              CatalogScanRequest(order=(CatalogOrder('code'),CatalogOrder('code'))),
              CatalogScanRequest(CatalogComparison('ref','lt',CatalogKey(self.backend.database_id,self.product.identity,uuid4()))),
              CatalogScanRequest(CatalogComparison('deletion_mark','eq',1)))
        for bad in bads:
            with self.subTest(request=bad),self.assertRaises(BackendError):view.scan_catalog(self.product.identity,bad)
        view.close()

    def test_continuations_bound_to_view_and_request(self):
        self.seed();view=self.backend.begin_read();request=CatalogScanRequest(page_size=1)
        token=view.scan_catalog(self.product.identity,request).continuation
        with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,replace(request,page_size=2,continuation=token))
        view.close();view=self.backend.begin_read()
        with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,replace(request,continuation=token))
        first=view.scan_catalog(self.product.identity,request)
        view.scan_catalog(self.category.identity,request)
        with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,replace(request,continuation=first.continuation))
        view.close()

    def test_lookup_beyond_1000_and_ambiguity_not_truncated(self):
        self.seed(1002);view=self.backend.begin_read()
        page=view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogComparison('code','eq','1001'),page_size=2))
        self.assertEqual([c.code for c in page.cards],['1001']);self.assertIsNone(page.continuation)
        page=view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogComparison('description','eq','same'),page_size=1))
        self.assertEqual(len(page.cards),1);self.assertIsNotNone(page.continuation)
        view.close()

    def test_reference_scope_and_hostile_types_refused(self):
        view=self.backend.begin_read()
        class Hostile:
            def __eq__(self,other):raise AssertionError('hostile equality')
            def __hash__(self):raise AssertionError('hostile hash')
        values=(CatalogKey(uuid4(),self.product.identity,uuid4()),
            CatalogKey(Hostile(),self.product.identity,uuid4()),Hostile())
        for value in values:
            with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogComparison('ref','eq',value)))
        with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogComparison(Hostile(),'eq','x')))
        view.close()

    def test_predicate_depth_and_width_bounds(self):
        view=self.backend.begin_read();pred=CatalogComparison('code','eq','a')
        for _ in range(10):pred=CatalogPredicate('and',(pred,))
        with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,CatalogScanRequest(pred))
        with self.assertRaises(BackendError):view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogPredicate('or',(CatalogComparison('code','eq','a'),)*65)))
        view.close()

    def test_scan_cannot_claim_snapshot_on_mutable_write_view(self):
        tx=self.backend.begin_write(uuid4())
        with self.assertRaisesRegex(BackendError,'unsupported'):tx.scan_catalog(self.product.identity,CatalogScanRequest())
        tx.rollback()


    def test_materialization_preflight_rejects_before_payload_fetch(self):
        from unittest import mock
        import yadinassi.sqlite_catalog as storage
        self.seed();view=self.backend.begin_read();connection=view._connection
        class Guard:
            def execute(self,sql,*args):
                if sql.startswith('SELECT record_id,revision'):
                    raise AssertionError('payload materialized before resource refusal')
                return connection.execute(sql,*args)
            def __getattr__(self,name):return getattr(connection,name)
        view._connection=Guard()
        with mock.patch.object(storage,'_MAX_CONFIG_BYTES',1):
            with self.assertRaisesRegex(BackendError,'unsupported'):
                view.scan_catalog(self.product.identity,CatalogScanRequest())
        view.close()

    def test_large_decimal_coefficient_refuses_before_tuple_expansion(self):
        view=self.backend.begin_read();amount=self.product.fields[1].identity
        large=Decimal('1.'+'0'*100000)
        with self.assertRaisesRegex(BackendError,'invalid_input'):
            view.scan_catalog(self.product.identity,CatalogScanRequest(CatalogComparison(amount,'eq',large)))
        view.close()

    def test_runtime_exact_find_reaches_late_row_and_refuses_ambiguous_description(self):
        from yadinassi import Interpreter
        from yadinassi.errors import BSLRuntimeError
        from yadinassi.database_context import SQLiteDBContext
        self.seed(1002);self.backend.close()
        context=SQLiteDBContext(self.path);output=[]
        try:
            vm=Interpreter(database_context=context,output=output.append)
            vm.execute('Message(Catalogs.Products.FindByCode("1001").Code);')
            self.assertEqual(output,['1001'])
            with self.assertRaisesRegex(BSLRuntimeError,'ambiguous exact catalog lookup'):
                vm.execute('Catalogs.Products.FindByDescription("same",True);')
        finally:context.close()

    def test_versioned_casefold_policy_preserves_exact_default(self):
        tx=self.backend.begin_write(uuid4())
        for code,text in (('1','alpha'),('2','Alpha'),('3','АЛЬФА'),('4','альфа')):
            tx.create(replace(self.draft(code=code),description=text))
        tx.commit();view=self.backend.begin_read()
        for operand,exact,folded in (('alpha',('1',),('1','2')),('альфа',('4',),('3','4'))):
            request=CatalogScanRequest(CatalogComparison('description','eq',operand),(CatalogOrder('code'),))
            self.assertEqual(tuple(c.code for c in view.scan_catalog(self.product.identity,request).cards),exact)
            self.assertEqual(tuple(c.code for c in view.scan_catalog(self.product.identity,replace(request,string_comparison='casefold_v1')).cards),folded)
        view.close()

    def test_casefold_order_and_continuation_bind_policy(self):
        tx=self.backend.begin_write(uuid4())
        for code,text in (('1','Beta'),('2','alpha'),('3','ALPHA')):
            tx.create(replace(self.draft(code=code),description=text))
        tx.commit();view=self.backend.begin_read()
        request=CatalogScanRequest(order=(CatalogOrder('description'),CatalogOrder('code')),page_size=1,string_comparison='casefold_v1')
        first=view.scan_catalog(self.product.identity,request)
        self.assertEqual(first.cards[0].code,'2')
        with self.assertRaisesRegex(BackendError,'invalid_input'):
            view.scan_catalog(self.product.identity,replace(request,continuation=first.continuation,string_comparison='codepoint'))
        second=view.scan_catalog(self.product.identity,replace(request,continuation=first.continuation))
        self.assertEqual(second.cards[0].code,'3');view.close()

    def test_unknown_or_hostile_string_policy_refused(self):
        view=self.backend.begin_read()
        class Hostile:
            def __eq__(self,other):raise AssertionError('host equality')
        for policy in ('native-regional',None,Hostile()):
            with self.assertRaisesRegex(BackendError,'unsupported'):
                view.scan_catalog(self.product.identity,CatalogScanRequest(string_comparison=policy))
        view.close()
