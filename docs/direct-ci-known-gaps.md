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

## Public form-member references

On `e2eea8c6`, the unchanged managed-form source failed at MF31:
`BoundaryViolation: unregistered host member: NameField`. The generated call
correctly prepared a byref argument, but inherited reference binding still used
the generic HostMembers registry instead of the already-admitted form protocol.

FormBoundary now binds exact current-form model/self-form members after an eager
public read and reuses the existing `_HostMemberReference`. Reads remain live;
deferred writes use the existing form setter. Binding does not grant write
access: `Items.NameField` and `Commands.Apply` can be read by a handler but cannot
be reassigned. Writable public fields still use model validation. Foreign,
private, missing, retired and inactive/closed receivers are rejected. No new
reference implementation, raw attributes, alias cache or VM dispatch was added.

The exact unchanged managed-form source now completes MF1–MF40, including
FieldChanged, ApplyCommand, flag transfer and the two direct BeforeClose calls.
The actual comparator `EXECUTE_SCRIPT` also passes in an isolated `-I -B` child:
exit 0, empty stderr, 541 output bytes, 40 records accepted by
`parse_records`/`require_available`. Output SHA-256:
`3cbf5b2e8dee544690cd560f3405ab9029dfd3e0d711b2410c59ba288d8acb34`.
This is valid host output, **not** a new native measurement or native comparison.
The source's direct event calls do not prove automatic UI event parity.

Existing standalone zero-argument cross-side restrictions, excluded descriptor
operations, six-scenario managed-thick-file and Python 3.10 gaps remain. No
fixtures, native outputs, source hashes, gates or backend selectors changed.

Validation: 49 tests PASS normal and the same 49 PASS under `-O`, combining
`test_python_direct_forms`, `test_python_direct_form_invocation`,
`test_python_direct_form_database_admission`, `test_python_direct_bound_forms`,
`test_python_direct_form_callbacks` and `test_python_direct_form_rpc`.
Independent review: no blockers, 38 combined `-O` tests PASS. Regressions cover
read-only binding/deferred rejection, live writable properties, self-form writes,
foreign/private/missing members, retired controls/collections and inactive/closed
families. Original replay and source-level byref writes forbid legacy dispatch.

## Python 3.10: line-only direct diagnostics

CI on `944c6274`: Test/build run `44060348171`, Python 3.10 job
`133960636116` ran 32 regex tests with 9 errors, all initially blocked by
`error_boundaries requires Python code position metadata (3.11+)`. Performance
run `44060348045` succeeded; the browser job `133960729283` succeeded. Native
managed-form job `133960365934` in run `44060348318` succeeded and logged
`Managed form measurement accepted`. Linux light job `133960729266` failed;
its large log could not be retrieved through the connector (Transport closed),
so no new aggregate failure count is asserted here.

The chosen shared cause was the unconditional requirement for column metadata,
not the regex implementation. On real CPython 3.10.22, even the default Array
smoke failed before executing any BSL. SourceMap already rewrites generated AST
line numbers to the original BSL source. Python 3.10's line metadata is therefore
sufficient for execution and line-level diagnostics. Admission now requires
`co_lines` (3.10+); error conversion uses traceback line and column **1** when
`co_positions` is unavailable. Python 3.11+ keeps its existing exact-position
path. This is an explicit diagnostic precision difference, not VM fallback.
No execution wrapper, hot-loop check, exception-type widening, source/schema/
transaction change, CI allowance or backend selector was introduced.

Validation used actual CPython 3.10.22 and 3.12.14, not a mocked version:

* On **each** version, the same 84 focused tests passed normal and `-O`: mapping
  unit tests, portable diagnostics, permission-error control, direct default,
  prepared API, SQLite database and forms. Another 13 neighboring review tests
  passed normal and `-O` on each version. The missing-line-support test still
  rejects before execution; only its required-version diagnostic was updated.
* Independent review found that stale `3.11` assertion; it was fixed and the
  reviewer independently passed all 13 tests under `-O` on both versions.
  No remaining blockers. The older full error suite still has the previously
  confirmed Array wording mismatch (`list index out of range` versus the Russian
  checked-index message); it was reproduced on the unchanged 3.12 baseline.
* Exact isolated comparator children on 3.10 now complete CatalogObject
  (24 observations, 156 bytes) and managed form (40 records, 541 bytes). Their
  output hashes exactly match the 3.12 results above. This is host output
  equivalence, not a new native measurement on 3.10.
