"""Movement receivers retain live document/context provenance in direct execution."""
import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
import test_accumulation_query_runtime as fixture

DENIED=(BoundaryViolation,BSLError,ValueError,TypeError)

class DirectAccumulationOwnershipTests(unittest.TestCase):
    def setUp(self):
        owner=fixture.AccumulationQueryRuntimeTests();self.addCleanup(owner.doCleanups)
        self.vm,self.context=owner.make(allow_extensions=True)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            p=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name));p.start();self.addCleanup(p.stop)
    def prepared(self):
        self.vm.execute('O=Documents.OwnedAccumulationDoc.CreateDocument();O.Date=Date(2024,1,1);Collection=O.RegisterRecords;Set=Collection.OwnedAccumulationRows;R=Set.Add();')
        return self.vm
    def test_live_collection_set_row_fields_without_vm(self):
        vm=self.prepared()
        vm.execute('R.Item="A";R.Warehouse=1;R.Amount=7;R.Quantity=2;R.Note="owned";R.Period=Date(2024,1,1);R.RecordType=AccumulationRecordType.Receipt;Set.Write=True;')
        self.assertEqual(vm.execute('Set.Count();'),1)
        self.assertEqual(vm.execute('R.Amount;'),7)
        self.assertIs(vm.execute('Set.Get(0);'),vm.variables['r'])
        self.assertIs(vm.execute('Set.Write;'),True)
        self.assertIsNotNone(vm.execute('R.Recorder;'))
    def test_same_context_foreign_vm_collection_set_row_refused(self):
        vm=self.prepared();other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        for name,code in (('collection','Foreign.OwnedAccumulationRows;'),('set','Foreign.Add();'),('r','Foreign.Amount=99;')):
            other.variables['foreign']=vm.variables[name]
            with self.subTest(name=name),self.assertRaises(DENIED):other.execute(code)
        self.assertEqual(vm.execute('Set.Count();'),1)
        self.assertEqual(vm.execute('R.Amount;'),0)
    def test_row_clear_revokes_current_and_saved_reference(self):
        vm=self.prepared();vm.execute('Set.Clear();')
        for code in ('R.Amount;','R.Amount=7;'):
            with self.subTest(code=code),self.assertRaises(DENIED):vm.execute(code)
        self.assertEqual(vm.execute('Set.Count();'),0)
    def test_unbound_set_write_does_not_bypass_transaction(self):
        vm=self.prepared()
        with self.assertRaises(DENIED):vm.execute('Set.Write();')
        self.assertEqual(vm.execute('Set.Count();'),1)
        self.assertTrue(vm.variables['o'].is_new())
    def test_saved_add_revalidates_context_and_receiver(self):
        vm=self.prepared();vm.execute('Add=Set.Add;Count=Set.Count;')
        self.assertEqual(vm.execute('Count();'),1)
        vm.execute('More=Add();');self.assertEqual(vm.execute('Count();'),2)
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreignadd']=vm.variables['add']
        with self.assertRaises(DENIED):other.execute('ForeignAdd();')
        self.assertEqual(vm.execute('Count();'),2)
    def test_closed_database_denies_retained_set(self):
        vm=self.prepared();recordset=vm.variables['set'];before=len(recordset._rows);self.context.close()
        with self.assertRaises(DENIED):vm.execute('Set.Add();')
        self.assertEqual(len(recordset._rows),before)
    def test_reparented_set_rejected_before_argument_effect(self):
        vm=self.prepared();vm.execute('Other=Documents.OwnedAccumulationDoc.CreateDocument();')
        original=vm.variables['set']._document;vm.variables['set']._document=vm.variables['other'];effects=[]
        vm.register_function('Touch',lambda:effects.append('arg') or Decimal(0))
        try:
            with self.assertRaises(DENIED):vm.execute('Set.Get(Touch());')
            self.assertEqual(effects,[])
        finally:vm.variables['set']._document=original
    def test_row_owner_reparenting_denied(self):
        vm=self.prepared();vm.execute('Other=Documents.OwnedAccumulationDoc.CreateDocument();OtherSet=Other.RegisterRecords.OwnedAccumulationRows;')
        row=vm.variables['r'];original=row._owner;row._owner=vm.variables['otherset']
        try:
            with self.assertRaises(DENIED):vm.execute('R.Amount=1;')
        finally:row._owner=original
    def test_collection_replacement_revokes_retained_handle(self):
        vm=self.prepared();vm.execute('Other=Documents.OwnedAccumulationDoc.CreateDocument();')
        doc=vm.variables['o'];original=doc._movements;doc._movements=vm.variables['other']._movements
        try:
            with self.assertRaises(DENIED):vm.execute('Collection.OwnedAccumulationRows;')
            with self.assertRaises(DENIED):vm.execute('Set.Count();')
        finally:doc._movements=original
    def test_late_row_owner_mutation_blocks_setter(self):
        vm=self.prepared();vm.execute('Other=Documents.OwnedAccumulationDoc.CreateDocument();OtherSet=Other.RegisterRecords.OwnedAccumulationRows;')
        row=vm.variables['r'];old=row._owner
        def touch():row._owner=vm.variables['otherset'];return Decimal(99)
        vm.register_function('Touch',touch)
        try:
            with self.assertRaises(DENIED):vm.execute('R.Amount=Touch();')
            self.assertEqual(row._values['amount'],0)
        finally:row._owner=old
    def test_uncertain_commit_mutation_gate_preserved(self):
        vm=self.prepared();doc=vm.variables['o'];doc._pending_write=object()
        try:
            with self.assertRaises(DENIED):vm.execute('Set.Add();')
            self.assertEqual(len(vm.variables['set']._rows),1)
        finally:doc._pending_write=None
    def test_coherent_collection_reparenting_denied_by_origin(self):
        vm=self.prepared();vm.execute('Other=Documents.OwnedAccumulationDoc.CreateDocument();OtherCollection=Other.RegisterRecords;')
        a,b=vm.variables['o'],vm.variables['other'];ca,cb=a._movements,b._movements
        a._movements,b._movements=cb,ca;ca._document,cb._document=b,a
        for recordset in ca._sets.values():recordset._document=b
        for recordset in cb._sets.values():recordset._document=a
        try:
            with self.assertRaises(DENIED):vm.execute('Collection.OwnedAccumulationRows;')
            with self.assertRaises(DENIED):vm.execute('Set.Add();')
        finally:
            a._movements,b._movements=ca,cb;ca._document,cb._document=a,b
            for recordset in ca._sets.values():recordset._document=a
            for recordset in cb._sets.values():recordset._document=b
    def test_coherent_row_transfer_denied_by_origin(self):
        vm=self.prepared();vm.execute('Other=Documents.OwnedAccumulationDoc.CreateDocument();OtherSet=Other.RegisterRecords.OwnedAccumulationRows;')
        row=vm.variables['r'];old=row._owner;new=vm.variables['otherset']
        old._rows.remove(row);new._rows.append(row);row._owner=new
        try:
            with self.assertRaises(DENIED):vm.execute('R.Amount=9;')
        finally:new._rows.remove(row);old._rows.append(row);row._owner=old
    def test_forged_native_row_copy_not_admitted(self):
        from yadinassi.db.registers.accumulation_posting_values import BSLAccumulationRow
        vm=self.prepared();original=vm.variables['r'];copy=object.__new__(BSLAccumulationRow);copy.__dict__.update(original.__dict__)
        group=vm.variables['set'];group._rows.append(copy);vm.variables['forged']=copy
        try:
            with self.assertRaises(DENIED):vm.execute('Forged.Amount;')
            with self.assertRaises(DENIED):vm.execute('Set.Count();')
        finally:group._rows.remove(copy)
    def test_configuration_and_key_callbacks_not_invoked(self):
        vm=self.prepared();runtime=vm._documents._posting_runtime;doc=vm.variables['o'];effects=[]
        class Fake:
            @property
            def registers(self):effects.append('registers');return ()
            @property
            def document_id(self):effects.append('document_id');return None
        for obj,field in ((runtime,'configuration'),(doc,'_key')):
            old=getattr(obj,field);setattr(obj,field,Fake())
            try:
                with self.subTest(field=field),self.assertRaises(DENIED):vm.execute('Set.Count();')
            finally:setattr(obj,field,old)
        self.assertEqual(effects,[])
    def test_saved_get_late_reparenting_before_call(self):
        vm=self.prepared();vm.execute('Get=Set.Get;Other=Documents.OwnedAccumulationDoc.CreateDocument();')
        group=vm.variables['set'];old=group._document
        def touch():group._document=vm.variables['other'];return Decimal(0)
        vm.register_function('Touch',touch)
        try:
            with self.assertRaises(DENIED):vm.execute('Get(Touch());')
        finally:group._document=old
    def test_database_generation_change_revokes_buffer(self):
        vm=self.prepared();backend=self.context._backend;old=backend.configuration_generation
        backend.configuration_generation=old+1
        try:
            with self.assertRaises(DENIED):vm.execute('Set.Count();')
        finally:backend.configuration_generation=old
