"""Fail-closed, offline policy for the bounded owner-only native CI route.

The admission section is copied literally into the permissionless workflow job.
Tests enforce equality so admission never checks out or imports candidate code.
This is an eligibility policy, not a boundary against malicious workflow edits.
"""

# BEGIN NATIVE CI ADMISSION
import json
import os
import re
import sys

REPOSITORY = "Atridis/yadinassi"
REPOSITORY_ID = 359770628
OWNER = "Atridis"
OWNER_ID = 30860798
ASYNC_REVIEWED_REF = "refs/heads/codex/native-client-async-reviewed"
PR_ACTIONS = frozenset({"opened", "synchronize", "reopened"})
MAX_EVENT_BYTES = 8 * 1024 * 1024


class PolicyError(Exception):
    """A finite reason safe to emit without printing event data."""


def require(condition, reason):
    if not condition:
        raise PolicyError(reason)


def object_value(value):
    return value if type(value) is dict else {}


def is_sha(value):
    return (type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None
            and value != "0" * 40)


def owner_identity(value):
    value = object_value(value)
    return (value.get("login") == OWNER and type(value.get("id")) is int
            and value["id"] == OWNER_ID and value.get("type") == "User")


def trusted_repository(value):
    value = object_value(value)
    return (value.get("full_name") == REPOSITORY and type(value.get("id")) is int
            and value["id"] == REPOSITORY_ID and value.get("fork") is False
            and owner_identity(value.get("owner")))


def validate_admission(event, context):
    require(type(event) is dict and type(context) is dict, "event_invalid")
    expected = {
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY_ID": str(REPOSITORY_ID),
        "GITHUB_REPOSITORY_OWNER": OWNER,
        "GITHUB_REPOSITORY_OWNER_ID": str(OWNER_ID),
        "GITHUB_ACTOR": OWNER,
        "GITHUB_ACTOR_ID": str(OWNER_ID),
        # GitHub exposes triggering_actor login, not a triggering_actor_id.
        # Anchor that unique login to the checked current repository owner.
        "NATIVE_TRIGGERING_ACTOR": OWNER,
    }
    require(all(context.get(key) == value for key, value in expected.items()), "identity_not_approved")
    require(trusted_repository(event.get("repository")), "repository_not_approved")
    require(owner_identity(event.get("sender")), "sender_not_approved")
    require(is_sha(context.get("GITHUB_SHA")), "revision_invalid")
    if context.get("GITHUB_EVENT_NAME") == "pull_request":
        require(event.get("action") in PR_ACTIONS if type(event.get("action")) is str else False,
                "pr_action_not_approved")
        pr = object_value(event.get("pull_request"))
        number = event.get("number")
        require(type(number) is int and 0 < number < 10 ** 12 and pr.get("number") == number
                and type(pr.get("number")) is int, "pr_number_invalid")
        require(context.get("GITHUB_REF") == f"refs/pull/{number}/merge", "pr_ref_invalid")
        require(pr.get("state") == "open" and pr.get("merged") is False
                and type(pr.get("draft")) is bool, "pr_state_not_approved")
        require(owner_identity(pr.get("user")), "pr_author_not_approved")
        base, head = object_value(pr.get("base")), object_value(pr.get("head"))
        require(trusted_repository(base.get("repo")) and trusted_repository(head.get("repo")),
                "pr_repositories_not_approved")
        require(base.get("ref") == "main" and context.get("GITHUB_BASE_REF") == "main",
                "pr_base_not_approved")
        require(is_sha(base.get("sha")) and is_sha(head.get("sha")), "pr_revisions_invalid")
        return "pull_request"
    if context.get("GITHUB_EVENT_NAME") == "push":
        ref = context.get("GITHUB_REF")
        require(ref in ("refs/heads/main", ASYNC_REVIEWED_REF) and event.get("ref") == ref,
                "push_ref_not_approved")
        if ref == ASYNC_REVIEWED_REF:
            # Deliberately advancing this exact owner-only branch opts in the reviewed SHA.
            # Branch naming is not a security boundary against repository/workflow editors.
            require(event.get("forced") is False, "push_forced_or_invalid")
            require(context.get("GITHUB_REF_TYPE") == "branch"
                    and context.get("GITHUB_BASE_REF") == "" and context.get("GITHUB_HEAD_REF") == "",
                    "push_reviewed_context_invalid")
            require(context.get("GITHUB_WORKFLOW_REF") == f"{REPOSITORY}/.github/workflows/native-1c-isolated-smoke.yml@{ref}"
                    and context.get("GITHUB_WORKFLOW_SHA") == context["GITHUB_SHA"],
                    "push_workflow_revision_mismatch")
        require(event.get("deleted") is False, "push_deleted_or_invalid")
        require(event.get("after") == context["GITHUB_SHA"]
                and object_value(event.get("head_commit")).get("id") == context["GITHUB_SHA"],
                "push_revision_mismatch")
        return "push"
    if context.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        # This owner-only opt-in attests review of an immutable same-repo revision.
        # It is not a security boundary against edits to this workflow or policy.
        inputs = object_value(event.get("inputs"))
        require(set(inputs) == {"client_async_measurement", "reviewed_sha"}
                and inputs.get("client_async_measurement") == "true",
                "dispatch_inputs_not_approved")
        try:
            typed_inputs = json.loads(context.get("NATIVE_DISPATCH_INPUTS", ""), object_pairs_hook=unique_object)
        except (ValueError, TypeError, RecursionError):
            raise PolicyError("dispatch_inputs_not_approved") from None
        require(type(typed_inputs) is dict and set(typed_inputs) == set(inputs)
                and typed_inputs.get("client_async_measurement") is True
                and typed_inputs.get("reviewed_sha") == inputs.get("reviewed_sha"),
                "dispatch_inputs_not_approved")
        require(is_sha(inputs.get("reviewed_sha")) and inputs["reviewed_sha"] == context["GITHUB_SHA"],
                "dispatch_revision_mismatch")
        ref = context.get("GITHUB_REF")
        require(type(ref) is str and re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,239}", ref) is not None
                and ".." not in ref and "//" not in ref and not ref.endswith(("/", "."))
                and all(not part.startswith(".") and not part.endswith(".lock") for part in ref.split("/"))
                and context.get("GITHUB_REF_TYPE") == "branch"
                and context.get("GITHUB_BASE_REF") == "" and context.get("GITHUB_HEAD_REF") == ""
                and event.get("ref") in (ref, ref.removeprefix("refs/heads/")),
                "dispatch_ref_not_approved")
        require(context.get("GITHUB_WORKFLOW_REF") == f"{REPOSITORY}/.github/workflows/native-1c-isolated-smoke.yml@{ref}"
                and context.get("GITHUB_WORKFLOW_SHA") == context["GITHUB_SHA"],
                "dispatch_workflow_revision_mismatch")
        return "workflow_dispatch"
    raise PolicyError("event_not_approved")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "event_invalid")
        result[key] = value
    return result


