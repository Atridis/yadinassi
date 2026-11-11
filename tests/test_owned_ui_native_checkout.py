"""Exact authored UI packets survive Windows checkout without normalizing readers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git'), 'actual checkout requires git')
class OwnedUINativeCheckoutTests(unittest.TestCase):
    def sources(self):
        return sorted(path.relative_to(ROOT).as_posix()
                      for folder in ('dialog_packet', 'form_results_packet')
                      for path in (ROOT / 'scripts' / folder).rglob('*')
                      if path.is_file() and path.suffix in ('.xml', '.bsl'))

    def git(self, cwd, *args, data=None):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run(['git', *args], cwd=cwd, env=env, input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        return result.stdout

    def test_every_authored_packet_has_exact_lf_checkout_policy(self):
        names = self.sources()
        self.assertEqual(len(names), 14)  # five dialog files + observer + eight form-result files
        with tempfile.TemporaryDirectory(prefix='owned-ui-attributes-') as temporary:
            root = Path(temporary)
            (root / '.gitattributes').write_bytes((ROOT / '.gitattributes').read_bytes())
            self.git(root, 'init', '-q')
            raw = self.git(root, 'check-attr', '-z', '--stdin', 'text', 'eol',
                           data=b'\0'.join(name.encode('utf-8') for name in names) + b'\0')
            parts = raw.decode('utf-8').split('\0')[:-1]
            values = {(parts[i], parts[i + 1]): parts[i + 2] for i in range(0, len(parts), 3)}
            for name in names:
                self.assertEqual(values[name, 'text'], 'set', name)
                self.assertEqual(values[name, 'eol'], 'lf', name)

    def test_autocrlf_checkout_preserves_packet_bytes(self):
        names = self.sources()
        with tempfile.TemporaryDirectory(prefix='owned-ui-checkout-') as temporary:
            root = Path(temporary)
            self.git(root, 'init', '-q')
            self.git(root, 'config', 'core.autocrlf', 'true')
            (root / '.gitattributes').write_bytes((ROOT / '.gitattributes').read_bytes())
            expected = {}
            for name in names:
                raw = (ROOT / name).read_bytes()
                raw.decode('utf-8')
                self.assertNotIn(b'\r\n', raw, name)
                expected[name] = hashlib.sha256(raw).hexdigest()
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            self.git(root, 'add', '.gitattributes', *names)
            for name in names:
                (root / name).unlink()
            self.git(root, 'checkout-index', '-a', '-f')
            for name, digest in expected.items():
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)

    def test_form_result_lane_does_not_repurpose_historical_bootstrap(self):
        provenance = json.loads((ROOT / 'tests/fixtures/accumulation_register/provenance.json').read_bytes())
        name = 'scripts/native_1c_bootstrap/run_stage.py'
        expected = provenance['native_report']['stage3']['input_sha256'][name]
        self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
        self.assertNotIn('form_results', (ROOT / name).read_text(encoding='utf-8'))
        dedicated = (ROOT / 'scripts/native_1c_bootstrap/run_form_results_stage.py').read_text(encoding='utf-8')
        self.assertIn('import form_results_suite as form_lane', dedicated)
