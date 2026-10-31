#!/usr/bin/env bash
# Runs only inside the separately approved, isolated, digest-pinned image.
# Stage two runs only with the explicit fixed --bootstrap-simple-epf argument.
set -euo pipefail
SECONDS=0
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
bus_pid=''
bus_cleanup_failed=false
bootstrap=false
full_suite=false
invocation_nonce=''
client_probe=false
watchdog_check=false
client_dates=false
client_values=false
client_collections=false
client_numbers=false
client_async=false
client_args=()
preprocessor_measurement=false
tree_suite=false
if [ "$#" -eq 3 ] && { [ "$1" = --tree-suite ] || [ "$1" = --tree-copy-suite ] || [ "$1" = --tree-sort-suite ] || [ "$1" = --tree-columns-move-suite ] || [ "$1" = --tree-columns-move-boundary-suite ] || [ "$1" = --tree-columns-move-tail-suite ] || [ "$1" = --tree-columns-clear-suite ] || [ "$1" = --tree-columns-clear-lifetime-suite ] || [ "$1" = --tree-columns-clear-metadata-suite ] || [ "$1" = --tree-columns-delete-suite ] || [ "$1" = --tree-columns-delete-string-suite ]; }; then
    tree_suite=true
    if [ "$1" = --tree-copy-suite ]; then tree_suite=copy; fi
    if [ "$1" = --tree-sort-suite ]; then tree_suite=sort; fi
    if [ "$1" = --tree-columns-move-suite ]; then tree_suite=columns-move; fi
    if [ "$1" = --tree-columns-move-boundary-suite ]; then tree_suite=columns-move-boundary; fi
    if [ "$1" = --tree-columns-move-tail-suite ]; then tree_suite=columns-move-tail; fi
    if [ "$1" = --tree-columns-clear-suite ]; then tree_suite=columns-clear; fi
    if [ "$1" = --tree-columns-clear-lifetime-suite ]; then tree_suite=columns-clear-lifetime; fi
    if [ "$1" = --tree-columns-clear-metadata-suite ]; then tree_suite=columns-clear-metadata; fi
    if [ "$1" = --tree-columns-delete-suite ]; then tree_suite=columns-delete; fi
    if [ "$1" = --tree-columns-delete-string-suite ]; then tree_suite=columns-delete-string; fi
    set -- --full-suite "$2" "$3" --client-probe
fi
if [ "$#" -ge 5 ] && [ "$#" -le 10 ] && [ "${!#}" = --client-preprocessor-measurement ] && [ "${4}" = --client-probe ]; then
    preprocessor_measurement=true
    set -- "${@:1:$(($# - 1))}"
fi
if [ "$#" -eq 5 ] && [ "${5}" = --client-async-measurement ] && [ "${4}" = --client-probe ]; then
    client_async=true
    set -- "$1" "$2" "$3" "$4"
fi
if { [ "$#" -eq 5 ] || [ "$#" -eq 6 ] || [ "$#" -eq 7 ] || [ "$#" -eq 8 ] || [ "$#" -eq 9 ]; } && [ "${!#}" = --client-numbers-parity ] && [ "${4}" = --client-probe ]; then
    client_numbers=true
    set -- "${@:1:$(($# - 1))}"
fi
if { [ "$#" -eq 5 ] || [ "$#" -eq 6 ] || [ "$#" -eq 7 ] || [ "$#" -eq 8 ]; } && [ "${!#}" = --client-collections-parity ] && [ "${4}" = --client-probe ]; then
    client_collections=true
    set -- "${@:1:$(($# - 1))}"
fi
if { [ "$#" -eq 5 ] || [ "$#" -eq 6 ] || [ "$#" -eq 7 ]; } && [ "${!#}" = --client-values-parity ] && [ "${4}" = --client-probe ]; then
    client_values=true
    set -- "${@:1:$(($# - 1))}"
fi
if { [ "$#" -eq 5 ] || [ "$#" -eq 6 ]; } && [ "${!#}" = --client-dates-parity ] && [ "${4}" = --client-probe ]; then
    client_dates=true
    set -- "${@:1:$(($# - 1))}"
