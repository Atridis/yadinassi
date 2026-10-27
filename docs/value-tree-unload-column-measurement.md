# ValueTree Rows.UnloadColumn: bounded measurement inputs

This is an observation-first input layer, **not an implementation or a native
expected-output fixture**. The receiver is `ValueTreeRowCollection`, through root
or child `Rows`. `ValueTable.UnloadColumn` is a separate API; its implementation
and column conversion rules are not evidence of native tree behavior.

The candidate starts at main `15fdcddaebb7e022aec08733a7eca4c6eea05238`.
Interpreter package source/data, workflows, old native literals and all existing
946 collection inputs remain unchanged. The current provenance inventory remains
66 files, but the pinned host/comparison adapters change its aggregate digest.
Staged inputs remain 24 and scenarios remain six. No serializer/report cap is
raised.

## Fixed matrix

There are exactly 27 new records, ordinals 947–973:

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

Current collections973 has 4501 lines and SHA256
`bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada`.
There are 130 declarations/endings and 16 message sites; the zero-based body line
is 3210. Helper/call hashes independently reject altered probes even if an outer
source hash is changed. The generated full-client module SHA256 is
`66b2e8263c9a1a68c21996e02dd153bb3390cb3fb2481456b54d0c5990e39188`.

A new isolated test-only harness inverse restores exact main15fd adapters before
existing cleanup, Find and older historical inverses. Old hashes/fixtures remain
unchanged and are not made live-admissible. All 27 new observations are strict
byte comparisons; the eight existing Map-order exceptions are unchanged.

## Required acceptance

Capture genuine native client/server outputs for this exact source and
independently authenticate run, head/tree, staged sources and complete outputs.
Inspect every new record. A comparison failure while host UnloadColumn is absent
is expected, but remains a failed workflow rather than feature acceptance.
Only a later bounded implementation with fresh native/full-host and four-platform
checks can establish supported behavior. No native measurement has yet been
performed for this source.
