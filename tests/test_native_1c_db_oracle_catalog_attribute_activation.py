"""Exact one-token activation and current source pins; not native evidence."""
from pathlib import Path
import unittest
from test_native_1c_db_oracle_standard_activation import checkout_source_sha256

ROOT = Path(__file__).resolve().parents[1]


class CatalogAttributeActivationTests(unittest.TestCase):
    def test_workflow_changes_only_one_reviewed_selector(self):
        raw = (ROOT / 'tests/fixtures/native_catalog_readonly_workflow.yml').read_bytes()
        self.assertEqual(raw.count(b'--catalog-readonly-binding'), 1)
        previous = raw.replace(b'--catalog-readonly-binding', b'--config-catalog-field-matrix')
        self.assertEqual(checkout_source_sha256(previous),
            '4f0d0d77bf30c9e28cd742bb7a159084b997cc934af40412ac092f80517dd4af')
        self.assertNotIn(b'--config-catalog-field-matrix', raw)

    def test_exact_reviewed_current_pins_and_unchanged_matrix_policy(self):
        pins = {'yadinassi/storage/config_catalog_attributes.py': '8b6ecc0d0952b7ed4c1ebe0032b386a7283717744b3089ed37b3f02d954e98d1', 'scripts/native_1c_db_oracle/config_catalog_attribute_binding.py': '44d44998b4a54732c8aa232034cfd84ace5e2dd3ff841dfe9f22bfb8ae75bf22', 'scripts/native_1c_db_oracle/config_framing_reader.py': '5590051c5f0e9548c777be908cbd4d0f3dff293b44c14dbaabc3ed80e1a9f43e', 'scripts/native_1c_db_oracle/config_catalog_field_matrix.py': '16236e0e5617c27827a662512b7e88d7f8a1c84e3e97afa1d219de3190a4ba92'}
        for path, expected in pins.items():
            raw = (ROOT / path).read_bytes()
            with self.subTest(path=path):
                self.assertEqual(checkout_source_sha256(raw), expected)
                self.assertEqual(checkout_source_sha256(raw.decode('utf-8').replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')), expected)
                self.assertNotEqual(checkout_source_sha256(raw + b'# drift\n'), expected)


if __name__ == '__main__': unittest.main()
