"""Current runtime inventory is not a rewrite of frozen native evidence."""
import hashlib
from pathlib import Path
import unittest
import test_native_async_fixture as history

class SourceWorkspaceAssetsInverseTests(unittest.TestCase):
    def source(self):
        return (Path(__file__).resolve().parents[1]/'scripts/native_1c_full_host.py').read_text(encoding='utf-8')

    def test_exact_new_layer_restores_previous_bytes_and_history(self):
        raw=self.source();prior=history.without_source_workspace_assets_provenance(raw)
        self.assertEqual(hashlib.sha256(prior.encode()).hexdigest(),'fe969cfcf973e68e2be1ab418eed31a2f6f3b6ecebcce5d1c7fbdfd3d25132fe')
        self.assertEqual(history.without_source_workspace_assets_provenance(prior),prior)
        restored=history.without_repository_inventory_budget(raw)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'5a096d8db934a21c83fbb24fbaa81215c260c2b4a0f61c14bef470794a15d133')

    def test_changed_inventory_or_suffix_cannot_be_normalized(self):
        raw=self.source()
        for changed in (raw+'\n',raw.replace('"source-workspace"','"foreign"'),raw.replace('"source-workspace"','"source-workspace", "source-workspace"')):
            with self.subTest(sha=hashlib.sha256(changed.encode()).hexdigest()):
                self.assertEqual(history.without_source_workspace_assets_provenance(changed),changed)
                with self.assertRaises(AssertionError):history.without_repository_inventory_budget(changed)
