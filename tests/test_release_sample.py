"""The release sample is independent of native scenario discovery."""
import hashlib
from pathlib import Path
import unittest

from integrational_tests.test_launcher import collect_scripts
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]


class ReleaseSampleTests(unittest.TestCase):
    def test_source_and_owner_fixture_are_preserved_byte_for_byte(self):
        # Existing Git blob identities establish provenance, not new native data.
        for path, sha in (
            ('basic.bsl', '62730fcfa3943bc674f2eb03b1da249bbe5df1e7'),
            ('tests/fixtures/basic.out', 'ea90add03d8036f78ec7e6c61cd67bc974fbd6bc'),
        ):
            data = (ROOT / path).read_bytes()
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode()
                                         + b'\0' + data).hexdigest(), sha)

    def test_sample_is_not_an_integration_scenario(self):
        self.assertFalse((ROOT / 'integrational_tests/tests/basic.bsl').exists())
        self.assertFalse((ROOT / 'integrational_tests/output/basic.out').exists())
        scripts = collect_scripts(ROOT / 'integrational_tests/tests')
        self.assertEqual({p.stem for p in scripts},
                         {'functions', 'strings', 'collections', 'numbers', 'dates', 'values'})
        self.assertTrue(all(p.parent == ROOT / 'integrational_tests/tests' for p in scripts))
        # Owner-uploaded source copies must not be confused with executable input
        # discovery or with native .out evidence.
        self.assertNotIn(ROOT / 'integrational_tests/output/basic.bsl', scripts)

    def test_third_doubling_remains_checked_against_genuine_fixture(self):
        output = []
        Interpreter(output=output.append).execute((ROOT / 'basic.bsl').read_text(encoding='utf-8'))
        expected = (ROOT / 'tests/fixtures/basic.out').read_text(encoding='utf-8').splitlines()
        self.assertEqual(output, expected)
        self.assertEqual(len(output), 18)
        self.assertTrue(output[6].startswith('СуммаДробное3: '))

    def test_build_and_smoke_use_independent_sample_path(self):
        for relative in ('scripts/build.py', 'scripts/smoke_test.py'):
            source = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('ROOT / "basic.bsl"', source)
            self.assertNotIn('ROOT / "integrational_tests" / "tests" / "basic.bsl"', source)
        self.assertIn('(ROOT / "basic.bsl", "basic.bsl")',
                      (ROOT / 'scripts/build.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
