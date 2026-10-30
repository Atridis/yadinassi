"""Offline native CI admission, immutable binding and fail-closed gate tests."""
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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "scripts/native_1c_ci_policy.py"
WORKFLOW_PATH = ROOT / ".github/workflows/native-1c-isolated-smoke.yml"
SPEC = importlib.util.spec_from_file_location("native_1c_ci_policy", POLICY_PATH)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
BASE, HEAD, MERGE = "1" * 40, "2" * 40, "3" * 40


def owner():
    return {"login": "Atridis", "id": 30860798, "type": "User"}


def repository():
    return {"full_name": "Atridis/yadinassi", "id": 359770628, "fork": False, "owner": owner()}


def fixtures(route="pull_request", draft=True):
    event = {"repository": repository(), "sender": owner()}
    context = {
        "GITHUB_REPOSITORY": "Atridis/yadinassi", "GITHUB_REPOSITORY_ID": "359770628",
        "GITHUB_REPOSITORY_OWNER": "Atridis", "GITHUB_REPOSITORY_OWNER_ID": "30860798",
        "GITHUB_ACTOR": "Atridis", "GITHUB_ACTOR_ID": "30860798", "NATIVE_TRIGGERING_ACTOR": "Atridis",
        "GITHUB_EVENT_NAME": route, "GITHUB_SHA": MERGE, "GITHUB_BASE_REF": "main",
        "GITHUB_REF": "refs/pull/72/merge",
    }
    if route == "pull_request":
        event.update(action="opened", number=72, pull_request={
            "number": 72, "state": "open", "merged": False, "draft": draft, "user": owner(),
            "base": {"repo": repository(), "ref": "main", "sha": BASE},
            "head": {"repo": repository(), "ref": "codex/candidate", "sha": HEAD},
        })
    elif route == "push":
        context.update(GITHUB_REF="refs/heads/main", GITHUB_BASE_REF="")
        event.update(ref="refs/heads/main", deleted=False, after=MERGE, head_commit={"id": MERGE})
    return event, context


def section(source, name):
    marker = f"# BEGIN NATIVE CI {name}\n"
    end = f"# END NATIVE CI {name}"
    return source.split(marker, 1)[1].split(end, 1)[0].rstrip() + "\n"


def workflow_job(name):
    source = WORKFLOW_PATH.read_text().split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n  [a-z][a-z_]*:\n", source, maxsplit=1)[0]


