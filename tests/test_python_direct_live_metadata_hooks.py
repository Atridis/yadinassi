"""Independent metadata publication, callback and lifetime guards."""
import unittest
from unittest.mock import patch
from yadinassi.configuration import metadata
from yadinassi.types import type_qualifiers
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
import test_python_direct_live_metadata_ownership as fixture

class LiveMetadataHookTests(unittest.TestCase):
    setUp=fixture.LiveMetadataOwnershipTests.setUp
    prepared=fixture.LiveMetadataOwnershipTests.prepared
    def test_hash_guard_precedes_registry_lookup(self):
        vm=self.prepared();effects=[]
        with patch.object(metadata.BSLAttributeMetadata,'__hash__',lambda self:effects.append('hash') or 1):
            with self.assertRaises(fixture.DENIED):vm.execute('A.Name;')
        self.assertEqual(effects,[])
    def test_root_instance_helper_denied(self):
        effects=[];root=self.vm._metadata
        root.find_by_full_name=lambda *args:effects.append('root')
        try:
            with self.assertRaises(fixture.DENIED):self.vm.execute('Metadata.FindByFullName("Catalog.Products");')
        finally:del root.find_by_full_name
        self.assertEqual(effects,[])
    def test_lazy_qualifier_factory_guard(self):
        vm=self.prepared();effects=[]
        with patch.object(type_qualifiers.BSLStringQualifiers,'__init__',lambda *a,**kw:effects.append('factory')):
            with self.assertRaises(fixture.DENIED):vm.execute('A.Type;')
        self.assertEqual(effects,[])
        self.assertIsNone(vm.variables['a']._description)
    def test_schema_slot_mutation_cannot_reseal(self):
        vm=self.prepared();field=vm.variables['a']._field;old=field.kind
        object.__setattr__(field,'kind','boolean')
        try:
            with self.assertRaises(fixture.DENIED):vm.execute('A.Type;')
            self.assertIsNone(vm.variables['a']._description)
        finally:object.__setattr__(field,'kind',old)
    def test_captured_private_method_is_not_capability(self):
        self.vm.variables['foreign']=HostFunction('Private',self.vm._metadata._ensure_source_info)
        with self.assertRaises(fixture.DENIED):self.vm.execute('Foreign();')
        self.assertIsNone(self.vm._metadata._identity)
    def test_saved_public_method_rechecks_metadata(self):
        vm=self.prepared();vm.execute('Saved=A.FullName;')
        self.assertEqual(vm.execute('Saved();'),'Справочник.Products.Реквизит.Text')
        saved=vm.variables['saved'];old=saved.reference_parameters;saved.reference_parameters=frozenset({0})
        try:
            with self.assertRaises(fixture.DENIED):vm.execute('Saved();')
        finally:saved.reference_parameters=old
    def test_type_slot_descriptor_denied_before_callback(self):
        from yadinassi.db.catalog.catalog_types import BSLCatalogType
        vm=self.prepared();vm.execute('T=Type("CatalogRef.Products");');effects=[]
        with patch.object(BSLCatalogType,'snapshot',property(lambda self:effects.append('type'))):
            with self.assertRaises(fixture.DENIED):vm.execute('Metadata.FindByType(T);')
        self.assertEqual(effects,[])
    def test_reference_description_array_factory_denied(self):
        from yadinassi.types.values import BSLArray
        self.vm.execute('A=Metadata.Catalogs.Products.Attributes.Category;');effects=[]
        with patch.object(BSLArray,'__init__',lambda *a,**kw:effects.append('array')):
            with self.assertRaises(fixture.DENIED):self.vm.execute('A.Type;')
        self.assertEqual(effects,[])
        self.assertIsNone(self.vm.variables['a']._description)
    def test_qualifier_enum_binding_denied(self):
        vm=self.prepared();effects=[]
        class Trap:
            @property
            def VARIABLE(self):effects.append('enum')
        with patch.object(type_qualifiers,'BSLAllowedLength',Trap()):
            with self.assertRaises(fixture.DENIED):vm.execute('A.Type;')
        self.assertEqual(effects,[])
        self.assertIsNone(vm.variables['a']._description)
