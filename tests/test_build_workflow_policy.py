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


LINUX_OWNERSHIP_STEP_NAME = '      - name: Verify strict Linux-owned SQLite client replay\n'
LINUX_OWNERSHIP_CONDITION = "matrix.target == 'linux'"
LINUX_OWNERSHIP_STEP = (
    LINUX_OWNERSHIP_STEP_NAME
    + '        if: ' + LINUX_OWNERSHIP_CONDITION + '\n'
    "        shell: bash\n"
    "        run: |\n"
    "          python -I -B - <<'PY'\n"
    "          from pathlib import Path\n"
    "          import sys\n"
    "\n"
    "          root = Path.cwd().resolve(strict=True)\n"
    "          sys.path.insert(0, str(root / 'scripts'))\n"
    "          import native_1c_full_host as host\n"
    "\n"
    "          host.verify_client_interpreter(root, root / host.CLIENT_SOURCE,\n"
    "                                         host.PREPROCESSOR_SOURCE_SHA256)\n"
    "          PY\n"
)
LIGHT_PARTITION_STEP = (
    '      - name: Run every light module (unknown tests included)\n'
    '        id: partition\n'
    '        run: python -m scripts.test_partition --tier light --report test-results/partition.json\n'
)


def assert_linux_ownership_step(case, steps):
    # The exact verifier must be a direct, mandatory Linux step. The exact
    # adjacent partition step has no condition or error bypass: GitHub runs it
    # only on success, leaving nothing for stamp/upload if the verifier fails.
    case.assertEqual(steps.count(LINUX_OWNERSHIP_STEP_NAME), 1)
    case.assertIn(LINUX_OWNERSHIP_STEP + LIGHT_PARTITION_STEP + '      - ', steps)


def assert_concurrency_contract(case, source):
    case.assertEqual(source.count(CONCURRENCY), 1)
    # Only a top-level block between the existing permissions and env sections.
    case.assertIn("\npermissions:\n  contents: read\n\n" + CONCURRENCY + "\nenv:\n", source)
    remainder = source.replace(CONCURRENCY, '', 1)
    for forbidden in ('concurrency:', 'cancel-in-progress:'):
        case.assertNotIn(forbidden, remainder)


