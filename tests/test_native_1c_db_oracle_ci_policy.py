"""Offline tests only: reviewed-push DB-oracle admission is not native proof."""
import ast
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
POLICY_PATH = ROOT / "scripts/native_1c_db_oracle_ci_policy.py"
WORKFLOW_PATH = ROOT / ".github/workflows/native-1c-file-db-oracle.yml"
SPEC = importlib.util.spec_from_file_location("native_1c_db_oracle_ci_policy", POLICY_PATH)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
COMMIT, TREE, OTHER = "1" * 40, "2" * 40, "3" * 40
REF = "refs/heads/codex/native-file-db-oracle-reviewed"
WORKFLOW_REF = "Atridis/yadinassi/.github/workflows/native-1c-file-db-oracle.yml@" + REF


def owner():
    return {"login": "Atridis", "id": 30860798, "type": "User"}


def repository():
    return {"full_name": "Atridis/yadinassi", "id": 359770628, "fork": False, "owner": owner()}


def fixtures():
    event = {
        "repository": repository(), "sender": owner(), "ref": REF,
        "forced": False, "deleted": False, "after": COMMIT, "head_commit": {"id": COMMIT},
    }
    context = {
        "GITHUB_REPOSITORY": "Atridis/yadinassi", "GITHUB_REPOSITORY_ID": "359770628",
        "GITHUB_REPOSITORY_OWNER": "Atridis", "GITHUB_REPOSITORY_OWNER_ID": "30860798",
        "GITHUB_ACTOR": "Atridis", "GITHUB_ACTOR_ID": "30860798", "NATIVE_TRIGGERING_ACTOR": "Atridis",
        "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": COMMIT, "GITHUB_REF": REF,
        "GITHUB_REF_TYPE": "branch", "GITHUB_BASE_REF": "", "GITHUB_HEAD_REF": "",
        "GITHUB_WORKFLOW_REF": WORKFLOW_REF, "GITHUB_WORKFLOW_SHA": COMMIT,
    }
    return event, context


def section(source, name):
    marker = f"# BEGIN NATIVE DB ORACLE CI {name}\n"
    end = f"# END NATIVE DB ORACLE CI {name}"
    return source.split(marker, 1)[1].split(end, 1)[0].rstrip() + "\n"


def workflow_job(name):
    source = WORKFLOW_PATH.read_text().split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n  [a-z][a-z_]*:\n", source, maxsplit=1)[0]


def inline_program(job):
    block = workflow_job(job).split("        run: |\n", 1)[1]
    program = textwrap.dedent(block).split("<<'PYTHON'\n", 1)[1].split("\nPYTHON", 1)[0]
    return program + "\n"


