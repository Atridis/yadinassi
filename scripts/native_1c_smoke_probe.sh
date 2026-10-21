#!/usr/bin/env bash
# Runs only inside the separately approved, isolated, digest-pinned image.
# Stage two runs only with the explicit fixed --bootstrap-simple-epf argument.
set -euo pipefail
umask 077
exec 2>/dev/null
ONEC=/opt/1cv8t/x86_64/8.3.27.1508/1cv8t
stage=capabilities
python_available=false
python_supported=false
libraries_resolved=false
display_started=false
infobase_created=false
configuration_dumped=false
x_pid=''
bootstrap=false
full_suite=false
invocation_nonce=''
if [ "$#" -eq 1 ] && [ "$1" = --bootstrap-simple-epf ]; then
    bootstrap=true
elif [ "$#" -eq 3 ] && [ "$1" = --full-suite ] && [ "$2" = --invocation-nonce ] && [[ "$3" =~ ^[0-9a-f]{32}$ ]]; then
    bootstrap=true
    full_suite=true
    invocation_nonce=$3
elif [ "$#" -ne 0 ]; then
    exit 2
fi

finish() {
    result=$?
    trap - EXIT
    if [ -n "$x_pid" ]; then
        kill "$x_pid" 2>/dev/null || true
        wait "$x_pid" 2>/dev/null || true
    fi
    if [ "$python_available" != true ]; then
        printf '{"schema":1,"status":"python_missing"}\n'
    elif [ "$python_supported" != true ]; then
        printf '{"schema":1,"status":"python_unsupported"}\n'
    else
        python3 - "$result" "$stage" "$libraries_resolved" "$display_started" \
          "$infobase_created" "$configuration_dumped" "$bootstrap" "$full_suite" "$invocation_nonce" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

code, stage, libraries, display, created, dumped, bootstrap, full_mode, nonce = sys.argv[1:]
report = {
    "schema": 1,
    "status": "ok" if code == "0" else stage + "_failed",
    "python_version": ".".join(map(str, sys.version_info[:3])),
    "nonroot": os.geteuid() != 0,
    "executable_available": os.access("/opt/1cv8t/x86_64/8.3.27.1508/1cv8t", os.X_OK),
    "libraries_resolved": libraries == "true",
    "display_started": display == "true",
    "infobase_created": created == "true",
    "configuration_dumped": dumped == "true",
    # A path/tag does not prove the actual running platform version.
    "runtime_version": None,
    "runtime_version_source": "not_measured",
    "native_tests_completed": False,
    "security_settings_changed": False,
    "configuration_format": None,
}
if dumped == "true":
    try:
        path = Path("/tmp/onec-smoke/config/Configuration.xml")
        with path.open("rb") as source:
            data = source.read(1_048_577)
        if len(data) > 1_048_576 or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
            raise ValueError("unsafe XML")
        root = ET.fromstring(data)
        elements = list(root.iter())
        if len(elements) > 4096:
            raise ValueError("excessive XML")
        namespace = "http://v8.1c.ru/8.3/MDClasses"
        if root.tag != "{" + namespace + "}MetaDataObject":
            raise ValueError("unexpected root")
        version = root.get("version", "")
        if not re.fullmatch(r"[0-9]{1,2}(?:\.[0-9]{1,3}){1,3}", version):
            raise ValueError("unexpected schema version")
        configuration = root.find("{" + namespace + "}Configuration")
        if configuration is None:
            raise ValueError("no Configuration")
        # Only fixed known names, counts, a digest and numeric schema version leave
        # the container. No arbitrary XML text, UUIDs, paths or raw native output.
        allowed = {
            "Name", "Synonym", "Comment", "NamePrefix", "ConfigurationExtensionCompatibilityMode",
            "DefaultRunMode", "UsePurposes", "ScriptVariant", "DefaultRoles", "BriefInformation",
            "DetailedInformation", "Copyright", "Vendor", "Version", "CompatibilityMode",
            "DefaultLanguage", "DefaultStyle", "DefaultInterface", "UseManagedFormInOrdinaryApplication",
            "UseOrdinaryFormInManagedApplication", "EnableManagedLock", "MainClientApplicationWindowMode",
            "DefaultDataLockControlMode", "ModalityUseMode", "SynchronousPlatformExtensionAndAddInCallUseMode",
            "InterfaceCompatibilityMode", "DatabaseTablespacesUseMode", "MobileApplicationURLs",
            "CommonPictures", "Roles", "Languages", "CommonModules", "Subsystems", "SessionParameters",
        }
        detected = sorted({element.tag.rsplit("}", 1)[-1] for element in elements} & allowed)
        report["configuration_format"] = {
            "root": "MetaDataObject", "kind": "Configuration", "namespace": namespace,
            "schema_version": version, "element_count": len(elements),
            "sha256": hashlib.sha256(data).hexdigest(), "known_elements": detected,
            "managed_application_module_present": Path("/tmp/onec-smoke/config/Ext/ManagedApplicationModule.bsl").is_file(),
            "session_module_present": Path("/tmp/onec-smoke/config/Ext/SessionModule.bsl").is_file(),
        }
    except (OSError, ValueError, ET.ParseError):
        report["status"] = "format_failed"
        report["configuration_format"] = None
if bootstrap == "true":
    report["stage2"] = None
    path = Path("/tmp/onec-smoke/stage2-report.json")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    if path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 8192:
        try:
            stage2 = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
            report["stage2"] = stage2
            report["runtime_version"] = stage2["actual_version"]
            report["runtime_version_source"] = stage2["version_source"]
            report["security_settings_changed"] = {"not_attempted": False, "unverified": None, "verified": True}[stage2["security_settings_state"]]
        except (OSError, ValueError, KeyError, TypeError):
            report["status"] = "stage2_failed"
    if stage in {"stage2", "complete"} and report["stage2"] is None:
        # Even a simultaneous native-format failure cannot imply no mutation
        # after stage two may have begun. The host rejects this to unknown.
        report["status"] = "stage2_failed"
if full_mode == "true":
    sys.path.insert(0, "/smoke/bootstrap")
    import full_suite
    suite = full_suite.empty_report(nonce)
    try:
        path = Path("/tmp/onec-smoke/stage3-report.json")
        if path.exists() or path.is_symlink():
            suite = full_suite.strict_json(full_suite.secure_bytes(path, full_suite.MAX_STAGE_REPORT))
        elif (report.get("stage2") or {}).get("status") == "ok":
            suite.update(status="failed", failure_kind="unexpected_failure")
    except Exception:
        suite = full_suite.empty_report(nonce)
        suite.update(status="failed", failure_kind="export_failed")
    report["stage3"] = suite
    # A failed stage-three exit is not a failed bootstrap; preserve both outcomes.
    if report.get("stage2") is not None and report["stage2"]["status"] == "ok":
        if stage == "stage2" and code != "0":
            report["status"] = "stage3_failed"
        if suite["status"] != "ok" and report["status"] == "ok":
            report["status"] = "stage3_failed"
    report["native_tests_completed"] = report["status"] == "ok" and suite["status"] == "ok"
    raw = full_suite.build_envelope(
        report, nonce, Path("/tmp/onec-smoke") / ("stage3-" + nonce),
        quiet=full_suite.native_processes_quiet(Path("/opt/1cv8t/x86_64/8.3.27.1508/1cv8t")))
    sys.stdout.buffer.write(raw)
    raise SystemExit(0 if report["status"] == "ok" else 1)
else:
    print(json.dumps(report, sort_keys=True))
PY
    fi
    exit "$result"
}
trap finish EXIT

