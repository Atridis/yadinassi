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
# Current candidate compatibility-integrity pins, NOT the original native
# activation receipt. New zero-Code physical/typed reader acceptance requires fresh native
# evidence bound to its public-reader lane (standalone measurement is not parity). Historical hashes remain in
# docs/catalog-description-rows.md; retain direct current LF/CRLF/drift checks.
SOURCE_PINS = {
    'yadinassi/storage/catalog_reader.py': 'f7a7bdb40c4ccaaae822cdd5b5c5c13e65dac19662b86ee4d4a1cca34bb25e75',
    'yadinassi/storage/config_catalog_transport.py': 'b526877c583900b263779c00f8db5c74cb40ff423b1df0e16f866cc4abca01ff',
    'yadinassi/storage/config_catalog_binding.py': 'd054f485f5fe077bf50cb7636966edd9b31c8c7911596285d1d831bbc2040636',
    'yadinassi/storage/config_catalog_records.py': '5a797947ff465656d34d9d83b73f0a31319fa979bb9ab093d134d4946e230f1f',
    'scripts/native_1c_db_oracle/catalog_binding_reader.py': '18d3729d2dc6bd8b198ade1188eb79cd8c48ad75001399e79975b7eb6c8f81b9',
    'scripts/native_1c_db_oracle/catalog_readonly_binding.py': '47b661c13fcdd515fdfdde76130ab4b3f2bb9f781965cbd505b429cb5bd6bedb',
}


class CatalogReadonlyActivationTests(unittest.TestCase):
    def test_archived_activation_changed_only_one_reviewed_selector(self):
        # Historical evidence remains pinned; the active workflow now measures references.
        raw=(ROOT/'tests/fixtures/native_catalog_readonly_workflow.yml').read_bytes()
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
        self.assertEqual(json.loads(result.stdout),[37,38,'owned_catalog_readonly_binding_v1',37,
            'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728'])

if __name__=='__main__':unittest.main()
