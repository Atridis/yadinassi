"""Offline selector/source/recipe pins; never dispatch or run native commands."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/native-1c-file-db-oracle.yml'
SOURCE_PINS = {
    'scripts/native_1c_db_oracle/config_catalog_standard_binding.py':
        '9a144719343eb5acc4577b8b78b39a1a7e354365b9147533669fde96ee77e777',
    'scripts/native_1c_db_oracle/config_framing_reader.py':
        '885bf6241ac71ce165ebd6d8712e24f83a4e319c0ff0bc8df55d3f854547f803',
    'yadinassi/storage/config_catalog_name.py':
        '1b8052be83d5de69b89089885c600640d431fb73157e7b3c9a0c913c01575a1d',
}


class StandardActivationTests(unittest.TestCase):
    def test_workflow_changes_exactly_one_selector_and_nothing_else(self):
        raw = (ROOT/WORKFLOW).read_bytes()
        self.assertEqual(raw.count(b'--config-catalog-standard-binding'), 1)
        self.assertNotIn(b'--config-catalog-name-binding', raw)
        original = raw.replace(b'--config-catalog-standard-binding', b'--config-catalog-name-binding')
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '17f9855ec28d8e09e0cc1e21f34e5901769f9ea2eec089850eaee93298e68b9c')

    def test_reviewed_policy_parser_and_reader_source_pins(self):
        for path, expected in SOURCE_PINS.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), expected)

    def test_cold_policy_recipe_inventory_and_approved_image_pins(self):
        source = '''
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
sys.path[:0]=[str(root/'scripts/native_1c_db_oracle'),str(root/'yadinassi/storage')]
import config_catalog_standard_binding as p
import config_catalog_name_binding as old
import config_framing_reader as r
import inputs,protocol
profile=r.ConfigCatalogStandardProfile(p.DECLARATIONS,'0',0)
if profile.recipe()!=p.RECIPE_DESCRIPTION or profile.recipe_sha256!=p.RECIPE_SHA256:
    raise SystemExit('recipe mismatch')
if set(inputs.inventory(config_catalog_standard_binding=True))!=set(p.CATALOG_SOURCE_FILES):
    raise SystemExit('inventory mismatch')
print(json.dumps([p.SCHEMA,p.CAPTURE_SCHEMA,p.LANE,p.RECIPE_ID,p.RECIPE_SHA256,
    len(p.CATALOG_SOURCE_FILES),protocol.IMAGE,old.SCHEMA,old.CAPTURE_SCHEMA,old.RECIPE_SHA256]))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', source, str(ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(json.loads(result.stdout.decode('utf-8')), [
            29,30,'owned_config_catalog_standard_binding_v1','config_catalog_standard_8380_8192_v1',
            '984cd24e251525d9d4a11dcad373344ce95bd6af0d6b33d77f472e2d8922f0e4',26,
            'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728',
            27,28,'14a3109e66ed19dacd5499b3a2f762b3318b56244fd82e2a2304d0b041e0a2be'])


if __name__ == '__main__': unittest.main()
