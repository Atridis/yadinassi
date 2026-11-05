import hashlib
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.demo_cf_fixture import ARCHIVE_SHA256, ROOT, fixture_files, stage


class DemoFixtureTests(unittest.TestCase):
    def test_original_identity(self):
        self.assertEqual(hashlib.sha256((ROOT / 'original.zip').read_bytes()).hexdigest(), ARCHIVE_SHA256)

    def test_exact_inventory(self):
        files = fixture_files()
        self.assertEqual(len(files), 19)
        self.assertEqual(sum(n.endswith('.xml') for n in files), 15)
        self.assertEqual(sum(n.endswith('.bsl') for n in files), 4)
        self.assertNotIn('validate_dump.py', files)
        self.assertNotIn('README.txt', files)

    def test_normalized_language_filename(self):
        files = fixture_files()
        self.assertIn('Languages/Русский.xml', files)
        self.assertNotIn('Languages/Русский.xml', files)
        root = ET.fromstring(files['Languages/Русский.xml'])
        self.assertEqual(root.find('.//{*}Name').text, 'Русский')

    def test_xml_is_well_formed_only(self):
        for name, data in fixture_files().items():
            if name.endswith('.xml'):
                with self.subTest(name=name):
                    self.assertIsNotNone(ET.fromstring(data))

    def test_staging_preserves_all_source_bytes(self):
        with tempfile.TemporaryDirectory() as parent:
            target = stage(Path(parent) / 'dump')
            actual = {p.relative_to(target).as_posix(): p.read_bytes()
                      for p in target.rglob('*') if p.is_file()}
            self.assertEqual(actual, fixture_files())

    def test_staging_never_overwrites(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / 'dump'
            target.mkdir()
            sentinel = target / 'keep'
            sentinel.write_bytes(b'unchanged')
            with self.assertRaises(FileExistsError):
                stage(target)
            self.assertEqual(sentinel.read_bytes(), b'unchanged')

    def test_changed_archive_rejected(self):
        original = (ROOT / 'original.zip').read_bytes()
        with tempfile.TemporaryDirectory() as parent:
            altered = Path(parent) / 'changed.zip'
            for data in (original[:-1], original + b'x', bytes([original[0] ^ 1]) + original[1:]):
                altered.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    fixture_files(altered)


if __name__ == '__main__':
    unittest.main()
