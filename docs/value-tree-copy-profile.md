# Isolated ValueTree.Copy measurement profile

This is a measurement-only follow-up to the existing `tree-v1` negative
FillValues API regression. It does **not** implement `ValueTree.Copy` or claim
native semantics from synthetic copies. The observer and decoder are described
in [the measurement plan](value-tree-copy-measurement-plan.md).

## Closed route and evidence

`python3 scripts/native_1c_tree_profile.py --execute-approved-image --export-native-outputs --profile tree-copy-v1`
selects a fixed, immutable registry entry, never a source path. The host invokes
`--tree-copy-suite --invocation-nonce …`; the shell and stage runner reject mixed
routes. The original default remains `tree-v1`. Both use the same hardened,
digest-pinned native image and unchanged isolation/cleanup rules.

The Copy shard has exactly one source, `integrational_tests/measurements/tree_copy.bsl`,
SHA256 `aadb8667848308bc4e14b82764dd693bc30fdd6a184598caf479e5a0cdc32572`.
It emits one separate access probe, calibration and nine cases (exactly 11 records).
The staged inventory has 24 fixed inputs,
including the registry, versioned nine-case Copy decoder, finite diagnostic helper
and strict access-probe capture/witness helper. The default
Fill shard has 22 inputs (its original 21 plus the registry). Every staged byte
is hashed before and after execution; source, generated server/client modules,
nonce, producer state, output identity and cleanup remain admission requirements.
The selected profile is passed explicitly, not installed by changing globals.

Validated observations and provenance are atomically exported under
`native-smoke/tree-copy-outputs/`; the finite host report is
`native-smoke/tree-copy-report.json`. Unvalidated observations are not exported.
`native_measurement_accepted` and `runtime_parity_accepted` are independent:
valid native data can be retained despite the expected interpreter mismatch.
The CLI, Copy workflow job and required verdict remain **parity-gated**. There
is no measurement-only success bypass, so this Draft can correctly remain red
until native evidence is reviewed and the runtime follow-up is implemented.
The parent can add those follow-up commits to the same Draft before merge.
In addition to raw equality, Copy acceptance requires successful zero-argument
English Copy on an empty tree (case1) and Russian Скопировать on the ordinary
valid hierarchy (case8). `comparison.native_copy_available` records this predicate.
All M/A/O records remain exportable authenticated observations; even raw matched
all-M output is rejected as Copy acceptance. No positive outcomes are imposed on
the other semantic cases or the extra-argument case9.

## Bounds and filesystem rules

The existing caps remain: observation 8192 bytes, client marker 16384, native
stage report 8192, host report 32768, transport 65536. Synthetic structural maxima
are not native results: the main Copy wire maximum is 6746 bytes; with the
separate access probe full capture is 6778 bytes and compact Python JSON marker
is 6918 bytes. Tests also charge optional JSON slash escaping. The actual
native serializer still must be exercised by the native job.

Public staged directories are explicitly 0755 and files 0644 even under umask077.
The container's source bind is read-only; copied launcher templates remain
owner-writable. Credentials and private work are 0700 and are never mounted.
Finite Copy diagnostics expose only site, ordinal, category and calibration
code; they never publish raw exception descriptions. The observer captures error
text in the original exception handler before nested catches/helpers.

The six ordinary sources and four ordinary client adapters remain unchanged.
The default Fill generated client module remains SHA256
`e43224c91c76a1c92dc6c2bf4e6c90a07fe23fbf4aa42d1c6a17630de70a937a`.
A new hash-bound, test-only inverse first removes the probe projection; the
unchanged historical inverse then removes the Copy selector before applying the
unchanged historical inverse chain; production source admission is not relaxed.


## First acquisition: observer failure, not Copy semantics

Native run40910090323 attempt1, Draft147 head
`a4e087e189be43785663c5afa19287e97ea62cd9`, did not yield accepted
Copy observations: native server case5 failed the observer during its mutation
phase (`observer_m`). No Copy output artifact was exported. This is not evidence
for a copying/aliasing policy and is not an interpreter mismatch. The original
source SHA was `c4ae4e0a725b6e807dc65b2e221cf65a555927b7c04adbed956dbb3cc9b45316`.
The failed run remains attributable to that source; a new source-bound native
run is required for this diagnostic revision.

The observer now distinguishes case5 steps M01–M18:

| Steps | Operation |
| --- | --- |
| 01 | Add a child to the copied first root row |
| 02–04 | Assign that child's Payload, N, Text |
| 05–06 | Snapshot source, then copy |
| 07 | Delete the copied second root row |
| 08–09 | Snapshot source, then copy |
| 10 | Add a source root row |
| 11–13 | Assign its Payload, N, Text |
| 14–15 | Snapshot source, then copy |
| 16 | Delete the source first child subtree |
| 17–18 | Snapshot source, then copy |

