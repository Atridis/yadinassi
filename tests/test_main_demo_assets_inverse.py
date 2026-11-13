"""Exact test-only inverse of main-demo renderer provenance inventory."""
from pathlib import Path
import hashlib
import unittest
import test_native_async_fixture as history


class MainDemoAssetsInverseTests(unittest.TestCase):
    def source(self):
        return (Path(__file__).resolve().parents[1] / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')

    def test_restores_exact_previous_layer_then_unchanged_history(self):
        source = self.source()
        restored = history.without_main_demo_assets_provenance(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'c4ec7682edce0148a266917e22db661e887a80e2d1b1601f14490687b70aff69')
        self.assertEqual(history.without_main_demo_assets_provenance(restored), restored)
        inner = history.without_repository_inventory_budget(source)
        self.assertEqual(hashlib.sha256(inner.encode()).hexdigest(),
                         '5a096d8db934a21c83fbb24fbaa81215c260c2b4a0f61c14bef470794a15d133')

    def test_unknown_source_or_inventory_drift_is_not_normalized(self):
        source = self.source()
        for changed in (source + '\n', source.replace('"main-demo"', '"foreign"'),
                        source.replace('"main-demo"', '"main-demo", "main-demo"'),
                        source.replace(', "main-demo"', '')):
            if hashlib.sha256(changed.encode()).hexdigest() == 'c4ec7682edce0148a266917e22db661e887a80e2d1b1601f14490687b70aff69':
                continue  # The exact previous source remains valid by design.
            with self.subTest(digest=hashlib.sha256(changed.encode()).hexdigest()), self.assertRaises(AssertionError):
                history.without_repository_inventory_budget(changed)
