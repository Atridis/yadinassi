"""Owned browser fixture seeds choices only; its audit never writes the DB."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class MainDemoBrowserFixtureTests(unittest.TestCase):
    def test_seed_choices_and_read_only_empty_business_audit(self):
        path = Path(__file__).resolve().parent / 'browser_ui' / 'main_demo_fixture.py'
        spec = importlib.util.spec_from_file_location('owned_main_demo_fixture', path)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory(prefix='owned-main-demo-browser-') as temporary:
            root = Path(temporary)
            created = fixture.seed(root)
            self.assertEqual(created['authoredWarehouses'], 70)
            database = root / fixture.DATABASE
            before = sha256(database.read_bytes()).hexdigest()
            result = fixture.audit(root)
            audit_bytes = len((json.dumps(result, sort_keys=True) + '\n').encode('utf-8'))
            self.assertLessEqual(audit_bytes, 131072)
            print(f'main_demo_audit_json_bytes={audit_bytes}')
            self.assertTrue(result['readOnlyAudit'])
            self.assertEqual(len(result['catalogs']['Склады']), 70)
            self.assertEqual(result['catalogs']['ВидыНоменклатуры'], [])
            self.assertEqual(result['catalogs']['Номенклатура'], [])
            self.assertEqual(result['documents'], {'Receipt': [], 'Issue': []})
            self.assertEqual(result['movementRows'], [])
            self.assertEqual(set(result['catalogSchemas']),
                             {'ВидыНоменклатуры', 'Склады', 'Номенклатура'})
            self.assertEqual(set(result['documentSchemas']), {'Receipt', 'Issue'})
            self.assertEqual(set(result['registerSchemas']), {'Stock'})
            receipt = result['documentSchemas']['Receipt']
            self.assertIn('Warehouse', [field['name'] for field in receipt['fields']])
            lines = next(section for section in receipt['tabular_sections']
                         if section['name'] == 'Lines')
            self.assertTrue({'Product', 'Quantity', 'Amount'}.issubset(
                field['name'] for field in lines['fields']))
            self.assertEqual(sha256(database.read_bytes()).hexdigest(), before)
