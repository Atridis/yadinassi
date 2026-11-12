"""Canonical next-block demo source contracts; not a runtime support claim."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples/demo'
from legacy_demo_fixture import legacy_demo_files
M = '{http://v8.1c.ru/8.3/MDClasses}'
I = '{urn:yadinassi:inventory-application:1}'


class MainDemoSourceTests(unittest.TestCase):
    def test_original_catalog_forms_handlers_and_identities_are_preserved(self):
        originals = legacy_demo_files()
        self.assertEqual(len(originals), 19)
        for name, raw in originals.items():
            if name != 'Configuration.xml':
                with self.subTest(path=name):
                    self.assertEqual((SOURCE / name).read_bytes(), raw)

    def test_one_configuration_declares_all_scenarios_without_duplicate_catalogs(self):
        root = ET.parse(SOURCE / 'Configuration.xml').getroot().find(M+'Configuration')
        original = ET.fromstring(legacy_demo_files()['Configuration.xml']).find(M+'Configuration')
        self.assertEqual(root.attrib['uuid'], original.attrib['uuid'])
        declarations = root.find(M+'ChildObjects')
        by_kind = {}
        for child in declarations:
            by_kind.setdefault(child.tag.removeprefix(M), []).append(child.text)
        self.assertEqual(set(by_kind['Catalog']), {'ВидыНоменклатуры', 'Склады', 'Номенклатура'})
        self.assertEqual(set(by_kind['Document']), {'Receipt', 'Issue'})
        self.assertEqual(by_kind['AccumulationRegister'], ['Stock'])
        self.assertEqual(set(by_kind['Enum']), {'Units', 'States'})
        self.assertFalse((SOURCE / 'Catalogs/Products.xml').exists())
        self.assertFalse((SOURCE / 'Catalogs/Warehouses.xml').exists())

    def test_document_and_register_references_target_original_russian_catalogs(self):
        refs = set()
        for folder in ('Documents', 'AccumulationRegisters'):
            for path in (SOURCE/folder).rglob('*.xml'):
                refs.update(re.findall(r'cfg:CatalogRef\.([^<\s]+)', path.read_text(encoding='utf-8')))
        self.assertEqual(refs, {'Номенклатура', 'Склады'})

    def test_document_commands_and_reports_share_the_same_saved_catalogs(self):
        root = ET.parse(SOURCE/'InventoryApplication.xml').getroot()
        forms = root.find(I+'Forms')
        self.assertEqual([f.attrib['name'] for f in forms], ['Document.Receipt.Form.Card', 'Document.Issue.Form.Card'])
        for form in forms:
            self.assertEqual([c.attrib['mode'] for c in form], ['Write', 'Post', 'UndoPosting'])
        reports = root.find(I+'Reports')
        self.assertEqual([r.attrib['view'] for r in reports], ['Movements', 'Balance', 'Turnovers', 'BalanceAndTurnovers'])
        ids = {ET.parse(SOURCE/('Catalogs/'+name+'.xml')).getroot().find(M+'Catalog').attrib['uuid']
               for name in ('Номенклатура','Склады')}
        self.assertEqual({f.attrib['catalogId'] for f in reports[-1].findall(I+'Filter')}, ids)

    def test_complete_bounded_xml_bsl_envelope(self):
        paths = [p for p in SOURCE.rglob('*') if p.is_file()]
        self.assertEqual(len(paths), 33)
        self.assertTrue(all(p.suffix in ('.xml', '.bsl') for p in paths))
        for path in paths:
            if path.suffix == '.xml':
                with self.subTest(path=path.relative_to(SOURCE)):
                    ET.parse(path)
