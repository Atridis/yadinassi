"""Fixed, observe-only Array/Var acquisition using the existing native bootstrap."""
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

BASE = "6ff2eb54c59601625922557f4a5a01dd44ca585b"
REF = "refs/heads/codex/native-ordinary-oracle-reviewed"
WORKFLOW = "Atridis/yadinassi/.github/workflows/native-1c-ordinary-array-var.yml@" + REF
PROBES = "integrational_tests/measurements/ordinary_array_var"
MANIFEST = PROBES + "/sha256.json"
EXPECTED_IMAGE = "ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728"
SCHEMA = "ordinary-array-var-v1"
VERSION = "8.3.27.1508"
FILES = ("01_lexical_var.bsl", "02_module_var.bsl", "03_loop_local_var.bsl", "04_array_indices.bsl")
PREFIXES = ("var.lexical", "var.module", "var.loop-local")
INDEXES = ("zero", "one", "upper", "minus-one", "minus-half", "half", "one-point-nine", "true")
METHODS = ("bracket-read", "get", "bracket-write", "set")
NUMBER = r'\{"N",-?[0-9]{1,10}\}'
VAR_COLUMN = 37  # pinned loop-local source, UTF-8 ASCII line 1
MAX_CASE = 8192
MAX_TRANSPORT = 49152
SELF = "scripts/native_1c_ordinary_array_var.py"
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


def parse_outcome(index, raw):
    """Return exact strings, but only when every byte is in the finite grammar."""
    need(type(raw) is str and 0 < len(raw) <= MAX_CASE and raw.isascii())
    lines = raw.split("\n")
    need(lines.pop() == "")
    if index < 3:
        need(len(lines) == 1 and re.fullmatch(re.escape(PREFIXES[index]) + r": observed\|" + NUMBER, lines[0]))
        if index == 0:
            need(lines[0] == 'var.lexical: observed|{"N",42}')
        elif index == 1:
            need(lines[0] != 'var.module: observed|{"N",42}')
        return raw
    need(len(lines) == 33 and lines[-1] == "array.indices: complete")
    for i, label in enumerate(INDEXES):
        for j, method in enumerate(METHODS):
            line = lines[4 * i + j]
            prefix = "array." + method + "." + label + ": "
            need(line.startswith(prefix))
            result = line[len(prefix):]
            if j < 2:
                need(re.fullmatch(r"(?:error|ok\|" + NUMBER + ")", result))
                if i < 3:
                    need(result == ('ok|{"N",7}', 'ok|{"N",9}', 'error')[i])
            else:
                need(re.fullmatch(r'(?:ok|error)\|\{"N",2\}\|' + NUMBER + r'\|' + NUMBER, result))
                if i < 3:
                    need(result == ('ok|{"N",2}|{"N",99}|{"N",9}', 'ok|{"N",2}|{"N",7}|{"N",99}',
                                    'error|{"N",2}|{"N",7}|{"N",9}')[i])
    return raw


def var_compile_position(text, source):
    """Recognize only an explicit source-bound diagnostic; never expose raw lines."""
    owned_line = source.decode("utf-8").split("\n")[0]
    token = "Var i;i=10"
    need(owned_line[VAR_COLUMN - 1:].startswith(token))
    phrase = re.compile(r"(?:объявлени[ея]|определени[ея]) переменн(?:ых|ой).*?(?:в начале|не допуска)|"
                        r"(?:variable declaration|variables).*?(?:at the beginning|not allowed)", re.I)
    frame = re.compile(r"^\{(?:ВнешняяОбработка\.TestModule\.МодульОбъекта|"
                       r"ExternalDataProcessor\.TestModule\.ObjectModule)\(1,\s*" + str(VAR_COLUMN) + r"\)\}")
    for line in text.splitlines():
        if frame.match(line.lstrip()) and phrase.search(line):
            return VAR_COLUMN
    return None


