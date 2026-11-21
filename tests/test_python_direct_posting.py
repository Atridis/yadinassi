"""Actual source posting, unchanged SQL writer, no interpreter dispatch."""
from decimal import Decimal
from unittest.mock import patch
import sqlite3
import unittest
import test_main_demo_runtime as runtime_fixture
from yadinassi.db.sqlite.sqlite_movement_layout import table_name as movement_table
from yadinassi.db.document.document_posting_values import DocumentWriteMode
from yadinassi.db.document.document_posting import _PostingInterpreter

class DirectPostingTests(unittest.TestCase):
    def setUp(self):
        self.fixture=runtime_fixture.MainDemoRuntimeTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.vm=self.fixture.vm;self.vm.execute(runtime_fixture.SEED)
    def document(self,mode=0):
        d=self.vm._documents.get_member('Receipt').create_document()
        d.set_member('Number','r1');d.set_member('Date',self.vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
        d.set_member('Warehouse',self.vm.variables['склад'].get_member('Ссылка'))
        line=d.get_member('Lines').add()
        for name,value in [('Product',self.vm.variables['карточка'].get_member('Ссылка')),('Quantity',Decimal(5)),('Amount',Decimal(10))]:line.set_member(name,value)
        d.get_member('AdditionalProperties').insert('Mode',Decimal(mode))
        return d
    def counts(self):
        movement = movement_table('accumulation', self.fixture.context.backend.accumulation_configuration.registers[0])
        with sqlite3.connect(self.fixture.path) as db:
            return tuple(db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('document_record','document_posting_state',movement))
    def test_original_receipt_no_vm_dispatch(self):
        d=self.document()
        with patch.object(_PostingInterpreter,'call_routine',side_effect=AssertionError('legacy dispatch')):
            d.write(DocumentWriteMode.POSTING)
        self.assertEqual(self.counts(),(1,1,1));self.assertIsNone(d._posting_active)
    def test_cancel_and_raise_rollback_real_source(self):
        for mode in (1,2):
            with self.subTest(mode=mode):
                d=self.document(mode);before=self.counts()
                with self.assertRaises(Exception):d.write(DocumentWriteMode.POSTING)
                self.assertEqual(d.get_member('AdditionalProperties').get_member('Inside'),Decimal(1))
                self.assertEqual(self.counts(),before)
                self.assertIsNone(d._posting_active);self.assertIsNone(d._pending_write)

    def test_transaction_callback_cannot_commit_posting(self):
        from test_document_posting_runtime import PostingRuntimeTests
        f=PostingRuntimeTests();f.setUp();self.addCleanup(f.doCleanups)
        f.make('Procedure Posting(Cancel,Mode) Message("attempt"); EndProcedure')
        f.vm.output=lambda text:f.vm._commit_transaction()
        d=f.vm._documents.get_member('OwnedPostingDoc').create_document()
        d.set_member('Number','3');d.set_member('Date',self.vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
        with self.assertRaises(Exception):d.write(DocumentWriteMode.POSTING)
        self.assertEqual(f.sql('SELECT count(*) FROM document_record'),[(0,)])
        self.assertIsNone(d._posting_active)

    def test_nonboolean_cancel_refuses_atomic_write(self):
        from test_document_posting_runtime import PostingRuntimeTests
        f=PostingRuntimeTests();f.setUp();self.addCleanup(f.doCleanups)
        f.make('Procedure Posting(Cancel,Mode) Cancel=1; EndProcedure')
        d=f.vm._documents.get_member('OwnedPostingDoc').create_document()
        d.set_member('Number','3');d.set_member('Date',self.vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
        with self.assertRaisesRegex(TypeError,'Boolean'):d.write(DocumentWriteMode.POSTING)
        self.assertEqual(f.sql('SELECT count(*) FROM document_record'),[(0,)])

    def test_parent_close_revokes_posting_before_commit(self):
        from test_document_posting_runtime import PostingRuntimeTests
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        f=PostingRuntimeTests();f.setUp();self.addCleanup(f.doCleanups)
        f.make('Procedure Posting(Cancel,Mode) Message("close"); EndProcedure')
        f.vm.output=lambda text:f.vm.close()
        d=f.vm._documents.get_member('OwnedPostingDoc').create_document()
        d.set_member('Number','3');d.set_member('Date',self.vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
        with self.assertRaises(BoundaryViolation):d.write(DocumentWriteMode.POSTING)
        self.assertEqual(f.sql('SELECT count(*) FROM document_record'),[(0,)])
        self.assertEqual(f.sql('SELECT count(*) FROM document_posting_state'),[(0,)])
        self.assertIsNone(d._posting_active);self.assertIsNone(d._pending_write)

    def test_generated_handler_has_server_module_scope(self):
        from test_document_posting_runtime import PostingRuntimeTests
        from yadinassi.db.document.document_posting import _PostingInterpreter
        f=PostingRuntimeTests();f.setUp();self.addCleanup(f.doCleanups)
        f.make('Procedure Posting(Cancel,Mode) Message("side"); EndProcedure')
        seen=[];children=[];original=_PostingInterpreter.__init__
        def initialize(vm,*args):
            original(vm,*args);children.append(vm)
            vm.output=lambda text:seen.append((vm.execution_context,vm._module_context_stack[-1]))
        d=f.vm._documents.get_member('OwnedPostingDoc').create_document()
        d.set_member('Number','3');d.set_member('Date',self.vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
        with patch.object(_PostingInterpreter,'__init__',initialize):d.write(DocumentWriteMode.POSTING)
        self.assertEqual(seen,[('server',True)])
        self.assertEqual(len(children[0]._context_stack),1)
        self.assertEqual(len(children[0]._module_context_stack),1)

    def test_stale_generation_and_released_child_reject(self):
        from yadinassi.execution.direct.python_direct_posting import PostingBoundary
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        d=self.document();d._posting_active=object()
        child=_PostingInterpreter(d,self.vm,[]);boundary=PostingBoundary(child);boundary.start()
        self.addCleanup(child.close)
        try:
            boundary._check()
            child.close()
            with self.assertRaises(BoundaryViolation):boundary._check()
            child2=_PostingInterpreter(d,self.vm,[]);boundary2=PostingBoundary(child2);boundary2.start()
            self.addCleanup(child2.close)
            self.vm.close();self.vm._require_family()
            self.assertFalse(self.vm._family_closed)
            with self.assertRaises(BoundaryViolation):boundary2._check()
        finally:d._posting_active=None

    def test_host_invoked_posting_preserves_native_target_scope(self):
        from test_document_posting_runtime import PostingRuntimeTests
        from yadinassi import Interpreter
        from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508,current_native_target
        f=PostingRuntimeTests();f.setUp();self.addCleanup(f.doCleanups)
        f.make('Procedure Posting(Cancel,Mode) Message("target"); EndProcedure')
        f.vm.close();seen=[]
        vm=Interpreter(database_context=f.context,native_target=LINUX_8_3_27_1508,output=lambda text:seen.append(current_native_target()))
        self.addCleanup(vm.close)
        d=vm._documents.get_member('OwnedPostingDoc').create_document()
        d.set_member('Number','3');d.set_member('Date',vm.functions['date'](Decimal(2024),Decimal(1),Decimal(1)))
        before=current_native_target();d.write(DocumentWriteMode.POSTING)
        self.assertEqual(seen,[LINUX_8_3_27_1508]);self.assertEqual(current_native_target(),before)


class PostingDiscoveryTests(unittest.TestCase):
    def test_fixture_import_does_not_rediscover_foreign_tests(self):
        import sys
        from scripts.test_partition import leaves
        suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
        ids = [test.id() for test in leaves(suite)]
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(name.startswith(__name__ + '.') for name in ids))