def subprocess_environment(values):
    # Preserve only OS essentials, not job credentials; Windows needs SystemRoot.
    essential = {key: value for key, value in os.environ.items()
                 if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    return {**essential, **values}


def inline_program(job):
    block = workflow_job(job).split("        run: |\n", 1)[1]
    program = textwrap.dedent(block).split("<<'PYTHON'\n", 1)[1].split("\nPYTHON", 1)[0]
    return program + "\n"


class AdmissionTests(unittest.TestCase):
    def test_owner_pr_including_draft_and_owner_main_are_admitted(self):
        for route, draft in (("pull_request", True), ("pull_request", False), ("push", True)):
            with self.subTest(route=route, draft=draft):
                event, context = fixtures(route, draft)
                self.assertEqual(policy.validate_admission(event, context), route)
        for action in ("opened", "synchronize", "reopened"):
            event, context = fixtures()
            event["action"] = action
            self.assertEqual(policy.validate_admission(event, context), "pull_request")

    def test_context_identity_and_original_actor_cannot_be_replaced_by_rerunner(self):
        for key in ("GITHUB_REPOSITORY", "GITHUB_REPOSITORY_ID", "GITHUB_REPOSITORY_OWNER",
                    "GITHUB_REPOSITORY_OWNER_ID", "GITHUB_ACTOR", "GITHUB_ACTOR_ID", "NATIVE_TRIGGERING_ACTOR"):
            for value in (None, 30860798, True, "", "other", "Atridis\n$(echo injected)"):
                event, context = fixtures()
                context[key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(policy.PolicyError, "^identity_not_approved$"):
                    policy.validate_admission(event, context)
        # An owner rerunning a nonowner-origin run does not adopt that run.
        event, context = fixtures()
        context.update(GITHUB_ACTOR="outside", GITHUB_ACTOR_ID="999", NATIVE_TRIGGERING_ACTOR="Atridis")
        with self.assertRaises(policy.PolicyError):
            policy.validate_admission(event, context)
        event, context = fixtures()
        context["NATIVE_TRIGGERING_ACTOR"] = "outside"
        with self.assertRaises(policy.PolicyError):
            policy.validate_admission(event, context)

    def test_repository_sender_author_and_fork_identity_fail_closed(self):
        for field in ("repository", "sender", "author", "base_repo", "head_repo"):
            for replacement in (None, [], "injected", {}, {"login": "Atridis", "id": True}):
                event, context = fixtures()
                if field in ("repository", "sender"):
                    event[field] = replacement
                elif field == "author":
                    event["pull_request"]["user"] = replacement
                else:
                    event["pull_request"][field.split("_")[0]]["repo"] = replacement
                with self.subTest(field=field, replacement=replacement), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)
        for repo_path in ("repository", "base", "head"):
            for key, value in (("full_name", "other/yadinassi"), ("id", "359770628"), ("id", True),
                               ("id", 999), ("fork", True), ("fork", 0), ("fork", None)):
                event, context = fixtures()
                target = event["repository"] if repo_path == "repository" else event["pull_request"][repo_path]["repo"]
                target[key] = value
                with self.subTest(path=repo_path, key=key, value=value), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)
        for identity in ("owner", "sender", "author", "base_owner", "head_owner"):
            for key, value in (("login", "other"), ("id", 999), ("id", "30860798"), ("id", True), ("type", "Bot")):
                event, context = fixtures()
                target = {"owner": event["repository"]["owner"], "sender": event["sender"],
                          "author": event["pull_request"]["user"],
                          "base_owner": event["pull_request"]["base"]["repo"]["owner"],
                          "head_owner": event["pull_request"]["head"]["repo"]["owner"]}[identity]
                target[key] = value
                with self.subTest(identity=identity, key=key), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)

    def test_unsupported_event_action_ref_and_state_fail_closed(self):
        for event_name in ("workflow_call", "workflow_run", "pull_request_target", "release", None, [], ""):
            event, context = fixtures()
            context["GITHUB_EVENT_NAME"] = event_name
            with self.subTest(event_name=event_name), self.assertRaisesRegex(policy.PolicyError, "^event_not_approved$"):
                policy.validate_admission(event, context)
        for action in ("closed", "edited", "ready_for_review", "labeled", "converted_to_draft", "opened\necho pwned", None, [], {}):
            event, context = fixtures()
            event["action"] = action
            with self.subTest(action=action), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key, value in (("state", "closed"), ("state", None), ("merged", True), ("merged", 0),
                           ("draft", None), ("draft", "false"), ("draft", 1)):
            event, context = fixtures()
            event["pull_request"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for ref in ("refs/pull/72/head", "refs/pull/73/merge", "refs/heads/main", "refs/tags/v1", None):
            event, context = fixtures()
            context["GITHUB_REF"] = ref
            with self.subTest(ref=ref), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        for key in ("number", "pr_number"):
            for number in (True, "72", -1, 0, None, 73, 10 ** 12):
                event, context = fixtures()
                target = event if key == "number" else event["pull_request"]
                target["number"] = number
                with self.subTest(key=key, number=number), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)

    def test_retarget_requires_current_main_and_new_supported_event(self):
        for target in ("develop", None, "main\n$(echo pwned)"):
            for context_only in (False, True):
                event, context = fixtures()
                if context_only:
                    context["GITHUB_BASE_REF"] = target
                else:
                    event["pull_request"]["base"]["ref"] = target
                with self.subTest(target=target, context_only=context_only), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)
        event, context = fixtures()
        event["action"] = "reopened"
        event["changes"] = {"base": {"ref": {"from": "develop"}}}
        self.assertEqual(policy.validate_admission(event, context), "pull_request")

    def test_malformed_revisions_never_pass(self):
        for invalid in (None, "", "0" * 40, "A" * 40, "f" * 39, "f" * 41, "$(id)", 123, [], True):
            for where in ("context", "base", "head"):
                event, context = fixtures()
                if where == "context":
                    context["GITHUB_SHA"] = invalid
                else:
                    event["pull_request"][where]["sha"] = invalid
                with self.subTest(where=where, invalid=invalid), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)

    def test_main_push_rejects_tags_deletion_missing_or_mismatched_commit(self):
        edits = [lambda e, c: e.update(deleted=True), lambda e, c: e.update(deleted=0),
                 lambda e, c: e.pop("deleted"), lambda e, c: e.update(after=HEAD),
                 lambda e, c: e.update(head_commit=None), lambda e, c: e["head_commit"].update(id=HEAD)]
        for ref in ("refs/heads/topic", "refs/tags/v1", "main", None):
            edits += [lambda e, c, ref=ref: e.update(ref=ref), lambda e, c, ref=ref: c.update(GITHUB_REF=ref)]
        for edit in edits:
            event, context = fixtures("push")
            edit(event, context)
            with self.subTest(edit=edit), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_malformed_event_data_produces_only_a_finite_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "event.json"
            context = {"GITHUB_EVENT_PATH": str(path)}
            for raw in (b"not-json SECRET", b"\xff", b'{"sender":1,"sender":2}', b"[" * 2000,
                        b" " * (policy.MAX_EVENT_BYTES + 1)):
                path.write_bytes(raw)
                with self.subTest(raw=raw[:40]), self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                    policy.read_event(context)
            path.unlink()
            with self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                policy.read_event(context)
        for event in (None, [], "secret", True):
            _, context = fixtures()
            with self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                policy.validate_admission(event, context)


