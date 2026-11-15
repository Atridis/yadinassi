"""Only one root XML remains historical; original forms/handlers are canonical."""
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from legacy_demo_fixture import (ROOT, HISTORICAL_ROOT, SOURCE_SHA256,
    legacy_demo_files, materialize_legacy_demo)
from yadinassi.configuration_xml import _DEMO_KINDS_SOURCE_SHA256


class LegacyDemoFixtureTests(unittest.TestCase):
    def test_compatibility_projection_matches_all_runtime_pins(self):
        self.assertEqual(SOURCE_SHA256, _DEMO_KINDS_SOURCE_SHA256)
        files = legacy_demo_files()
        self.assertEqual({name: sha256(raw).hexdigest() for name, raw in files.items()}, SOURCE_SHA256)
        self.assertEqual(len(files), 19)
        self.assertFalse((ROOT / 'tests/fixtures/demo_cf').exists())
        for name, raw in files.items():
            if name != 'Configuration.xml':
                self.assertEqual(raw, (ROOT / 'examples/demo' / name).read_bytes())

    def test_owned_materialization_keeps_old_root_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'compatibility'
            materialize_legacy_demo(target)
            actual = {p.relative_to(target).as_posix(): p.read_bytes()
                      for p in target.rglob('*') if p.is_file()}
            self.assertEqual(actual, legacy_demo_files())
            with self.assertRaises(FileExistsError):
                materialize_legacy_demo(target)

    def test_changed_historical_or_canonical_bytes_refuse_before_projection(self):
        for changed in ('Configuration.xml', 'Catalogs/Номенклатура/Ext/ObjectModule.bsl'):
            with self.subTest(path=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name, raw in legacy_demo_files().items():
                    path = root / (HISTORICAL_ROOT if name == 'Configuration.xml' else 'examples/demo/' + name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw + (b'\n' if name == changed else b''))
                with self.assertRaises(ValueError):
                    legacy_demo_files(root)