Both TCId comparisons (against Undefined and against a registry entry) capture
an exception description immediately in their original handler and rethrow a
fixed observer tag. Registry indexing remains outside that comparison handler.
The outer observer also captures immediately and emits only the fixed stage plus
an optional identity suffix I. It does not turn invalid-handle comparisons into
false, skip identities, or change successful IDs. Whether deleted handles cause
the actual failure is still a hypothesis until the next native run.

`XM01`–`XM18` map only for case5 to `case5_step01`–`case5_step18`;
`XM01I`–`XM18I` map to the corresponding `_identity` categories. `XBI`, `XII`,
`XOI`, `XMI` map to generic `identity_b/i/o/m` for cases1–9. All remain rejected
observer outcomes, never accepted observations or raw error text. The four-field
diagnostic schema, successful Copy grammar, positive controls and parity gate
are unchanged. The initial substep revision used categories of at most21 characters; the
next sentinel revision below expands the closed vocabulary without changing caps.


## Second acquisition and fixed sentinels

The diagnostic head `76dc081aa12bedc29c6a815a65f41817cf78f81b` localized failure
to server `case5_step15`: the copy snapshot after adding/assigning a source row,
after the source snapshot14 succeeded. There was no identity-comparison suffix.
Thus the deleted-handle-comparison hypothesis is **not supported by this run**.
No valid Copy output was exported; no runtime semantics are established.

The next revision preserves all calls/accessor frequencies, source/result snapshot
order, nine cases, success grammar, registry cap62, and acceptance predicates.
Known fixed guard exceptions are classified separately from unknown accessor
faults. Snapshot/flatten handlers capture their original exception description
immediately and propagate only a closed fixed code. The classifier never exports
private descriptions. Registry G01 is emitted only after the observed Count equals
62; G02 means Count greater than62. Existing identity lookup still precedes the cap.

Guard codes:

| Code | Meaning |
| --- | --- |
| G01 | `registry_62` (`copy-identities-count62`) |
| G02 | `registry_over62` (`copy-identities-over62`) |
| G03 | `number_bound` (`copy-number`) |
| G04 | `word_vocabulary` (`copy-word`) |
| G05 | `cell_shape` (`copy-cell`) |
| G06 | `inner_array_shape` (`copy-inner`) |
| G07 | `flatten_row_limit` (`copy-rows`) |
| G08 | `result_type` (`copy-result-type`) |
| G09 | `column_limit` (`copy-columns`) |
| G10 | `column_type` (`copy-column-type`) |
| G11 | `types_count` (`copy-types`) |
| G12 | `date_qualifier` (`copy-date`) |
| G13 | `collection_parent` (`copy-collection-parent`) |
| G14 | `root_parent` (`copy-root-parent`) |
| G15 | `exception_result` (`copy-exception-result`) |

Unknown non-guard snapshot faults use these exact operation points:

| Code | Operation |
| --- | --- |
| S01 | `result_type_read` |
| S02 | `columns_count_guard` |
| S03 | `tree_identity` |
| S04 | `root_rows_owner_label` |
| S05 | `columns_identity` |
| S06 | `columns_count_encode` |
| S07 | `columns_iteration` |
| S08 | `column_value_type` |
| S09 | `description_types` |
| S10 | `type_count_and_items` |
| S11 | `date_qualifiers` |
| S12 | `column_identity` |
| S13 | `column_name` |
| S14 | `column_title` |
| S15 | `column_width` |
| S16 | `number_digits` |
| S17 | `number_fraction` |
| S18 | `number_allowed_sign` |
| S19 | `string_length` |
| S20 | `string_allowed_length` |
| S21 | `binary_length` |
| S22 | `binary_allowed_length` |
| S23 | `flatten_rows` |
| S24 | `flatten_count_encode` |
| S25 | `nodes_iteration` |
| S26 | `row_identity` |
| S27 | `row_parent` |
| S28 | `row_owner` |
| S29 | `row_level` |
| S30 | `row_children_owner_label` |
| S31 | `row_children_count` |
| S32 | `row_collection_parent` |
| S33 | `cell_loop_column_count` |
| S34 | `cell_read_and_encode` |
| S35 | `root_rows_parent` |

Flatten F01 covers iteration/count, F02 appending the node, and F03 child access/
recursive traversal. A deeper known code is propagated rather than overwritten.
`I` remains the specific identity-comparison code. Public categories preserve
case5 step and reason (`case5_step15_registry_62`, for example); other cases retain
B/I/O/M phase via `detail_b/i/o/m_<reason>`. The resulting closed set has1218
categories, maximum30characters, with the same four diagnostic fields. All X
records still fail observation admission; no partial or fabricated semantic output
is accepted. Explicit byte-majorants remain below the unchanged caps.

The initial registry-growth hypothesis was subsequently tested by the separate
source-bound probe below. That historical sentinel revision established the exact
62-entry guard; it did not itself establish accessor or Copy semantics.


## Separate repeated-access diagnosis

