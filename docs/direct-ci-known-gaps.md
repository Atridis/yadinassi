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

## Owned catalog selection follow-up

On `7486c984`, the unchanged replay command above reproduces
`BoundaryViolation: unregistered or foreign database receiver` at `CS.Next()`
after observations 1–17. The direct database boundary now admits the exact
`BSLCatalogSelection` type only through its manager's current catalog root,
using the same owner check as catalog objects. Public Next/Следующий,
GetObject/ПолучитьОбъект and field access use the existing selection protocol.
There is no VM dispatch, generic getattr, detached-selection exemption or new
iterator adapter. Selection fields remain read-only; explicit database
transactions and existing writer/source/schema checks are unchanged.

The original replay now emits observations 1–23, including count=1 and the
rejected stale write (persisted `first-update`, buffer `stale-update`). It still
fails at observation 24: `BSLRuntimeError: Переменная или функция не определена:
Metadata`. No fixture, native expected output or comparison gate changed.
This is a host replay prefix, **not** a complete accepted comparison or native
remeasurement. Managed-form TypeDescription, six-scenario managed-thick-file,
Python 3.10 source positions and broader legacy parity gaps remain.

Focused regressions exercise actual SQLite selection, both aliases, fields,
GetObject, empty/end/restart behavior, foreign/subclass rejection, private and
write/iteration denial, owner replacement after method binding, closed-family
checks and the unchanged original replay with legacy dispatch forbidden:

```sh
PYTHONPATH=tests:scripts:. python -B -m unittest test_python_direct_database test_python_direct_uuid
PYTHONPATH=tests:scripts:. python -B -O -m unittest test_python_direct_database test_python_direct_uuid
```

Validation for this slice: 60 tests PASS in normal mode and the same 60 PASS
under `-O`: the two modules above plus `test_python_direct_form_database_admission`,
`test_python_direct_catalog_preparation`, `test_python_direct_prepared_validator`
and `test_python_direct_default`. Independent review found no blockers.
The additional `test_catalog_dynamic_types` probe had one existing failure,
`test_interpreter_value_operations` on `ref.IsEmpty()` (foreign database
receiver); it was reproduced separately on unchanged `7486c984`. Combined with
the first three focused modules, that probe ran 38 tests: 37 PASS, one error,
in both modes. No full CI success is claimed.

## Catalog metadata follow-up

On `392b6fa5`, the unchanged CatalogObject replay reproduced the undefined
`Metadata` failure at observation 24. The direct database namespace now resolves
`Metadata`/`Метаданные` to the current runtime metadata root. Exact root,
catalog metadata collection and catalog metadata item receivers use current
runtime identity checks before public protocol access and again before a bound
method invocation. The existing metadata implementation still owns lazy snapshot
loading, source order and schema validation; no VM dispatch or new cache is added.
Public catalog lookup, indexing, Name/FullName and identity are available.
Private members, writes, subclasses, foreign runtime metadata and collection
iteration remain rejected. Other metadata receiver families (including document
collections and catalog child collections) have not been admitted by this slice.
The namespace remains scoped to the existing host-selected database profile;
no-database/configuration/managed-profile compatibility is not claimed.

The exact original `catalog_object_behavior.replay.replay()` now returns all
24 observations, including the final reference/metadata identity `True`:

```text
[True, True, True, True, True, True, True, True, 'initial', 'initial',
 True, True, 'edited', False, True, True, '100', 1, False,
 'first-update', 'stale-update', True, True, True]
```

The full host replay regression forbids Interpreter.block/call_routine. No
native fixture, expected output, source binding, comparison gate or backend
selector changed. This completes that owned logical host replay, **not** a new
native measurement or a claim that its output matches native observations.
Managed-form TypeDescription, six-scenario managed-thick-file, Python 3.10 source
positions and broader direct compatibility gaps remain.

Validation: 67 tests PASS normal and the same 67 PASS under `-O`, using
`test_python_direct_database`, `test_python_direct_uuid`,
`test_python_direct_form_database_admission`,
`test_python_direct_catalog_preparation`,
`test_python_direct_prepared_validator`, and `test_python_direct_default`.
New tests cover both aliases, public lookup/identity, foreign/subclass/private/
write/iteration denials, prepared current-runtime binding, and owner/context
replacement after method binding before invocation.

The actual comparator's `EXECUTE_SCRIPT` also ran in an isolated `-I -B` child:
exit 0, empty stderr, 156 bytes, 24 observations accepted by `parse_output`.
Canonical output SHA-256:
`5a94916806539bfdd40517a7092b3a543ea6dc53d52f0f0cedbd8d37ba3b23f4`.
This establishes valid host output; native comparison was not run locally.

