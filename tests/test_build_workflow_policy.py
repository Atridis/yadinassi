"""Keep build trigger deduplication separate from validation/release policy.

These source-contract tests need no YAML dependency. GitHub interprets the
explicit filters; this test deliberately does not implement a second matcher.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build.yml'


class BuildWorkflowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text(encoding='utf-8')

    def test_main_all_tags_pr_and_manual_routes(self):
        events = self.source.split('\non:\n', 1)[1].split('\npermissions:\n', 1)[0]
        # ** preserves every tag, including non-v and slash-containing names.
        # PR/manual remain unfiltered; non-main branch pushes are intentionally
        # absent, even before a PR is opened.
        self.assertEqual(events, "  push:\n    branches: [main]\n    tags: ['**']\n  pull_request:\n  workflow_dispatch:\n")

    def test_every_route_keeps_all_four_platforms(self):
        build = self.source.split('\n  build:\n', 1)[1].split('\n  release:\n', 1)[0]
        header, steps = build.split('    steps:\n', 1)
        self.assertIn('    name: ${{ matrix.target }}\n', header)
        self.assertIn('    runs-on: ${{ matrix.os }}\n', header)
        self.assertIn('      fail-fast: false\n', header)
        self.assertNotRegex(header, r'(?m)^\s*exclude\s*:')
        platforms = re.findall(r'          - target: (\S+)\n            os: (\S+)\n            architecture: (\S+)\n', header)
        self.assertEqual(platforms, [('windows', 'windows-2022', 'x64'),
                                     ('linux', 'ubuntu-22.04', 'x64'),
                                     ('mac-x86', 'macos-15-intel', 'x64'),
                                     ('mac-arm', 'macos-14', 'arm64')])
        self.assertNotIn('if:', header)
        self.assertNotIn('        if:', steps)

    def test_no_skip_paths_cancellation_or_error_bypass(self):
        for forbidden in ('paths:', 'paths-ignore:', 'branches-ignore:',
                          'tags-ignore:', 'continue-on-error:', 'concurrency:',
                          'cancel-in-progress:', 'pull_request_target:',
                          'workflow_run:', 'pull_request.draft'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_launcher_unit_binary_and_artifact_steps_remain(self):
        commands = re.findall(r'^        run: (.+)$', self.source, re.M)
        self.assertEqual(commands, [
            'python -m pip install -e ".[build]"',
            'python integrational_tests/check_launcher.py',
            'python -m unittest discover -s tests -v',
            'python scripts/build.py --target ${{ matrix.target }}',
            'sha256sum yadinassi-* > SHA256SUMS', '|'])
        self.assertIn('          persist-credentials: false\n', self.source)
        self.assertIn('\npermissions:\n  contents: read\n', self.source)
        self.assertIn('      - uses: actions/upload-artifact@v7\n', self.source)
        self.assertIn('          path: ${{ steps.package.outputs.archive-path }}\n', self.source)
        self.assertIn('          if-no-files-found: error\n', self.source)

    def test_release_still_needs_successful_matrix_and_v_tag_push(self):
        release = self.source.split('\n  release:\n', 1)[1]
        self.assertIn("    if: startsWith(github.ref, 'refs/tags/v') && github.event_name == 'push'\n    needs: build\n", release)
        self.assertIn('    permissions:\n      contents: write\n', release)
        self.assertIn('gh release create "$RELEASE_TAG" --verify-tag', release)
        self.assertIn('gh release upload "$RELEASE_TAG" artifacts/* --clobber', release)
        self.assertNotIn('always()', release)


if __name__ == '__main__':
    unittest.main()
