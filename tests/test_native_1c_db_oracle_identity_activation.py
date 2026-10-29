"""Reviewed one-token identity selector and source pins, not native evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from test_native_1c_db_oracle_standard_activation import checkout_source_sha256

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/native-1c-file-db-oracle.yml'
STANDARD_WORKFLOW_SHA256 = 'fdca596908e058649cb4614e459f5f74882acecf56464a6cdf2f01fee3cb3b5c'
SOURCE_PINS = {'scripts/native_1c_db_oracle/config_catalog_identity_binding.py': '2e5a9efb49de55e37387cb81c2d792c3413029e00de9a279180bbacb187bcd19', 'scripts/native_1c_db_oracle/config_framing_reader.py': '5590051c5f0e9548c777be908cbd4d0f3dff293b44c14dbaabc3ed80e1a9f43e', 'yadinassi/storage/config_catalog_name.py': '1d77c88a2d9baabf38c1b0dba65b71316f94f292be8a3b7741a8d792c56338aa'}


class IdentityActivationTests(unittest.TestCase):
    def test_only_one_workflow_selector_changes(self):
        raw = (ROOT / 'tests/fixtures/native_catalog_readonly_workflow.yml').read_bytes()
        self.assertEqual(raw.count(b'--catalog-readonly-binding'), 1)
        self.assertNotIn(b'--config-catalog-standard-binding', raw)
        original = raw.replace(b'--catalog-readonly-binding', b'--config-catalog-standard-binding')
        self.assertEqual(checkout_source_sha256(original), STANDARD_WORKFLOW_SHA256)

    def test_exact_current_source_pins(self):
        for path, expected in SOURCE_PINS.items():
            with self.subTest(path=path):
                raw = (ROOT / path).read_bytes()
                self.assertEqual(checkout_source_sha256(raw), expected)
                self.assertEqual(checkout_source_sha256(raw.decode('utf-8').replace('\r\n', '\n')
                                 .replace('\n', '\r\n').encode('utf-8')), expected)
                self.assertNotEqual(checkout_source_sha256(raw + b'# drift\n'), expected)

    def test_cold_recipe_inventory_and_old_standard_identity(self):
        code = """
import sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'scripts/native_1c_db_oracle'),str(root/'yadinassi/storage')]
import config_catalog_identity_binding as p
import config_catalog_standard_binding as old
import config_framing_reader as r
import inputs,protocol
profile=r.ConfigCatalogIdentityProfile(p.DECLARATIONS,'0',0)
assert profile.recipe()==p.RECIPE_DESCRIPTION and profile.recipe_sha256==p.RECIPE_SHA256
assert set(inputs.inventory(config_catalog_identity_binding=True))==set(p.CATALOG_SOURCE_FILES)
print(json.dumps([p.SCHEMA,p.CAPTURE_SCHEMA,p.LANE,p.RECIPE_ID,p.RECIPE_SHA256,
len(p.CATALOG_SOURCE_FILES),protocol.IMAGE,old.SCHEMA,old.CAPTURE_SCHEMA,old.RECIPE_SHA256]))
"""
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', code, str(ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(json.loads(result.stdout), [31, 32, 'owned_config_catalog_identity_binding_v1',
            'config_catalog_identity_8380_8192_v1',
            '815804b8bc0fa5f743554dc2250c3be6eda4027e7df8a2003f47c32a94c9662d', 26,
            'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728',
            29, 30, '984cd24e251525d9d4a11dcad373344ce95bd6af0d6b33d77f472e2d8922f0e4'])


if __name__ == '__main__': unittest.main()
