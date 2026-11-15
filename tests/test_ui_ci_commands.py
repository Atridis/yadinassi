"""Execute CI shell contracts on synthetic inputs, not source-string snapshots."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def command(name):
    text = (ROOT / '.github/workflows/build.yml').read_text(encoding='utf-8')
    found = re.search(r'^      - name: ' + re.escape(name) + r'\n        run: (.+)$', text, re.M)
    if found is None:
        raise AssertionError('missing single-line CI step: ' + name)
    return found[1]


@unittest.skipUnless(os.name == 'posix' and shutil.which('git'), 'POSIX CI shell')
class UiCiCommandTests(unittest.TestCase):
    def test_asset_guard_rejects_modified_staged_and_untracked_outputs(self):
        guard = command('Require committed assets to match their source')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
            def accepted():
                return subprocess.run(['sh', '-c', guard], cwd=root).returncode == 0
            git('init', '-q')
            asset = root / 'yadinassi/ui/assets/app.js'
            asset.parent.mkdir(parents=True)
            asset.write_text('original', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
            self.assertTrue(accepted())
            asset.write_text('modified', encoding='utf-8')
            self.assertFalse(accepted())
            git('add', '.')
            self.assertFalse(accepted())
            git('restore', '--staged', '.')
            git('restore', '.')
            (asset.parent / 'forgotten.js').write_text('new', encoding='utf-8')
            self.assertFalse(accepted())

    def test_shell_discovers_all_frontend_and_support_suites(self):
        run = command('Test every client and browser support suite')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ['frontend/catalog/test/presentation.test.mjs',
                     'frontend/main-demo/test/styles.test.mjs',
                     'frontend/new-surface/test/future.test.mjs',
                     'tests/browser_ui/support.test.mjs',
                     'tests/browser_ui/new-support.test.mjs']
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            binary = root / 'bin'
            binary.mkdir()
            node = binary / 'node'
            node.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding='utf-8')
            node.chmod(0o700)
            result = subprocess.run(['sh', '-c', run], cwd=root, env={**os.environ, 'PATH': str(binary)+os.pathsep+os.environ['PATH']}, check=True, text=True, capture_output=True)
            self.assertEqual(result.stdout.splitlines(), ['--test'] + sorted(paths))