def assert_error_bypass_contract(case, source):
    """The known-divergence report is the only permitted nonblocking job."""
    advisory = '\n  compatibility:\n'
    case.assertEqual(source.count(advisory), 1)
    block = re.split(r'\n  [a-z][a-z0-9-]*:\n', source.split(advisory, 1)[1], maxsplit=1)[0]
    header = block.split('    steps:\n', 1)[0]
    case.assertEqual(re.findall(r'(?m)^    continue-on-error: (.+)$', header), ['true'])
    case.assertEqual(source.count('continue-on-error'), 1)
    # Do not let an advisory result be a direct or transitive dependency
    # of required validation/release. Cover flow and block needs lists.
    for needs in re.findall(r'(?m)^    needs:[^\n]*(?:\n {6,}[^\n]*)*', source):
        case.assertNotRegex(needs, r'(?<![\w-])compatibility(?![\w-])')
    case.assertNotIn('needs.compatibility', source)


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
        self.assertEqual(events, "  push:\n    branches: [main]\n    tags: ['**']\n  pull_request:\n    types: [opened, synchronize, reopened, ready_for_review]\n  workflow_dispatch:\n")

    def test_all_three_matrices_come_from_validated_admission(self):
        admission = self.source.split('\n  admission:\n', 1)[1].split('\n  light:\n', 1)[0]
        for output in ('light_matrix', 'heavy_matrix'):
            self.assertIn('      ' + output + ': ${{ steps.admit.outputs.' + output + ' }}\n', admission)
        for job, output in (('light', 'light_matrix'), ('heavy', 'heavy_matrix'), ('build', 'light_matrix')):
            block = self.source.split('\n  ' + job + ':\n', 1)[1]
            block = re.split(r'\n  [a-z][a-z0-9-]*:\n', block, maxsplit=1)[0]
            header, steps = block.split('    steps:\n', 1)
            self.assertIn('    runs-on: ${{ matrix.os }}\n', header)
            self.assertIn('      fail-fast: false\n', header)
            self.assertEqual(re.findall(r'^      matrix: (.+)$', header, re.M),
                             ['${{ fromJSON(needs.admission.outputs.' + output + ') }}'])
            self.assertNotRegex(header, r'(?m)^\s*(include|exclude)\s*:')
            # Only diagnostic stamp/upload may run after an ordinary failure.
            expected_conditions = []
            if job == 'light':
                assert_linux_ownership_step(self, steps)
                expected_conditions.append(LINUX_OWNERSHIP_CONDITION)
            if job != 'build':
                expected_conditions.extend([
                    "${{ !cancelled() && (steps.partition.outcome == 'success' || steps.partition.outcome == 'failure') && hashFiles('test-results/partition.json') != '' }}",
                    "${{ !cancelled() && steps.stamp.outcome == 'success' }}",
                ])
            self.assertEqual(re.findall(r'^        if: (.+)$', steps, re.M), expected_conditions)
            if job != 'light':
                self.assertIn("    if: needs.admission.outputs.heavy == 'true'\n", header)
        # Package and light consume the SAME matrix, including ARM on every tag.
        # Runtime route/ref/phase and complete matrix contents are checked in
        # test_ci_test_gate; no workflow input may override platform selection.
        self.assertNotIn('inputs.', self.source)
        self.assertNotIn('--platforms', self.source)

    def test_linux_ownership_cannot_be_moved_or_bypassed(self):
        steps = self.source.split('\n  light:\n', 1)[1].split('\n  heavy:\n', 1)[0].split('    steps:\n', 1)[1]
        mutations = {
            'removed verifier': steps.replace(LINUX_OWNERSHIP_STEP, ''),
            'verifier after partition': steps.replace(LINUX_OWNERSHIP_STEP + LIGHT_PARTITION_STEP,
                                                       LIGHT_PARTITION_STEP + LINUX_OWNERSHIP_STEP),
            'Linux verdict skips verifier': steps.replace(LINUX_OWNERSHIP_CONDITION, "matrix.target == 'windows'"),
            'ignored verifier exit': steps.replace("<<'PY'\n", "<<'PY' || true\n"),
            'nonblocking verifier': steps.replace(LINUX_OWNERSHIP_STEP_NAME,
                                                   LINUX_OWNERSHIP_STEP_NAME + '        continue-on-error: true\n'),
            'partition ignores verifier failure': steps.replace('        id: partition\n',
                                 '        id: partition\n        if: ${{ always() }}\n'),
        }
        for label, candidate in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(candidate, steps)
                with self.assertRaises(AssertionError):
                    assert_linux_ownership_step(self, candidate)

    def test_no_skip_paths_or_error_bypass(self):
        for forbidden in ('paths:', 'paths-ignore:', 'branches-ignore:',
                          'tags-ignore:', 'pull_request_target:',
                          'workflow_run:', 'pull_request.draft'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)
        assert_error_bypass_contract(self, self.source)

    def test_error_bypass_is_rejected_outside_advisory_and_in_gate_dependencies(self):
        flag = '    continue-on-error: true\n'
        mutations = {
            'required job': self.source.replace('\n  light:\n', '\n  light:\n' + flag),
            'advisory step': self.source.replace(flag, '', 1).replace(
                '      - name: Compare historical ValueTable ordering with 1C\n',
                '      - name: Compare historical ValueTable ordering with 1C\n  ' + flag
            ),
            'verdict depends on advisory': self.source.replace(
                'build, regex-python310, javascript]', 'build, regex-python310, javascript, compatibility]'
            ),
            'release depends on advisory': self.source.replace(
                'needs: [build, regex-python310, verdict]',
                'needs:\n      - build\n      - regex-python310\n      - verdict\n      - compatibility'
            ),
        }
        for label, source in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(source, self.source)
                with self.assertRaises(AssertionError):
                    assert_error_bypass_contract(self, source)

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
        self.assertEqual(commands.count('python integrational_tests/check_launcher.py'), 1)
        self.assertEqual(commands.count('python scripts/build.py --target ${{ matrix.target }}'), 1)
        self.assertIn('python -m scripts.test_partition --tier light --report test-results/partition.json', commands)
        self.assertIn('python -m scripts.test_partition --tier heavy --shard-count ${{ matrix.shard_count }} --shard-index ${{ matrix.shard_index }} --report test-results/partition.json', commands)
        self.assertNotIn('python -m scripts.run_tests discover -s tests -v', commands)
        self.assertEqual(commands.count('python -m pip install -e ".[build]" wcwidth==0.8.2'), 1)
        self.assertIn('sha256sum yadinassi-* > SHA256SUMS', commands)
        self.assertIn('          persist-credentials: false\n', self.source)
        self.assertIn('\npermissions:\n  contents: read\n', self.source)
        self.assertIn('      - uses: actions/upload-artifact@v7\n', self.source)
        self.assertIn('          path: ${{ steps.package.outputs.archive-path }}\n', self.source)
        self.assertIn('          if-no-files-found: error\n', self.source)

    def test_release_still_needs_successful_matrix_and_v_tag_push(self):
        release = self.source.split('\n  release:\n', 1)[1]
        self.assertIn("    if: startsWith(github.ref, 'refs/tags/v') && github.event_name == 'push'\n    needs: [build, regex-python310, verdict]\n", release)
        self.assertIn('    permissions:\n      contents: write\n', release)
        self.assertIn('gh release create "$RELEASE_TAG" --verify-tag', release)
        self.assertIn('gh release upload "$RELEASE_TAG" artifacts/* --clobber', release)
        self.assertNotIn('always()', release)


if __name__ == '__main__':
    unittest.main()
