"""One full-source demo grant, separate from every historical source profile."""
from dataclasses import replace
from pathlib import Path
import unittest
from yadinassi.configuration_main_demo import (
    PROFILE, MainDemoConfiguration, import_main_demo_configuration, canonical)
from yadinassi.configuration_xml import _DEMO_KINDS_SOURCE_SHA256
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]

def source():
    root = ROOT/'examples/demo'
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

class MainDemoConfigurationTests(unittest.TestCase):
    def config(self):
        return import_main_demo_configuration(source(),profile=PROFILE)

    def test_one_source_three_original_catalogs_and_inventory_objects(self):
        c=self.config()
        self.assertIs(type(c),MainDemoConfiguration)
        self.assertEqual({x.name for x in c.catalogs},{'ВидыНоменклатуры','Склады','Номенклатура'})
        self.assertEqual({x.name for x in c.documents},{'Receipt','Issue'})
        self.assertEqual([x.name for x in c.registers],['Stock'])
        self.assertEqual({x.name for x in c.enumerations},{'Units','States'})
        self.assertEqual(len(c.commands),6);self.assertEqual(len(c.reports),4)

    def test_original_eighteen_nonroot_files_are_identical(self):
        files=source()
        for path,digest in _DEMO_KINDS_SOURCE_SHA256.items():
            if path!='Configuration.xml':self.assertEqual(sha256(files[path]).hexdigest(),digest)
        self.assertEqual(len(files),47)

    def test_original_reference_section_and_callback_not_erased(self):
        c=self.config();cats={x.name:x for x in c.catalogs};product=cats['Номенклатура']
        self.assertEqual(product.fields[0].target_catalog_id,cats['ВидыНоменклатуры'].identity)
        self.assertEqual(product.tabular_sections[0].fields[0].target_catalog_id,cats['Склады'].identity)
        self.assertEqual(c.catalog_handlers[0][0],product.identity)
        self.assertTrue(any(x.name=='Номенклатура' and len(x.forms)==2 for x in c.catalog_sources))

    def test_explicit_new_profile_required(self):
        for profile in (None,'inventory-enum-v1','inventory-enum-forms-v1','demo_products_v1',object()):
            with self.assertRaises(ValueError):import_main_demo_configuration(source(),profile=profile)

    def test_source_missing_extra_or_changed_refused(self):
        files=source()
        for operation in ('missing','extra','changed'):
            changed=dict(files)
            if operation=='missing':changed.pop('InventoryApplication.xml')
            elif operation=='extra':changed['CommonModules/Injected.xml']=b'<x/>'
            else:changed['Documents/Receipt/Ext/ObjectModule.bsl']+=b'\n'
            with self.assertRaises(ValueError):import_main_demo_configuration(changed,profile=PROFILE)

    def test_canonical_reimport_rejects_forged_schema(self):
        c=self.config();self.assertEqual(canonical(c),c)
        for changed in (replace(c,catalogs=()),replace(c,commands=()),replace(c,catalog_handlers=()),replace(c,profile='inventory-enum-v1')):
            with self.assertRaises(ValueError):canonical(changed)

    def test_canonical_foreign_object_does_not_read_properties(self):
        class Foreign:
            @property
            def profile(self):raise AssertionError('foreign property')
        with self.assertRaises(ValueError):canonical(Foreign())

    def test_caller_mapping_is_detached(self):
        files=source();c=import_main_demo_configuration(files,profile=PROFILE)
        files.clear();self.assertEqual(len(c.files),47)
        self.assertEqual(canonical(c),c)

    def test_native_internal_info_uses_exact_matching_metadata_owners(self):
        import xml.etree.ElementTree as ET
        M='{http://v8.1c.ru/8.3/MDClasses}'
        for relative, name in (('Documents/Receipt.xml','Receipt.xml'),
                ('Documents/Issue.xml','Issue.xml'),('AccumulationRegisters/Stock.xml','Stock.xml')):
            current=ET.fromstring(source()[relative])
            native=ET.parse(ROOT/'scripts/inventory_enum_behavior'/name).getroot()
            owners={node.get('uuid'):node for node in current.iter() if node.get('uuid')}
            for node in native.iter():
                expected=node.find(M+'InternalInfo')
                if expected is None:continue
                owner=owners[node.get('uuid')]
                self.assertEqual(owner.tag,node.tag)
                def shape(n):
                    return n.tag,sorted(n.attrib.items()),(n.text or '').strip(),[shape(c) for c in n]
                self.assertEqual(shape(owner.find(M+'InternalInfo')),shape(expected))
        c=self.config()
        self.assertEqual({x.name for x in c.documents},{'Receipt','Issue'})

    def test_internal_info_tampering_cannot_expand_source_grant(self):
        files=source()
        changed=dict(files)
        changed['Documents/Receipt.xml']=files['Documents/Receipt.xml'].replace(
            b'dbcc2f23-ac27-50ff-9f05-76514e6751bc',b'dbcc2f23-ac27-50ff-9f05-76514e6751bd')
        self.assertNotEqual(changed,files)
        with self.assertRaises(ValueError):
            import_main_demo_configuration(changed,profile=PROFILE)

    def test_internal_info_patch_preserves_all_other_source_bytes(self):
        import re
        prior = {'Documents/Receipt.xml': 'f27a24ac214549a5a8dc83884d7425c29151e00de51e3ee2f66761704c4d0fcd', 'Documents/Issue.xml': '3c51f6281c269656b34595dad6643545f89b2b45765add3d684b405fc93ffe01', 'AccumulationRegisters/Stock.xml': '7979da48a1a1c122e8d9dcd21eaa7ea6542ea0f6499ede34c5456cb9cc6fb7fc'}
        for path, digest in prior.items():
            stripped=re.sub(rb'<InternalInfo(?: xmlns:xr="[^"]+")?>.*?</InternalInfo>',b'',source()[path],flags=re.S)
            stripped=re.sub(rb'<!-- InternalInfo adapted from .*? -->',b'',stripped,flags=re.S)
            # Localized display synonyms are the only new metadata bytes.
            stripped=re.sub(rb'<Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>[^<]+</v8:content></v8:item></Synonym>',b'',stripped,count=1)
            self.assertEqual(sha256(stripped).hexdigest(),digest)

        from yadinassi.configuration_main_demo import _runtime_metadata_projection
        files=source(); projected=_runtime_metadata_projection(files)
        self.assertIn(b'<InternalInfo>',files['Documents/Receipt.xml'])
        self.assertNotIn(b'<InternalInfo',projected['Documents/Receipt.xml'])
        self.assertEqual(dict(self.config().files),files)
        self.assertEqual(files,source())
        changed=dict(files);changed['Documents/Receipt.xml']+=b' '
        with self.assertRaises(ValueError):_runtime_metadata_projection(changed)

    def test_native_layout_projection_preserves_source_and_semantics(self):
        import xml.etree.ElementTree as ET
        from yadinassi.configuration_main_demo import _NATIVE_LAYOUTS, _runtime_metadata_projection
        files=source(); before=dict(files); projected=_runtime_metadata_projection(files)
        L='{http://v8.1c.ru/8.3/xcf/logform}'; V='{http://v8.1c.ru/8.1/data/core}'
        prior = {'CommonForms/DraftDetails/Ext/Form.xml':'67f34e7bebf16a62bc8e8616bccc82d170d2bc13d7a543f30a16c03ad6251983',
                 'CommonForms/OperationDraft/Ext/Form.xml':'cf2b4d0296fb5932b3000ed823e661649cd25346119d57575f67be52aa0df42e',
                 'Documents/Issue/Forms/Card/Ext/Form.xml':'2747be3390be238f91b80dcded8bdce77598ce648c6625475cfd449a5ea34222',
                 'Documents/Receipt/Forms/Card/Ext/Form.xml':'f01260926e2526025a0d58ba7859d7d7eda6fd0d5b733396b20c4cc0677dd97d'}
        self.assertEqual(set(_NATIVE_LAYOUTS), set(prior) | {'CommonForms/DemoWelcome/Ext/Form.xml'})
        for path in _NATIVE_LAYOUTS:
            # Retain all historical digests; DemoWelcome is a new authored layout.
            if path in prior:
                # Preserve historical fingerprints: only the display titles changed.
                from main_demo_russian_fixture import historical_titles
                self.assertEqual(sha256(historical_titles(projected[path])).hexdigest(),prior[path])
            native=ET.fromstring(files[path]); runtime=ET.fromstring(projected[path])
            self.assertEqual([n.find(V+'item/'+V+'content').text for n in native.iter(L+'Title')],
                             [n.text for n in runtime.iter(L+'Title')])
            self.assertEqual([n.text.removeprefix('Form.Command.') for n in native.iter(L+'CommandName')],
                             [n.text for n in runtime.iter(L+'CommandName')])
            self.assertIn(b'xmlns:xs=',projected[path])
            self.assertIn(b'xs:',projected[path])
        self.assertEqual(files,before)
        self.assertEqual(dict(self.config().files),before)

    def test_native_layout_projection_rejects_unpinned_and_wrong_shape(self):
        from unittest.mock import patch
        from yadinassi.configuration_main_demo import _NATIVE_LAYOUTS, _runtime_layout_projection
        import yadinassi.configuration_main_demo as module
        path='CommonForms/DraftDetails/Ext/Form.xml'; raw=source()[path]
        variants=(raw.replace(b'>ru<',b'>en<',1),
                  raw.replace(b'<v8:item>',b'<v8:item bad="1">',1),
                  raw.replace(b'Form.Command.Accept',b'Form.Command.Unknown',1))
        for changed in variants:
            with self.assertRaises(ValueError):_runtime_layout_projection(path,changed)
            with patch.dict(module.SOURCE_SHA256,{path:sha256(changed).hexdigest()}):
                with self.assertRaises(ValueError):_runtime_layout_projection(path,changed)
        with self.assertRaises(ValueError):_runtime_layout_projection('Foreign/Ext/Form.xml',raw)
