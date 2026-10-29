"""Offline tests for the separately opted-in, immutable manual and reviewed-push measurement routes."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/native-1c-isolated-smoke.yml"
POLICY = ROOT / "scripts/native_1c_ci_policy.py"
SPEC = importlib.util.spec_from_file_location("manual_native_ci_policy", POLICY)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
SHA = "1234567890abcdef" * 2 + "12345678"
REF = "refs/heads/codex/async-client-measurement"
STANDARD_COMMAND = "python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --client-probe --client-watchdog-check --client-dates-parity --client-values-parity --client-collections-parity --client-numbers-parity --output native-smoke/report.json --export-native-outputs --native-target linux-8.3.27.1508 --comparison-mode typed-map-order-v1"
MEASUREMENT_COMMAND = "python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --client-probe --client-async-measurement --output native-smoke/report.json --export-native-outputs --native-target linux-8.3.27.1508 --comparison-mode typed-map-order-v1"


def fixture(sha=SHA):
    owner = {"login": "Atridis", "id": 30860798, "type": "User"}
    inputs = {"client_async_measurement": "true", "reviewed_sha": sha}
    event = {
        "repository": {"full_name": "Atridis/yadinassi", "id": 359770628, "fork": False, "owner": owner},
        "sender": copy.deepcopy(owner), "ref": REF, "inputs": inputs,
    }
    context = {
        "GITHUB_REPOSITORY": "Atridis/yadinassi", "GITHUB_REPOSITORY_ID": "359770628",
        "GITHUB_REPOSITORY_OWNER": "Atridis", "GITHUB_REPOSITORY_OWNER_ID": "30860798",
        "GITHUB_ACTOR": "Atridis", "GITHUB_ACTOR_ID": "30860798", "NATIVE_TRIGGERING_ACTOR": "Atridis",
        "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": sha,
        "GITHUB_REF": REF, "GITHUB_REF_TYPE": "branch", "GITHUB_BASE_REF": "", "GITHUB_HEAD_REF": "",
        "GITHUB_WORKFLOW_REF": f"Atridis/yadinassi/.github/workflows/native-1c-isolated-smoke.yml@{REF}",
        "GITHUB_WORKFLOW_SHA": sha,
        "NATIVE_DISPATCH_INPUTS": json.dumps({"client_async_measurement": True, "reviewed_sha": sha}),
    }
    return event, context


def environment(context):
    essentials = {key: value for key, value in os.environ.items()
                  if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    return {**essentials, **context}


def inline_admission():
    block = WORKFLOW.read_text().split("\n  eligibility:\n", 1)[1].split("\n  smoke:\n", 1)[0]
    return textwrap.dedent(block.split("        run: |\n", 1)[1]).split("<<'PYTHON'\n", 1)[1].split("\nPYTHON", 1)[0]


REVIEWED_REF = "refs/heads/codex/native-client-async-reviewed"


def push_fixture(sha=SHA):
    event, context = fixture(sha)
    event.pop("inputs")
    event.update(ref=REVIEWED_REF, after=sha, head_commit={"id": sha}, deleted=False, forced=False)
    context.update(GITHUB_EVENT_NAME="push", GITHUB_REF=REVIEWED_REF,
                   GITHUB_WORKFLOW_REF=f"Atridis/yadinassi/.github/workflows/native-1c-isolated-smoke.yml@{REVIEWED_REF}")
    context.pop("NATIVE_DISPATCH_INPUTS")
    return event, context


class ReviewedPushAdmissionTests(unittest.TestCase):
    def test_exact_owner_reviewed_push_and_immutable_binding(self):
        event, context = push_fixture()
        self.assertEqual(policy.validate_admission(event, context), "push")
        policy.validate_binding(event, context, SHA, ["2" * 40], "")
        for commit, status in (("2" * 40, ""), (SHA, "?? injected.py"), (SHA, " M tracked.py")):
            with self.subTest(commit=commit, status=status), self.assertRaises(policy.PolicyError):
                policy.validate_binding(event, context, commit, [], status)

    def test_force_delete_missing_and_nonboolean_flags_fail_closed(self):
        for flag in ("forced", "deleted"):
            for value in (None, True, "false", "true", 0, 1, [], {}):
                event, context = push_fixture()
                event[flag] = value
                with self.subTest(flag=flag, value=value), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)
            event, context = push_fixture()
            del event[flag]
            with self.subTest(missing=flag), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_only_exact_reviewed_ref_not_working_branch_or_tag(self):
        for ref in (REVIEWED_REF + "/child", REVIEWED_REF + "-extra", REVIEWED_REF.upper(),
                    "refs/heads/codex/native-client-async-measurement", "refs/tags/codex/native-client-async-reviewed",
                    REVIEWED_REF.removeprefix("refs/heads/"), None, [], "", "refs/pull/90/merge"):
            event, context = push_fixture()
            event["ref"] = ref
            context["GITHUB_REF"] = ref
            with self.subTest(ref=ref), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for target in ("event", "context"):
            event, context = push_fixture()
            if target == "event":
                event["ref"] = "refs/heads/main"
            else:
                context["GITHUB_REF"] = "refs/heads/main"
            with self.subTest(target=target), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_same_repository_owner_and_actor_ids_remain_mandatory(self):
        for key in ("GITHUB_REPOSITORY", "GITHUB_REPOSITORY_ID", "GITHUB_REPOSITORY_OWNER",
                    "GITHUB_REPOSITORY_OWNER_ID", "GITHUB_ACTOR", "GITHUB_ACTOR_ID", "NATIVE_TRIGGERING_ACTOR"):
            event, context = push_fixture()
            context[key] = "other"
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key, value in (("fork", True), ("id", 1), ("id", "359770628"), ("full_name", "fork/yadinassi"), ("owner", {})):
            event, context = push_fixture()
            event["repository"][key] = value
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        event, context = push_fixture()
        event["sender"]["id"] = 1
        with self.assertRaises(policy.PolicyError):
            policy.validate_admission(event, context)

    def test_push_and_workflow_revisions_and_branch_context_are_exact(self):
        for key, value in (("GITHUB_SHA", "2" * 40), ("GITHUB_WORKFLOW_SHA", "2" * 40),
                           ("GITHUB_WORKFLOW_REF", "Atridis/yadinassi/.github/workflows/native-1c-isolated-smoke.yml@refs/heads/main"),
                           ("GITHUB_REF_TYPE", "tag"), ("GITHUB_BASE_REF", "main"), ("GITHUB_HEAD_REF", "topic")):
            event, context = push_fixture()
            context[key] = value
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key, value in (("after", "2" * 40), ("head_commit", {"id": "2" * 40}), ("head_commit", None)):
            event, context = push_fixture()
            event[key] = value
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_inline_reviewed_push_isolated_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "json.py").write_text("raise RuntimeError('candidate code ran')")
            event_path = root / "event.json"
            for mode in ("approved", "forced", "deleted", "stale", "fork"):
                event, context = push_fixture()
                if mode in ("forced", "deleted"):
                    event[mode] = True
                elif mode == "stale":
                    context["GITHUB_WORKFLOW_SHA"] = "2" * 40
                elif mode == "fork":
                    event["repository"]["fork"] = True
                event_path.write_text(json.dumps(event))
                context["GITHUB_EVENT_PATH"] = str(event_path)
                result = subprocess.run([sys.executable, "-I", "-B", "-c", inline_admission()], cwd=root,
                                        env=environment(context), capture_output=True, timeout=30)
                with self.subTest(mode=mode):
                    self.assertEqual(result.returncode, 0 if mode == "approved" else 1, result.stderr)
                    self.assertNotIn(b"candidate code ran", result.stderr)


class ManualAdmissionTests(unittest.TestCase):
    def test_explicit_owner_opt_in_binds_reviewed_branch_revision(self):
        for ref in (REF, REF.removeprefix("refs/heads/")):
            event, context = fixture()
            event["ref"] = ref
            with self.subTest(ref=ref):
                self.assertEqual(policy.validate_admission(event, context), "workflow_dispatch")
                policy.validate_binding(event, context, SHA, ["2" * 40], "")

    def test_missing_false_or_nonboolean_opt_in_is_rejected(self):
        for value in (None, "false", False, True, "True", "1", 1, 0, "", [], {}, "true\n"):
            event, context = fixture()
            event["inputs"]["client_async_measurement"] = value
            with self.subTest(raw=value), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for value in (None, False, "true", "false", 1, 0, [], {}):
            event, context = fixture()
            context["NATIVE_DISPATCH_INPUTS"] = json.dumps({"client_async_measurement": value, "reviewed_sha": SHA})
            with self.subTest(typed=value), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key in ("client_async_measurement", "reviewed_sha"):
            event, context = fixture()
            del event["inputs"][key]
            with self.subTest(missing=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_inputs_schema_is_exact_and_json_is_not_evaluated(self):
        for value in (None, [], {}, "true", {"client_async_measurement": "true", "reviewed_sha": SHA, "command": "id"}):
            event, context = fixture()
            event["inputs"] = value
            with self.subTest(event_inputs=value), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for value in (None, "", "not-json SECRET", "null", "[]", "true", "{}",
                      json.dumps({"client_async_measurement": True, "reviewed_sha": SHA, "command": "id"}),
                      '{"client_async_measurement":true,"client_async_measurement":true,"reviewed_sha":"' + SHA + '"}'):
            event, context = fixture()
            context["NATIVE_DISPATCH_INPUTS"] = value
            with self.subTest(typed_inputs=value), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_exact_nonzero_lowercase_reviewed_sha_is_required(self):
        for value in (None, "", "0" * 40, SHA.upper(), "a" * 39, "a" * 41, "2" * 40, 1, True, [], "$(id)"):
            event, context = fixture()
            event["inputs"]["reviewed_sha"] = value
            context["NATIVE_DISPATCH_INPUTS"] = json.dumps({"client_async_measurement": True, "reviewed_sha": value})
            with self.subTest(reviewed_sha=value), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key in ("GITHUB_SHA", "GITHUB_WORKFLOW_SHA"):
            event, context = fixture()
            context[key] = "2" * 40
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_forks_nonowners_and_different_repositories_are_rejected(self):
        for key in ("GITHUB_REPOSITORY", "GITHUB_REPOSITORY_ID", "GITHUB_REPOSITORY_OWNER",
                    "GITHUB_REPOSITORY_OWNER_ID", "GITHUB_ACTOR", "GITHUB_ACTOR_ID", "NATIVE_TRIGGERING_ACTOR"):
            event, context = fixture()
            context[key] = "other"
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key, value in (("full_name", "outside/yadinassi"), ("id", 1), ("id", "359770628"),
                           ("fork", True), ("fork", 0), ("owner", {})):
            event, context = fixture()
            event["repository"][key] = value
            with self.subTest(repository_field=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key, value in (("login", "outside"), ("id", 1), ("id", "30860798"), ("type", "Bot")):
            event, context = fixture()
            event["sender"][key] = value
            with self.subTest(sender_field=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_only_same_repository_branch_ref_is_admitted(self):
        for ref in (None, "", SHA, "refs/tags/v1", "refs/pull/72/merge", "refs/heads/", "refs/heads/a//b",
                    "refs/heads/a/../b", "refs/heads/a.lock", "refs/heads/.a", "refs/heads/a/", "refs/heads/a.",
                    "refs/heads/a@{1}", "refs/heads/a\n$(id)", "refs/heads/a b", "refs/heads/" + "a" * 241):
            event, context = fixture()
            event["ref"] = ref
            context["GITHUB_REF"] = ref
            with self.subTest(ref=ref), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key, value in (("GITHUB_REF_TYPE", "tag"), ("GITHUB_REF_TYPE", ""),
                           ("GITHUB_BASE_REF", "main"), ("GITHUB_HEAD_REF", "fork"),
                           ("GITHUB_WORKFLOW_REF", f"other/yadinassi/.github/workflows/native-1c-isolated-smoke.yml@{REF}"),
                           ("GITHUB_WORKFLOW_REF", "Atridis/yadinassi/.github/workflows/native-1c-isolated-smoke.yml@refs/heads/main")):
            event, context = fixture()
            context[key] = value
            with self.subTest(key=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for ref in ("main", "refs/heads/main", "refs/tags/codex/async-client-measurement", SHA):
            event, context = fixture()
            event["ref"] = ref
            with self.subTest(event_ref=ref), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_other_events_cannot_reuse_manual_inputs(self):
        for name in ("push", "pull_request", "pull_request_target", "workflow_run", "workflow_call", "repository_dispatch", ""):
            event, context = fixture()
            context["GITHUB_EVENT_NAME"] = name
            with self.subTest(event=name), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_immutable_binding_rejects_wrong_or_dirty_checkout(self):
        event, context = fixture()
        for commit, status in (("2" * 40, ""), (SHA, " M scripts/native_1c_smoke.py"), (SHA, "?? added.py")):
            with self.subTest(commit=commit, status=status), self.assertRaises(policy.PolicyError):
                policy.validate_binding(event, context, commit, [], status)

    def test_actual_inline_admission_runs_isolated_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "json.py").write_text("raise RuntimeError('candidate code ran')")
            event_path = root / "event.json"
            for mode in ("approved", "false", "missing", "stale", "fork", "typed_string"):
                event, context = fixture()
                if mode == "false":
                    event["inputs"]["client_async_measurement"] = "false"
                if mode == "missing":
                    del event["inputs"]["reviewed_sha"]
                if mode == "stale":
                    context["GITHUB_SHA"] = "2" * 40
                if mode == "fork":
                    event["repository"]["fork"] = True
                if mode == "typed_string":
                    context["NATIVE_DISPATCH_INPUTS"] = json.dumps(event["inputs"])
                event_path.write_text(json.dumps(event))
                context["GITHUB_EVENT_PATH"] = str(event_path)
                result = subprocess.run([sys.executable, "-I", "-B", "-c", inline_admission()], cwd=root,
                                        env=environment(context), capture_output=True, timeout=30)
                with self.subTest(mode=mode):
                    self.assertEqual(result.returncode, 0 if mode == "approved" else 1, result.stderr)
                    self.assertNotIn(b"candidate code ran", result.stderr)

    def test_actual_binder_cli_accepts_only_reviewed_clean_git_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "repo"
            checkout.mkdir()
            hooks = root / "empty-hooks"
            hooks.mkdir()
            env = environment({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"})
            def git(*arguments):
                return subprocess.run(["git", "-c", "user.name=Native CI Test", "-c", "user.email=native-ci@example.invalid",
                                       "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}", *arguments],
                                      cwd=checkout, env=env, check=True, capture_output=True, timeout=30).stdout.decode().strip()
            git("init", "-q", "-b", REF.removeprefix("refs/heads/"))
            (checkout / "source.txt").write_text("reviewed\n")
            git("add", ".")
            git("commit", "-qm", "reviewed")
            sha = git("rev-parse", "HEAD")
            event, context = fixture(sha)
            event_path = root / "event.json"
            event_path.write_text(json.dumps(event))
            context["GITHUB_EVENT_PATH"] = str(event_path)
            def invoke():
                return subprocess.run([sys.executable, "-I", "-B", str(POLICY), "bind"], cwd=checkout,
                                      env={**env, **context}, capture_output=True, timeout=30)
            self.assertEqual(invoke().returncode, 0)
            (checkout / "source.txt").write_text("unreviewed\n")
            self.assertIn(b"checkout_not_clean", invoke().stderr)
            git("add", ".")
            git("commit", "-qm", "unreviewed")
            self.assertIn(b"checkout_revision_mismatch", invoke().stderr)


class ManualWorkflowTests(unittest.TestCase):
    def test_manual_checks_cannot_satisfy_standard_required_check_names(self):
        source = WORKFLOW.read_text()
        for job, manual_name, standard_name in (
            ("smoke", "Native 1C async measurement", "Native 1C six scenarios"),
            ("verdict", "Native 1C async measurement verdict", "Native 1C required verdict"),
        ):
            block = source.split(f"\n  {job}:\n", 1)[1]
            name = block.splitlines()[0].strip()
            expected = "name: ${{ (github.event_name == 'workflow_dispatch' || (github.event_name == 'push' && github.ref == 'refs/heads/codex/native-client-async-reviewed')) && '" + manual_name + "' || '" + standard_name + "' }}"
            self.assertEqual(name, expected)
            self.assertNotEqual(manual_name, standard_name)

    def test_manual_schema_defaults_off_and_requires_reviewed_sha(self):
        dispatch = WORKFLOW.read_text().split("  workflow_dispatch:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(dispatch, """    inputs:
      client_async_measurement:
        description: Run the separately approved bounded async client measurement
        type: boolean
        required: true
        default: false
      reviewed_sha:
        description: Exact reviewed 40-character commit SHA on the selected same-repository branch
        type: string
        required: true