def copied_source(base, source, case):
    original = base.bounded_bytes(source, MAX_CASE)
    copied = base.bounded_bytes(case / "src/TestModule/Ext/ObjectModule.bsl", MAX_CASE)
    need(copied.decode("utf-8-sig").encode("utf-8") == original)
    return original


def locate_var_refusal(base, source, case):
    # The only raw evidence read here is owned by this one EPF attempt.
    paths = (("designer", "TestModule.designer.log"), ("designer", "TestModule.designer-console.log"),
             ("enterprise", "enterprise.log"), ("enterprise", "enterprise-console.log"),
             ("enterprise", "result.json"))
    original = copied_source(base, source, case)
    for phase, diagnostic in paths:
        log = case / diagnostic
        if not log.exists() or log.stat().st_size == 0:
            continue
        raw = base.bounded_bytes(log, 65536)
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        if diagnostic == "result.json":
            text = base.read_marker(log)["error"]
            need(type(text) is str)
        position = var_compile_position(text, original)
        if position is not None:
            return {"kind": "compile-refusal", "line": 1, "column": position, "phase": phase}
    return {"kind": "inconclusive"}


def acq_stage(bootstrap):
    # Runs at the trusted launcher stage while its private display is still alive.
    sys.path.insert(0, str(bootstrap.parent))
    base = load(bootstrap, "ordinary_base_stage")
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
    outcomes = []
    for index, name in enumerate(FILES):
        case = oracle / str(index)
        source = base.INPUTS / "probes" / name
        output = oracle / (str(index) + ".out")
        outcome = {"kind": "inconclusive"}
        try:
            launcher.run_case(platform, source, epf, case, output)
        except launcher.LaunchError as error:
            # The pinned launcher uses this prefix only after its timeout and
            # process cleanup. Partial logs are not admissible in that case.
            if index == 2 and not str(error).startswith("Истек таймаут "):
                try:
                    outcome = locate_var_refusal(base, source, case)
                except (KeyError, OSError, ValueError, base.DraftError):
                    pass
        except (OSError, UnicodeError):
            pass
        else:
            # A completed launcher with invalid output is inconclusive, not a
            # compiler refusal even if there is text in a diagnostic log.
            try:
                base.require_zero_result(case / "TestModule.build-result.txt", 0)
                base.require_epf(case / "TestModule.epf")
                copied_source(base, source, case)
                value = parse_outcome(index, base.bounded_bytes(output, MAX_CASE).decode("utf-8"))
                outcome = {"kind": "ran", "output": value}
            except (OSError, ValueError, base.DraftError):
                pass
        outcomes.append(outcome)
    nonce = base.bounded_bytes(base.INPUTS / "nonce", 32).decode("ascii")
    with (base.ROOT / (SCHEMA + ".json")).open("x", encoding="ascii") as path:
        path.write(json.dumps({"schema": SCHEMA, "nonce": nonce, "outcomes": outcomes}) + "\n")
    return 0


def validate_outcomes(value, nonce):
    need(type(value) is dict and set(value) == {"schema", "nonce", "outcomes"}
         and value["schema"] == SCHEMA and value["nonce"] == nonce)
    outcomes = value["outcomes"]
    need(type(outcomes) is list and len(outcomes) == len(FILES))
    for index, item in enumerate(outcomes):
        need(type(item) is dict)
        if set(item) == {"kind", "output"} and item["kind"] == "ran":
            parse_outcome(index, item["output"])
        elif index == 2 and set(item) == {"kind", "line", "column", "phase"}:
            need(item["kind"] == "compile-refusal" and type(item["line"]) is int and item["line"] == 1
                 and type(item["column"]) is int and item["column"] == VAR_COLUMN
                 and item["phase"] in ("designer", "enterprise"))
        else:
            need(item == {"kind": "inconclusive"})
    return outcomes