* The unchanged 32-test Python 3.10 regex CI command now has **7 errors**, down
  from 9. Remaining failures are real direct gaps: regex-result receivers,
  optional argument holes, unsupported constructors and Chars/other system
  names in routines. The native regex replay also fails on 3.12, independently
  of line metadata. Neither the regex suite nor full CI is claimed green.

The source-map precision tests retain exact columns on 3.11+ and assert the
explicit column-1 contract on 3.10. Nested prepared errors, host-call errors,
partial effects, catchable arithmetic errors and noncatchable authority failures
are covered. More precise 3.10 columns would require additional bookkeeping;
this change deliberately does not add it.


### Direct immutable system names follow-up (2026-11-17)

Baseline `cba04ee94f1eeb067b0533a274a00f01093cd625`: Test/build
`44062308838` has failed Linux light and Python 3.10 regex jobs, successful
browser job `133967476079`. Native run `44062308424` has successful managed-form
`133967091980` and CatalogObject `133967092258`, but fails its required verdict
(including regex, CatalogQuery and six scenarios). These are exact baseline CI
results, not claims about this follow-up or general native parity.

The unchanged regex source stopped at RF-05 because routine `Chars.LF` compiled
to an undefined Python local. The direct compiler now binds eight finite system
namespaces through the existing external-name seam: Chars, SearchDirection,
SortDirection, RoundMode, AllowedSign, AllowedLength, DateFractions and
ErrorCategory, including their Russian aliases. Public operations use the
existing value implementations. Only the canonical singleton identities are
admitted; only the three already implemented direction/rounding iterators are
connected. There is no legacy name resolver, arbitrary reflection, new cache,
VM fallback or relaxation of database owner/source/schema/transaction checks.

The exact unchanged regex replay now emits its two controls and RF-01 through
RF-06 successfully, then stops at RF-07 on the still unsupported regex-result
receiver. This is progression, not completion. On the same 73 existing tests
(`test_round_modes`, `test_round_mode_iteration`, `test_search_directions`,
`test_sort_directions`), failures/errors fell from **8/115 to 7/71**; these
include subtest errors. Old Array representation, host return values, cross-call
routines and other compatibility gaps remain, and no old fixtures were edited.

Validation: 97 focused tests passed normal and `-O` (new system names, direct
default/prepared/database/forms/external namespaces, three Chars public API
tests). The eight new tests also passed on real Python 3.10 under `-O`.
Independent review passed 40 combined `-O` tests and eight normal tests, without
code/security blockers. Exact isolated CatalogObject and managed-form children
still produce the same 156-byte and 541-byte outputs and hashes recorded above.

Known naming limitation: these registered names are read-only externals.
Module rebinding/declarations, implicit routine-local assignment to such names,
and same-name routine declarations reject. Parameters and explicit routine-local
`Var` declarations can shadow them. This deliberately retains the existing
external-name contract rather than adding a general dynamic name resolver.
Qualified byref namespace members and other system namespaces are outside this
slice. No performance improvement or full CI success is claimed.

### Transaction-local source read (audit8, 2026-11-17)

On baseline `8da65871`, format-16 `_begin` read and validated source twice inside
one SQLite transaction. The second admission now consumes the first local tuple;
public standalone admission still reads fresh source. All subsequent validation
and prepared-import publication remain. No long-lived admission cache or VM
change. Source SELECT count for read/write/read: 6 -> 3.

85 normal + 85 optimized targeted tests pass; independent review: 47 optimized
pass, no blockers. Seven alternating actual MainDemoHost pairs show Product Save
55.643 -> 43.161ms, with all pair medians improved. Other operations have small
or negative/noisy changes; no generic speedup claimed. Current-snapshot and
corruption cases pass. [Raw results, reproducer, limits and next-candidate profile](../experiments/transaction_source_read/README.md) accompany this slice.

### Current-layout validation without creation preflight (audit8, 2026-11-17)

Baseline `0cdb512c`: existing main-demo database validation constructed and
discarded a new layout/DDL before loading the actual persisted layout and
constructing DDL again. Shared fresh catalog validation is now separated from
creation-only construction. All current canonical/domain/codec/bounds/reference,
SQLite layout/DDL/index checks remain. Creation still preflights before allocation;
no cache or change to transaction/data-row validation.

98 normal + 98 optimized tests pass; independent review: 47 optimized, no blockers.
Seven alternating actual host pairs: Kind Save 31.255 -> 27.493ms, Product Save
42.692 -> 36.484ms. Six of seven pair medians improve; noise and all raw samples
are retained. [Reproducer, results and scope](../experiments/current_catalog_shape/README.md).
No general speedup/full CI/native parity claim.
