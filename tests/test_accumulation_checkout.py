"""Actual checkout policy for immutable accumulation evidence and its sources.

These are local Git fixtures, not a new native 1C acquisition. Raw-byte hash
checks stay strict; neither evidence nor production readers are normalized.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = 'tests/fixtures/accumulation_register/'
IMMUTABLE = {
    FIXTURE + 'observations.out': '1696b237a5912658363738c2603b791540c5f548f83390062e2e1a5cb12b2494',
    FIXTURE + 'provenance.json': 'c55aab6c9b49c5007432ed7ba27524a83ff8444f249cd2a58c72a67be29b6034',
    FIXTURE + 'RuntimeAccumulationRegister.xml': 'dbc670763140778ea4549a78035b28aaac8fd2215c3aa4d595df5cba1509833a',
}


@unittest.skipUnless(shutil.which('git'), 'actual checkout requires git')
class AccumulationCheckoutTests(unittest.TestCase):
    def pinned(self):
        evidence = json.loads((ROOT / (FIXTURE + 'provenance.json')).read_bytes())
        inputs = evidence['native_report']['stage3']['input_sha256']
        hosts = evidence['host_source_sha256']
        self.assertEqual((len(inputs), len(hosts)), (34, 4))
        self.assertFalse(set(inputs) & set(hosts))
        return {**inputs, **hosts, **IMMUTABLE}

    def git(self, cwd, *arguments, data=None):
        environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run(['git', *arguments], cwd=cwd, env=environment,
            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return result.stdout

    def test_all_historical_sources_and_fixtures_have_explicit_checkout_policy(self):
        pinned = self.pinned()
        self.assertEqual(len(pinned), 41)
        with tempfile.TemporaryDirectory(prefix='accumulation-attributes-') as temporary:
            root = Path(temporary)
            (root / '.gitattributes').write_bytes((ROOT / '.gitattributes').read_bytes())
            self.git(root, 'init', '-q')
            raw = self.git(root, 'check-attr', '-z', '--stdin', 'text', 'eol',
                           data=b'\0'.join(name.encode() for name in pinned) + b'\0')
            parts = raw.decode().split('\0')[:-1]
            attributes = {}
            for offset in range(0, len(parts), 3):
                name, key, value = parts[offset:offset + 3]
                attributes.setdefault(name, {})[key] = value
            self.assertEqual(set(attributes), set(pinned))
            for name, digest in pinned.items():
                with self.subTest(path=name):
                    self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
                    if name in IMMUTABLE:
                        self.assertEqual(attributes[name]['text'], 'unset')
                    else:
                        self.assertTrue(attributes[name]['text'] == 'unset' or
                                        attributes[name]['eol'] == 'lf')

    def test_autocrlf_checkout_retains_all_41_exact_byte_hashes(self):
        pinned = self.pinned()
        with tempfile.TemporaryDirectory(prefix='accumulation-autocrlf-') as temporary:
            parent = Path(temporary)
            source, checkout = parent / 'source', parent / 'checkout'
            source.mkdir()
            for name in ('.gitattributes', *pinned):
                destination = source / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / name).read_bytes())
            self.git(source, 'init', '-q')
            self.git(source, '-c', 'core.autocrlf=false', 'add', '.')
            self.git(source, '-c', 'user.name=Accumulation checkout fixture',
                     '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                     'commit', '-qm', 'Local exact accumulation fixture')
            self.git(parent, 'clone', '-q', '--no-hardlinks', '-c', 'core.autocrlf=true',
                     str(source), str(checkout))
            for name, digest in pinned.items():
                with self.subTest(path=name):
                    raw = (checkout / name).read_bytes()
                    self.assertEqual(raw, (ROOT / name).read_bytes())
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
