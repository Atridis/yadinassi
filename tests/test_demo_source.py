"""Light structural checks for the editable demo, not native acceptance."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / 'examples/demo'
from yadinassi.main_demo_source import SOURCE_SHA256
FILES = tuple(sorted(SOURCE_SHA256))


class DemoSourceTests(unittest.TestCase):
    def test_source_inventory(self):
        actual = tuple(sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()))
        self.assertEqual(actual, FILES)
        self.assertFalse(any(p.is_symlink() for p in ROOT.rglob('*')))

    def test_xml_well_formed(self):
        for name in FILES:
            if name.endswith('.xml'):
                with self.subTest(name=name):
                    ET.fromstring((ROOT / name).read_bytes())

    def test_language_filename_matches_metadata(self):
        node = ET.fromstring((ROOT / 'Languages/Русский.xml').read_bytes())
        self.assertEqual(node.find('.//{*}Name').text, 'Русский')


if __name__ == '__main__':
    unittest.main()
