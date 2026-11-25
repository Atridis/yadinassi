"""Information-register movement buffers use the same live ownership fence."""
import unittest
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
import test_document_posting_runtime as fixture

class DirectRecorderOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.owner=fixture.PostingRuntimeTests();self.owner.setUp();self.addCleanup(self.owner.doCleanups)
        self.vm=self.owner.vm
        self.vm.execute('O=Documents.OwnedPostingDoc.CreateDocument();C=O.RegisterRecords;S=C.OwnedPostingRows;R=S.Add();')
    def test_live_and_cleared_row(self):
        self.assertEqual(self.vm.execute('S.Count();'),1)
        self.assertIs(self.vm.execute('S.Get(0);'),self.vm.variables['r'])
        self.vm.execute('S.Clear();')
        with self.assertRaises((BoundaryViolation,ValueError,BSLRuntimeError)):
            self.vm.execute('R.Active;')
    def test_same_context_other_vm_cannot_borrow(self):
        other=Interpreter(database_context=self.owner.context);self.addCleanup(other.close)
        for name,code in (('c','X.OwnedPostingRows;'),('s','X.Add();'),('r','X.Active;')):
            other.variables['x']=self.vm.variables[name]
            with self.subTest(name=name),self.assertRaises(BoundaryViolation):other.execute(code)
