"""Relocation keeps genuine historical evidence separate from generated output."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from test_native_1c_full_host import SyntheticFilesystemCase, full

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/native_windows"
# Exact Git blobs from main f4654d7fd4db08af51258b13deefca4ea72bf6fb.
BLOBS = {'collections.out': '97e90791a4011bd7f6ef2922533f92f698557cbd', 'dates.out': '05d23c46540b301820f2ac81c8a67fc0e1273dc8', 'functions.out': '6df192ac9d10c07755948d7c14cfed9e2311c65f', 'numbers.out': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13', 'strings.out': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462', 'values.out': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27'}


class HistoricalFixtureLayoutTests(unittest.TestCase):
    def test_all_six_owner_captures_retain_their_exact_git_blobs(self):
        self.assertEqual({p.name for p in FIXTURES.glob("*.out")}, set(BLOBS))
        self.assertEqual(list(FIXTURES.glob("*.err")), [])
        for name, expected in BLOBS.items():
            with self.subTest(name=name):
                # Existing checkout transport convention only; no payload rewriting.
                data = (FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")
                actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                self.assertEqual(actual, expected)

    def test_launcher_directory_is_retained_and_generated_content_is_ignored(self):
        self.assertTrue((ROOT / "integrational_tests/output/.gitkeep").is_file())
        patterns = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/integrational_tests/output/*", patterns)
        self.assertIn("!/integrational_tests/output/.gitkeep", patterns)
        self.assertGreater(patterns.index("!/integrational_tests/output/.gitkeep"),
                           patterns.index("/integrational_tests/output/*"))
        # Do not require the runtime directory to be empty after a genuine run.
        self.assertTrue((ROOT / "tests/fixtures/basic.out").is_file())


class RelocatedFingerprintTests(SyntheticFilesystemCase):
    def test_native_guard_protects_fixtures_not_disposable_launcher_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            # macOS /var is a symlink; fixtures must use their real directory,
            # just like production and the other strict-reader tests.
            root = Path(temporary).resolve()
            fixtures = root / "tests/fixtures/native_windows"
            fixtures.mkdir(parents=True)
            generated = root / "integrational_tests/output"
            generated.mkdir(parents=True)
            (root / "integrational_tests/meta.md").write_bytes(b"synthetic metadata\n")
            for name in full.SCENARIOS:
                (fixtures / (name + ".out")).write_bytes(b"synthetic fixture\n")
            before = full.windows_fingerprints(root)
            self.assertEqual(set(before),
                             {f"tests/fixtures/native_windows/{name}.out" for name in full.SCENARIOS}
                             | {"integrational_tests/meta.md"})
            (generated / "collections.out").write_bytes(b"new synthetic runtime capture\n")
            (generated / "collections.err").write_bytes(b"synthetic runtime error\n")
            self.assertEqual(full.windows_fingerprints(root), before)
            changed = fixtures / "collections.out"
            changed.write_bytes(b"mutated fixture\n")
            self.assertNotEqual(full.windows_fingerprints(root), before)
            changed.unlink()
            with self.assertRaises(full.FullError):
                full.windows_fingerprints(root)
            changed.write_bytes(b"")
            with self.assertRaises(full.FullError):
                full.windows_fingerprints(root)


if __name__ == "__main__":
    unittest.main()