def admitted_sources(root, smoke):
    read = smoke.FULL.read_regular
    pin = smoke.FULL.strict_json(read(root / MANIFEST, MAX_CASE, nonempty=True), MAX_CASE)
    files = {**smoke.staged_files(False, False), **{PROBES + "/" + n: "probes/" + n for n in FILES}}
    need(type(pin) is dict and set(pin) == set(files) | set(HOST_HELPERS))
    payload = {}
    for source in pin:
        path = root / source
        need(not path.is_symlink() and not any(parent.is_symlink() for parent in path.parents if parent != root))
        raw = read(path, 1048576, nonempty=True)
        need(digest(raw) == pin[source])
        if source in files:
            payload[files[source]] = raw
    return pin, payload


def bind(root, smoke):
    policy = load(root / "scripts/native_1c_ci_policy.py", "ordinary_ci_policy")
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
         and ((event.get("created") is True and event.get("before") == "0" * 40)
              or (event.get("created") is False and event.get("before") == BASE)))
    proven = smoke.FULL.repository_provenance(root)
    # One reviewed child of published L49. Raw parents survive a depth-1 checkout.
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
    command[-2:] = ["-c", '/bin/bash --noprofile --norc /smoke/probe.sh --bootstrap-simple-epf && /bin/cat /tmp/onec-smoke/ordinary-array-var-v1.json']
    return name, command


def run(root, smoke, provenance, pins, payload):
    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    token = os.environ.pop("GHCR_TOKEN", "")
    actor = os.environ.pop("GHCR_USER", "")
    need(token and actor == "Atridis")
    with tempfile.TemporaryDirectory(prefix="onec-ordinary-", dir=temp) as folder:
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
            outcomes = validate_outcomes(smoke.FULL.strict_json(lines[1], 8192), nonce)
        finally:
            smoke.run_silent(["docker", "rm", "--force", name], env, 30)
            code, live = smoke.bounded_run(["docker", "ps", "--all", "--filter", "name=^/" + name + "$",
                                            "--format", "{{.Names}}"], env, 30, 128)
            need(code == 0 and not live.strip())
    need(bind(root, smoke) == provenance and admitted_sources(root, smoke) == (pins, payload))
    accepted = all(o["kind"] != "inconclusive" for o in outcomes)
    return {"schema": SCHEMA, "native_complete": accepted, "runtime_parity_accepted": False, "repository": provenance,
            "image": EXPECTED_IMAGE, "version": VERSION, "platform": "linux/amd64",
            "mode": "managed-thick-file", "locale": "ru_RU", "input_sha256": pins,
            "driver_sha256": digest((root / SELF).read_bytes()),
            "observations": dict(zip(FILES, outcomes))}


def main():
    if Path(__file__) == Path("/smoke/bootstrap/run_stage.py") and not sys.argv[1:]:
        return acq_stage(Path("/smoke") / BOOTSTRAP_ALIAS)
    root = Path(__file__).resolve().parents[1]
    smoke = load(root / "scripts/native_1c_smoke.py", "ordinary_smoke")
    need(smoke.IMAGE == EXPECTED_IMAGE and smoke.EXPECTED_VERSION == VERSION)
    need(sys.argv[1:] in (["--verify"], ["--execute-approved-image"]))
    provenance = bind(root, smoke)
    pins, payload = admitted_sources(root, smoke)
    if sys.argv[1:] == ["--verify"]:
        return 0
    result = run(root, smoke, provenance, pins, payload)
    out = Path(os.environ["RUNNER_TEMP"]) / "native-ordinary-array-var.json"
    with out.open("x", encoding="ascii") as path:
        path.write(json.dumps(result, sort_keys=True) + "\n")
    print("Native observation complete." if result["native_complete"] else "Native observation incomplete.")
    return 0 if result["native_complete"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # No raw Docker, native, repository, process, or filesystem diagnostics.
        print("Native Array/Var observation unavailable.", file=sys.stderr)
        raise SystemExit(1) from None
