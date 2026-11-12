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
        self.assertEqual(len(files),39)

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
        files.clear();self.assertEqual(len(c.files),39)
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
            self.assertEqual(sha256(stripped).hexdigest(),digest)

        from yadinassi.configuration_main_demo import _runtime_metadata_projection
        files=source(); projected=_runtime_metadata_projection(files)
        self.assertIn(b'<InternalInfo>',files['Documents/Receipt.xml'])
        self.assertNotIn(b'<InternalInfo',projected['Documents/Receipt.xml'])
        self.assertEqual(dict(self.config().files),files)
        self.assertEqual(files,source())
        changed=dict(files);changed['Documents/Receipt.xml']+=b' '
        with self.assertRaises(ValueError):_runtime_metadata_projection(changed)
