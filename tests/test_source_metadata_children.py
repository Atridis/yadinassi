"""Generic source child graph without executable/storage capability grants."""
import unittest
from decimal import Decimal
from test_source_metadata import xml
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_metadata import SourceMetadataRoot, _FAMILIES


def embedded(family, name, **kwargs):
    import xml.etree.ElementTree as ET
    return ET.tostring(ET.fromstring(xml(family,name,**kwargs))[0],encoding='unicode')


class SourceMetadataChildrenTests(unittest.TestCase):
    def root(self, children='', family='Catalog', folder='Catalogs'):
        return SourceMetadataRoot(import_source({
            'Configuration.xml':xml('Configuration','Demo',children='<'+family+'>Items</'+family+'>'),
            folder+'/Items.xml':xml(family,'Items',children=children)}))

    def test_attributes_real_identity_and_order(self):
        root=self.root(embedded('Attribute','Second')+embedded('Attribute','First'))
        collection=root.find_by_full_name('Catalog.Items').get_member('Attributes')
        self.assertEqual([x._name for x in collection],['Second','First'])
        self.assertIs(collection.get(Decimal(0)),root.find_by_full_name('Справочник.Items.Реквизит.Second'))
        self.assertEqual(collection.get(Decimal(0)).full_name(),'Справочник.Items.Реквизит.Second')

    def test_nested_tabular_attributes(self):
        root=self.root(embedded('TabularSection','Lines',children=embedded('Attribute','Amount')))
        field=root.find_by_full_name('Catalog.Items.TabularSection.Lines.Attribute.Amount')
        self.assertEqual(field.full_name(),'Справочник.Items.ТабличнаяЧасть.Lines.Реквизит.Amount')
        self.assertEqual(root.find_by_full_name('Catalog.Items').get_member('Attributes').count(),0)

    def test_register_dimensions_resources_and_attributes(self):
        root=self.root(embedded('Dimension','Item')+embedded('Resource','Amount')+embedded('Attribute','Note'),
                       'AccumulationRegister','AccumulationRegisters')
        for family,name in [('Dimension','Item'),('Resource','Amount'),('Attribute','Note')]:
            self.assertEqual(root.find_by_full_name('AccumulationRegister.Items.'+family+'.'+name)._name,name)

    def test_enum_values_are_source_metadata_not_value_objects(self):
        root=self.root(embedded('EnumValue','First'),'Enum','Enums')
        self.assertEqual(root.find_by_full_name('Enum.Items.EnumValue.First')._name,'First')

    def test_commands_source_only(self):
        root=self.root(embedded('Command','Open'))
        self.assertEqual(root.find_by_full_name('Catalog.Items.Command.Open')._name,'Open')

    def test_all_top_level_family_names(self):
        for family,folder,ru,label in _FAMILIES:
            with self.subTest(family=family):
                root=self.root(family=family,folder=folder)
                self.assertIs(root.get_member(folder).find('Items'),root.find_by_full_name(family+'.Items'))

    def test_bad_embedded_uuid_rejected_lazily(self):
        root=self.root('<Attribute uuid="bad"><Properties><Name>X</Name></Properties></Attribute>')
        with self.assertRaisesRegex(ValueError,'UUID'):root.find_by_full_name('Catalog.Items').get_member('Attributes')

    def test_duplicate_names_and_identity_rejected(self):
        node=embedded('Attribute','X')
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.root(node+node).find_by_full_name('Catalog.Items').get_member('Attributes')
        # Distinct UUIDs must not allow case-insensitive name ambiguity.
        other = embedded('Attribute', 'x')
        with self.assertRaisesRegex(ValueError, 'ambiguous metadata name'):
            self.root(node+other).find_by_full_name('Catalog.Items').get_member('Attributes')

    def test_missing_name_not_synthesized(self):
        root=self.root(embedded('Attribute','X').replace('>X<','><'))
        with self.assertRaisesRegex(ValueError,'name'):root.find_by_full_name('Catalog.Items').get_member('Attributes')

    def test_unknown_type_and_writes_remain_unsupported(self):
        field=self.root(embedded('Attribute','X')).find_by_full_name('Catalog.Items.Attribute.X')
        with self.assertRaises(ValueError):field.get_member('Type')
        with self.assertRaises(ValueError):field.set_member('Name','Y')

    def test_invalid_family_owner_not_fake_empty(self):
        role=self.root(family='Role',folder='Roles').find_by_full_name('Role.Items')
        with self.assertRaises(ValueError):role.get_member('Attributes')