fi
if [ "$#" -eq 5 ] && [ "${5}" = --client-watchdog-check ] && [ "${4}" = --client-probe ]; then
    watchdog_check=true
    set -- "$1" "$2" "$3" "$4"
fi
if [ "$#" -eq 4 ] && [ "${4}" = --client-probe ]; then
    client_probe=true
    client_args=(--client-probe)
    if [ "$client_async" = true ]; then
        client_args+=(--client-async-measurement)
    fi
    if [ "$watchdog_check" = true ]; then
        client_args+=(--client-watchdog-check)
    fi
    if [ "$client_dates" = true ]; then
        client_args+=(--client-dates-parity)
    fi
    if [ "$client_values" = true ]; then
        client_args+=(--client-values-parity)
    fi
    if [ "$client_collections" = true ]; then
        client_args+=(--client-collections-parity)
    fi
    if [ "$client_numbers" = true ]; then
        client_args+=(--client-numbers-parity)
    fi
    if [ "$preprocessor_measurement" = true ]; then
        client_args+=(--client-preprocessor-measurement)
    fi
    set -- "$1" "$2" "$3"
fi
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
    if [ -n "$bus_pid" ]; then
        if python3 - "$invocation_nonce" "$bus_pid" "$$" <<'PYSTOPBUS'
