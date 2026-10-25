# Combined UUID runtime and observation candidate — local only

This combines the scalar runtime prototype with the independently authored v3
native-observation source. Native behavior is **unmeasured**. Passing host tests,
a host ledger, and historical native replay are not native UUID agreement.

The anticipated baseline is the `ci-build-dedup-main-v1` snapshot, tree
`2c9ad87ddc1b5cd00b526f370fd906f7f0777213`. Its future main commit is unknown;
this local candidate is not bound to a published commit. The candidate is not an amendment to
PR110. The runtime inventory is derived through `interpreter_provenance`: 62
files (61 base plus `unique_identifiers.py`). Only exact inventory assertions
in the two synthetic preprocessor-budget modules change; caps do not increase.

The independent values source has SHA-256
`0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c` and emits 441
records. The exact guarded historical inverse returns values402 source SHA-256
`dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12`.
The current adapter still refuses old/tampered source. Historical tests and smoke
routes explicitly use the inverse; no native fixture bytes are rewritten.
The collections866 contract, eight finite Map exceptions, security admission,
workflow, native package, transport caps and fixed-path ownership are unchanged.

The independent 30 probes include UUID/Russian/UniqueIdentifier aliases, fixed
canonical strings, equality, scalar Map/FixedMap projections, zero-filled,
descriptor queries, malformed input and generated-value projections. No raw
random value is printed. Runtime default v4 generation remains a provisional
local choice; the probe observes the version nibble without assuming its value.

`uuid-ci-dedup-preview-v2-host-ledger.json` is an external local work artifact,
not a committed native golden fixture. Every native observation and agreement
field is null. Host descriptor probes intentionally error because descriptors
are deferred. Separate local ledger checks record expected refusal for internal
codec values/type records, XML and context transport. These refusals do not
predict the native platform's results. Type-display formatting and accepted
input forms also remain open native questions.

See [runtime bounds](uuid-scalar-provisional.md) and
[independent probes](uuid-native-observations.md). Before publication or native
acceptance, review the exact combined source, finish the active core PR, obtain
the coordinated native run, and compare exact fresh output. Any mismatch remains
a failure requiring diagnosis, not a waiver or new tolerated record.

## Codec observation supplement

Nine independent fixed/nil codec probes bring the current source to 441 records:
internal fixed/nil/type encoding, two internal round-trips, XML fixed/nil encoding
and two XML round-trips. In this provisional host runtime all nine report
`encode-error`: fixed-value setup succeeded, encoding is deliberately refused,
and decode was not reached. This is not native codec behavior or support.
Native/agreement fields remain null; no codec identifiers or tags are invented.
The helper separately labels setup, encode and decode errors and enforces its
existing 256-character probe-output bound without changing transport caps.
