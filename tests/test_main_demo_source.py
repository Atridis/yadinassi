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
        self.assertEqual(set(by_kind['CommonForm']), {'OperationDraft', 'DraftDetails'})
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
        self.assertEqual(len(paths), 39)
        self.assertTrue(all(p.suffix in ('.xml', '.bsl') for p in paths))
        for path in paths:
            if path.suffix == '.xml':
                with self.subTest(path=path.relative_to(SOURCE)):
                    ET.parse(path)

    def test_document_form_descriptors_do_not_declare_unsupported_child_objects(self):
        # Designer rejects ChildObjects on metadata Form (not the Ext/Form layout).
        expected = {'Receipt': '76eaf69d-2f5a-59f4-98f6-d62742c51881',
                    'Issue': '5caedcf5-cc3b-5979-93a8-98af5e0d39fa'}
        for name, identity in expected.items():
            with self.subTest(document=name):
                form = ET.parse(SOURCE / f'Documents/{name}/Forms/Card.xml').getroot().find(M+'Form')
                self.assertEqual(form.attrib['uuid'], identity)
                self.assertEqual([child.tag for child in form], [M+'Properties'])
                self.assertEqual(form.findtext(M+'Properties/'+M+'Name'), 'Card')
                self.assertEqual(form.findtext(M+'Properties/'+M+'FormType'), 'Managed')

    def test_common_form_descriptors_only_declare_properties(self):
        for name in ('OperationDraft', 'DraftDetails'):
            with self.subTest(form=name):
                form = ET.parse(SOURCE / f'CommonForms/{name}.xml').getroot().find(M+'CommonForm')
                self.assertEqual([child.tag for child in form], [M+'Properties'])
                self.assertEqual(form.findtext(M+'Properties/'+M+'Name'), name)
                self.assertEqual(form.findtext(M+'Properties/'+M+'FormType'), 'Managed')

    def test_authored_layout_titles_and_commands_use_native_representation(self):
        from hashlib import sha256
        v = '{http://v8.1c.ru/8.1/data/core}'
        l = '{http://v8.1c.ru/8.3/xcf/logform}'
        before = {
            'CommonForms/DraftDetails/Ext/Form.xml':'67f34e7bebf16a62bc8e8616bccc82d170d2bc13d7a543f30a16c03ad6251983',
            'CommonForms/OperationDraft/Ext/Form.xml':'cf2b4d0296fb5932b3000ed823e661649cd25346119d57575f67be52aa0df42e',
            'Documents/Issue/Forms/Card/Ext/Form.xml':'2747be3390be238f91b80dcded8bdce77598ce648c6625475cfd449a5ea34222',
            'Documents/Receipt/Forms/Card/Ext/Form.xml':'f01260926e2526025a0d58ba7859d7d7eda6fd0d5b733396b20c4cc0677dd97d',
        }
        for path, digest in before.items():
            with self.subTest(path=path):
                raw = (SOURCE/path).read_bytes(); root = ET.fromstring(raw)
                for title in root.iter(l+'Title'):
                    self.assertEqual([n.tag for n in title], [v+'item'])
                    self.assertEqual(title.findtext(v+'item/'+v+'lang'), 'ru')
                    self.assertTrue(title.findtext(v+'item/'+v+'content'))
                for command in root.iter(l+'CommandName'):
                    self.assertTrue(command.text.startswith('Form.Command.'))
                projected = re.sub(rb'<Title><v8:item><v8:lang>ru</v8:lang><v8:content>([^<]*)</v8:content></v8:item></Title>', rb'<Title>\1</Title>', raw)
                projected = projected.replace(b'<CommandName>Form.Command.', b'<CommandName>')
                self.assertEqual(sha256(projected).hexdigest(), digest)
