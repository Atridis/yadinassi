"""Keep ordinary build scheduling separate from validation/release policy.

These source-contract tests need no YAML dependency. GitHub interprets the
explicit filters; this test deliberately does not implement a second matcher.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build.yml'


# Deliberately exact source contract, not a second YAML/expression interpreter.
# Changes to this expression require reviewing GitHub concurrency semantics.
FIRST_PR_ATTEMPT = "github.event_name == 'pull_request' && github.run_attempt == '1'"
CONCURRENCY = (
    "concurrency:\n"
    "  group: yadinassi-build-${{ github.event_name }}-${{ "
    + FIRST_PR_ATTEMPT
    + " && format('pr-{0}', github.event.pull_request.number)"
    " || format('run-{0}-attempt-{1}', github.run_id, github.run_attempt) }}\n"
    "  cancel-in-progress: ${{ " + FIRST_PR_ATTEMPT + " }}\n"
)


def assert_concurrency_contract(case, source):
    case.assertEqual(source.count(CONCURRENCY), 1)
    # Only a top-level block between the existing permissions and env sections.
    case.assertIn("\npermissions:\n  contents: read\n\n" + CONCURRENCY + "\nenv:\n", source)
    remainder = source.replace(CONCURRENCY, '', 1)
    for forbidden in ('concurrency:', 'cancel-in-progress:'):
        case.assertNotIn(forbidden, remainder)


def scheduling_example(event, run_id, attempt, pr=None):
    """Semantic examples for the exact expression above, not GitHub emulation.

    run_id survives a retry; run_attempt increments. Distinct isolated groups
    also prevent GitHub's pending-member replacement (even without cancellation).
    """
    shared = event == 'pull_request' and str(attempt) == '1'
    suffix = f'pr-{pr}' if shared else f'run-{run_id}-attempt-{attempt}'
    return f'yadinassi-build-{event}-{suffix}', shared


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

    def test_no_skip_paths_or_error_bypass(self):
        for forbidden in ('paths:', 'paths-ignore:', 'branches-ignore:',
                          'tags-ignore:', 'continue-on-error:', 'pull_request_target:',
                          'workflow_run:', 'pull_request.draft'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_only_exact_top_level_first_attempt_pr_concurrency(self):
        assert_concurrency_contract(self, self.source)

    def test_same_pr_first_attempts_share_group_and_cancel(self):
        first = scheduling_example('pull_request', 100, 1, 132)
        later = scheduling_example('pull_request', 101, 1, 132)
        self.assertEqual(first, ('yadinassi-build-pull_request-pr-132', True))
        self.assertEqual(first, later)
        self.assertNotEqual(first[0], scheduling_example('pull_request', 102, 1, 133)[0])

    def test_old_retries_cannot_cancel_or_displace_current_pr(self):
        current = scheduling_example('pull_request', 101, 1, 132)
        old_retry = scheduling_example('pull_request', 100, 2, 132)
        another_retry = scheduling_example('pull_request', 100, 3, 132)
        current_retry = scheduling_example('pull_request', 101, 2, 132)
        self.assertEqual(old_retry, ('yadinassi-build-pull_request-run-100-attempt-2', False))
        self.assertEqual(len({item[0] for item in (current, old_retry, another_retry, current_retry)}), 4)
        self.assertFalse(another_retry[1])
        self.assertFalse(current_retry[1])

    def test_main_tag_manual_and_cross_event_runs_are_isolated(self):
        examples = []
        # Main and tags both use push. No ref enters the group: each distinct
        # run/attempt remains isolated even for successive pushes to one ref.
        for route, event, run_id in (('main', 'push', 200),
                                     ('tag', 'push', 300),
                                     ('manual', 'workflow_dispatch', 400)):
            for offset in (0, 1):
                for attempt in (1, 2):
                    with self.subTest(route=route, offset=offset, attempt=attempt):
                        group, cancel = scheduling_example(event, run_id + offset, attempt)
                        self.assertFalse(cancel)
                        examples.append(group)
        self.assertEqual(len(set(examples)), len(examples))
        # Explicit event namespace also distinguishes hypothetical equal IDs.
        groups = [scheduling_example(event, 100, 2, 132)[0]
                  for event in ('push', 'workflow_dispatch', 'pull_request')]
        self.assertEqual(len(set(groups)), 3)

    def test_broader_malformed_and_job_level_policies_are_rejected(self):
        mutations = {
            'missing': self.source.replace(CONCURRENCY, ''),
            'unconditional cancellation': self.source.replace(
                'cancel-in-progress: ${{ ' + FIRST_PR_ATTEMPT + ' }}', 'cancel-in-progress: true'),
            'all PR attempts': self.source.replace(" && github.run_attempt == '1'", ''),
            'group omits attempt': self.source.replace(
                "format('run-{0}-attempt-{1}', github.run_id, github.run_attempt)",
                "format('run-{0}', github.run_id)"),
            'shared refs': self.source.replace('github.run_id, github.run_attempt', 'github.ref, github.run_attempt'),
            'all branches': self.source.replace('github.event.pull_request.number', 'github.head_ref'),
            'wrong namespace': self.source.replace('yadinassi-build-', 'native-1c-'),
            'duplicate': self.source.replace(CONCURRENCY, CONCURRENCY * 2),
            'indented block': self.source.replace(CONCURRENCY, '  ' + CONCURRENCY.replace('\n', '\n  ').rstrip() + '\n'),
            'job sibling cancellation': self.source.replace(
                '\n  build:\n', '\n  build:\n    concurrency: same-matrix-group\n'),
            'job cancellation flag': self.source.replace(
                '\n  build:\n', '\n  build:\n    cancel-in-progress: true\n'),
            'release concurrency': self.source.replace(
                '\n  release:\n', '\n  release:\n    concurrency: shared-release\n'),
            'wrong location': self.source.replace(CONCURRENCY, '').replace('jobs:\n', CONCURRENCY + '\njobs:\n'),
        }
        for label, source in mutations.items():
            with self.subTest(mutation=label):
                with self.assertRaises(AssertionError):
                    assert_concurrency_contract(self, source)

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
