# Batched catalog-read evidence lane

Status: locally integrated and synthetically tested; **no target native result**.
This is the evidence/acquisition portion of the larger BSL catalog-reading block,
not a declaration that multi-row storage admission or cursor parity is complete.
Existing production max-one-active-record and nonreserved-free-slot refusals remain.

## Closed execution

`python3 scripts/native_1c_catalog_read_oracle.py --run --ci-report` uses the
existing approved immutable training image, existing registry credentials, and
existing networkless/read-only/unprivileged Docker confinement. It accepts no
caller database, source, image, catalog name, path, or arbitrary BSL.

The existing owner-reviewed file-DB workflow has one new selected-only route,
`catalog-read-batch-v1`, on the **same** reviewed branch and owner/exact-SHA checks.
No new trigger, credential-bearing branch, token scope, or permission is added.
The existing metadata jobs and old routes remain intact. Root review of the final
source/readiness precedes publication or any advancement of the reviewed ref.

Source staging reuses the isolated runtime/dependency bundle and binds every
fixture, generated identity, module, host/controller and runtime source through
an exact manifest. The target runs `python3 -I -S -B`, activating only that bundle.
Only `native-catalog-read/catalog-read.json` is exported after validation; raw
DB/config/log files remain private and are deleted. Raw **bounded scalar wires**,
including newly generated UUID values, intentionally remain in the finite report.

## Matrix and acquisition

Two saved independent identity sets each add two generated catalogs to the
original owned `NativeOracleItems` configuration. Existing users/roles are kept;
CRUD rights are extended only to the two exact generated catalogs. Each installed
configuration is loaded, applied, dumped again, and checked against the complete
expected file/XML/module inventory and saved UUIDs. No IDs are regenerated during
replay or redump verification.

Each of the five states starts from its own empty applied clone:

* `empty`: no records;
* `one`: U, code 30;
* `several`: three records with insertion/code/UUID ordering deliberately unlike
  each other, one logically marked for deletion;
* `deleted`: an intermediate ghost V is physically deleted after insertion;
* `reused`: delete then insert V again, **an experiment**, not a promised slot reuse.

Setup performs writes and independently queries total/U/V counts (12 scalar
witnesses across two catalogs). Frozen setup images seed independent client and
server clones. Eight bounded blocks run in **one session per context/state**:
identity, types, errors, fresh, cursor, fields, lookup, fourth row/reference fields.
This is 30 measurement sessions (10 setup + 20 context), plus two installation
admin audits and existing bootstrap
and Designer lifecycle commands—not 160 separate observation launches.

There are 180 observation rows per context/state, 3,600 across the complete matrix.
After each context run, a quiescent postimage is frozen. The physical observer and
public interpreter readback run inside the same descriptor's before/after full
hash and process-census envelope. Setup/origin/postimage digests and tokens bind
these captures; cleanup failure discards them. Independent physical graphs for
the two catalogs share source-read caps and reject duplicate data header pages.
They do not claim a full global allocation proof across both graphs.

## Availability, fresh values, and comparison

Scalar observer calibration is required before interpreting any action results.
Manager/name/UUID controls give an explicit available/unavailable outcome for each
block. In the managed client, Catalogs action expressions resolve through trusted
same-function `Eval` (and readonly action statements through `Execute`), so absent
global availability does not prevent calibration by failing module compilation.
No external expression is evaluated. Cursor variables remain local; source vs
wrapped probes are compared on the synthetic public runtime.

The native server authorizes the exact nonce/token/closed operation and verifies
the existing CRUD user/role/nonprivileged invariants before client-local execution.
All setup Query/writes and observations use the existing CRUD identity, which
already holds the closed object grants; the administrative identity does not.
A separate existing admin audit after each installation verifies both users and
roles. No rights are added, and CRUD sessions do not enumerate the user list.
Fixed completion/server phases diagnose failed sessions without native error text.
Native setup Query/writes remain server-only and are not runtime features.

Fresh GetRef uses exactly two calls per capture. Original UUID strings and wire
hashes are retained; independent executions compare nonempty/distinct/not-known-
identity relations, never equality of random bytes. Logical `DeletionMark` is
reported separately from physical slot markers. No native order or free-list
interpretation is predeclared.

A green lane means a complete, validated **measurement** with cleanup, not that
all runtime comparisons match. Explicit mismatch facts and unavailable controls
remain visible. Its verdict is `measurement_only_not_production_admission`.
Only reviewed authentic native results can authorize lifting production guards.

## Primary documentation consulted

The official EDT syntax documentation archive was inspected as ZIP/text only:

* `https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`
* SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`
* `nl/en/html/SyntaxHelperContext/objects/catalog125/catalog126/CatalogsManager.html`
* `.../object128/methods/GetRef1611.html`, `Select254.html`, `FindByCode250.html`,
  `FindByDescription251.html`.

These identify server/thick-client availability, not thin/web availability, and
specify generation of a new reference for no-argument GetRef. The exact managed
client behavior is still measured; documentation is not substituted for native
cursor/default-order/reset/exhaustion observations.

## Deferred corners

`!todo`: after native evidence, finish multi-row/free-slot production admission,
then resolve measured cursor ordering/reset/end-field differences as one coherent
runtime update. These guards are intentionally not relaxed in this measurement
commit. Broader catalog schemas, hierarchy, runtime writes/transactions/Query and
cross-catalog full allocation analysis are not claimed by this finite fixture.
