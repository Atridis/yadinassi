"""Exact one-token activation delta; no claim of new native acceptance."""
from pathlib import Path
import unittest
from test_native_1c_db_oracle_standard_activation import checkout_source_sha256

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/native-1c-file-db-oracle.yml'
IDENTITY_WORKFLOW_SHA256 = 'ed8bc1fdc4bcf73a12d7f74a31745a051a01740c951ddb77605125e29ddc07dc'


class FieldMatrixActivationTests(unittest.TestCase):
    def test_only_selector_changes_from_accepted_identity_workflow(self):
        raw = (ROOT / WORKFLOW).read_bytes()
        self.assertEqual(raw.count(b'--config-catalog-field-matrix'), 1)
        self.assertNotIn(b'--config-catalog-identity-binding', raw)
        previous = raw.replace(b'--config-catalog-field-matrix', b'--config-catalog-identity-binding')
        self.assertEqual(checkout_source_sha256(previous), IDENTITY_WORKFLOW_SHA256)
        self.assertNotEqual(checkout_source_sha256(previous + b'# drift\n'), IDENTITY_WORKFLOW_SHA256)


if __name__ == '__main__': unittest.main()