## Dynamic form declarations follow-up

On `bc0d117d`, the unchanged managed-form command above failed during preparation
with `UnsupportedNakedSyntax: constructor TypeDescription`. The direct form
bridge now admits TypeDescription/ОписаниеТипов only with the existing exact
BSLTypeDescription constructor and FormAttribute/РеквизитФормы only with the
current form interpreter's canonical `_make_attribute` binding. Binding checks
run before constructor argument effects. Existing descriptor/form-model type,
qualifier, side, scope and lifecycle validation remains in place.

A small ChangeAttributes/ИзменитьРеквизиты service adapter converts exact native
Python lists to the existing BSLArray input protocol; the model still validates
and atomically installs/removes declarations. The exact current self-form gets
public property reads/writes through its existing model methods. Foreign forms,
private members, missing properties, client-side declaration mutation and
transaction activation remain rejected. No generic reflection, VM dispatch,
source fallback or new cache is introduced.

The original unchanged source now executes all 24 server observations and client
observation 25. It creates the five scalar attributes, controls and commands,
sets String/Number/Boolean fields and successfully adds/removes `Temporary`.
The next failure is `BoundaryViolation: unregistered host service: serverread`
in `FormOpen` at client observation 26. No complete managed-form comparison or
native parity is claimed, and no fixture/gate/source hash changed.

This slice supports dynamic scalar declarations and own-self properties, not
all TypeDescription overloads or descriptor operations: native-list type arrays,
qualifier constructors, methods on unattached descriptors and arbitrary
self-form methods remain outside this bridge. The standalone form's cross-side
server routine binding needs a separate implementation; the existing enrolled
form/RPC route was not replaced.

Validation: 36 tests PASS normal and the same 36 PASS with `-O`, combining
`test_python_direct_forms`, `test_python_direct_form_database_admission`,
`test_python_direct_bound_forms`, `test_python_direct_form_invocation`,
`test_python_direct_form_callbacks` and `test_python_direct_form_rpc`.
The original replay-prefix regression forbids Interpreter.block/call_routine.
Independent review found a private-member exception-class regression, which was
fixed while retaining the original boundary test; the reviewer then passed 19
combined `-O` tests plus the two final live-binding/client-mutation regressions.
No remaining review blockers; no full CI/native pass is claimed.

## Standalone zero-argument server calls

On `1cd9d1f4`, the original managed-form host source reproduced
`BoundaryViolation: unregistered host service: serverread` at MF26. Direct
handler preparation deliberately separates client and server closure families;
standalone FormSession had not installed a cross-side invocation binding.

The default standalone FormSession now opts in to bindings for its own
zero-argument server routines. Custom interpreter factories, DB contexts and
reference scopes do not opt in. The existing invocation binding protocol checks
current binding/routine identity, side, signature, arity and function/procedure
use. Existing bound transports take precedence; no renderer dispatch, network
RPC or general configuration-module route is replaced. Later enrollment or
acquisition of DB/configuration/reference ownership rejects the local path.

Invocation uses the existing prepared Python export entry with fresh server
state and the existing side/transaction scope. Return values pass through the
existing cross-context packet copier, so form/capability objects do not escape.
No AST body dispatch, legacy activation interpreter or fallback is used.
Parameterized calls, default/byref argument transfer and native Python
collection transfer are outside this narrow slice.

The unchanged managed-form source now reaches MF1–MF30: MF26 reads `Ada`, MF27
observes `server-updated`, and MF30 is `programmatic`. It next fails at MF31 with
`BoundaryViolation: unregistered host member: NameField`, while preparing the
byref `Items.NameField` argument of FieldChanged. This is a separate control
reference boundary, not a failed server call. Full managed-form output/native
comparison remains incomplete; fixtures, source hashes and gates are unchanged.

Validation: 43 tests PASS normal and the same 43 PASS under `-O`, combining
`test_python_direct_forms`, `test_python_direct_form_invocation`,
`test_python_direct_form_database_admission`, `test_python_direct_bound_forms`,
`test_python_direct_form_callbacks` and `test_python_direct_form_rpc`.
Independent review: no blockers; 29 focused `-O` tests PASS, including actual
Receipt RPC. Tests cover actual server side/restoration, failure restoration,
capability-return rejection, custom-factory and parameterized-call exclusion,
retained binding/signature/side/lifetime checks, later enrollment rejection and
transaction denial. Original source replay forbids legacy block/call_routine.