if ! command -v python3 >/dev/null 2>&1; then exit 10; fi
python_available=true
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
python_supported=true
[ "$(id -u)" -eq 1000 ]
[ -x "$ONEC" ]
for tool in timeout ldd Xtigervnc xauth xdpyinfo; do
    command -v "$tool" >/dev/null 2>&1
done
mkdir -p "$HOME" "$XDG_RUNTIME_DIR" /tmp/onec-smoke/config /tmp/.X11-unix
chmod 700 "$HOME" "$XDG_RUNTIME_DIR" /tmp/onec-smoke
chmod 1777 /tmp/.X11-unix

stage=libraries
LC_ALL=C timeout --signal=TERM --kill-after=5s 15s ldd "$ONEC" > /tmp/onec-smoke/ldd.log 2>&1
python3 - /tmp/onec-smoke/ldd.log <<'PYLIBRARIES'
from pathlib import Path
import sys
with Path(sys.argv[1]).open("rb") as source:
    data = source.read(65537)
raise SystemExit(0 if data and len(data) <= 65536 and b"not found" not in data else 1)
PYLIBRARIES
libraries_resolved=true

stage=display
export XAUTHORITY=/tmp/onec-smoke/xauth
cookie=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
xauth -f "$XAUTHORITY" add "$DISPLAY" MIT-MAGIC-COOKIE-1 "$cookie" >/dev/null 2>&1
unset cookie
# -rfbport -1 disables RFB TCP. No RFB Unix socket is configured. X11 TCP is off.
# Keep TigerVNC authentication defaults; do not use -ac or SecurityTypes=None.
Xtigervnc "$DISPLAY" -geometry 1280x800 -depth 24 -rfbport -1 -nolisten tcp \
    -auth "$XAUTHORITY" > /tmp/onec-smoke/display.log 2>&1 &
