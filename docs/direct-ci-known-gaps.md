# Native CI: known direct host gaps

Investigation of PR #337 run `43968817166` (candidate `2dc26d2d`,
GitHub merge checkout `0fb06a48`). These are **host implementation gaps**, not
permission to skip comparisons or substitute the legacy backend. Local host
reproductions on the later direct tree reproduce the first failures below.
No native container is needed for these reproductions.

| Job | First local host failure | What this proves |
| --- | --- | --- |
| Six scenarios, `133655283568` | `PythonDirectUnsupported` in `_admit_vm`: the client witness uses `managed-thick-file`, not the admitted standalone profile | Host preflight fails before native execution. CI reports `unexpected_host_failure`; this is not a native measurement. |
| Catalog object, `133655283566` | `PythonDirectUnsupported: constructor UUID` | The host replay cannot compile the original observation source; no host comparison output is produced. |
| Managed form, `133655283682` | `UnsupportedNakedSyntax: constructor TypeDescription` in `prepare_form` | The host form cannot compile its original declaration/event source; no host comparison output is produced. |

The catalog and managed-form reports separately accepted their real native
measurements, but rejected host comparison (`interpreter_size: 0`). Accepted
native evidence does **not** mean interpreter parity or an accepted comparison.
Their job logs end with a measurement/comparison failure. The six-scenario
report instead has native completion and acceptance fields false.

## Reproduce the host routes

Run from the repository root with its Python dependencies installed. Each
command intentionally raises the current failure. No GHCR credentials or
native execution are involved.

Catalog object, the exact replay used by its host comparator:

```sh
PYTHONPATH=scripts:. python -B -c 'from catalog_object_behavior.replay import replay; replay()'
```

Managed form, the same source and lifecycle binding used by its comparator:

```sh
PYTHONPATH=scripts:. python -B - <<'PY'
from form_runtime_packet import source
from yadinassi.form_runtime import FormSession
session = FormSession(source(), bindings={
    'OnCreateAtServer': 'FormCreate', 'OnOpen': 'FormOpen',
    'BeforeClose': 'FormBeforeClose'})
session.open()
PY
```

Six-scenario preflight, including its existing exclusively owned synthetic
SQLite fixture. This needs Linux and a free fixture location under `/tmp`.
The diagnostic runner only reveals the stderr which the finite public report
otherwise hides. It neither substitutes the backend nor changes the source.

```sh
PYTHONPATH=scripts:. python -B - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import native_1c_full_host as full
import native_1c_smoke as smoke

def diagnostic_runner(arguments, root):
    result = subprocess.run(arguments, cwd=root, capture_output=True, timeout=60)
    print(result.stderr.decode('utf-8', errors='replace'))
    return result.returncode, result.stdout, result.stderr

with TemporaryDirectory() as temporary:
    staged = Path(temporary) / 'staged'
    hashes = smoke.stage_inputs(staged, full_suite=True, client_probe=True)
    full.verify_client_interpreter(
        Path.cwd(), staged / 'bootstrap/client_probe.bsl',
        hashes[full.CLIENT_SOURCE], runner=diagnostic_runner)
PY
```

The child rejects its first `execute`; `verify_client_interpreter` then raises
`FullError('interpreter_failed')`. A small standalone-profile smoke would not
exercise this contract.

## Scope of follow-up work

* UUID is a bounded scalar value already implemented by `BSLUUID`. A narrow
  direct constructor binding is plausible; it is not implemented by this
  report. Completing it would not prove the entire catalog replay: later
  reference/metadata operations still need their own actual run.
* The managed-form source also constructs `FormAttribute`, changes declarations
  through `ChangeAttributes`, and exercises public form operations. Allowing
  `TypeDescription` alone is not evidence that the complete form passes.
* The six-scenario witness requires the managed compilation profile and its
  actual context/routine contracts. Removing standalone admission or silently
  executing an old VM is not a correction.

There are no changed CI allowances, expected outputs, source hashes, backend
selectors, or runtime permissions in this documentation-only change.

## Narrow UUID follow-up

The direct standalone/database entry now accepts the two existing UUID
constructor aliases, with exact canonical `HostFunction(BSLUUID)` admission.
Prepared reuse checks the current registry; a new constructor resolution checks
it again before argument effects. An already bound constructor remains the
callee if an argument callback replaces the registry entry. Construction still
uses the existing scalar value implementation, not a new object/member adapter.

With this change the unchanged catalog replay reaches observations 1–17,
including assigned UUID references, writes, reads, and duplicate-write rejection.
Its next failure is the unsupported `BSLCatalogSelection.Next()` receiver at the
public database boundary. The complete catalog comparison remains unsupported;
no native remeasurement or CI pass is claimed. Six-scenario and managed-form
failures above are unchanged. Focused tests cover aliases, invalid arguments,
registry substitution before execution and at a service boundary, argument
ordering, prepared-module revalidation, and the actual catalog replay prefix.
