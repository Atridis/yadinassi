# PARAMS slot/link hypothesis measurement

This separate lane investigates the genuine applied-state rejection
`dbnames_nonreserved_slot` in run41032055755 (reviewed source29ba0198459a7f5fbd52d506c2c475eb9d5c502a).
The public typed reader remains unchanged and its Description/Payload64 acceptance
is still failed. A successful observation does not turn that failure into support.

The fixed profile checks the exact PARAMS seven-field DBNames descriptor, then
uses its301-byte candidate stride. One catalog graph owns the selected data and
BLOB mappings and all cumulative budgets. BLOB bodies and index contents are not
read. No retry of a failed public-reader graph occurs.

Every candidate marker is scanned (maximum4096); only aggregate zero/one/other
classes are public. For slot0 and nonzero later markers, four bytes at offset1
are privately interpreted as a u32LE candidate link. Only this predeclared
hypothesis is tested; no offset/endian alternative or matching-model selection
exists. Traversal uses cached links, at most4095 distinct candidates, and returns
`terminated`, `out_of_range`, `cycle` or `zero_marker_target`. Linked and unlinked
nonzero counts are observations, not claims of free-list validity. Even marker
one without a link is not automatically malformed.

For later zero markers only, the filename field undergoes bounded strict UTF16LE
validation. Empty/nonempty fields and fixed ASCII-case DBNAMES matches are
counted; names, hashes of names, indices, link values and ordinary payload fields
never leave the private graph. A zero marker or filename match is not proof of
active-file eligibility. Duplicates remain measured counts, not target selection.

## Source basis and limits

Pinned Tool1CD commit `d5e31816f4c9b11a445f73fc92d08803840ce599` provides a
source-motivated, not official, hypothesis:
[Table.cpp2031–2032 and2085–2102](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L2085-L2102)
uses raw four-byte uint32 reads at offset1 and zero as append sentinel.
[Class_1CD.cpp379–400](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Class_1CD.cpp#L379-L400)
constructs PARAMS as a generic table. Explicit LE is our conditional wire
hypothesis, not a portable-endian statement from upstream. Its deletion writer
at Table.cpp1698–1706 is inconsistent with the insertion offsets and is not
corroborating evidence. Its marker-only removal operation2007–2022 does not link
slots. No upstream implementation is copied or executed here.

## Closed acquisition

Lane `catalog-params-slot-measurement-v1` uses invocation29, report56, capture57
and aggregate58. Existing Description8/17 fixtures run separately, each capturing
only the existing updated and applied post-observer frozen images. Existing
native sessions, Payload32-to64 migration, all13 lifecycle stages,11 snapshots,
cleanup and provenance gates remain required. No additional BSL commands, users,
permissions, credential jobs or database writes are introduced.

The unchanged schema3 observer sidecar is still authenticated privately in its
session; its Description and UUID values do not select fields or determine this
observation. Each state has its own token, source origin and exact frozen
postimage. Source staging contains44 explicit files; final validation runs cold
before imports can initialize a reader. The two case files are hash-bound to the
same run/attempt before the compact aggregate is emitted.

All four link outcomes can be successful *measurements*. Every capture and
projection says `runtime_support=not_claimed`. Failure or unsafe cleanup discards
the entire capture. Reports retain no private source strings or arbitrary errors.
The unchanged caps are8192 capture and32768 report bytes; independent rectangular
constructors reserve the full capture cap within the whole lifecycle report:
1945 bytes capture including newline,28655 bytes complete report including the
full8192 capture reservation and newline,612 bytes aggregate including newline.
Native evidence for this new lane is pending; synthetic tests are not format or
migration acceptance. A later runtime change requires a separate reviewed model
and fresh exact-source public-reader Description/UUID parity after migration.
