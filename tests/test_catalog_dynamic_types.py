"""Local value-model tests; native catalog scenario acceptance is separate."""
from dataclasses import FrozenInstanceError
import unittest
from uuid import UUID
from types import SimpleNamespace

from yadinassi import Interpreter
from yadinassi.catalog_types import BSLCatalogReference, BSLCatalogType
from yadinassi.serialization import value_to_string_internal
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_values import type_of
from yadinassi.value_checks import value_is_filled
from yadinassi.values import BSLArray, BSLType, equal, to_string


class CatalogDynamicTypesTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = object()
        self.kind = BSLCatalogType(UUID(int=10), 'Товары', self.snapshot)
        self.ref = BSLCatalogReference(self.kind, UUID(int=20))

    def test_type_and_presentation(self):
        self.assertIs(type_of(self.ref), self.kind)
        self.assertIs(type_of(self.kind), BSLType.TYPE)
        self.assertEqual(to_string(self.kind), 'СправочникСсылка.Товары')
        self.assertTrue(equal(self.kind, BSLCatalogType(UUID(int=10), 'Товары', self.snapshot)))
        self.assertFalse(equal(self.kind, BSLCatalogType(UUID(int=11), 'Другой', self.snapshot)))

    def test_catalog_families_are_distinct(self):
        kinds = [BSLCatalogType(UUID(int=10), 'Name', self.snapshot, family)
                 for family in ('ref', 'manager', 'selection')]
        self.assertEqual(len(set(kinds)), 3)
        self.assertEqual([str(k) for k in kinds],
                         ['СправочникСсылка.Name', 'СправочникМенеджер.Name',
                          'СправочникВыборка.Name'])
        for kind in kinds:
            self.assertIs(type_of(kind), BSLType.TYPE)
            with self.assertRaisesRegex(ValueError, 'справочников'):
                value_to_string_internal(kind)
        for kind in kinds[1:]:
            with self.assertRaisesRegex(TypeError, 'reference type family'):
                BSLCatalogReference(kind, UUID(int=20))
        with self.assertRaisesRegex(ValueError, 'family'):
            BSLCatalogType(UUID(int=10), 'Name', self.snapshot, 'object')

    def test_manager_and_selection_type_identity(self):
        from yadinassi.catalogs import BSLCatalogManager, BSLCatalogSelection
        metadata = SimpleNamespace(_metadata_uuid=str(UUID(int=10)), _name='Name')
        catalogs = SimpleNamespace(_metadata=self.snapshot)
        manager = BSLCatalogManager(catalogs, metadata)
        cursor = BSLCatalogSelection(manager, SimpleNamespace(rows=()))
        self.assertIs(type_of(manager), manager._manager_type)
        self.assertIs(type_of(cursor), manager._selection_type)
        self.assertIs(type_of(manager.empty_ref()), manager._value_type)
        self.assertEqual(len({type_of(manager), type_of(cursor), type_of(manager.empty_ref())}), 3)

    def test_references_same_uuid_different_catalogs(self):
        other = BSLCatalogType(UUID(int=11), 'Другой', self.snapshot)
        self.assertTrue(equal(self.ref, BSLCatalogReference(self.kind, UUID(int=20))))
        self.assertFalse(equal(self.ref, BSLCatalogReference(other, UUID(int=20))))
        self.assertFalse(equal(self.ref, self.ref.unique_identifier()))
        self.assertEqual(hash(self.ref), hash(BSLCatalogReference(self.kind, UUID(int=20))))

    def test_snapshot_identity_not_host_equality(self):
        class Hostile:
            def __eq__(self, other):
                raise AssertionError('must not compare host snapshot')
            def __hash__(self):
                raise AssertionError('must not hash host snapshot')
        first, second = Hostile(), Hostile()
        a = BSLCatalogType(UUID(int=10), 'Name', first)
        b = BSLCatalogType(UUID(int=10), 'Name', second)
        self.assertNotEqual(a, b)
        self.assertEqual(a, BSLCatalogType(UUID(int=10), 'Name', first))
        hash(a)

    def test_empty_and_filled(self):
        empty = BSLCatalogReference(self.kind, UUID(int=0))
        self.assertTrue(empty.is_empty())
        self.assertFalse(value_is_filled(empty))
        self.assertTrue(value_is_filled(self.ref))
        self.assertEqual(str(empty), '')
        self.assertEqual(self.ref.unique_identifier().text, str(UUID(int=20)))

    def test_immutable(self):
        for obj, field, value in ((self.ref, 'reference_uuid', UUID(int=21)),
                                  (self.kind, 'name', 'Changed')):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, field, value)
        with self.assertRaisesRegex(ValueError, 'недоступно'):
            self.ref.set_member('Ref', self.ref)

    def test_metadata_and_field_callback_do_not_change_identity(self):
        metadata = object()
        seen = []
        def read(ref, name):
            seen.append((ref.reference_uuid, name))
            return 'Display'
        ref = BSLCatalogReference(self.kind, UUID(int=20), metadata, read)
        self.assertTrue(equal(ref, self.ref))
        self.assertIs(ref.get_metadata(), metadata)
        self.assertIs(ref.get_member('Ref'), ref)
        self.assertEqual(ref.get_member('Description'), 'Display')
        self.assertEqual(str(ref), 'Display')
        self.assertEqual(len(seen), 2)
        with self.assertRaisesRegex(ValueError, 'presentation'):
            str(self.ref)

    def test_interpreter_value_operations(self):
        vm = Interpreter()
        vm.set_variable('ref', self.ref)
        vm.set_variable('kind', self.kind)
        self.assertTrue(vm.execute('(TypeOf(ref) = kind)'))
        self.assertTrue(vm.execute('(TypeOf(kind) = Type("Type"))'))
        self.assertTrue(vm.execute('ValueIsFilled(ref)'))
        self.assertFalse(vm.execute('ref.IsEmpty()'))
        self.assertEqual(vm.execute('String(ref.УникальныйИдентификатор())'), str(UUID(int=20)))
        self.assertEqual(vm.execute('String(ref.UUID())'), str(UUID(int=20)))

    def test_explicit_unsupported_consumers(self):
        for value in (self.ref, self.kind):
            with self.assertRaisesRegex(ValueError, 'справочников'):
                value_to_string_internal(value)
            nested = BSLArray()
            nested.items = [value]
            with self.assertRaisesRegex(ValueError, 'справочников'):
                value_to_string_internal(nested)
        with self.assertRaisesRegex(ValueError, 'справочника'):
            BSLTypeDescription('String').adjust_value(self.ref)
        types = BSLArray()
        types.items = [self.kind]
        with self.assertRaisesRegex(ValueError, 'ссылки справочника'):
            BSLTypeDescription(types)
        with self.assertRaisesRegex(ValueError, 'ссылки справочника'):
            BSLTypeDescription('String').contains_type(self.kind)


if __name__ == '__main__':
    unittest.main()