def read_event(context):
    try:
        with open(context["GITHUB_EVENT_PATH"], "rb") as stream:
            data = stream.read(MAX_EVENT_BYTES + 1)
        require(len(data) <= MAX_EVENT_BYTES, "event_invalid")
        return json.loads(data, object_pairs_hook=unique_object)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise PolicyError("event_invalid") from None


def admission_main():
    try:
        validate_admission(read_event(os.environ), dict(os.environ))
    except PolicyError as error:
        print(f"Native CI blocked: {error}", file=sys.stderr)
        return 1
    print("Native CI admission accepted.")
    return 0
# END NATIVE CI ADMISSION


def validate_binding(event, context, commit, parents, worktree_status):
    """Bind exactly the event's immutable revision, not a branch or PR head."""
    route = validate_admission(event, context)
    require(is_sha(commit) and commit == context["GITHUB_SHA"], "checkout_revision_mismatch")
    require(worktree_status == "", "checkout_not_clean")
    require(type(parents) is list and all(is_sha(parent) for parent in parents), "checkout_parents_invalid")
    if route == "pull_request":
        pr = event["pull_request"]
        require(parents == [pr["base"]["sha"], pr["head"]["sha"]], "pr_merge_parents_mismatch")


def binding_main():
    import subprocess

    def git(*arguments):
        try:
            result = subprocess.run(["git", "--no-replace-objects", *arguments], check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 65536,
                    "checkout_evidence_unavailable")
            return result.stdout.decode("ascii").strip()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise PolicyError("checkout_evidence_unavailable") from None

    try:
        context = dict(os.environ)
        event = read_event(context)
        validate_admission(event, context)
        validate_binding(event, context, git("rev-parse", "HEAD^{commit}"),
                         git("show", "-s", "--format=%P", "HEAD").split(),
                         git("status", "--porcelain", "--untracked-files=all"))
    except PolicyError as error:
        print(f"Native CI blocked: {error}", file=sys.stderr)
        return 1
    print("Native CI checkout binding verified.")
    return 0


# BEGIN NATIVE CI VERDICT
def final_verdict(eligibility_result, native_result):
    # Skipped, cancelled, unavailable and failed native runs are never green.
    return 0 if eligibility_result == "success" and native_result == "success" else 1
# END NATIVE CI VERDICT


if __name__ == "__main__":
    if sys.argv[1:] == ["admit"]:
        raise SystemExit(admission_main())
    if sys.argv[1:] == ["bind"]:
        raise SystemExit(binding_main())
    print("Native CI blocked: command_not_approved", file=sys.stderr)
    raise SystemExit(1)