class BindingTests(unittest.TestCase):
    def test_exact_ordered_merge_parents_and_main_commit(self):
        event, context = fixtures()
        policy.validate_binding(event, context, MERGE, [BASE, HEAD], "")
        event, context = fixtures("push")
        policy.validate_binding(event, context, MERGE, [BASE], "")
        policy.validate_binding(event, context, MERGE, [], "")

    def test_head_checkout_stale_rerun_missing_swapped_or_wrong_parents_fail(self):
        event, context = fixtures()
        for commit in (HEAD, BASE, "0" * 40, "not-a-sha", None):
            with self.subTest(commit=commit), self.assertRaises(policy.PolicyError):
                policy.validate_binding(event, context, commit, [BASE, HEAD], "")
        for parents in ([], [BASE], [HEAD, BASE], [BASE, HEAD, MERGE], [BASE, MERGE], [MERGE, HEAD],
                        [BASE, ""], "", None, (BASE, HEAD)):
            with self.subTest(parents=parents), self.assertRaises(policy.PolicyError):
                policy.validate_binding(event, context, MERGE, parents, "")
        for side in ("base", "head"):
            event, context = fixtures()
            event["pull_request"][side]["sha"] = "4" * 40
            with self.subTest(side=side), self.assertRaisesRegex(policy.PolicyError, "^pr_merge_parents_mismatch$"):
                policy.validate_binding(event, context, MERGE, [BASE, HEAD], "")

    def test_dirty_or_unavailable_checkout_is_not_success(self):
        event, context = fixtures()
        for status in (" M scripts/native_1c_ci_policy.py", "?? injected.py", None, False):
            with self.subTest(status=status), self.assertRaisesRegex(policy.PolicyError, "^checkout_not_clean$"):
                policy.validate_binding(event, context, MERGE, [BASE, HEAD], status)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "event.json"
            path.write_text(json.dumps(event))
            context["GITHUB_EVENT_PATH"] = str(path)
            for failure in (OSError("private error"), subprocess.TimeoutExpired(["git"], 30),
                            subprocess.CompletedProcess(["git"], 1, b"", b"private error"),
                            subprocess.CompletedProcess(["git"], 0, b"\xff", b""),
                            subprocess.CompletedProcess(["git"], 0, b"x" * 65537, b"")):
                with self.subTest(failure=type(failure).__name__), mock.patch.dict(os.environ, context, clear=True):
                    kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
                    with mock.patch("subprocess.run", **kwargs), mock.patch("builtins.print") as output:
                        self.assertEqual(policy.binding_main(), 1)
                    self.assertIn("checkout_evidence_unavailable", str(output.call_args))
                    self.assertNotIn("private error", str(output.call_args))

    def test_cli_binds_real_git_merge_and_detects_dirty_or_changed_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "repo"
            checkout.mkdir()
            hooks = root / "empty-hooks"
            hooks.mkdir()
            git_env = subprocess_environment({})
            git_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
            def git(*args):
                result = subprocess.run(["git", "-c", "user.name=Native CI Test", "-c", "user.email=native-ci@example.invalid",
                                         "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}", *args],
                                        cwd=checkout, env=git_env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return result.stdout.decode().strip()
            git("init", "-q", "-b", "main")
            (checkout / "base.txt").write_text("base\n")
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "candidate")
            (checkout / "head.txt").write_text("head\n")
            git("add", ".")
            git("commit", "-qm", "head")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "--no-edit", "candidate")
            merge = git("rev-parse", "HEAD")
            event, context = fixtures()
            event["pull_request"]["base"]["sha"] = base
            event["pull_request"]["head"]["sha"] = head
            context["GITHUB_SHA"] = merge
            path = root / "event.json"
            path.write_text(json.dumps(event))
            context["GITHUB_EVENT_PATH"] = str(path)
            env = {**git_env, **context}
            def invoke():
                return subprocess.run([sys.executable, "-I", "-B", str(POLICY_PATH), "bind"], cwd=checkout,
                                      env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(invoke().returncode, 0)
            (checkout / "injected.txt").write_text("untracked")
            self.assertIn(b"checkout_not_clean", invoke().stderr)
            (checkout / "injected.txt").unlink()
            (checkout / "base.txt").write_text("changed")
            self.assertIn(b"checkout_not_clean", invoke().stderr)
            git("checkout", "--", "base.txt")
            git("checkout", "-q", head)
            self.assertIn(b"checkout_revision_mismatch", invoke().stderr)


class WorkflowTests(unittest.TestCase):
    def test_inline_admission_and_verdict_are_exact_canonical_source(self):
        source = POLICY_PATH.read_text()
        for job, name in (("eligibility", "ADMISSION"), ("verdict", "VERDICT")):
            self.assertEqual(section(inline_program(job), name), section(source, name))

    def test_actual_inline_admission_is_credential_free_and_fail_closed(self):
        source = inline_program("eligibility")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Candidate modules cannot be imported by the isolated inline process.
            (root / "json.py").write_text("raise RuntimeError('candidate code ran')")
            path = root / "event.json"
            event, context = fixtures()
            context["GITHUB_EVENT_PATH"] = str(path)
            for event_name, expected in (("pull_request", 0), ("pull_request_target", 1)):
                context["GITHUB_EVENT_NAME"] = event_name
                path.write_text(json.dumps(event))
                result = subprocess.run([sys.executable, "-I", "-B", "-c", source], cwd=root,
                                        env=subprocess_environment(context), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, expected, result.stderr.decode())
                self.assertNotIn(b"candidate code ran", result.stderr)
            path.write_text("SECRET $(touch injected) invalid-json")
            result = subprocess.run([sys.executable, "-I", "-B", "-c", source], cwd=root,
                                    env=subprocess_environment(context), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, ("Native CI blocked: event_invalid" + os.linesep).encode("ascii"))
            self.assertFalse((root / "injected").exists())

    def test_actual_inline_final_verdict_never_turns_a_skip_into_success(self):
        source = inline_program("verdict")
        statuses = ("success", "failure", "cancelled", "skipped", "timed_out", "neutral", "", None, "success\necho injected")
        for eligibility in statuses:
            for native in statuses:
                expected = 0 if eligibility == "success" and native == "success" else 1
                self.assertEqual(policy.final_verdict(eligibility, native), expected)
        for eligibility, native in (("success", "success"), ("failure", "skipped"), ("skipped", "success"),
                                    ("success", "skipped"), ("success", "failure"), ("success", "cancelled"),
                                    ("success", ""), ("success", "success\necho injected")):
            result = subprocess.run([sys.executable, "-I", "-B", "-c", source],
                                    env=subprocess_environment({"ELIGIBILITY_RESULT": eligibility, "NATIVE_RESULT": native}),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, policy.final_verdict(eligibility, native))
            self.assertNotIn(b"injected", result.stdout + result.stderr)

    def test_exact_routes_no_path_filters_and_per_revision_concurrency(self):
        source = WORKFLOW_PATH.read_text()
        events = source.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(events.split("  workflow_dispatch:\n", 1)[0], "  pull_request:\n    branches: [main]\n    types: [opened, synchronize, reopened]\n  push:\n    branches: [main, codex/native-client-async-reviewed]\n")
        self.assertIn("group: native-1c-${{ github.event.pull_request.number || github.ref }}", source)
        self.assertIn("cancel-in-progress: false", source)
        for forbidden in ("paths:", "paths-ignore:", "workflow_call:", "pull_request_target:",
                          "workflow_run:", "schedule:", "tags:", "secrets:", "continue-on-error:", "pull_request.draft"):
            self.assertNotIn(forbidden, source)

    def test_only_admitted_native_job_has_read_permissions(self):
        source = WORKFLOW_PATH.read_text()
        self.assertIn("\npermissions: {}\n", source)
        self.assertEqual(re.findall(r"^  ([a-z_]+):$", source.split("\njobs:\n")[1], re.M),
                         ["eligibility", "smoke", "tree_smoke", "tree_copy_smoke", "verdict"])
        self.assertEqual(source.count("contents: read"), 3)
        self.assertEqual(source.count("packages: read"), 3)
        self.assertNotIn(": write", source)
        for job in ("eligibility", "verdict"):
            block = workflow_job(job)
            self.assertIn("    permissions: {}", block)
            self.assertNotIn("uses:", block)
            self.assertNotIn("github.token", block)
            self.assertNotIn("GHCR_TOKEN", block)
            self.assertNotIn("scripts/", block)
            self.assertNotIn("${{", block.split("        run: |\n", 1)[1])
        native = workflow_job("smoke")
        self.assertIn("    needs: eligibility", native)
        self.assertIn("needs.eligibility.result == 'success'", native)
        for guard in ("github.repository == 'Atridis/yadinassi'", "github.repository_id == '359770628'",
                      "github.repository_owner_id == '30860798'", "github.actor == 'Atridis'",
                      "github.actor_id == '30860798'", "github.triggering_actor == 'Atridis'",
                      "github.event_name == 'pull_request'", "github.base_ref == 'main'",
                      "github.event_name == 'push'", "github.ref == 'refs/heads/main'"):
            self.assertIn(guard, native)
        verdict = workflow_job("verdict")
        self.assertIn("    name: ${{ (github.event_name == 'workflow_dispatch' || (github.event_name == 'push' && github.ref == 'refs/heads/codex/native-client-async-reviewed')) && 'Native 1C async measurement verdict' || 'Native 1C required verdict' }}", verdict)
        self.assertIn("    if: always()", verdict)
        self.assertIn("    needs: [eligibility, smoke, tree_smoke, tree_copy_smoke]", verdict)

    def test_exact_job_headers_do_not_allow_extra_bypass_conditions(self):
        expected_headers = {
            "eligibility": """    name: Native 1C eligibility
    permissions: {}
    runs-on: ubuntu-24.04
    timeout-minutes: 5
""",
            "smoke": """    name: ${{ (github.event_name == 'workflow_dispatch' || (github.event_name == 'push' && github.ref == 'refs/heads/codex/native-client-async-reviewed')) && 'Native 1C async measurement' || 'Native 1C six scenarios' }}
    needs: eligibility
    if: >-
      needs.eligibility.result == 'success' &&
      github.repository == 'Atridis/yadinassi' &&
      github.repository_id == '359770628' &&
      github.repository_owner_id == '30860798' &&
      github.actor == 'Atridis' &&
      github.actor_id == '30860798' &&
      github.triggering_actor == 'Atridis' &&
      ((github.event_name == 'pull_request' && github.base_ref == 'main') ||
       (github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/codex/native-client-async-reviewed')) ||
       (github.event_name == 'workflow_dispatch' && startsWith(github.ref, 'refs/heads/') && inputs.client_async_measurement == true))
    permissions:
      contents: read
      packages: read
    runs-on: ubuntu-24.04
    timeout-minutes: 60
""",
            "verdict": """    name: ${{ (github.event_name == 'workflow_dispatch' || (github.event_name == 'push' && github.ref == 'refs/heads/codex/native-client-async-reviewed')) && 'Native 1C async measurement verdict' || 'Native 1C required verdict' }}
    if: always()
    needs: [eligibility, smoke, tree_smoke, tree_copy_smoke]
    permissions: {}
    runs-on: ubuntu-24.04
    timeout-minutes: 5
""",
        }
        expected_headers["tree_smoke"] = expected_headers["smoke"].replace(
            expected_headers["smoke"].splitlines()[0], "    name: Native 1C tree profile", 1).replace(
            "needs.eligibility.result == 'success' &&",
            "needs.eligibility.result == 'success' &&\n      github.event_name != 'workflow_dispatch' &&\n      github.ref != 'refs/heads/codex/native-client-async-reviewed' &&", 1)
        expected_headers["tree_copy_smoke"] = expected_headers["tree_smoke"].replace(
            "Native 1C tree profile", "Native 1C ${{ matrix.profile }} measurement") + """    strategy:
      fail-fast: false
      matrix:
        include:
          - profile: tree-copy-v1
            artifact: tree-copy
            case: tree_copy
          - profile: tree-sort-v1
            artifact: tree-sort
            case: tree_sort
          - profile: tree-columns-move-v1
            artifact: tree-columns-move
            case: tree_columns_move
"""
        for job, expected in expected_headers.items():
            with self.subTest(job=job):
                self.assertEqual(workflow_job(job).split("    steps:\n", 1)[0], expected)
        for job in ("eligibility", "verdict"):
            steps = workflow_job(job).split("    steps:\n", 1)[1]
            self.assertEqual(len(re.findall(r"^      - ", steps, re.M)), 1)
            self.assertNotRegex(steps, r"(?m)^        if:")
        native = workflow_job("smoke")
        self.assertEqual(len(re.findall(r"^      - ", native, re.M)), 8)
        self.assertEqual(native.count("GHCR_TOKEN: ${{ github.token }}"), 2)
        self.assertIn("        env:\n          GHCR_USER: ${{ github.actor }}\n          GHCR_TOKEN: ${{ github.token }}\n        run: python3 scripts/native_1c_smoke.py", native)

    def test_exact_tree_matrix_header_rejects_bypass_and_mixed_entries(self):
        original = workflow_job
        changes = (
            lambda block: block.replace("needs.eligibility.result == 'success' &&",
                                        "needs.eligibility.result == 'success' || true ||", 1),
            lambda block: block.replace('profile: tree-sort-v1', 'profile: tree-copy-v1', 1),
            lambda block: block.replace('profile: tree-sort-v1', 'profile: arbitrary-v1', 1),
            lambda block: block.replace('artifact: tree-sort', 'artifact: tree-copy', 1),
            lambda block: block.replace('case: tree_sort', 'case: tree_copy', 1),
        )
        for change in changes:
            def mutated(job):
                block = original(job)
                return change(block) if job == 'tree_copy_smoke' else block
            # Execute the real whole-header equality guard, retaining its
            # subTest failure reporting rather than loosening it to substrings.
            result = unittest.TestResult()
            with mock.patch(__name__ + '.workflow_job', side_effect=mutated):
                WorkflowTests('test_exact_job_headers_do_not_allow_extra_bypass_conditions').run(result)
            self.assertEqual(len(result.errors), 0)
            self.assertEqual(len(result.failures), 1)

    def test_immutable_actions_checkout_and_binding_precede_native_token(self):
        native = workflow_job("smoke")
        self.assertEqual(re.findall(r"uses: ([^\n]+)", native), [
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7",
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7",
            "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7",
            "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7",
        ])
        for setting in ("ref: ${{ github.sha }}", "persist-credentials: false", "fetch-depth: 2", "submodules: false", "lfs: false"):
            self.assertIn(setting, native)
        binding = native.index("run: python3 -I -B scripts/native_1c_ci_policy.py bind")
        self.assertLess(native.index("actions/checkout@"), binding)
        self.assertLess(binding, native.index("actions/setup-python@"))
        self.assertLess(binding, native.index("GHCR_TOKEN:"))
        self.assertIn("run: python3 -m pip install --disable-pip-version-check --no-deps prompt-toolkit==3.0.53 pyuca==1.2 tzdata==2026.5 wcwidth==0.8.2", native)
        self.assertIn("run: python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --client-probe --client-watchdog-check --client-dates-parity --client-values-parity --client-collections-parity --client-numbers-parity --output native-smoke/report.json --export-native-outputs --native-target linux-8.3.27.1508 --comparison-mode typed-map-order-v1", native)

    def test_exact_artifact_paths_gates_and_retention_are_unchanged(self):
        native = workflow_job("smoke")
        self.assertEqual(native.count("retention-days: 7"), 2)
        self.assertEqual(native.count("if-no-files-found: error"), 2)
        self.assertIn("if: always() && (steps.native.outputs.native_outputs_ready == 'true' || steps.native_async.outputs.native_outputs_ready == 'true')", native)
        self.assertIn("path: native-smoke/report.json", native)
        output_paths = native.split("          path: |\n", 1)[1].split("          if-no-files-found:", 1)[0]
        self.assertEqual(output_paths.split(), [f"native-smoke/native-outputs/{name}" for name in (
            "collections.out", "dates.out", "functions.out", "numbers.out", "strings.out", "values.out", "provenance.json")])
        self.assertNotIn("*", output_paths)


if __name__ == "__main__":
    unittest.main()
