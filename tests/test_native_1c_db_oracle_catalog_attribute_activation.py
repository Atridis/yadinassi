"""Exact one-token activation and current source pins; not native evidence."""
from pathlib import Path
import unittest
from test_native_1c_db_oracle_standard_activation import checkout_source_sha256

ROOT = Path(__file__).resolve().parents[1]


class CatalogAttributeActivationTests(unittest.TestCase):
    def test_workflow_changes_only_one_reviewed_selector(self):
        raw = (ROOT / '.github/workflows/native-1c-file-db-oracle.yml').read_bytes()
        self.assertEqual(raw.count(b'--config-catalog-attribute-binding'), 1)
        previous = raw.replace(b'--config-catalog-attribute-binding', b'--config-catalog-field-matrix')
        self.assertEqual(checkout_source_sha256(previous),
            '4f0d0d77bf30c9e28cd742bb7a159084b997cc934af40412ac092f80517dd4af')
        self.assertNotIn(b'--config-catalog-field-matrix', raw)

    def test_exact_reviewed_current_pins_and_unchanged_matrix_policy(self):
        pins = {'yadinassi/storage/config_catalog_attributes.py': 'e3be535c317911d0bfc634f69d4640e9592f906b93aca3aef3f4f1e4a4cdf3d9', 'scripts/native_1c_db_oracle/config_catalog_attribute_binding.py': '44d44998b4a54732c8aa232034cfd84ace5e2dd3ff841dfe9f22bfb8ae75bf22', 'scripts/native_1c_db_oracle/config_framing_reader.py': '7986c3ca6beb7b45e47d68a16093f1580c49ff33e10b6d9e8e947ad0d2e961d4', 'scripts/native_1c_db_oracle/config_catalog_field_matrix.py': '16236e0e5617c27827a662512b7e88d7f8a1c84e3e97afa1d219de3190a4ba92'}
        for path, expected in pins.items():
            raw = (ROOT / path).read_bytes()
            with self.subTest(path=path):
                self.assertEqual(checkout_source_sha256(raw), expected)
                self.assertEqual(checkout_source_sha256(raw.decode('utf-8').replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')), expected)
                self.assertNotEqual(checkout_source_sha256(raw + b'# drift\n'), expected)


if __name__ == '__main__': unittest.main()
