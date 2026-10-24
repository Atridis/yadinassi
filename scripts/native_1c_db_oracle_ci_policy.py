"""Independent owner-reviewed push admission for the bounded file-DB oracle.

The admission source is copied literally into the permissionless eligibility job.
Tests enforce equality: eligibility neither checks out nor imports candidate code.
This is admission policy, not a privacy boundary against workflow edits or the
existing public-repository package grant. Advancing the one reviewed branch is
an explicit opt-in; neither main pushes nor PRs nor manual dispatch start it.
"""

# BEGIN NATIVE DB ORACLE CI ADMISSION
import json
import os
import re
import sys

REPOSITORY = "Atridis/yadinassi"
REPOSITORY_ID = 359770628
OWNER = "Atridis"
OWNER_ID = 30860798
REVIEWED_REF = "refs/heads/codex/native-file-db-oracle-reviewed"
WORKFLOW_PATH = ".github/workflows/native-1c-file-db-oracle.yml"
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
        # triggering_actor has a login but no numeric ID in GitHub's context.
        # Bind that unique login to the independently checked repository owner.
        "NATIVE_TRIGGERING_ACTOR": OWNER,
    }
    require(all(context.get(key) == value for key, value in expected.items()), "identity_not_approved")
    require(trusted_repository(event.get("repository")), "repository_not_approved")
    require(owner_identity(event.get("sender")), "sender_not_approved")
    require(context.get("GITHUB_EVENT_NAME") == "push", "event_not_approved")
    require(context.get("GITHUB_REF") == REVIEWED_REF and event.get("ref") == REVIEWED_REF,
            "push_ref_not_approved")
    require(context.get("GITHUB_REF_TYPE") == "branch"
            and context.get("GITHUB_BASE_REF") == "" and context.get("GITHUB_HEAD_REF") == "",
            "push_reviewed_context_invalid")
    require(event.get("forced") is False, "push_forced_or_invalid")
    require(event.get("deleted") is False, "push_deleted_or_invalid")
    require(is_sha(context.get("GITHUB_SHA")), "revision_invalid")
    require(event.get("after") == context["GITHUB_SHA"]
            and object_value(event.get("head_commit")).get("id") == context["GITHUB_SHA"],
            "push_revision_mismatch")
    require(context.get("GITHUB_WORKFLOW_REF") == f"{REPOSITORY}/{WORKFLOW_PATH}@{REVIEWED_REF}"
            and context.get("GITHUB_WORKFLOW_SHA") == context["GITHUB_SHA"],
            "push_workflow_revision_mismatch")
    return "push"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "event_invalid")
        result[key] = value
    return result


def reject_constant(_value):
    raise PolicyError("event_invalid")


def read_event(context):
    try:
        with open(context["GITHUB_EVENT_PATH"], "rb") as stream:
            data = stream.read(MAX_EVENT_BYTES + 1)
        require(len(data) <= MAX_EVENT_BYTES, "event_invalid")
        return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise PolicyError("event_invalid") from None


def admission_main():
    try:
        validate_admission(read_event(os.environ), dict(os.environ))
    except PolicyError as error:
        print(f"Native DB oracle CI blocked: {error}", file=sys.stderr)
        return 1
    print("Native DB oracle CI admission accepted.")
    return 0
# END NATIVE DB ORACLE CI ADMISSION


def validate_binding(event, context, commit, tree, worktree_status):
    """Bind the clean checkout to the event and workflow's one immutable SHA.

    The host independently verifies this commit/tree and hashes its exact source
    manifest immediately before execution and again before accepting evidence.
    """
    validate_admission(event, context)
    require(is_sha(commit) and commit == context["GITHUB_SHA"], "checkout_revision_mismatch")
    require(is_sha(tree), "checkout_tree_invalid")
    require(type(worktree_status) is str and worktree_status == "", "checkout_not_clean")


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
                         git("rev-parse", "HEAD^{tree}"),
                         git("status", "--porcelain", "--untracked-files=all"))
    except PolicyError as error:
        print(f"Native DB oracle CI blocked: {error}", file=sys.stderr)
        return 1
    print("Native DB oracle CI checkout binding verified.")
    return 0


# BEGIN NATIVE DB ORACLE CI VERDICT
def final_verdict(eligibility_result, native_result):
    # Skipped, cancelled, unavailable and failed native runs are never green.
    return 0 if eligibility_result == "success" and native_result == "success" else 1
# END NATIVE DB ORACLE CI VERDICT


if __name__ == "__main__":
    if sys.argv[1:] == ["admit"]:
        raise SystemExit(admission_main())
    if sys.argv[1:] == ["bind"]:
        raise SystemExit(binding_main())
    print("Native DB oracle CI blocked: command_not_approved", file=sys.stderr)
    raise SystemExit(1)