import sys
from pathlib import Path
sys.path.insert(0, "/smoke/bootstrap")
import full_suite
full_suite.stop_session_bus(Path("/tmp/onec-smoke"), sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
PYSTOPBUS
        then
            # The pidfd confirmed termination; wait only reaps this direct child.
            wait "$bus_pid" 2>/dev/null || true
        else
            result=1
            stage=stage2
            bus_cleanup_failed=true
        fi
    fi
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
          "$infobase_created" "$configuration_dumped" "$bootstrap" "$full_suite" "$invocation_nonce" "$client_probe" "$watchdog_check" "$client_dates" "$client_values" "$client_collections" "$client_numbers" "$client_async" "$bus_cleanup_failed" "$preprocessor_measurement" "$tree_suite" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

emitter_args = sys.argv[1:]
tree_mode = emitter_args.pop() if len(emitter_args) == 19 else "false"
if tree_mode not in {"false", "true", "copy", "sort", "columns-move", "columns-move-boundary", "columns-move-tail", "columns-clear", "columns-clear-lifetime", "columns-clear-metadata", "columns-delete", "columns-delete-string"}:
    raise ValueError("tree mode")
preprocessor_mode = emitter_args.pop() if len(emitter_args) == 18 else "false"
if preprocessor_mode not in {"false", "true"}:
    raise ValueError("preprocessor mode")
async_mode = emitter_args.pop(15) if len(emitter_args) == 17 else "false"
if async_mode not in {"false", "true"}:
    raise ValueError("async mode")
code, stage, libraries, display, created, dumped, bootstrap, full_mode, nonce, client_mode, watchdog_mode, dates_mode, values_mode, collections_mode, numbers_mode, bus_cleanup_failed = emitter_args
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
if tree_mode in {"true", "copy", "sort", "columns-move", "columns-move-boundary", "columns-move-tail", "columns-clear", "columns-clear-lifetime", "columns-clear-metadata", "columns-delete", "columns-delete-string"}:
    sys.path.insert(0, "/smoke/bootstrap")
    import tree_suite as tree_lane
    import full_suite
    raw = tree_lane.finish_report(report, nonce, Path("/tmp/onec-smoke") / ("stage3-" + nonce),
        quiet=full_suite.native_processes_quiet(Path("/opt/1cv8t/x86_64/8.3.27.1508/1cv8t")),
        bus_cleanup_failed=bus_cleanup_failed == "true", profile={"copy":"tree-copy-v1", "sort":"tree-sort-v1", "columns-move":"tree-columns-move-v1", "columns-move-boundary":"tree-columns-move-boundary-v1", "columns-move-tail":"tree-columns-move-tail-v1", "columns-clear":"tree-columns-clear-v1", "columns-clear-lifetime":"tree-columns-clear-lifetime-v1", "columns-clear-metadata":"tree-columns-clear-metadata-v1", "columns-delete":"tree-columns-delete-v1", "columns-delete-string":"tree-columns-delete-string-v1", "true":"tree-v1"}[tree_mode])
    sys.stdout.buffer.write(raw)
    raise SystemExit(0)
if full_mode == "true":
    sys.path.insert(0, "/smoke/bootstrap")
    import full_suite
    suite = full_suite.empty_report(nonce, client_probe=client_mode == "true", watchdog_check=watchdog_mode == "true", client_dates=dates_mode == "true", client_values=values_mode == "true", client_collections=collections_mode == "true", client_numbers=numbers_mode == "true", **({"client_async": True} if async_mode == "true" else {}), **({"preprocessor_measurement": True} if preprocessor_mode == "true" else {}), preprocessor_runtime=client_mode == "true" and preprocessor_mode != "true")
    try:
        path = Path("/tmp/onec-smoke/stage3-report.json")
        if path.exists() or path.is_symlink():
            suite = full_suite.decode_stage_wire(full_suite.strict_json(
                full_suite.secure_bytes(path, full_suite.MAX_STAGE_REPORT)))
        elif (report.get("stage2") or {}).get("status") == "ok":
            suite.update(status="failed", failure_kind="unexpected_failure")
    except Exception:
        suite = full_suite.empty_report(nonce, client_probe=client_mode == "true", watchdog_check=watchdog_mode == "true", client_dates=dates_mode == "true", client_values=values_mode == "true", client_collections=collections_mode == "true", client_numbers=numbers_mode == "true", **({"client_async": True} if async_mode == "true" else {}), **({"preprocessor_measurement": True} if preprocessor_mode == "true" else {}), preprocessor_runtime=client_mode == "true" and preprocessor_mode != "true")
        suite.update(status="failed", failure_kind="export_failed")
    report["stage3"] = suite
    # A failed stage-three exit is not a failed bootstrap; preserve both outcomes.
    if report.get("stage2") is not None and report["stage2"]["status"] == "ok":
        if stage == "stage2" and code != "0":
            report["status"] = "stage3_failed"
        if suite["status"] != "ok" and report["status"] == "ok":
            report["status"] = "stage3_failed"
    if client_mode == "true" and report["status"] == "ok" and suite["status"] == "ok":
        try:
            full_suite.final_client_process_census(nonce)
        except full_suite.FullError as exc:
            report["status"] = "stage3_failed"
            full_suite.fail_client_process_checkpoint(suite, watchdog_mode == "true",
                exc.diagnostics if isinstance(exc, full_suite.ClientProcessError) else None)
    if client_mode == "true" and bus_cleanup_failed == "true" and suite["status"] == "ok":
        report["status"] = "stage3_failed"
        full_suite.fail_client_process_checkpoint(suite, watchdog_mode == "true")
    if async_mode == "true" and report["status"] == "ok" and suite["status"] == "ok":
        try:
            full_suite.final_async_evidence_check(Path("/tmp/onec-smoke") / ("stage3-" + nonce) / "client-async", Path("/smoke"), nonce, suite["client_async"]["continuity_sha256"])
        except (full_suite.FullError, OSError):
            report["status"] = "stage3_failed"
            full_suite.fail_client_process_checkpoint(suite, False)
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
if [ "$client_async" = true ]; then
    python3 - "$SECONDS" "$invocation_nonce" <<'PYASYNCDEADLINE'
import json
from pathlib import Path
import sys
import time
elapsed = int(sys.argv[1])
if not 0 <= elapsed <= 2340:
    raise SystemExit(1)
# One second conservative rounding plus60 seconds cleanup outside this deadline.
with Path('/tmp/onec-smoke/async-deadline.json').open('x', encoding='utf-8') as output:
    json.dump({'schema': 1, 'nonce': sys.argv[2], 'deadline': int(time.monotonic() + 2339 - elapsed)}, output)
PYASYNCDEADLINE
fi

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

# Own one private session bus before native code can autolaunch detached helpers.
# Preserve the pinned image's existing session policy. No host bus, TCP listener,
# address fallback, shell-evaluated output or executable-class exemption is used.
if [ "$client_probe" = true ]; then
    [ -x /usr/bin/dbus-daemon ]
    python3 -c 'import os, signal; assert hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"); fd = os.pidfd_open(os.getpid()); os.close(fd)'
    bus_dir="/tmp/onec-smoke/session-bus-$invocation_nonce"
    mkdir -m 700 "$bus_dir"
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_dir/bus"
    /usr/bin/dbus-daemon --session --nofork --nopidfile --nosyslog \
        --address="$DBUS_SESSION_BUS_ADDRESS" --print-address=3 \
        3> "$bus_dir/address" > "$bus_dir/console.log" 2>&1 &
    bus_pid=$!
    python3 - "$invocation_nonce" "$bus_pid" "$$" <<'PYPREPAREBUS'
import sys
from pathlib import Path
sys.path.insert(0, "/smoke/bootstrap")
import full_suite
full_suite.prepare_session_bus(Path("/tmp/onec-smoke"), sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
PYPREPAREBUS
fi

# Before any native invocation, record only the already-running harness/display/bus.
# The census Python process excludes itself; run_stage later admits only its own PID.
if [ "$client_probe" = true ]; then
    python3 - "$invocation_nonce" <<'PYCLIENTBASELINE'
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, "/smoke/bootstrap")
import full_suite
path = Path("/tmp/onec-smoke/client-process-baseline.json")
full_suite.absent(path)
bus = full_suite.require_session_bus(Path("/tmp/onec-smoke"), sys.argv[1])
identities = sorted(identity for identity in full_suite.client_process_snapshot()
                    if identity[0] != os.getpid())
if bus not in identities:
    raise full_suite.FullError("process_failed")
with path.open("x", encoding="utf-8") as stream:
    json.dump({"schema": 1, "nonce": sys.argv[1], "processes": identities}, stream)
PYCLIENTBASELINE
fi

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
    if [ "$tree_suite" != false ]; then
        tree_flag=--tree-suite
        if [ "$tree_suite" = copy ]; then tree_flag=--tree-copy-suite; fi
        if [ "$tree_suite" = sort ]; then tree_flag=--tree-sort-suite; fi
        if [ "$tree_suite" = columns-move ]; then tree_flag=--tree-columns-move-suite; fi
        if [ "$tree_suite" = columns-move-boundary ]; then tree_flag=--tree-columns-move-boundary-suite; fi
        if [ "$tree_suite" = columns-move-tail ]; then tree_flag=--tree-columns-move-tail-suite; fi
        if [ "$tree_suite" = columns-clear ]; then tree_flag=--tree-columns-clear-suite; fi
        if [ "$tree_suite" = columns-clear-lifetime ]; then tree_flag=--tree-columns-clear-lifetime-suite; fi
        if [ "$tree_suite" = columns-clear-metadata ]; then tree_flag=--tree-columns-clear-metadata-suite; fi
        if [ "$tree_suite" = columns-delete ]; then tree_flag=--tree-columns-delete-suite; fi
        if [ "$tree_suite" = columns-delete-string ]; then tree_flag=--tree-columns-delete-string-suite; fi
        python3 /smoke/bootstrap/run_stage.py "$tree_flag" --invocation-nonce "$invocation_nonce" \
            > /tmp/onec-smoke/stage2-console.log 2>&1
    elif [ "$full_suite" = true ]; then
        python3 /smoke/bootstrap/run_stage.py --full-suite --invocation-nonce "$invocation_nonce" "${client_args[@]}" \
            > /tmp/onec-smoke/stage2-console.log 2>&1
    else
        python3 /smoke/bootstrap/run_stage.py > /tmp/onec-smoke/stage2-console.log 2>&1
    fi
fi
stage=complete