x_pid=$!
for attempt in {1..40}; do
    kill -0 "$x_pid"
    if timeout 2s xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        display_started=true
        break
    fi
    sleep 0.25
done
[ "$display_started" = true ]

check_result() {
    python3 - "$1" <<'PYRESULT'
from pathlib import Path
import sys
with Path(sys.argv[1]).open("rb") as source:
    data = source.read(4097)
if len(data) > 4096:
    raise SystemExit(1)
encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
raise SystemExit(0 if data.decode(encoding).strip() == "0" else 1)
PYRESULT
}

stage=create
# One disposable, initially empty file infobase; no template or existing data.
timeout --signal=TERM --kill-after=10s 120s "$ONEC" CREATEINFOBASE \
    'File="/tmp/onec-smoke/db";' /Lru \
    /Out /tmp/onec-smoke/create.log /DumpResult /tmp/onec-smoke/create-result.txt \
    > /tmp/onec-smoke/create-console.log 2>&1
check_result /tmp/onec-smoke/create-result.txt
[ -s /tmp/onec-smoke/db/1Cv8.1CD ]
infobase_created=true

stage=dump
timeout --signal=TERM --kill-after=10s 120s "$ONEC" DESIGNER \
    /F /tmp/onec-smoke/db /DisableStartupDialogs /DisableStartupMessages \
    /DumpConfigToFiles /tmp/onec-smoke/config -Format Hierarchical \
    /Out /tmp/onec-smoke/dump.log /DumpResult /tmp/onec-smoke/dump-result.txt \
    > /tmp/onec-smoke/dump-console.log 2>&1
check_result /tmp/onec-smoke/dump-result.txt
[ -s /tmp/onec-smoke/config/Configuration.xml ]
configuration_dumped=true
if [ "$bootstrap" = true ]; then
    stage=stage2
    # All source inputs are host-allowlisted and read-only. All outputs stay tmpfs.
    if [ "$full_suite" = true ]; then
        python3 /smoke/bootstrap/run_stage.py --full-suite --invocation-nonce "$invocation_nonce" \
            > /tmp/onec-smoke/stage2-console.log 2>&1
    else
        python3 /smoke/bootstrap/run_stage.py > /tmp/onec-smoke/stage2-console.log 2>&1
    fi
fi
stage=complete