Native run 40918709582 (head `a043638db653982d4008361551a4cd799fe3a19b`)
confirmed `case5_step15_registry_62`: the observer exhausted its existing identity
registry. This does not establish which accessor caused growth or any Copy
semantics. The registry cap remains 62; no wrapper identity is normalized away.

A fixed first record `TC-P` now runs on a separate fresh fixture, before the
unchanged nine Copy cases. Its 23 positions are number equal/unequal, string
equal/unequal, tree alias/distinct, Array alias/distinct, and alias/repeated
retrieval/distinct for row, root Rows, child Rows, Columns and column. `T`/`F`
are actual equality outcomes; `E` is a comparison exception; `A` is an accessor
exception. `B` alone reports setup failure. Original error descriptions are
captured privately and never exported. Only truthful `TFTF` scalar controls
allow probe acceptance; no wrapper outcome is prescribed.

The strict full capture has exactly `TC-P`, `TC-C2`, then `TC-1` through `TC-9`.
There is no old ten-record fallback, reordering, duplicate or extra-record
admission. The versioned Copy decoder receives only `TC-C2` plus nine cases.
The full synthetic bound is 6778 bytes (main capture 6746 plus probe 32); compact
marker 6918, or 7010 including slash escaping, optional delimiter spaces and BOM.
With both probe witnesses and failure metadata, conservative report bounds are
stage 5522, native 10648, host 16466, provenance 16271 and transport 21825 bytes.
No caps have increased. These are synthetic bounds, not native serializer results.

`copy_access_probes.server/client` are separate nullable witnesses, bound to
nonce, exact source/generated module, full-capture hash/size/count and the
main-capture hash/size. `record` contains only the fixed probe record. The
comparison's existing `native_sha256`/`interpreter_sha256` and sizes continue to
identify full captures; explicitly named `native_main_sha256` and
`interpreter_main_sha256` identify the `TC-C2-and-nine-cases` parity projection.
Server/client Copy parity likewise compares only the main projection, not probe
wrapper equality. Scalar control failure is never accepted as valid measurement.

An authenticated expected observer failure may retain its bounded native report
and valid probe in the summary only after container removal, final input/source,
repository/interpreter provenance and private-directory cleanup checks all pass.
`probe_measurement_accepted` reports server and client separately; a missing
client witness is false, never implied success. Such a summary still has
`native_measurement_accepted=false`, `runtime_parity_accepted=false`, no raw failed
nine-case output, no output artifact and no `tree_outputs_ready` signal. Every
transport, source or cleanup failure still rejects evidence. Copy remains a red
Draft until its own validated native semantics and runtime parity are complete.


## Version 2: structural Rows-owner labels

Native run 40923398103, head `4703abea64eaf90070262823859e7f0e93a3cc05`,
authenticated server record `TC-P: [TFTFTFTFTTFTFFTFFTTFTTF]`. Scalar controls
were `TFTF`; saved aliases compared equal, but repeated root Rows and child Rows
access compared unequal. Repeated row, Columns and column access compared equal.
This disproves the old observer's stable Rows-access equality assumption. It does
not prove allocation behavior, deep/shallow Copy, or native identity semantics
outside this bounded probe. The client probe was absent; main Copy observation
still failed at `case5_step15_registry_62`.

The corrected main grammar requires exactly `TC-C2: [-]` as its successful
calibration header, followed by the existing nine `TC-N` records. `TC-C` is
rejected, not normalized. The positive calibration operations and failure codes
are unchanged; only the versioned header identifies the changed label meaning.

Snapshot header fields are `tree identity`, `rows_owner`, `Columns identity`,
column count, schema and row count. `rows_owner` repeats the already measured
tree ID as a structural label. Each row's `children_owner` similarly repeats its
already measured row ID. These labels allocate no registry entries and never
claim equality/inequality of native Rows wrapper objects. The strict decoder
requires the exact existing owner ID, rejecting forward, cross-kind and mismatched
labels. Row records expose `RowObservation.children_owner`; snapshot dictionaries
use `rows_owner`, not the former `rows` identity field. Labels follow owner identity,
not sibling positions, so insertion/deletion does not relabel surviving containers.

True tree, row, column, Columns collection and outer/nested Array identities remain
observed. Actual row Owner, Parent, Level, collection Parent checks, child counts,
column metadata, cells and every mutation snapshot remain unchanged. Structural
root labels from two trees **must not** be read as evidence that their native
collections are independent: shared-collection behavior is still observed through
add/delete/scalar/column/Array mutations. Actual row Owner is not forced to equal
the snapshot's tree, preserving possible sharing observations. S04/S30 now label
structural owners; all other finite sentinel meanings remain unchanged.

The registry cap remains 62. A synthetic fresh-access wrapper model reproduces
the old case5-step15 overflow; the revised observer completes all nine synthetic
Copy cases without growing the registry with wrappers. That regression validates
the measuring instrument, not native Copy semantics. A new exact-source native
run is mandatory before runtime Copy implementation or merge.
