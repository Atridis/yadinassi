# Columns.Clear retained-collection lifetime probe (CL6)

Measurement only; no runtime forwarding implementation. The authenticated CC12
acquisition (run 41066943188, 2252 bytes, SHA-256
`4db4c7b231ca12b087ba6ff7e3a16069b0dffc27b5c35c12db7dc061d082460c`)
observed invalid old rows, reset retained column metadata, and successful Add
through a held child collection producing an active root row while the held
collection's Parent remained the old child. It does not establish generic
forwarding or retained-wrapper equality. Original CC12 source and decoder remain
unchanged; its runtime parity rejection is not converted into acceptance.

The separate immutable `tree-columns-clear-lifetime-v1` profile uses the original
CC strict snapshot decoder as a fixed staged dependency. Four saved handles are
labelled by their original root-child, child, grandchild and sibling positions;
wrappers are never compared for identity. Each checkpoint independently records
active schema/topology, the original 24 retained queries, each handle's Count,
Parent and Get(0), and the returned row's identity, Owner, Parent and Level.
Returned-row structure is never inferred from a saved collection's Parent.

## Six fixed cases

1. Nonempty English Clear positive control.
2. Nonempty Russian Очистить positive control.
3. Clear, then separate Adds through saved root-child, grandchild and sibling
   collections, observing after each action.
4. Clear, phased root rebuild (add Key column, add root row, write 5), saved
   grandchild Insert(0), saved sibling Get(0).
5. Clear, the same root rebuild, saved child collection Clear.
6. Clear, root rebuild, repeated Columns.Clear, saved grandchild Add, saved sibling
   Get(0).

All cases start with two columns and four rows including depth two. The 24 total
checkpoints retain partial states and original action-error classifications.
Failure of the first Clear prevents subsequent actions; subsequent failures do
not suppress later independent actions. Each original exception description is
captured before helper calls. Diagnostics are finite codes, never raw messages.
Only EN/RU nonempty-before, successful-Clear, empty-after effects gate availability;
no forwarding behavior or agreement among queries gates decoding or availability.

## Bounds and limitations

The unchanged core domain is at most three columns, five reachable rows and 62
shared typed identities. Core snapshots are at most 175 bytes; 16 independent
extra tokens add 32 bytes. Checkpoint framing is fixed by case. The complete
constructive maximum is **5147 bytes**, below the unchanged 8192 capture cap.
Unsupported scalar/type/identity domains produce finite observer failure. An
unexpected no-op followed by Add can exceed five reachable rows and be rejected;
that is an observation-domain limitation, not evidence that no-op is impossible.

The client alphabet admits `~` only for this fixed new profile; all seven earlier
generated modules and their accepted grammars remain byte-identical. There are
23 staged sources including both immutable decoders; missing or modified basis
files must fail cold staging/provenance checks. Windows fixtures use explicit
UTF-8 and canonical LF only at synthetic boundaries, never relax production
source hashes or filesystem checks. Real shell-fragment tests use reviewed Git
Bash selection and quoted profile arguments, not WSL or shared native fixtures.

## Temporary native execution

For this measurement head, CL6 replaces the CC12 row in the fixed existing matrix;
it does not add a job or container. The original CC12 registry remains manually
reproducible. Before runtime acceptance/merge, restore CC12 as the required native
lane and retain all CL6 observations as exact offline regression fixtures with
original run attribution. No final merge may treat this exploratory substitution
as passing the still-unimplemented core runtime. No credentials, permissions,
full-suite source, resource caps, or Clear/last-column runtime guards change.
