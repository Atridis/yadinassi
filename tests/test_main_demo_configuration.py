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
        self.assertEqual(len(files),33)

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
        files.clear();self.assertEqual(len(c.files),33)
        self.assertEqual(canonical(c),c)
