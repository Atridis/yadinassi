"""Bounded reference TypeDescription API, not additional native codec evidence."""
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from yadinassi import Interpreter
from yadinassi.catalog_types import BSLCatalogReference, BSLCatalogType
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.document_types import BSLDocumentReference, BSLDocumentType
from yadinassi.json_processing import BSLJSONWriter, write_json
from yadinassi.query_sources import _snapshot
from yadinassi.serialization import value_to_string_internal
from yadinassi.structures import BSLStructure
from yadinassi.type_descriptions import (BSLTypeDescription, _reference_description,
                                         _query_nullable_description)
from yadinassi.type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
                                       BSLDateQualifiers, BSLBinaryDataQualifiers)
from yadinassi.type_values import type_of
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.value_storage import BSLValueStorage
from yadinassi.value_tables import BSLValueTable
from yadinassi.value_trees import BSLValueTree
from yadinassi.values import BSLArray, BSLType, NULL
from yadinassi.xml_values import xml_string
from test_document_configuration_xml import document_files

D = Decimal


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


class MetadataReferenceDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = object()
        self.catalog = BSLCatalogType(UUID(int=10), 'Products', self.snapshot)
        self.document = BSLDocumentType(UUID(int=20), 'Orders', self.snapshot)

    def kinds(self):
        return ((self.catalog, BSLCatalogReference), (self.document, BSLDocumentReference))

    def test_array_constructor_retains_exact_bound_type_and_five_field_shape(self):
        for kind, _ in self.kinds():
            source = array(kind)
            description = BSLTypeDescription(source)
            self.assertEqual(set(vars(description)), {'types', 'number_qualifiers', 'string_qualifiers',
                'date_qualifiers', 'binary_data_qualifiers'})
            self.assertIs(description.types[0], kind)
            self.assertIs(type_of(description), BSLType.TYPE_DESCRIPTION)
            source.items.clear()
            self.assertEqual(description.get_types().items, [kind])
            self.assertEqual(description.number_qualifiers.digits, D(0))
            self.assertEqual(description.string_qualifiers.length, D(0))
            self.assertEqual(str(description), kind.name)

    def test_types_returns_independent_arrays_without_cloning_type_identity(self):
        for kind, _ in self.kinds():
            description = _reference_description(kind)
            first, second = description.get_types(), description.get_types()
            self.assertIsNot(first, second)
            self.assertIs(first.items[0], kind)
            first.items[:] = [BSLType.STRING]
            self.assertIs(second.items[0], kind)
            self.assertIs(description.get_types().items[0], kind)

    def test_simple_copy_and_structural_hash_preserve_snapshot_identity(self):
        for kind, _ in self.kinds():
            description = _reference_description(kind)
            clone = BSLTypeDescription(description)
            same = type(kind)(kind.metadata_uuid, kind.name, kind.snapshot)
            foreign = type(kind)(kind.metadata_uuid, kind.name, object())
            self.assertIsNot(clone, description)
            self.assertIs(clone.types[0], kind)
            self.assertEqual(clone, _reference_description(same))
            self.assertEqual(hash(clone), hash(description))
            self.assertNotEqual(clone, _reference_description(foreign))
            self.assertNotEqual(clone, BSLTypeDescription('String'))

    def test_contains_type_matches_family_uuid_and_snapshot_not_spelling(self):
        for kind, _ in self.kinds():
            description = _reference_description(kind)
            same = type(kind)(kind.metadata_uuid, 'OtherPresentation', kind.snapshot)
            other_id = type(kind)(UUID(int=99), kind.name, kind.snapshot)
            foreign = type(kind)(kind.metadata_uuid, kind.name, object())
            self.assertTrue(description.contains_type(same))
            for other in (other_id, foreign, BSLType.STRING, BSLType.UNDEFINED,
                          type(kind)(kind.metadata_uuid, kind.name, kind.snapshot, 'manager')):
                self.assertFalse(description.contains_type(other))
            self.assertFalse(BSLTypeDescription('String').contains_type(kind))
        self.assertFalse(_reference_description(self.catalog).contains_type(self.document))

    def test_matching_empty_and_nonempty_reference_values_are_unchanged(self):
        def forbidden(*args): raise AssertionError('reference callback must not run')
        for kind, ref_class in self.kinds():
            description = _reference_description(kind)
            for identity in (UUID(int=0), UUID(int=42)):
                reference = ref_class(kind, identity, object(), forbidden, forbidden)
                self.assertIs(description.adjust_value(reference), reference)
                self.assertIs(reference.value_type, kind)

    def test_foreign_snapshot_and_other_metadata_reference_are_not_converted(self):
        for kind, ref_class in self.kinds():
            description = _reference_description(kind)
            for other in (type(kind)(kind.metadata_uuid, kind.name, object()),
                          type(kind)(UUID(int=99), kind.name, kind.snapshot)):
                value = ref_class(other, UUID(int=42))
                with self.assertRaisesRegex(TypeError, 'snapshot'): description.adjust_value(value)
                self.assertIs(value.value_type, other)
        with self.assertRaises(ValueError):
            _reference_description(self.catalog).adjust_value(BSLDocumentReference(self.document, UUID(int=42)))

    def test_defaults_and_unmeasured_reference_coercions_stay_closed(self):
        for kind, _ in self.kinds():
            description = _reference_description(kind)
            with self.assertRaises(ValueError): description.adjust_value()
            for value in (None, NULL, '', str(UUID(int=42)), BSLUUID(str(UUID(int=42))),
                          False, D(0), kind, BSLStructure(), array()):
                with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                    description.adjust_value(value)

    def test_reference_type_names_are_not_resolved_without_a_bound_registry(self):
        for name in ('CatalogRef.Products', 'СправочникСсылка.Products',
                     'DocumentRef.Orders', 'ДокументСсылка.Orders'):
            with self.assertRaises(ValueError): BSLTypeDescription(name)

    def test_reference_unions_duplicates_and_undefined_mixtures_are_closed(self):
        for kind, _ in self.kinds():
            for extra in (kind, BSLType.STRING, BSLType.UNDEFINED, BSLType.NULL,
                          self.catalog if kind is self.document else self.document):
                for values in ((kind, extra), (extra, kind)):
                    with self.assertRaises(ValueError): BSLTypeDescription(array(*values))

    def test_scalar_qualifier_overloads_are_not_inferred_for_references(self):
        for kind, _ in self.kinds():
            for args in ((None,), (BSLNumberQualifiers(),),
                         (None, BSLStringQualifiers()), (None, None, BSLDateQualifiers()),
                         (None, None, None, BSLBinaryDataQualifiers())):
                with self.assertRaises(ValueError): BSLTypeDescription(array(kind), *args)

    def test_reference_copy_add_remove_and_scalar_to_reference_extension_are_closed(self):
        for kind, _ in self.kinds():
            description = _reference_description(kind)
            for args in ((None,), (array(kind),), (None, array(kind)), ('String',)):
                with self.assertRaises(ValueError): BSLTypeDescription(description, *args)
            for args in ((array(kind),), (None, array(kind))):
                with self.assertRaises(ValueError): BSLTypeDescription(BSLTypeDescription(), *args)

    def test_nonreference_metadata_type_families_are_not_descriptors(self):
        for kind, _ in self.kinds():
            for family in ('manager', 'selection', 'object'):
                other = type(kind)(kind.metadata_uuid, kind.name, kind.snapshot, family)
                with self.assertRaises(ValueError): BSLTypeDescription(array(other))
                self.assertFalse(_reference_description(kind).contains_type(other))

    def test_description_and_qualifiers_remain_immutable(self):
        description = _reference_description(self.catalog)
        with self.assertRaises(FrozenInstanceError): description.types = ()
        with self.assertRaises(FrozenInstanceError): description.string_qualifiers.length = D(8)
        with self.assertRaises(ValueError): description.set_member('Types', array(BSLType.STRING))

    def test_metadata_type_hashing_never_calls_opaque_snapshot_hooks(self):
        class Hostile:
            def __hash__(self): raise AssertionError('snapshot hash')
            def __eq__(self, other): raise AssertionError('snapshot equality')
            def __getattribute__(self, name): raise AssertionError('snapshot reflection')
        snapshot = Hostile()
        for cls in (BSLCatalogType, BSLDocumentType):
            kind = cls(UUID(int=10), 'Name', snapshot)
            description = _reference_description(kind)
            self.assertTrue(description.contains_type(cls(UUID(int=10), 'Name', snapshot)))
            self.assertEqual(hash(description), hash(BSLTypeDescription(description)))
            self.assertFalse(description.contains_type(cls(UUID(int=10), 'Name', Hostile())))

    def test_hostile_types_subclasses_and_metaclasses_are_not_reflected(self):
        class Meta(type):
            def __eq__(self, other): raise AssertionError('class equality')
        class Hostile(metaclass=Meta):
            def __getattribute__(self, name): raise AssertionError('attribute hook')
            def __hash__(self): raise AssertionError('hash hook')
        class Derived(BSLCatalogType, metaclass=Meta):
            def __hash__(self): raise AssertionError('subclass hash')
        for value in (Hostile(), Derived(UUID(int=10), 'Name', object())):
            with self.assertRaises(TypeError): BSLTypeDescription(array(value))
            with self.assertRaises(TypeError): _reference_description(self.catalog).contains_type(value)
            with self.assertRaises(ValueError): _reference_description(self.catalog).adjust_value(value)

    def test_array_internal_state_and_budget_are_checked_before_iteration(self):
        class Hostile(list):
            def __iter__(self): raise AssertionError('iteration hook')
            def __len__(self): raise AssertionError('length hook')
        source = array(self.catalog); source.items = Hostile(source.items)
        with self.assertRaises(TypeError): BSLTypeDescription(source)
        source.items = [self.catalog]
        with patch('yadinassi.type_descriptions._MAX_TYPE_ARGUMENT', 0), self.assertRaises(ValueError):
            BSLTypeDescription(source)

    def test_malformed_reference_type_state_rejected_before_hash_or_comparison(self):
        class Hostile:
            def __hash__(self): raise AssertionError('hash hook')
            def __eq__(self, other): raise AssertionError('equality hook')
            def __str__(self): raise AssertionError('string hook')
        for cls in (BSLCatalogType, BSLDocumentType):
            for attribute in ('metadata_uuid', 'name', 'family'):
                kind = cls(UUID(int=10), 'Name', object())
                object.__setattr__(kind, attribute, Hostile())
                with self.assertRaises(ValueError): BSLTypeDescription(array(kind))
                with self.assertRaises(ValueError): _reference_description(self.catalog).contains_type(kind)

    def test_malformed_reference_descriptor_is_not_normalized_by_copy_or_methods(self):
        for attribute, value in (('number_qualifiers', object()), ('types', []),
                                  ('types', (self.catalog, BSLType.STRING))):
            description = _reference_description(self.catalog)
            object.__setattr__(description, attribute, value)
            for operation in (lambda: BSLTypeDescription(description), description.get_types,
                              lambda: description.contains_type(self.catalog),
                              lambda: description.adjust_value(BSLCatalogReference(self.catalog, UUID(int=1)))):
                with self.assertRaises((TypeError, ValueError)): operation()
        description = _reference_description(self.catalog)
        object.__setattr__(description.string_qualifiers, 'length', object())
        with self.assertRaises(ValueError): description.get_types()

    def test_nullable_query_factory_does_not_admit_reference_descriptors(self):
        for kind, _ in self.kinds():
            with self.assertRaises(ValueError): _query_nullable_description(_reference_description(kind))

    def test_generic_internal_codecs_and_value_storage_stay_closed(self):
        for kind, ref_class in self.kinds():
            description = _reference_description(kind)
            reference = ref_class(kind, UUID(int=42))
            for value in (description, array(description), BSLStructure('Type', description), kind, reference):
                with self.assertRaises((TypeError, ValueError)): value_to_string_internal(value)
                with self.assertRaises((TypeError, ValueError)): BSLValueStorage(value)

    def test_json_and_xml_do_not_gain_metadata_descriptor_codecs(self):
        for kind, _ in self.kinds():
            description = _reference_description(kind)
            with self.assertRaises(TypeError): xml_string(description)
            writer = BSLJSONWriter(); writer.set_string()
            with self.assertRaises((TypeError, ValueError)): write_json(writer, description)

    def test_reference_columns_cannot_synthesize_defaults_or_publish_partial_schema(self):
        for owner in (BSLValueTable(), BSLValueTree()):
            for kind, _ in self.kinds():
                with self.assertRaises(ValueError): owner.columns.add('Ref', _reference_description(kind))
                self.assertEqual(owner.columns.items, [])

    def test_host_bound_reference_table_schema_stays_closed_for_storage_and_queries(self):
        for kind, ref_class in self.kinds():
            table = BSLValueTable(); column = table.columns.add('Ref')
            row = table.add(); reference = ref_class(kind, UUID(int=42)); row.set_member('Ref', reference)
            # Host-injected schemas are not a backdoor around scalar admission.
            column.value_type = _reference_description(kind)
            with self.assertRaises((TypeError, ValueError)): BSLValueStorage(table)
            with self.assertRaises((TypeError, ValueError)): value_to_string_internal(table)
            with self.assertRaises(TypeError): _snapshot(table, [0])
            self.assertIs(row.get_member('Ref'), reference)


class BoundMetadataReferenceDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.context = SQLiteDBContext.create(Path(self.temp.name) / 'owned.sqlite',
                                             import_configuration(document_files()))
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)

    def test_runtime_array_type_constructor_and_bilingual_methods(self):
        for name, ref in (('CatalogRef.Categories', 'Catalogs.Categories.EmptyRef()'),
                          ('DocumentRef.Orders', 'Documents.Orders.EmptyRef()')):
            self.vm.execute(f'A=New Array;K=Type("{name}");A.Add(K);D=New TypeDescription(A);'
                            f'R={ref};V=D.ПривестиЗначение(R);C=Новый ОписаниеТипов(D);')
            self.assertIs(self.vm.variables['v'], self.vm.variables['r'])
            self.assertTrue(self.vm.execute('D.ContainsType(K) And C.СодержитТип(ТипЗнч(R))'))
            self.assertIs(self.vm.execute('D.Types()[0]'), self.vm.variables['k'])
            self.vm.execute('A.Clear();B=D.Типы();B.Clear();')
            self.assertEqual(self.vm.execute('D.Types().Count()'), D(1))

    def test_metadata_factory_uses_current_manager_type_for_standard_ref(self):
        for manager in (self.vm._catalogs.get_index('Categories'), self.vm._documents.get_index('Orders')):
            description = _reference_description(manager._value_type)
            reference = manager.empty_ref()
            self.assertIs(description.get_types().items[0], type_of(reference))
            self.assertIs(description.adjust_value(reference), reference)
            self.assertIs(reference.metadata, manager._metadata)

    def test_same_database_other_interpreter_snapshot_remains_foreign(self):
        other = Interpreter(database_context=self.context)
        for expression in ('Catalogs.Categories.EmptyRef()', 'Documents.Orders.EmptyRef()'):
            own = self.vm.execute(expression); foreign = other.execute(expression)
            description = _reference_description(own.value_type)
            self.assertFalse(description.contains_type(foreign.value_type))
            with self.assertRaises(TypeError): description.adjust_value(foreign)
            self.assertIs(description.adjust_value(own), own)

    def test_adjustment_does_not_read_records_or_replace_bound_callbacks(self):
        manager = self.vm._catalogs.get_index('Categories')
        reference = manager.get_ref(BSLUUID(str(UUID(int=42))))
        description = _reference_description(manager._value_type)
        with patch.object(manager, '_read', side_effect=AssertionError('record read')):
            self.assertIs(description.adjust_value(reference), reference)
        self.assertIs(reference.metadata, manager._metadata)
        self.assertIs(reference.read_member.__self__, manager)
        self.assertIs(reference.get_object.__self__, manager)

    def test_catalog_field_foreign_reference_guard_is_not_weakened(self):
        own = self.vm.execute('Catalogs.Categories.EmptyRef()')
        other = Interpreter(database_context=self.context)
        foreign = other.execute('Catalogs.Categories.EmptyRef()')
        description = _reference_description(own.value_type)
        target = self.vm.execute('Catalogs.Products.CreateItem()')
        target.set_member('Category', description.adjust_value(own))
        with self.assertRaises(TypeError): description.adjust_value(foreign)
        with self.assertRaises(TypeError): target.set_member('Category', foreign)
        self.assertIs(target.get_member('Category'), own)

    def test_reference_query_projection_still_cannot_unload_to_typed_table(self):
        self.vm.execute('Q=New Query("SELECT Ref FROM Catalog.Products");Result=Q.Execute();')
        with self.assertRaises(ValueError): self.vm.variables['result'].unload()

    def test_imported_reference_description_binds_shared_family_snapshot(self):
        path = Path(self.temp.name) / 'Helper.bsl'
        path.write_text('Function Describe() Export A=New Array;A.Add(Type("CatalogRef.Categories"));'
                        'Return New TypeDescription(A);EndFunction', encoding='utf-8')
        self.vm.execute('// #Import Helper.bsl\nD=Helper.Describe();', str(path.with_name('main.bsl')))
        child = self.vm.imports['helper'].interpreter
        description = self.vm.variables['d']
        own = child.execute('Catalogs.Categories.EmptyRef()')
        parent = self.vm.execute('Catalogs.Categories.EmptyRef()')
        self.assertIs(description.types[0], own.value_type)
        self.assertIs(description.adjust_value(own), own)
        self.assertIs(description.adjust_value(parent), parent)


if __name__ == '__main__': unittest.main()
