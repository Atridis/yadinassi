"""Instance shadowing cannot intercept an admitted movement protocol."""
import unittest
from unittest.mock import patch
import test_python_direct_accumulation_ownership as fixture
from yadinassi.db.registers import accumulation_posting_values as native
DENIED=fixture.DENIED

class MovementHookTests(unittest.TestCase):
    setUp=fixture.DirectAccumulationOwnershipTests.setUp
    prepared=fixture.DirectAccumulationOwnershipTests.prepared
    def test_movement_instance_hooks_are_rejected_without_callbacks(self):
        vm=self.prepared();effects=[]
        cases=(('collection','get_member','Collection.OwnedAccumulationRows;'),
               ('set','_mutable','Set.Add();'),('set','_budget','Set.Add();'),
               ('set','_stored_rows','Set.Write();'),('set','_replace','Set.Write();'),
               ('r','_check','R.Amount;'),('r','_check','R.Amount=4;'))
        for receiver,name,code in cases:
            value=vm.variables[receiver]
            with self.subTest(receiver=receiver,name=name,code=code):
                setattr(value,name,lambda *args:effects.append(name))
                try:
                    with self.assertRaises(DENIED):vm.execute(code)
                    self.assertEqual(effects,[])
                    self.assertEqual(len(vm.variables['set']._rows),1)
                finally:delattr(value,name)
    def test_parent_manager_helpers_are_rejected_without_callbacks(self):
        vm=self.prepared();manager=vm.variables['o']._manager;effects=[]
        for name in ('_writable','_field_default','_assigned','_ref'):
            with self.subTest(name=name):
                setattr(manager,name,lambda *args:effects.append(name))
                try:
                    with self.assertRaises(DENIED):vm.execute('Set.Add();')
                    self.assertEqual(effects,[])
                finally:delattr(manager,name)

    def test_native_constructor_and_namespace_bindings_rejected(self):
        vm=self.prepared();effects=[]
        class Trap:
            def get_member(self,name):effects.append(name)
        with patch.object(native,'ACCUMULATION_RECORD_TYPES',Trap()):
            with self.assertRaises(DENIED):vm.execute('AccumulationRecordType.Receipt;')
        with patch.object(native,'BSLAccumulationRow',lambda *args:effects.append('constructor')):
            with self.assertRaises(DENIED):vm.execute('Set.Add();')
        self.assertEqual(effects,[])
    def test_accounting_tampering_rejected(self):
        vm=self.prepared()
        for target in (vm.variables['set'],vm.variables['r']):
            old=target._bytes;target._bytes=0
            try:
                with self.assertRaises(DENIED):vm.execute('Set.Count();')
            finally:target._bytes=old
    def test_parent_class_and_slot_hooks_rejected(self):
        from yadinassi.db.document.documents import BSLDocumentManager
        from yadinassi.db.document.document_backend import DocumentKey
        vm=self.prepared();effects=[]
        config=vm._documents._posting_runtime.configuration
        for cls,name,replacement in (
                (BSLDocumentManager,'_field_default',lambda *args:effects.append('default')),
                (BSLDocumentManager,'_writable',lambda *args:effects.append('write')),
                (DocumentKey,'document_id',property(lambda self:effects.append('key'))),
                (type(config),'registers',property(lambda self:effects.append('config')))):
            with self.subTest(name=name),patch.object(cls,name,replacement):
                with self.assertRaises(DENIED):vm.execute('Set.Add();')
                self.assertEqual(effects,[])
    def test_metadata_root_and_namespace_instance_hooks_rejected(self):
        vm=self.prepared();effects=[]
        class Fake:
            @property
            def _documents(self):effects.append('metadata')
        original=vm._metadata;vm._metadata=Fake()
        try:
            with self.assertRaises(DENIED):vm.execute('Set.Count();')
        finally:vm._metadata=original
        namespace=native.ACCUMULATION_RECORD_TYPES
        namespace.get_member=lambda name:effects.append('namespace')
        try:
            with self.assertRaises(DENIED):vm.execute('AccumulationRecordType.Receipt;')
        finally:del namespace.get_member
        self.assertEqual(effects,[])
