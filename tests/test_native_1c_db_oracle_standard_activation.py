"""Maintained standard-lane compatibility pins; never run native commands.

Shared source pins track this reviewed candidate, not the original native run.
The original source/run attribution remains in the standard-prefix documentation."""
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
        '5590051c5f0e9548c777be908cbd4d0f3dff293b44c14dbaabc3ed80e1a9f43e',
    'yadinassi/storage/config_catalog_name.py':
        '1d77c88a2d9baabf38c1b0dba65b71316f94f292be8a3b7741a8d792c56338aa',
}


WORKFLOW_LF_SHA256 = '17f9855ec28d8e09e0cc1e21f34e5901769f9ea2eec089850eaee93298e68b9c'


def checkout_source_sha256(raw):
    """Test-only Git source identity across LF/CRLF checkouts, not native bytes.

    Decode strict UTF-8 and normalize only CRLF pairs. Retain lone CR, BOM,
    whitespace and every other content byte. Production provenance/capture
    hashing remains byte-exact and does not use this test helper.
    """
    canonical = raw.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


class StandardActivationTests(unittest.TestCase):
    def test_workflow_changes_exactly_one_selector_and_nothing_else(self):
        raw = (ROOT/'tests/fixtures/native_catalog_readonly_workflow.yml').read_bytes()
        self.assertEqual(raw.count(b'--catalog-readonly-binding'), 1)
        self.assertNotIn(b'--config-catalog-name-binding', raw)
        original = raw.replace(b'--catalog-readonly-binding', b'--config-catalog-name-binding')
        self.assertEqual(checkout_source_sha256(original), WORKFLOW_LF_SHA256)

    def test_reviewed_policy_parser_and_reader_source_pins(self):
        for path, expected in SOURCE_PINS.items():
            with self.subTest(path=path):
                self.assertEqual(checkout_source_sha256((ROOT/path).read_bytes()), expected)

    def pinned_checkout_inputs(self):
        for path, expected in SOURCE_PINS.items():
            yield path, (ROOT/path).read_bytes(), expected
        original = (ROOT/'tests/fixtures/native_catalog_readonly_workflow.yml').read_bytes().replace(
            b'--catalog-readonly-binding', b'--config-catalog-name-binding')
        yield WORKFLOW, original, WORKFLOW_LF_SHA256

    def test_real_pinned_sources_accept_lf_and_crlf_checkouts(self):
        for path, raw, expected in self.pinned_checkout_inputs():
            lf = raw.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
            self.assertNotIn(b'\r', lf)
            crlf = lf.replace(b'\n', b'\r\n')
            with self.subTest(path=path):
                self.assertNotEqual(hashlib.sha256(lf).hexdigest(), hashlib.sha256(crlf).hexdigest())
                self.assertEqual(checkout_source_sha256(lf), expected)
                self.assertEqual(checkout_source_sha256(crlf), expected)

    def test_pins_reject_non_newline_drift_and_lone_cr(self):
        for path, raw, expected in self.pinned_checkout_inputs():
            lf = raw.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
            for changed in (lf+b'# changed content\n', b' '+lf, b'\xef\xbb\xbf'+lf,
                            lf.replace(b'\n', b'\r', 1), lf.replace(b'\n', b'', 1)):
                for candidate in (changed, changed.replace(b'\n', b'\r\n')):
                    with self.subTest(path=path, candidate=candidate[:32]):
                        self.assertNotEqual(checkout_source_sha256(candidate), expected)

    def test_canonical_hash_is_strict_utf8_and_preserves_unicode(self):
        lf = 'Имя 😀\nвторая строка\n'.encode('utf-8')
        self.assertEqual(checkout_source_sha256(lf.replace(b'\n', b'\r\n')),
                         hashlib.sha256(lf).hexdigest())
        self.assertNotEqual(checkout_source_sha256(lf.replace('Имя'.encode('utf-8'),
                                                            'Другое'.encode('utf-8'))),
                            hashlib.sha256(lf).hexdigest())
        with self.assertRaises(UnicodeDecodeError): checkout_source_sha256(b'\xff\r\n')

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
