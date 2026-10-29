"""Single reviewed selector delta and bounded source identities, not native proof."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from test_native_1c_db_oracle_standard_activation import checkout_source_sha256

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/native-1c-file-db-oracle.yml'
PREVIOUS_WORKFLOW = '1d104a9155553f3e7b6f2dbcc3fd6fb782056bb615b7b2c4931c6713aa1dd47c'
SOURCE_PINS = {
    'yadinassi/storage/config_catalog_binding.py': 'f7e3239cdf8597e4377eff6ca01c8bbbec8f2d071bd6931dbc3f9e19fd3dab98',
    'yadinassi/storage/config_catalog_records.py': '29346abc74341186a6ddd54d111c6ec5e2fe651dfc9bf8e8e57446dfeba3ffb4',
    'scripts/native_1c_db_oracle/catalog_binding_reader.py': '3f692efc96630ce7df3064c684093da40275079f5f45b4716c9fa4c484709de5',
    'scripts/native_1c_db_oracle/catalog_readonly_binding.py': '0e27e8144d736d460c79df301bb7fcbd9b8da192ea4e5bbbaffddc944b364e98',
}


class CatalogReadonlyActivationTests(unittest.TestCase):
    def test_exactly_one_selector_changes_no_workflow_permissions_or_steps(self):
        raw=(ROOT/WORKFLOW).read_bytes()
        self.assertEqual(raw.count(b'--catalog-readonly-binding'),1)
        self.assertNotIn(b'--config-catalog-attribute-binding',raw)
        previous=raw.replace(b'--catalog-readonly-binding',b'--config-catalog-attribute-binding')
        self.assertEqual(checkout_source_sha256(previous),PREVIOUS_WORKFLOW)
        self.assertEqual(checkout_source_sha256(previous.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')),PREVIOUS_WORKFLOW)
        self.assertNotEqual(checkout_source_sha256(previous+b'# drift\n'),PREVIOUS_WORKFLOW)

    def test_current_source_pins_lf_crlf_and_content_drift(self):
        for path,expected in SOURCE_PINS.items():
            raw=(ROOT/path).read_bytes()
            with self.subTest(path=path):
                lf=raw.decode('utf-8').replace('\r\n','\n').encode('utf-8')
                self.assertEqual(checkout_source_sha256(lf),expected)
                self.assertEqual(checkout_source_sha256(lf.replace(b'\n',b'\r\n')),expected)
                for invalid in (lf+b'# drift\n',b'\xef\xbb\xbf'+lf,lf.replace(b'\n',b'\r',1)):
                    self.assertNotEqual(checkout_source_sha256(invalid),expected)

    def test_cold_selected_policy_has_exact_closed_inventory_and_schemas(self):
        code='''import sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'scripts/native_1c_db_oracle'),str(root/'yadinassi/storage')]
import inputs,protocol,catalog_readonly_binding as p
inventory=inputs.inventory(catalog_readonly_binding=True)
assert inventory==inputs.CATALOG_BINDING_SOURCE_FILES
assert p.MODULE_SOURCE in inventory and p.READER_SOURCE in inventory
assert not any(n=='yadinassi' or n.startswith('yadinassi.') for n in sys.modules)
print(json.dumps([p.SCHEMA,p.CAPTURE_SCHEMA,p.LANE,len(inventory),protocol.IMAGE]))
'''
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8'))
        self.assertEqual(json.loads(result.stdout),[37,38,'owned_catalog_readonly_binding_v1',35,
            'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728'])

if __name__=='__main__':unittest.main()
