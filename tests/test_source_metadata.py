"""Source metadata reflects XML declarations, never database/runtime grants."""
from decimal import Decimal
import unittest
from uuid import uuid5, NAMESPACE_URL

from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_metadata import SourceMetadataRoot
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLError


def xml(family, name, *, properties='', children=''):
    return ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><' + family
            + ' uuid="' + str(uuid5(NAMESPACE_URL, family + '/' + name)) + '"><Properties><Name>'
            + name + '</Name>' + properties + '</Properties><ChildObjects>' + children
            + '</ChildObjects></' + family + '></MetaDataObject>').encode()


def files():
    return {
        'Configuration.xml': xml('Configuration', 'Demo', properties='<Version>1.0</Version>',
            children='<Subsystem>Features</Subsystem><Subsystem>Second</Subsystem><CommonModule>Helpers</CommonModule>'),
        'Subsystems/Features.xml': xml('Subsystem', 'Features', properties='<IncludeInCommandInterface>false</IncludeInCommandInterface>',
            children='<Subsystem>Child</Subsystem>'),
        'Subsystems/Second.xml': xml('Subsystem', 'Second', properties='<IncludeInCommandInterface>true</IncludeInCommandInterface>'),
        'Subsystems/Features/Subsystems/Child.xml': xml('Subsystem', 'Child', properties='<IncludeInCommandInterface>false</IncludeInCommandInterface>'),
        'CommonModules/Helpers.xml': xml('CommonModule', 'Helpers', properties='<Server>true</Server><Privileged>false</Privileged>'),
    }


class SourceMetadataTests(unittest.TestCase):
    def root(self, mapping=None):
        return SourceMetadataRoot(import_source(files() if mapping is None else mapping))

    def test_actual_root_name_and_version(self):
        root = self.root()
        self.assertEqual(root.get_member('Name'), 'Demo')
        self.assertEqual(root.get_member('Версия'), '1.0')

    def test_collection_named_find_and_count(self):
        collection = self.root().get_member('Subsystems')
        self.assertEqual(collection.count(), Decimal(2))
        self.assertIs(collection.find('features'), collection.get_member('Features'))
        self.assertIsNone(collection.find('Absent'))

    def test_declared_order_not_sorted_inventory_order(self):
        mapping = files()
        mapping['Configuration.xml'] = mapping['Configuration.xml'].replace(
            b'<Subsystem>Features</Subsystem><Subsystem>Second</Subsystem>',
            b'<Subsystem>Second</Subsystem><Subsystem>Features</Subsystem>')
        self.assertEqual([item.get_member('Name') for item in self.root(mapping).get_member('Subsystems')], ['Second', 'Features'])

    def test_nested_subsystems_do_not_flatten(self):
        root = self.root()
        parent = root.get_member('Subsystems').find('Features')
        self.assertEqual(parent.get_member('Subsystems').count(), Decimal(1))
        self.assertEqual(parent.get_member('Subsystems').find('Child').get_member('Имя'), 'Child')
        self.assertIsNone(root.get_member('Subsystems').find('Child'))

    def test_boolean_properties_from_source_not_defaults(self):
        root = self.root()
        collection = root.get_member('Subsystems')
        self.assertFalse(collection.find('Features').get_member('IncludeInCommandInterface'))
        self.assertTrue(collection.find('Second').get_member('ВключатьВКомандныйИнтерфейс'))
        helper = root.get_member('CommonModules').find('Helpers')
        self.assertTrue(helper.get_member('Server'))
        with self.assertRaisesRegex(ValueError, 'absent'):
            helper.get_member('ClientManagedApplication')

    def test_read_only_root_object_and_collection(self):
        root = self.root()
        collection = root.get_member('CommonModules')
        with self.assertRaises(ValueError): root.set_member('Name', 'Other')
        with self.assertRaises(ValueError): collection.set_index('Helpers', None)
        with self.assertRaises(ValueError): collection.find('Helpers').set_member('Server', False)

    def test_missing_declared_file_is_not_silent_empty_collection(self):
        mapping = files(); del mapping['Subsystems/Second.xml']
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.root(mapping).get_member('Subsystems')

    def test_orphan_file_is_not_claimed_declared_metadata(self):
        mapping = files(); mapping['Subsystems/Orphan.xml'] = xml('Subsystem', 'Orphan')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.root(mapping).get_member('Subsystems')

    def test_unknown_properties_and_embedded_families_fail(self):
        root = self.root()
        with self.assertRaises(ValueError): root.get_member('FutureFamily')
        with self.assertRaises(ValueError): root.get_member('Subsystems').find('Features').get_member('Content')
        with self.assertRaises(ValueError): root.get_member('CommonModules').find('Helpers').get_member('Subsystems')

    def test_find_by_full_name_and_existing_russian_fullname_convention(self):
        root = self.root()
        child = root.find_by_full_name('Subsystem.Features.Subsystem.Child')
        self.assertIs(child, root.find_by_full_name('Подсистема.Features.Подсистема.Child'))
        self.assertEqual(child.full_name(), 'Подсистема.Features.Подсистема.Child')
        self.assertIsNone(root.find_by_full_name('Subsystem.Missing'))

    def test_empty_family_is_source_backed(self):
        self.assertEqual(self.root().get_member('Catalogs').count(), Decimal(0))

    def test_bsl_iteration_and_index_use_existing_metadata_collection(self):
        vm = Interpreter(output=lambda _: None)
        self.addCleanup(vm.close)
        vm.variables['md'] = self.root()
        self.assertEqual(vm.execute('n=0; For Each s In md.Subsystems Do n=n+1; EndDo; n'), Decimal(2))
        self.assertEqual(vm.execute('md.CommonModules["Helpers"].Name'), 'Helpers')
        self.assertEqual(vm.execute('md.Subsystems.Get(0).Subsystems.Count()'), Decimal(1))

    def test_xml_boolean_requires_boolean_not_truthy_string(self):
        mapping = files(); mapping['Subsystems/Features.xml'] = mapping['Subsystems/Features.xml'].replace(b'>false<', b'>yes<')
        with self.assertRaisesRegex(ValueError, 'Boolean'):
            self.root(mapping).get_member('Subsystems').find('Features').get_member('IncludeInCommandInterface')

    def test_method_identity_stable_for_repeated_lookup(self):
        root = self.root()
        self.assertIs(root.get_member('Subsystems').find('Features'), root.find_by_full_name('Subsystem.Features'))

    def test_find_unsupported_family_is_not_false_absence(self):
        mapping = files()
        mapping['ChartsOfCharacteristicTypes/Features.xml'] = xml('ChartOfCharacteristicType', 'Features')
        root = self.root(mapping)
        with self.assertRaisesRegex(ValueError, 'unsupported source metadata family'):
            root.find_by_full_name('ChartOfCharacteristicType.Features')
        self.assertIsNone(root.find_by_full_name('Subsystem.Missing'))