""")

    def test_standard_and_measurement_commands_are_separate_exact_and_exclusive(self):
        source = WORKFLOW.read_text()
        native = source.split("        id: native\n", 1)[1].split("      - name:", 1)[0]
        measurement = source.split("        id: native_async\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("        if: github.event_name != 'workflow_dispatch' && !(github.event_name == 'push' && github.ref == 'refs/heads/codex/native-client-async-reviewed')\n", native)
        self.assertIn("        if: (github.event_name == 'workflow_dispatch' && inputs.client_async_measurement == true) || (github.event_name == 'push' && github.ref == 'refs/heads/codex/native-client-async-reviewed')\n", measurement)
        self.assertEqual(re.findall(r"^        run: (.*)$", native, re.M), [STANDARD_COMMAND])
        self.assertEqual(re.findall(r"^        run: (.*)$", measurement, re.M), [MEASUREMENT_COMMAND])
        self.assertEqual(source.count("--client-async-measurement"), 1)
        self.assertNotIn("${{", MEASUREMENT_COMMAND)

    def test_manual_admission_and_binding_precede_same_scoped_auth_and_artifacts(self):
        source = WORKFLOW.read_text()
        trees = {}
        legacy = source
        for job in ('tree_smoke', 'tree_copy_smoke'):
            matches = re.findall(r"(?ms)^  " + job + r":\n(.*?)(?=^  [a-z_]+:|\Z)", source)
            self.assertEqual(len(matches), 1)
            trees[job] = "  " + job + ":\n" + matches[0]
            legacy = legacy.replace(trees[job], '', 1)
        self.assertEqual(legacy.count("NATIVE_DISPATCH_INPUTS: ${{ toJSON(inputs) }}"), 2)
        self.assertEqual(legacy.count("GHCR_TOKEN: ${{ github.token }}"), 2)
        upload = "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
        self.assertEqual(legacy.count(upload), 2)
        for job, tree in trees.items():
            self.assertEqual(tree.count(upload), 2)
            self.assertEqual(tree.count("NATIVE_DISPATCH_INPUTS: ${{ toJSON(inputs) }}"), 1)
            self.assertEqual(tree.count("GHCR_TOKEN: ${{ github.token }}"), 1)
            self.assertIn("github.event_name != 'workflow_dispatch' &&", tree)
            self.assertIn("github.ref != 'refs/heads/codex/native-client-async-reviewed' &&", tree)
            self.assertIn("if: always() && steps.tree.outputs.tree_outputs_ready == 'true'", tree)
            if job == 'tree_smoke':
                self.assertIn('run: python3 scripts/native_1c_tree_profile.py --execute-approved-image --export-native-outputs\n', tree)
                self.assertIn('path: native-smoke/tree-report.json\n', tree)
                expected_paths = ['native-smoke/tree-outputs/tree_fill_values.out',
                                  'native-smoke/tree-outputs/provenance.json']
            else:
                self.assertIn('run: python3 scripts/native_1c_tree_profile.py --execute-approved-image --export-native-outputs --profile "$TREE_PROFILE"\n', tree)
                self.assertIn('TREE_PROFILE: ${{ matrix.profile }}\n', tree)
                self.assertIn('path: native-smoke/${{ matrix.artifact }}-report.json\n', tree)
                self.assertIn('      fail-fast: false\n', tree)
                expected_paths = ['native-smoke/${{ matrix.artifact }}-outputs/${{ matrix.case }}.out',
                                  'native-smoke/${{ matrix.artifact }}-outputs/provenance.json']
            output_paths = tree.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
            self.assertEqual([line.strip() for line in output_paths.splitlines()], expected_paths)
        for job in ('smoke', 'tree_smoke', 'tree_copy_smoke'):
            matches = re.findall(r"(?ms)^  " + job + r":\n(.*?)(?=^  [a-z_]+:|\Z)", source)
            self.assertEqual(len(matches), 1)
            block = matches[0]
            self.assertEqual(block.count("    permissions:\n      contents: read\n      packages: read\n"), 1)
            self.assertLess(block.index("scripts/native_1c_ci_policy.py bind"), block.index("GHCR_TOKEN:"))
            self.assertIn("ref: ${{ github.sha }}", block)
            self.assertIn("persist-credentials: false", block)
        self.assertEqual(source.count("contents: read"), 3)
        self.assertEqual(source.count("packages: read"), 3)
        self.assertNotIn(": write", source)
        self.assertIn("needs: [eligibility, smoke, tree_smoke, tree_copy_smoke]", source)
        self.assertIn("if: always() && (steps.native.outputs.native_outputs_ready == 'true' || steps.native_async.outputs.native_outputs_ready == 'true')", legacy)



if __name__ == "__main__":
    unittest.main()
