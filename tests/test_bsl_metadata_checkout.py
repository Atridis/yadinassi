"""Actual autocrlf checkout must preserve authenticated metadata replay bytes."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PINNED = {
    'tests/fixtures/metadata_catalog_runtime/native_observations.json':
        'e7a54e3ed988c32ecf897710c32e7c6c32a46b906009c846a34970b3f497b124',
    'scripts/native_1c_db_oracle/modules/MetadataCatalogProbe.bsl':
        'acb83b5ae6e5de3630cce70fe1214f9027439e8ee505a52a29e7697a3d5f5785',
}


@unittest.skipUnless(shutil.which('git'), 'actual checkout requires git')
class MetadataCheckoutTests(unittest.TestCase):
    def test_autocrlf_checkout_preserves_exact_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            checkout = Path(temporary) / 'checkout'
            source.mkdir()
            def git(*args, cwd=source):
                return subprocess.run(['git', *args], cwd=cwd, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            git('init', '-q')
            git('config', 'core.autocrlf', 'false')
            for name in ('.gitattributes', *PINNED):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            git('add', '.')
            git('-c', 'user.name=Metadata checkout test', '-c',
                'user.email=metadata-checkout@example.invalid', 'commit', '-qm', 'fixture')
            git('clone', '-q', '--no-hardlinks', '-c', 'core.autocrlf=true',
                str(source), str(checkout), cwd=Path(temporary))
            for name, digest in PINNED.items():
                with self.subTest(name=name):
                    self.assertEqual(hashlib.sha256((checkout / name).read_bytes()).hexdigest(), digest)

if __name__ == '__main__': unittest.main()