def subprocess_environment(values):
    # Do not pass credentials to an offline test subprocess.
    essential = {key: value for key, value in os.environ.items()
                 if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    return {**essential, **values}


class AdmissionTests(unittest.TestCase):
    def test_exact_owner_reviewed_push_is_the_only_route(self):
        event, context = fixtures()
        self.assertEqual(policy.validate_admission(event, context), "push")
        for route in ("pull_request", "pull_request_target", "workflow_dispatch", "workflow_call", "workflow_run",
                      "schedule", "repository_dispatch", "merge_group", "release", "", None, [], True):
            event, context = fixtures()
            context["GITHUB_EVENT_NAME"] = route
            event["inputs"] = {"file_db_oracle": "true", "reviewed_sha": COMMIT}
            with self.subTest(route=route), self.assertRaisesRegex(policy.PolicyError, "^event_not_approved$"):
                policy.validate_admission(event, context)

    def test_all_identity_fields_require_exact_values_and_original_actor(self):
        keys = ("GITHUB_REPOSITORY", "GITHUB_REPOSITORY_ID", "GITHUB_REPOSITORY_OWNER",
                "GITHUB_REPOSITORY_OWNER_ID", "GITHUB_ACTOR", "GITHUB_ACTOR_ID", "NATIVE_TRIGGERING_ACTOR")
        for key in keys:
            for value in (None, 30860798, True, [], {}, "", "other", "atridis", "Atridis\n$(echo SECRET)"):
                event, context = fixtures()
                context[key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(policy.PolicyError, "^identity_not_approved$"):
                    policy.validate_admission(event, context)
            event, context = fixtures()
            context.pop(key)
            with self.subTest(missing=key), self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)
        event, context = fixtures()
        context.update(GITHUB_ACTOR="outsider", GITHUB_ACTOR_ID="999", NATIVE_TRIGGERING_ACTOR="Atridis")
        with self.assertRaises(policy.PolicyError):
            policy.validate_admission(event, context)

    def test_repository_sender_and_owner_reject_malformed_objects(self):
        for field in ("repository", "sender", "owner"):
            for replacement in (None, [], "SECRET", True, {}, {"login": "Atridis", "id": True}):
                event, context = fixtures()
                target = event["repository"] if field == "owner" else event
                target[field] = replacement
                with self.subTest(field=field, replacement=replacement), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)

    def test_forks_renames_transfers_and_numeric_identity_confusion_fail(self):
        invalid = (("full_name", "outsider/yadinassi"), ("full_name", "Atridis/other"),
                   ("full_name", "atridis/yadinassi"), ("id", 999), ("id", "359770628"),
                   ("id", True), ("id", 359770628.0), ("fork", True), ("fork", None), ("fork", 0))
        for key, value in invalid:
            event, context = fixtures()
            event["repository"][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(policy.PolicyError, "^repository_not_approved$"):
                policy.validate_admission(event, context)
        for field in ("sender", "owner"):
            for key, value in (("login", "outside"), ("login", "atridis"), ("id", 999), ("id", "30860798"),
                               ("id", True), ("id", 30860798.0), ("type", "Bot"), ("type", "Organization")):
                event, context = fixtures()
                target = event["sender"] if field == "sender" else event["repository"]["owner"]
                target[key] = value
                with self.subTest(field=field, key=key, value=value), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)

    def test_normal_branches_tags_and_near_miss_reviewed_refs_are_inert(self):
        refs = ("refs/heads/main", "refs/heads/codex/native-client-async-reviewed", "refs/heads/topic",
                "refs/tags/codex/native-file-db-oracle-reviewed", "refs/pull/123/merge",
                REF + "/extra", REF + ".lock", REF + " ", REF.upper(), REF.removeprefix("refs/heads/"),
                "refs/heads/../" + REF, "", None, [], {})
        for ref in refs:
            for target in ("event", "context", "both"):
                event, context = fixtures()
                if target != "context":
                    event["ref"] = ref
                if target != "event":
                    context["GITHUB_REF"] = ref
                with self.subTest(ref=ref, target=target), self.assertRaisesRegex(policy.PolicyError, "^push_ref_not_approved$"):
                    policy.validate_admission(event, context)

    def test_branch_only_context_must_be_complete_and_exact(self):
        for key in ("GITHUB_REF_TYPE", "GITHUB_BASE_REF", "GITHUB_HEAD_REF"):
            invalid = (None, [], True, "main", "tag", "refs/heads/main", " ")
            for value in invalid:
                event, context = fixtures()
                context[key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(policy.PolicyError, "^push_reviewed_context_invalid$"):
                    policy.validate_admission(event, context)
            event, context = fixtures()
            context.pop(key)
            with self.assertRaisesRegex(policy.PolicyError, "^push_reviewed_context_invalid$"):
                policy.validate_admission(event, context)

    def test_deleted_forced_missing_and_non_boolean_flags_are_rejected(self):
        for key in ("forced", "deleted"):
            for value in (True, None, 0, 1, "false", "", [], {}):
                event, context = fixtures()
                event[key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(policy.PolicyError, f"^push_{key}_or_invalid$"):
                    policy.validate_admission(event, context)
            event, context = fixtures()
            event.pop(key)
            with self.assertRaises(policy.PolicyError):
                policy.validate_admission(event, context)

    def test_synchronized_event_context_and_workflow_shas_are_required(self):
        invalid = (None, "", "0" * 40, "A" * 40, "f" * 39, "f" * 41, OTHER, "$(echo SECRET)", 123, [], {}, True)
        for field in ("context", "after", "head_commit", "workflow"):
            for value in invalid:
                event, context = fixtures()
                if field == "context":
                    context["GITHUB_SHA"] = value
                elif field == "workflow":
                    context["GITHUB_WORKFLOW_SHA"] = value
                elif field == "head_commit":
                    event["head_commit"]["id"] = value
                else:
                    event["after"] = value
                with self.subTest(field=field, value=value), self.assertRaises(policy.PolicyError):
                    policy.validate_admission(event, context)
        for field in ("after", "head_commit"):
            event, context = fixtures()
            event.pop(field)
            with self.assertRaisesRegex(policy.PolicyError, "^push_revision_mismatch$"):
                policy.validate_admission(event, context)
        for value in (None, [], "SECRET", True):
            event, context = fixtures()
            event["head_commit"] = value
            with self.assertRaisesRegex(policy.PolicyError, "^push_revision_mismatch$"):
                policy.validate_admission(event, context)

    def test_even_synchronized_invalid_shas_do_not_pass(self):
        for value in ("0" * 40, "A" * 40, "e" * 39, "", None, [], True, 1):
            event, context = fixtures()
            context.update(GITHUB_SHA=value, GITHUB_WORKFLOW_SHA=value)
            event.update(after=value, head_commit={"id": value})
            with self.subTest(value=value), self.assertRaisesRegex(policy.PolicyError, "^revision_invalid$"):
                policy.validate_admission(event, context)

    def test_workflow_must_be_this_file_at_the_same_exact_branch(self):
        for value in (None, [], True, "", WORKFLOW_REF.replace("Atridis/", "outsider/"),
                      WORKFLOW_REF.replace("file-db-oracle.yml", "isolated-smoke.yml"),
                      WORKFLOW_REF.replace(REF, "refs/heads/main"), WORKFLOW_REF + "/extra", COMMIT):
            event, context = fixtures()
            context["GITHUB_WORKFLOW_REF"] = value
            with self.subTest(value=value), self.assertRaisesRegex(policy.PolicyError, "^push_workflow_revision_mismatch$"):
                policy.validate_admission(event, context)

    def test_malformed_top_level_values_fail_with_finite_reason(self):
        event, context = fixtures()
        for value in (None, [], True, "SECRET", 1):
            with self.subTest(event=value), self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                policy.validate_admission(value, context)
            with self.subTest(context=value), self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                policy.validate_admission(event, value)

    def test_event_json_rejects_duplicates_nonfinite_malformed_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "event.json"
            context = {"GITHUB_EVENT_PATH": str(path)}
            for raw in (b"not-json SECRET", b"\xff", b'{"sender":1,"sender":2}',
                        b'{"repository":{"id":1,"id":2}}', b'{"x":NaN}', b'{"x":Infinity}',
                        b'{"x":-Infinity}', b"[" * 2000, b" " * (policy.MAX_EVENT_BYTES + 1)):
                path.write_bytes(raw)
                with self.subTest(raw=raw[:40]), self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                    policy.read_event(context)
            event, _ = fixtures()
            path.write_text(json.dumps(event))
            self.assertEqual(policy.read_event(context), event)
            path.unlink()
            with self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                policy.read_event(context)
        for context in ({}, {"GITHUB_EVENT_PATH": None}, {"GITHUB_EVENT_PATH": "\x00SECRET"}):
            with self.assertRaisesRegex(policy.PolicyError, "^event_invalid$"):
                policy.read_event(context)


class BindingTests(unittest.TestCase):
    def test_checkout_matches_exact_reviewed_commit_and_has_valid_tree(self):
        event, context = fixtures()
        policy.validate_binding(event, context, COMMIT, TREE, "")
        for field in ("commit", "tree"):
            values = ("0" * 40, "A" * 40, "x", "", None, [], {}, True, 7)
            if field == "commit":
                values += (OTHER,)
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(policy.PolicyError):
                    policy.validate_binding(event, context, value if field == "commit" else COMMIT,
                                            value if field == "tree" else TREE, "")

    def test_dirty_or_unavailable_checkout_is_never_accepted(self):
        event, context = fixtures()
        for status in (" M source.py", "?? injected.py", " ", None, False, [], {}):
            with self.subTest(status=status), self.assertRaisesRegex(policy.PolicyError, "^checkout_not_clean$"):
                policy.validate_binding(event, context, COMMIT, TREE, status)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "event.json"
            path.write_text(json.dumps(event))
            context["GITHUB_EVENT_PATH"] = str(path)
            failures = (OSError("SECRET"), subprocess.TimeoutExpired(["git"], 30),
                        subprocess.CompletedProcess(["git"], 1, b"", b"SECRET"),
                        subprocess.CompletedProcess(["git"], 0, b"valid", b"SECRET"),
                        subprocess.CompletedProcess(["git"], 0, b"\xff", b""),
                        subprocess.CompletedProcess(["git"], 0, b"x" * 65537, b""))
            for failure in failures:
                with self.subTest(failure=type(failure).__name__), mock.patch.dict(os.environ, context, clear=True):
                    kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
                    with mock.patch("subprocess.run", **kwargs), mock.patch("builtins.print") as output:
                        self.assertEqual(policy.binding_main(), 1)
                    self.assertIn("checkout_evidence_unavailable", str(output.call_args))
                    self.assertNotIn("SECRET", str(output.call_args))

    def test_denied_admission_does_not_inspect_checkout(self):
        event, context = fixtures()
        context["GITHUB_EVENT_NAME"] = "workflow_dispatch"
        with mock.patch.dict(os.environ, context, clear=True), mock.patch.object(policy, "read_event", return_value=event):
            with mock.patch("subprocess.run") as git, mock.patch("builtins.print"):
                self.assertEqual(policy.binding_main(), 1)
                git.assert_not_called()

    def test_binding_uses_literal_commit_tree_and_cleanliness_commands(self):
        event, context = fixtures()
        results = [subprocess.CompletedProcess(["git"], 0, value, b"")
                   for value in ((COMMIT + "\n").encode(), (TREE + "\n").encode(), b"")]
        with mock.patch.dict(os.environ, context, clear=True), mock.patch.object(policy, "read_event", return_value=event):
            with mock.patch("subprocess.run", side_effect=results) as git, mock.patch("builtins.print"):
                self.assertEqual(policy.binding_main(), 0)
        self.assertEqual([call.args[0] for call in git.call_args_list], [
            ["git", "--no-replace-objects", "rev-parse", "HEAD^{commit}"],
            ["git", "--no-replace-objects", "rev-parse", "HEAD^{tree}"],
            ["git", "--no-replace-objects", "status", "--porcelain", "--untracked-files=all"],
        ])
        for call in git.call_args_list:
            self.assertEqual(call.kwargs, {"check": False, "stdout": subprocess.PIPE,
                                           "stderr": subprocess.PIPE, "timeout": 30})

    def test_real_git_cli_rejects_dirty_and_changed_checkout_without_native_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "repo"
            checkout.mkdir()
            hooks = root / "empty-hooks"
            hooks.mkdir()
            git_env = subprocess_environment({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                                              "GIT_TERMINAL_PROMPT": "0"})
            def git(*args):
                result = subprocess.run(["git", "-c", "user.name=Native Oracle Test", "-c", "user.email=oracle@example.invalid",
                                         "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}", *args],
                                        cwd=checkout, env=git_env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return result.stdout.decode().strip()
            git("init", "-q", "-b", "reviewed")
            (checkout / "source.txt").write_text("original\n")
            git("add", ".")
            git("commit", "-qm", "original")
            commit = git("rev-parse", "HEAD")
            event, context = fixtures()
            context.update(GITHUB_SHA=commit, GITHUB_WORKFLOW_SHA=commit)
            event.update(after=commit, head_commit={"id": commit})
            path = root / "event.json"
            path.write_text(json.dumps(event))
            context["GITHUB_EVENT_PATH"] = str(path)
            def invoke():
                return subprocess.run([sys.executable, "-I", "-B", str(POLICY_PATH), "bind"], cwd=checkout,
                                      env={**git_env, **context}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = invoke()
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            (checkout / "injected.txt").write_text("untracked")
            self.assertIn(b"checkout_not_clean", invoke().stderr)
            (checkout / "injected.txt").unlink()
            (checkout / "source.txt").write_text("changed\n")
            self.assertIn(b"checkout_not_clean", invoke().stderr)
            git("add", ".")
            git("commit", "-qm", "changed")
            self.assertIn(b"checkout_revision_mismatch", invoke().stderr)
            current = git("rev-parse", "HEAD")
            event.update(after=current, head_commit={"id": current})
            path.write_text(json.dumps(event))
            context["GITHUB_SHA"] = current
            self.assertIn(b"push_workflow_revision_mismatch", invoke().stderr)

    def test_cli_unknown_and_extra_arguments_fail_without_event_or_git(self):
        for args in ([], ["SECRET"], ["admit", "extra"], ["bind", "extra"], ["workflow_dispatch"]):
            result = subprocess.run([sys.executable, "-I", "-B", str(POLICY_PATH), *args],
                                    env=subprocess_environment({}), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, b"Native DB oracle CI blocked: command_not_approved" + os.linesep.encode())
            self.assertNotIn(b"SECRET", result.stdout + result.stderr)


class WorkflowTests(unittest.TestCase):
    def test_inline_programs_are_identical_to_tested_policy_sections(self):
        source = POLICY_PATH.read_text()
        for job, name in (("eligibility", "ADMISSION"), ("verdict", "VERDICT")):
            with self.subTest(job=job):
                self.assertEqual(section(inline_program(job), name), section(source, name))
        imports = {alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {"json", "os", "re", "sys", "subprocess"})
        self.assertFalse(any(isinstance(node, ast.ImportFrom) for node in ast.walk(ast.parse(source))))

    def test_actual_inline_admission_has_no_candidate_import_or_shell_interpolation(self):
        source = inline_program("eligibility")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "json.py").write_text("raise RuntimeError('candidate code ran')")
            path = root / "event.json"
            event, context = fixtures()
            context["GITHUB_EVENT_PATH"] = str(path)
            context["NATIVE_DB_ROUTE"] = "catalog-reference-codec-v1"
            context["GITHUB_OUTPUT"] = str(root / "output")
            for route, expected in (("push", 0), ("workflow_dispatch", 1), ("pull_request", 1), ("pull_request_target", 1)):
                context["GITHUB_EVENT_NAME"] = route
                path.write_text(json.dumps(event))
                result = subprocess.run([sys.executable, "-I", "-B", "-c", source], cwd=root,
                                        env=subprocess_environment(context), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, expected, result.stderr.decode())
                self.assertNotIn(b"candidate code ran", result.stderr)
            path.write_text("SECRET $(touch injected) invalid-json")
            result = subprocess.run([sys.executable, "-I", "-B", "-c", source], cwd=root,
                                    env=subprocess_environment(context), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, b"Native DB oracle CI blocked: event_invalid" + os.linesep.encode())
            self.assertFalse((root / "injected").exists())

    def test_verdict_never_turns_a_skip_cancel_failure_or_unknown_into_success(self):
        source = inline_program("verdict")
        statuses = ("success", "failure", "cancelled", "skipped", "timed_out", "neutral", "", None, "success\necho SECRET")
        for eligibility in statuses:
            for native in statuses:
                self.assertEqual(policy.final_verdict(eligibility, native),
                                 0 if eligibility == "success" and native == "success" else 1)
        for eligibility, native in (("success", "success"), ("failure", "skipped"), ("skipped", "success"),
                                    ("success", "skipped"), ("success", "failure"), ("success", "cancelled"),
                                    ("success", ""), ("success", "success\necho SECRET")):
            result = subprocess.run([sys.executable, "-I", "-B", "-c", source],
                                    env=subprocess_environment({"ELIGIBILITY_RESULT": eligibility, "NATIVE_RESULT": native,
                                        "NATIVE_ROUTE":"catalog-reference-identity-v1", "REFERENCE_A_RESULT":"success",
                                        "CODEC_A_RESULT":"skipped", "CODEC_RESULT":"skipped", "METADATA_RESULT":"skipped", "METADATA_RUNTIME_RESULT":"skipped", "CATALOG_READ_RESULT":"skipped"}),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, policy.final_verdict(eligibility, native))
            self.assertNotIn(b"SECRET", result.stdout + result.stderr)

    def test_only_reviewed_push_route_no_manual_trigger_or_path_filters(self):
        source = WORKFLOW_PATH.read_text()
        events = source.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(events, "  push:\n    branches: [codex/native-file-db-oracle-reviewed]\n")
        self.assertIn("group: native-1c-file-db-oracle-${{ github.ref }}", source)
        self.assertIn("cancel-in-progress: false", source)
        for forbidden in ("paths:", "paths-ignore:", "workflow_dispatch", "workflow_call", "pull_request", "workflow_run",
                          "schedule:", "tags:", "secrets:", "continue-on-error:", "inputs.", "native-client-async-reviewed"):
            self.assertNotIn(forbidden, source)

    def test_only_native_job_has_read_permissions_and_only_native_step_has_token(self):
        source = WORKFLOW_PATH.read_text()
        self.assertIn("\npermissions: {}\n", source)
        self.assertEqual(re.findall(r"^  ([a-z_]+):$", source.split("\njobs:\n")[1], re.M),
                         ["eligibility", "native_reference_a", "native_oracle", "native_codec_a", "native_codec_b", "native_metadata", "native_metadata_runtime", "native_catalog_read", "verdict"])
        self.assertEqual(source.count("contents: read"), 7)
        self.assertEqual(source.count("packages: read"), 7)
        self.assertNotIn(": write", source)
        for job in ("eligibility", "verdict"):
            block = workflow_job(job)
            self.assertIn("    permissions: {}", block)
            self.assertNotIn("uses:", block)
            self.assertNotIn("github.token", block)
            self.assertNotIn("GHCR_TOKEN", block)
            self.assertNotIn("scripts/", block)
            self.assertNotIn("${{", block.split("        run: |\n", 1)[1])
            self.assertEqual(len(re.findall(r"^      - ", block, re.M)), 1)
            self.assertNotRegex(block.split("    steps:\n", 1)[1], r"(?m)^        if:")
        native = workflow_job("native_oracle")
        self.assertEqual(native.count("GHCR_TOKEN:"), 1)
        self.assertEqual(native.count("GHCR_USER:"), 1)
        self.assertIn("          GHCR_USER: ${{ github.actor }}\n          GHCR_TOKEN: ${{ github.token }}\n        run: python3 scripts/native_1c_db_oracle.py", native)

    def test_job_headers_are_exact_and_cannot_silently_add_bypass_conditions(self):
        headers = {
            "eligibility": """    name: File-DB oracle eligibility
    outputs:
      route: ${{ steps.admission.outputs.route }}
    permissions: {}
    runs-on: ubuntu-24.04
    timeout-minutes: 5
""",
            "native_oracle": """    name: Native 1C file-DB oracle
    needs: eligibility
    if: >-
      needs.eligibility.result == 'success' &&
      github.repository == 'Atridis/yadinassi' &&
      github.repository_id == '359770628' &&
      github.repository_owner == 'Atridis' &&
      github.repository_owner_id == '30860798' &&
      github.actor == 'Atridis' &&
      github.actor_id == '30860798' &&
      github.triggering_actor == 'Atridis' &&
      github.event_name == 'push' &&
      github.ref == 'refs/heads/codex/native-file-db-oracle-reviewed' &&
      github.ref_type == 'branch' &&
      github.base_ref == '' && github.head_ref == '' &&
      github.event.ref == github.ref &&
      github.event.deleted == false && github.event.forced == false &&
      github.event.after == github.sha && github.event.head_commit.id == github.sha &&
      github.workflow_ref == 'Atridis/yadinassi/.github/workflows/native-1c-file-db-oracle.yml@refs/heads/codex/native-file-db-oracle-reviewed' &&
      github.workflow_sha == github.sha
    permissions:
      contents: read
      packages: read
    runs-on: ubuntu-24.04
    # The host has one 2400-second execution deadline plus bounded cleanup.
    # This outer budget also includes checkout, authentication and report upload.
    timeout-minutes: 50
""",
            "verdict": """    name: Native 1C file-DB oracle verdict
    if: always()
    needs: [eligibility, native_reference_a, native_oracle, native_codec_a, native_codec_b, native_metadata, native_metadata_runtime, native_catalog_read]
    permissions: {}
    runs-on: ubuntu-24.04
    timeout-minutes: 5
""",
        }
        old_native=headers['native_oracle']
        headers['native_metadata']=old_native.replace('name: Native 1C file-DB oracle', 'name: Native 1C Metadata Catalogs applied-view measurement').replace('    if: >-\n', "    if: >-\n      needs.eligibility.outputs.route == 'metadata-catalog-applied-view-v1' &&\n")
        headers['native_metadata_runtime']=headers['native_metadata'].replace('applied-view measurement', 'public runtime readback').replace('metadata-catalog-applied-view-v1', 'metadata-catalog-public-runtime-v1')
        headers['native_catalog_read']=headers['native_metadata_runtime'].replace('Native 1C Metadata Catalogs public runtime readback','Native 1C batched Catalog read scenario').replace('metadata-catalog-public-runtime-v1','catalog-read-batch-v1')
        # Reviewed linked lane shares this job; retain the complete exact guard.
        headers['native_catalog_read']=headers['native_catalog_read'].replace(
            "needs.eligibility.outputs.route == 'catalog-read-batch-v1' &&",
            "(needs.eligibility.outputs.route == 'catalog-read-batch-v1' || needs.eligibility.outputs.route == 'linked-catalog-cards-v1' || needs.eligibility.outputs.route == 'document-read-v1' || needs.eligibility.outputs.route == 'document-lines-v1' || needs.eligibility.outputs.route == 'information-register-read-v2') &&")
        headers['native_reference_a']=old_native.replace('name: Native 1C file-DB oracle', 'name: Native 1C reference identity case A')+"""    outputs:
      artifact_id: ${{ steps.upload.outputs.artifact-id }}
      reference_sha256: ${{ steps.native.outputs.reference_sha256 }}
      run_id: ${{ github.run_id }}
      run_attempt: ${{ github.run_attempt }}
"""
        headers['native_oracle']=old_native.replace('name: Native 1C file-DB oracle', 'name: Native 1C reference identity case B').replace('needs: eligibility', 'needs: [eligibility, native_reference_a]').replace("needs.eligibility.result == 'success' &&", "needs.eligibility.result == 'success' && needs.native_reference_a.result == 'success' &&")
        for name in ('native_reference_a', 'native_oracle'):
            headers[name] = headers[name].replace('    if: >-\n',
                "    if: >-\n      needs.eligibility.outputs.route == 'catalog-reference-identity-v1' &&\n", 1)
        headers['native_codec_a'] = headers['native_reference_a'].replace('reference identity case', 'reference codec case').replace('catalog-reference-identity-v1', 'catalog-reference-codec-v1')
        headers['native_codec_b'] = headers['native_oracle'].replace('reference identity case', 'reference codec case').replace('catalog-reference-identity-v1', 'catalog-reference-codec-v1').replace('native_reference_a', 'native_codec_a')
        for name in ('native_codec_a', 'native_codec_b'):
            headers[name] = headers[name].replace(
                "needs.eligibility.outputs.route == 'catalog-reference-codec-v1' &&",
                "(needs.eligibility.outputs.route == 'catalog-reference-codec-v1' || needs.eligibility.outputs.route == 'catalog-reference-rows-v1' || needs.eligibility.outputs.route == 'catalog-description-measurement-v1' || needs.eligibility.outputs.route == 'catalog-description-rows-v1' || needs.eligibility.outputs.route == 'catalog-params-slot-measurement-v1' || needs.eligibility.outputs.route == 'catalog-numeric-code-measurement-v1' || needs.eligibility.outputs.route == 'catalog-numeric-code-rows-v1' || needs.eligibility.outputs.route == 'catalog-zero-code-measurement-v1' || needs.eligibility.outputs.route == 'catalog-zero-code-rows-v1') &&")
        headers['native_codec_a'] = headers['native_codec_a'].replace(
            '      reference_sha256: ${{ steps.native.outputs.reference_sha256 }}\n',
            '      reference_sha256: ${{ steps.native.outputs.reference_sha256 }}\n      description_sha256: ${{ steps.native.outputs.description_sha256 }}\n      description_rows_sha256: ${{ steps.native.outputs.description_rows_sha256 }}\n      params_slots_sha256: ${{ steps.native.outputs.params_slots_sha256 }}\n      numeric_code_sha256: ${{ steps.native.outputs.numeric_code_sha256 }}\n      numeric_code_rows_sha256: ${{ steps.native.outputs.numeric_code_rows_sha256 }}\n      zero_code_sha256: ${{ steps.native.outputs.zero_code_sha256 }}\n      zero_code_rows_sha256: ${{ steps.native.outputs.zero_code_rows_sha256 }}\n')
        for job, expected in headers.items():
            with self.subTest(job=job):
                self.assertEqual(workflow_job(job).split("    steps:\n", 1)[0], expected)

    def test_pinned_actions_exact_checkout_binding_and_stdlib_only_host_command(self):
        native = workflow_job("native_oracle")
        self.assertEqual(re.findall(r"uses: ([^\n]+)", native), [
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7",
            "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8",
            "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7",
            "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7",
        ])
        checkout = native.split("      - uses:", 1)[1].split("      - name:", 1)[0]
        self.assertEqual(checkout, """ actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
        with:
          ref: ${{ github.sha }}
          persist-credentials: false
          fetch-depth: 1
          submodules: false
          lfs: false
""")
        binding = native.index("run: python3 -I -B scripts/native_1c_db_oracle_ci_policy.py bind")
        self.assertLess(native.index("actions/checkout@"), binding)
        self.assertLess(binding, native.index("GHCR_TOKEN:"))
        self.assertEqual(re.findall(r"^        run: (.+)$", native, re.M), [
            "python3 -I -B scripts/native_1c_db_oracle_ci_policy.py bind",
            "python3 -I -B -c 'import os,re; raise SystemExit(0 if re.fullmatch(r\"[1-9][0-9]{0,19}\",os.environ.get(\"REFERENCE_A_ARTIFACT_ID\",\"\")) else 1)'",
            "python3 scripts/native_1c_db_oracle.py --validate-reference-a",
            "python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --catalog-reference-identity distinct_b --output native-db-oracle/distinct_b.json",
            'test "${NATIVE_REPORT_READY}" = "true"',
        ])
        self.assertEqual(native.count('--catalog-reference-identity distinct_b'), 1)
        for selector in ('--config-catalog-attribute-binding', '--config-catalog-field-matrix', '--config-catalog-identity-binding', '--config-catalog-standard-binding', '--config-catalog-name-binding', '--config-catalog-reference-observation', '--config-root-reference-projection-observation', '--config-content-decode-observation', '--config-blob-chain-observation', '--config-entry-reference-observation', '--config-zero-marker-filename-observation', '--config-slot-marker-observation', '--config-framing-observation', '--config-transport-observation', '--dbnames-identity-validation', '--params-dbnames-extraction',
                         '--params-transport-observation', '--record-reader-validation',
                         '--record-metadata-observation'):
            self.assertNotIn(selector, native)
        self.assertEqual(len(re.findall(r"^      - ", native, re.M)), 9)
        for forbidden in ("pip install", "setup-python", "docker run", "docker pull", "container:", "services:",
                          "native_1c_smoke.py", "--export-native-outputs", "--full-suite", "--image", "--commit", "--tree"):
            self.assertNotIn(forbidden, native)

    def test_success_without_validated_report_readiness_cannot_be_green(self):
        native = workflow_job("native_oracle")
        block = native.split("      - name: Require validated report readiness on native success\n", 1)[1].split("      # The host emits", 1)[0]
        self.assertEqual(block, """        if: always() && steps.native.outcome == 'success'
        env:
          NATIVE_REPORT_READY: ${{ steps.native.outputs.report_ready }}
        shell: bash
        run: test "${NATIVE_REPORT_READY}" = "true"
""")
        # The value is environment data, never interpolated into executable source.
        self.assertLess(native.index("id: native"), native.index("NATIVE_REPORT_READY:"))
        self.assertLess(native.index("NATIVE_REPORT_READY:"), native.index("actions/upload-artifact@"))

    def test_artifacts_are_exact_host_validated_json_not_raw_or_directory(self):
        for job,paths in (('native_reference_a',['native-db-oracle/distinct_a.json']),
                          ('native_oracle',['native-db-oracle/distinct_b.json','native-db-oracle/reference-aggregate.json'])):
            native=workflow_job(job)
            uploads=[part for part in native.split('      - name: ')[1:] if 'actions/upload-artifact@' in part]
            self.assertEqual([re.search(r'^          path: (.+)$',part,re.M)[1] for part in uploads],paths)
            for part in uploads:
                self.assertIn('if: always() && steps.native.outputs.',part)
                self.assertIn(" == 'true'",part)
                self.assertIn('if-no-files-found: error',part)
                self.assertIn('retention-days: 7',part)
                for forbidden in ('*','.1CD','.cf','.dt','.log','.xml','native-outputs/'):
                    self.assertNotIn(forbidden,part)
        native=workflow_job('native_oracle')
        self.assertIn('artifact-ids: ${{ needs.native_reference_a.outputs.artifact_id }}',native)
        self.assertIn('digest-mismatch: error',native)
        self.assertNotIn('github-token:',native)
        self.assertLess(native.index('--validate-reference-a'),native.index('GHCR_TOKEN:'))
        for key in ('SHA256','RUN_ID','RUN_ATTEMPT'):
            self.assertEqual(native.count('REFERENCE_A_'+key+':'),2)

    def test_admission_boundary_comment_does_not_claim_package_privacy(self):
        source = WORKFLOW_PATH.read_text()
        self.assertIn("Admission is not a privacy boundary against workflow edits", source)
        self.assertIn("public-repository package grant", source)
        self.assertIn("one owner-reviewed branch explicitly opts in its exact SHA", source)


if __name__ == "__main__":
    unittest.main()
