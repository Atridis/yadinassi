"""Host issuer/profile/lifetime contracts, not inferred native conversion policy."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_inventory_enums import import_inventory_enum_configuration,PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLRuntimeError
from test_configuration_inventory_enums import source

ROOT=Path(__file__).resolve().parents[1]

class InventoryEnumRuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'owned.sqlite'
        self.config=import_inventory_enum_configuration(source(),inventory_runtime=PROFILE)
        self.context=SQLiteDBContext.create_inventory_enum(self.path,self.config)
        self.addCleanup(self.context.close)
        self.vm=Interpreter(database_context=self.context);self.addCleanup(self.vm.close)
        self.ref=self.vm.execute('Enums.Units.Piece')
        self.units=next(e.identity for e in self.config.enumerations if e.name=='Units')
        from yadinassi.inventory_enum_runtime import binding
        self.bridge=binding(self.vm._metadata)

    def test_root_namespace_and_typed_empty(self):
        self.assertTrue(self.vm.execute('TypeOf(Enums.Units.EmptyRef())=Type("EnumRef.Units")'))
        self.assertIs(self.vm.execute('Enums.Units.Piece'),self.ref)

    def test_catalog_default_and_roundtrip_canonical_identity(self):
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="P";C.Unit=Enums.Units.Piece;C.Write();')
        self.assertIs(self.vm.execute('C.Ref.GetObject().Unit'),self.ref)
        self.assertIs(self.vm.execute('Catalogs.Products.CreateItem().Unit'),self.vm.execute('Enums.Units.EmptyRef()'))

    def test_document_header_and_line_roundtrip(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument();D.Number="R";D.Date=Date(2024,2,10);D.State=Enums.States.Approved;L=D.Lines.Add();L.Unit=Enums.Units.Piece;D.Write();')
        self.assertIs(self.vm.execute('D.Ref.GetObject().State'),self.vm.execute('Enums.States.Approved'))
        self.assertIs(self.vm.execute('D.Ref.State'),self.vm.execute('Enums.States.Approved'))
        self.assertIs(self.vm.execute('D.Ref.GetObject().Lines[0].Unit'),self.ref)

    def test_document_point_read_uses_one_captured_snapshot(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument();D.Number="R";D.Date=Date(2024,2,10);D.State=Enums.States.Approved;D.Write();')
        # No metadata lookup inside this count: exercise the exact getter.
        ref=self.vm.execute('D.Ref');backend=self.context.backend
        with mock.patch.object(backend,'begin_read',wraps=backend.begin_read) as opened:
            self.assertIs(ref.get_member('State'),self.vm._metadata._enumerations.get_member('States').get_member('Approved'))
        self.assertEqual(opened.call_count,1)
        self.assertIsNone(backend._active)

    def test_captured_snapshot_is_lexical_and_not_another_roots_authority(self):
        from yadinassi.inventory_enum_runtime import binding,read_snapshot
        backend=self.context.backend
        with closing(Interpreter(database_context=self.context)) as other:
            foreign=binding(other._metadata)
            view=backend.begin_document_read()
            try:
                with read_snapshot(self.vm._metadata,view):
                    self.assertEqual(self.bridge.key(self.ref,self.units).enum_id,self.units)
                    with self.assertRaises(BackendError):foreign.value_type(self.units)
                # A live backend._active alone is never a captured witness.
                with self.assertRaises(BackendError):self.bridge.value_type(self.units)
                with read_snapshot(self.vm._metadata,view):
                    view.close()
                    with self.assertRaises(BackendError):self.bridge.value_type(self.units)
            finally:view.close()
        self.assertEqual(self.bridge.key(self.ref,self.units).enum_id,self.units)

    def test_failed_reopen_does_not_open_family_or_old_binding(self):
        self.vm.close()
        def failed_bind():
            self.assertTrue(self.vm._family_closed)
            raise BackendError('schema_changed')
        with mock.patch.object(self.vm,'_bind_schema_scope',side_effect=failed_bind):
            with self.assertRaises(BackendError):self.vm._require_family()
        self.assertTrue(self.vm._family_closed)
        with self.assertRaises(BackendError):self.bridge.value_type(self.units)
        self.assertIsNot(self.vm.execute('Enums.Units.Piece'),self.ref)

    def test_measured_adjustment_across_catalog_header_line_and_movements(self):
        from decimal import Decimal
        for expression in ('"Piece"','1','Undefined'):
            for assignment,read in (
                ('C=Catalogs.Products.CreateItem();C.Unit=', 'C.Unit'),
                ('D=Documents.Receipt.CreateDocument();D.State=', 'D.State'),
                ('D=Documents.Receipt.CreateDocument();L=D.Lines.Add();L.Unit=', 'L.Unit'),
                ('D=Documents.Receipt.CreateDocument();R=D.RegisterRecords.Stock.Add();R.Unit=', 'R.Unit'),
                ('D=Documents.Receipt.CreateDocument();R=D.RegisterRecords.Stock.Add();R.State=', 'R.State')):
                self.assertTrue(self.vm.execute(assignment+expression+';'+read+'.IsEmpty()'))
        self.assertTrue(self.vm.execute('C=Catalogs.Products.CreateItem();C.Unit=Enums.States.Draft;C.Unit.IsEmpty()'))

    def test_movement_buffer_stores_canonical_issuer(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument();R=D.RegisterRecords.Stock.Add();R.Unit=Enums.Units.Piece;')
        self.assertIs(self.vm.execute('R.Unit'),self.ref)

    def test_metadata_field_type_uses_same_issuer(self):
        self.assertTrue(self.vm.execute('Metadata.Catalogs.Products.Attributes.Unit.Type.ContainsType(Type("EnumRef.Units"))'))
        self.assertTrue(self.vm.execute('Metadata.Documents.Receipt.Attributes.State.Type.ContainsType(Type("EnumRef.States"))'))

    def test_independent_roots_are_not_same_issuer(self):
        with closing(Interpreter(database_context=self.context)) as other:
            foreign=other.execute('Enums.Units.Piece')
            self.assertIsNot(foreign,self.ref)
            with self.assertRaises(BackendError):self.bridge.key(foreign,self.units)

    def test_child_family_reuses_namespace(self):
        with closing(Interpreter(database_context=self.context,family_owner=self.vm)) as child:
            self.assertIs(child._metadata,self.vm._metadata)
            self.assertIs(child.execute('Enums.Units.Piece'),self.ref)

    def test_fabricated_equal_reference_is_not_storage_authority(self):
        with self.assertRaises(BackendError):self.bridge.key(replace(self.ref),self.units)

    def test_altered_reference_metadata_is_not_storage_authority(self):
        with self.assertRaises(BackendError):self.bridge.key(replace(self.ref,metadata=object()),self.units)

    def test_cloned_equal_type_is_not_storage_authority(self):
        with self.assertRaises(BackendError):self.bridge.key(replace(self.ref,value_type=replace(self.ref.value_type)),self.units)

    def test_root_close_fences_old_binding(self):
        self.vm.close()
        with self.assertRaises(BackendError):self.bridge.key(self.ref,self.units)

    def test_root_restart_uses_new_namespace(self):
        self.vm.close();new=self.vm.execute('Enums.Units.Piece')
        self.assertIsNot(new,self.ref)
        with self.assertRaises(BackendError):self.bridge.key(self.ref,self.units)

    def test_context_close_fences_old_binding(self):
        self.context.close()
        with self.assertRaises(BackendError):self.bridge.value_type(self.units)

    def test_current_transaction_borrow_does_not_end_owner(self):
        self.vm.execute('BeginTransaction(); C=Catalogs.Products.CreateItem();C.Code="P";C.Unit=Enums.Units.Piece;C.Write(); Inside=TransactionActive();RollbackTransaction();')
        self.assertTrue(self.vm.execute('Inside'))
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("P").IsEmpty()'))

    def test_other_root_cannot_borrow_current_transaction(self):
        from contextvars import Context
        from yadinassi.values import HostFunction
        from yadinassi.inventory_enum_runtime import binding
        calls=[]
        with closing(Interpreter(database_context=self.context)) as other:
            foreign=binding(other._metadata)
            def probe():
                # A nested synchronous callback intentionally inherits the
                # existing execution token. Model a genuinely separate root
                # execution, rather than relying on a second VM's identity.
                with self.assertRaises(BackendError):
                    Context().run(foreign.value_type,self.units)
                with self.assertRaises((BackendError,BSLRuntimeError)):
                    Context().run(other.execute,'C=Catalogs.Products.CreateItem();C.Unit=Enums.Units.Piece;')
                calls.append(True)
            self.vm.functions['probeother']=HostFunction('ProbeOther',probe)
            self.vm.execute('BeginTransaction();ProbeOther();Inside=TransactionActive();RollbackTransaction();')
        self.assertEqual(calls,[True])
        self.assertTrue(self.vm.execute('Inside'))

    def test_forged_namespace_replacement_fences_binding(self):
        self.vm._metadata._enumerations=object()
        with self.assertRaises(BackendError):self.bridge.value_type(self.units)

    def test_unbound_standalone_has_no_storage_enums(self):
        with closing(Interpreter()) as vm:
            self.assertIsNone(vm._metadata._enum_storage)
            with self.assertRaises(BSLRuntimeError):vm.execute('Enums.Units.Piece')

    def test_wrong_enum_never_becomes_unit_key(self):
        with self.assertRaises(BackendError):self.bridge.key(self.vm.execute('Enums.States.Draft'),self.units)

    def test_metadata_cached_type_still_checks_lifetime(self):
        field=self.vm.execute('Metadata.Catalogs.Products.Attributes.Unit')
        field.get_member('Type');self.vm.close()
        with self.assertRaises(BackendError):field.get_member('Type')

    def test_reopened_database_uses_own_canonical_namespace(self):
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="P";C.Unit=Enums.Units.Piece;C.Write();')
        with closing(SQLiteDBContext(self.path)) as context,closing(Interpreter(database_context=context)) as vm:
            value=vm.execute('Catalogs.Products.FindByCode("P").GetObject().Unit')
            self.assertIs(value,vm.execute('Enums.Units.Piece'))
            self.assertIsNot(value,self.ref)
