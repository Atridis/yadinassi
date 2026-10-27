# ValueTree Rows.UnloadColumn: bounded measurement inputs

This is an observation-first input layer, **not an implementation or a native
expected-output fixture**. The receiver is `ValueTreeRowCollection`, through root
or child `Rows`. `ValueTable.UnloadColumn` is a separate API; its implementation
and column conversion rules are not evidence of native tree behavior.

The initial candidate starts at main `15fdcddaebb7e022aec08733a7eca4c6eea05238`.
This three-input supplement follows measurement head
`04d67b04f03b7d4f4a397d2753a86ca8eeba2c84`.
Interpreter package source/data, workflows, old native literals and all existing
946 collection inputs remain unchanged. The current provenance inventory remains
66 files, but the pinned host/comparison adapters change its aggregate digest.
Staged inputs remain 24 and scenarios remain six. No serializer/report cap is
raised.

## Fixed matrix

There are exactly 30 new records, ordinals 947–976. The first 27 inputs
remain byte-for-byte unchanged; their fixed matrix is:

- Russian and English root calls on Id; child, empty leaf, genuinely empty tree
  and empty-schema receivers. The unchanged six-node `TreeSearchFresh` helper
  distinguishes root order, child order and any descendant inclusion.
- Case-varied name, indices 0 and 1, fractional/negative/out-of-range indices,
  own column object and same-named foreign-tree column object.
- Unknown column on nonempty and empty receivers; Undefined, Boolean, missing
  and extra arguments; wrong tree receiver.
- Number/Boolean and Undefined/Null cells, observed as distinct bounded tags.
- Deletion from the returned array versus addition to the source collection.
  These inspect independent membership, not whether cell values are copied.
- Both directions of mutation through a one-field Structure cell. Only the known
  `Mark` field is observed, and only `base`, `from-result`, `from-source` values
  are admitted. This distinguishes shared cell identity from equal presentation.

Three supplemental selectors (`1.5`, `1.9`, `-0.5`) use the existing fresh
tree whose Id, Key and Group columns have distinct values. Together with the
original 0, 1 and 0.5 selectors, these distinguish truncation, rounding and
negative-fraction handling without adding another coercion domain.

No predicted success/error, selected values, recursion or coercion outcome is
encoded in the inputs. No additional LoadColumn, Copy, Sort, codecs, detached
lifetimes or transport semantics are opened by this measurement.

## Bounded instrumentation

Four small helpers observe values, results, known source state and phase status.
Every call constructs a fresh tree. Setup, action, subsequent mutation and
observation errors remain distinguishable; exception text never escapes.
An action error still records the source state, so partial mutation is visible.

The only observed values are the previously bounded scalar cells or an exact
one-field Structure marker. Arrays/fixed arrays returned by the action have at
most seven observed elements. Nested collections and unexpected Structure shapes
fail closed. Source state records all six known nodes and seven collection counts;
empty-tree cases record rows/columns counts without dereferencing detached rows.
The source-add witness records changed collection cardinality without inventing
values for a seventh unknown node.

Each complete ASCII record is bounded by 2048 bytes, including the longest label,
full seven-element result and worst-case six-node source state. Independent local
tests inject fixed result arrays/known cell references, not an UnloadColumn
algorithm. They verify argument routing, all error phases, array independence,
identity witnesses and rejection of unexpected observer inputs. Unimplemented
host action errors are not native answers.

## Exact source and history

The untouched collections946 source has 4360 lines and SHA256
`9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3`.
New helpers precede the executable body and new calls are appended. The exact
source inverse removes only the four-helper block and the appended newline/call
block, restoring every old source byte; a plain prefix-preservation claim would
be incorrect.

The original collections973 had 4501 lines and SHA256
`bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada`.
The supplement contains 4504 lines and SHA256
`5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4`.
Removing only the three supplemental call lines restores exact collections973.
There are 130 declarations/endings and 16 message sites; the zero-based body line
is 3210. Helper/call hashes independently reject altered probes even if an outer
source hash is changed. The original 27-case generated full-client module SHA256 was
`66b2e8263c9a1a68c21996e02dd153bb3390cb3fb2481456b54d0c5990e39188`;
the supplement generated-module SHA256 is
`a7bfc4e3361bdb1bfde5794b211f3fd1c0594f5c81b4f5e3dafecac4c3049786`.

A new isolated test-only harness inverse restores exact main15fd adapters before
existing cleanup, Find and older historical inverses. Old hashes/fixtures remain
unchanged and are not made live-admissible. All 30 new observations are strict
byte comparisons; the eight existing Map-order exceptions are unchanged.

## Required acceptance

Capture genuine native client/server outputs for this exact source and
independently authenticate run, head/tree, staged sources and complete outputs.
Inspect every new record. A comparison failure while host UnloadColumn is absent
is expected, but remains a failed workflow rather than feature acceptance.
Only a later bounded implementation with fresh native/full-host and four-platform
checks can establish supported behavior. The original 27 were authenticated from failed measurement run
[40496124727](https://github.com/Atridis/yadinassi/actions/runs/40496124727):
16 succeeded, 11 reported action errors, no setup/change/observer failures.
Root/child calls return only local rows; arrays have independent membership and
the one-field Structure cell is shared in both mutation directions. The exact
0.5 selector chose column zero, but this alone does not establish a general
numeric conversion rule. The three supplemental cases were subsequently authenticated in
[run40525937279](https://github.com/Atridis/yadinassi/actions/runs/40525937279):
1.5 and 1.9 select Key (index1), -0.5 selects Id (index0), with unchanged state.
All prior973 native records remain byte-identical. Both measurement runs failed
host comparison before implementation; neither is feature acceptance. See the
[bounded runtime contract and pending gates](value-tree-unload-column-runtime.md).
