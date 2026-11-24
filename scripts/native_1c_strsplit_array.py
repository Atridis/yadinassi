"""Fixed, observe-only StrSplit Array acquisition using the existing native bootstrap."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

BASE = "97cae67fcb871c54516a21726467a27321f21455"
REF = "refs/heads/codex/native-strsplit-array-reviewed"
WORKFLOW = "Atridis/yadinassi/.github/workflows/native-1c-strsplit-array.yml@" + REF
PROBES = "integrational_tests/measurements/strsplit_array"
MANIFEST = PROBES + "/sha256.json"
EXPECTED_IMAGE = "ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728"
SCHEMA = "native-strsplit-array-v1"
VERSION = "8.3.27.1508"
SOURCE = "01_strsplit_array_indices.bsl"
SOURCE_SHA256 = "a58d5577c5925a96d2a649fa493596e9c2560ed2a2ab74f1a368eacf76c0abd7"
MANIFEST_SHA256 = "5c2600ea00f223aa7dec5a90f64459ec3e9ce9794037442ce426ad120c964a01"
PRODUCERS = ("new", "split")
INDEXES = ("minus-one", "minus-half", "half", "one-point-nine", "true", "upper")
METHODS = ("bracket-read", "get", "get-ru", "bracket-write", "set", "set-ru")
COMPLETE = "probe.strsplit-array-indices: complete"
READ_RESULT = re.compile(r"(?:error|ok\|(?:a|b|x|other))")
WRITE_RESULT = re.compile(r"(?:ok|error)\|(?:changed-count|2\|(?:a|b|x|other)\|(?:a|b|x|other))")
MAX_CASE = 8192
MAX_TRANSPORT = 49152
SELF = "scripts/native_1c_strsplit_array.py"
BOOTSTRAP_ALIAS = "bootstrap/base_stage.py"
HOST_HELPERS = ("scripts/native_1c_smoke.py", "scripts/native_1c_full_host.py",
                "scripts/native_1c_ci_policy.py")


def need(condition):
    if not condition:
        raise ValueError("observation_evidence_invalid")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_output(raw):
    """Admit exact framing and finite observations, never an expected verdict."""
    need(type(raw) is str and 0 < len(raw) <= MAX_CASE and raw.isascii())
    lines = raw.split("\n")
    need(len(lines) == 76 and lines[-2:] == [COMPLETE, ""])
    pos = 0
    for producer in PRODUCERS:
        # The fixed two-element controls establish that the matrix is comparable.
        need(lines[pos] == f"probe.{producer}: array|2|a|b")
        pos += 1
        for label in INDEXES:
            for index, method in enumerate(METHODS):
                prefix = f"probe.{producer}.{label}.{method}: "
                line = lines[pos]
                pos += 1
                grammar = READ_RESULT if index < 3 else WRITE_RESULT
                need(line.startswith(prefix) and grammar.fullmatch(line[len(prefix):]))
    return raw


def copied_source(base, source, case):
    original = base.bounded_bytes(source, MAX_CASE)
    copied = base.bounded_bytes(case / "src/TestModule/Ext/ObjectModule.bsl", MAX_CASE)
    need(copied.decode("utf-8-sig").encode("utf-8") == original)
    return original


def acq_stage(bootstrap):
    # Runs at the trusted launcher stage while its private display is still alive.
    sys.path.insert(0, str(bootstrap.parent))
    base = load(bootstrap, "strsplit_base_stage")
    status = base.main([])
    if status != 0:
        return status
    boot = [path for path in base.ROOT.glob("stage2-*")
            if re.fullmatch(r"stage2-[0-9a-f]{32}", path.name) and path.is_dir() and not path.is_symlink()]
    need(len(boot) == 1)
    epf = boot[0] / "Launcher.epf"
    base.require_epf(epf)
    launcher = base.load_launcher()
    platform = launcher.Platform(base.ONEC, base.ROOT / "db", 120, "NativeSmoke")
    oracle = base.ROOT / SCHEMA
    oracle.mkdir(mode=0o700)
    case = oracle / "case"
    source = base.INPUTS / "probes" / SOURCE
    output = oracle / "case.out"
    outcome = {"kind": "inconclusive"}
    try:
        need(digest(base.bounded_bytes(source, MAX_CASE)) == SOURCE_SHA256)
        launcher.run_case(platform, source, epf, case, output)
        base.require_zero_result(case / "TestModule.build-result.txt", 0)
        base.require_epf(case / "TestModule.epf")
        need(digest(copied_source(base, source, case)) == SOURCE_SHA256)
        result = parse_output(base.bounded_bytes(output, MAX_CASE).decode("utf-8"))
        outcome = {"kind": "ran", "output": result}
    except (launcher.LaunchError, OSError, ValueError, base.DraftError):
        pass
    nonce = base.bounded_bytes(base.INPUTS / "nonce", 32).decode("ascii")
    need(re.fullmatch(r"[0-9a-f]{32}", nonce))
    with (base.ROOT / (SCHEMA + ".json")).open("x", encoding="ascii") as path:
        path.write(json.dumps({"schema": SCHEMA, "nonce": nonce, "observation": outcome}) + "\n")
    return 0


def validate_observation(value, nonce):
    need(type(nonce) is str and re.fullmatch(r"[0-9a-f]{32}", nonce))
    need(type(value) is dict and set(value) == {"schema", "nonce", "observation"}
         and value["schema"] == SCHEMA and value["nonce"] == nonce)
    outcome = value["observation"]
    need(type(outcome) is dict)
    if set(outcome) == {"kind", "output"} and outcome["kind"] == "ran":
        parse_output(outcome["output"])
    else:
        need(outcome == {"kind": "inconclusive"})
    return outcome


def admitted_sources(root, smoke):
    read = smoke.FULL.read_regular
    manifest_path = root / MANIFEST
    need(not manifest_path.is_symlink()
         and not any(parent.is_symlink() for parent in manifest_path.parents if parent != root))
    manifest = read(manifest_path, MAX_CASE, nonempty=True)
    need(digest(manifest) == MANIFEST_SHA256)
    pin = smoke.FULL.strict_json(manifest, MAX_CASE)
    files = {**smoke.staged_files(False, False), PROBES + "/" + SOURCE: "probes/" + SOURCE}
    need(type(pin) is dict and set(pin) == set(files) | set(HOST_HELPERS))
    payload = {}
    for source in pin:
        path = root / source
        need(not path.is_symlink() and not any(parent.is_symlink() for parent in path.parents if parent != root))
        raw = read(path, MAX_CASE if source == PROBES + "/" + SOURCE else 1048576, nonempty=True)
        fingerprint = digest(raw)
        need(fingerprint == pin[source])
        if source == PROBES + "/" + SOURCE:
            need(fingerprint == SOURCE_SHA256)
        if source in files:
            payload[files[source]] = raw
    return pin, payload


def bind(root, smoke):
    policy = load(root / "scripts/native_1c_ci_policy.py", "strsplit_ci_policy")
    context = os.environ
    event = policy.read_event(context)
    expected = {
        "GITHUB_REPOSITORY": policy.REPOSITORY, "GITHUB_REPOSITORY_ID": str(policy.REPOSITORY_ID),
        "GITHUB_REPOSITORY_OWNER": policy.OWNER, "GITHUB_REPOSITORY_OWNER_ID": str(policy.OWNER_ID),
        "GITHUB_ACTOR": policy.OWNER, "GITHUB_ACTOR_ID": str(policy.OWNER_ID),
        "NATIVE_TRIGGERING_ACTOR": policy.OWNER, "GITHUB_EVENT_NAME": "push", "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF": REF, "GITHUB_WORKFLOW_REF": WORKFLOW,
    }
    need(all(context.get(key) == value for key, value in expected.items())
         and policy.trusted_repository(event.get("repository")) and policy.owner_identity(event.get("sender")))
    head = context.get("GITHUB_SHA")
    commit = policy.object_value(event.get("head_commit"))
    need(policy.is_sha(head) and context.get("GITHUB_WORKFLOW_SHA") == head
         and event.get("ref") == REF and event.get("after") == commit.get("id") == head
         and event.get("deleted") is False and event.get("forced") is False and not event.get("inputs")
         and event.get("created") is True and event.get("before") == "0" * 40)
    proven = smoke.FULL.repository_provenance(root)
    # One reviewed child of the pinned public base. Raw parents survive a depth-1 checkout.
    rc, raw, err = smoke.FULL.bounded_child(["git", "--no-replace-objects", "cat-file", "commit", head],
                                             root, stdout_limit=16384, stderr_limit=256)
    parents = re.findall(rb"(?m)^parent ([0-9a-f]{40})$", raw.split(b"\n\n", 1)[0])
    need(rc == 0 and not err and parents == [BASE.encode("ascii")] and proven["commit"] == head)
    return {"ref": REF, **proven}


def prepare(root, staged, smoke, payload, nonce):
    # Build the exact baseline command first with the unchanged normal inventory.
    smoke.stage_inputs(staged)
    need(type(nonce) is str and re.fullmatch("[0-9a-f]{32}", nonce))
    name = "onec-smoke-" + nonce
    command = smoke.container_command(staged, name, bootstrap=True)
    for dest, raw in payload.items():
        if dest.startswith("probes/"):
            path = staged / dest
            path.parent.mkdir(mode=0o755, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o644)
        else:
            need((staged / dest).read_bytes() == raw)
    (staged / "bootstrap/run_stage.py").rename(staged / BOOTSTRAP_ALIAS)
    wrapper = staged / "bootstrap/run_stage.py"
    wrapper.write_bytes(smoke.FULL.read_regular(root / SELF, 65536, nonempty=True))
    wrapper.chmod(0o644)
    (staged / "nonce").write_text(nonce, encoding="ascii")
    (staged / "nonce").chmod(0o644)
    # Unchanged smoke shell owns startup/teardown and its own validated report.
    # The fixed adapter executes in the existing stage hook, before display teardown.
    need(command[-2:] == ["/smoke/probe.sh", "--bootstrap-simple-epf"])
    command[-2:] = ["-c", '/bin/bash --noprofile --norc /smoke/probe.sh --bootstrap-simple-epf && /bin/cat /tmp/onec-smoke/native-strsplit-array-v1.json']
    return name, command


def run(root, smoke, provenance, pins, payload):
    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    token = os.environ.pop("GHCR_TOKEN", "")
    actor = os.environ.pop("GHCR_USER", "")
    need(token and actor == "Atridis")
    with tempfile.TemporaryDirectory(prefix="onec-strsplit-", dir=temp) as folder:
        work = Path(folder)
        nonce = uuid.uuid4().hex
        name, command = prepare(root, work / "staged", smoke, payload, nonce)
        auth = work / "auth"
        auth.mkdir(mode=0o700)
        try:
            env = smoke.docker_environment(auth)
            smoke.run_silent(["docker", "login", "ghcr.io", "--username", actor, "--password-stdin"],
                             env, 60, token.encode())
            smoke.run_silent(["docker", "pull", "--platform", "linux/amd64", EXPECTED_IMAGE], env, 600)
        finally:
            token = ""
            shutil.rmtree(auth)
        clean = work / "no-auth"
        clean.mkdir(mode=0o700)
        env = smoke.docker_environment(clean)
        code, data = smoke.bounded_run(["docker", "image", "inspect", "--format",
                                       "{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}", EXPECTED_IMAGE], env, 30, 128)
        need(code == 0 and data.strip() == b"linux/amd64|0")
        try:
            code, data = smoke.bounded_run(command, env, 1500, MAX_TRANSPORT)
            lines = data.splitlines()
            need(code == 0 and len(lines) == 2)
            bootstrap = smoke.validate_report(lines[0], bootstrap=True)
            need(bootstrap["status"] == "ok" and bootstrap["stage2"]["status"] == "ok"
                 and bootstrap["runtime_version"] == VERSION)
            observation = validate_observation(smoke.FULL.strict_json(lines[1], 8192), nonce)
        finally:
            smoke.run_silent(["docker", "rm", "--force", name], env, 30)
            code, live = smoke.bounded_run(["docker", "ps", "--all", "--filter", "name=^/" + name + "$",
                                            "--format", "{{.Names}}"], env, 30, 128)
            need(code == 0 and not live.strip())
    need(bind(root, smoke) == provenance and admitted_sources(root, smoke) == (pins, payload))
    complete = observation["kind"] == "ran"
    return {"schema": SCHEMA, "native_complete": complete, "runtime_parity_accepted": False, "repository": provenance,
            "image": EXPECTED_IMAGE, "version": VERSION, "platform": "linux/amd64",
            "mode": "managed-thick-file", "locale": "ru_RU", "input_sha256": pins,
            "driver_sha256": digest((root / SELF).read_bytes()),
            "observations": {SOURCE: observation}}


def main():
    if Path(__file__) == Path("/smoke/bootstrap/run_stage.py") and not sys.argv[1:]:
        return acq_stage(Path("/smoke") / BOOTSTRAP_ALIAS)
    root = Path(__file__).resolve().parents[1]
    smoke = load(root / "scripts/native_1c_smoke.py", "strsplit_smoke")
    need(smoke.IMAGE == EXPECTED_IMAGE and smoke.EXPECTED_VERSION == VERSION)
    need(sys.argv[1:] in (["--verify"], ["--execute-approved-image"]))
    provenance = bind(root, smoke)
    pins, payload = admitted_sources(root, smoke)
    if sys.argv[1:] == ["--verify"]:
        return 0
    result = run(root, smoke, provenance, pins, payload)
    out = Path(os.environ["RUNNER_TEMP"]) / "native-strsplit-array.json"
    with out.open("x", encoding="ascii") as path:
        path.write(json.dumps(result, sort_keys=True) + "\n")
    print("Native observation complete." if result["native_complete"] else "Native observation incomplete.")
    return 0 if result["native_complete"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # No raw Docker, native, repository, process, or filesystem diagnostics.
        print("Native StrSplit Array observation unavailable.", file=sys.stderr)
        raise SystemExit(1) from None
