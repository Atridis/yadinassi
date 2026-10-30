# Closed marker-one PARAMS admission

This is a narrow read-only candidate profile, not general free-list support.
The original `DBNamesProfile` defaults to `reserved_and_active_v1` and retains
its strict rejection of all nonzero later slots. Its positional constructor
arguments and profile identity are unchanged. The keyword-only alternative
`slot_policy='closed_marker1_chain_v1'` has the separate identity
`params_dbnames_closed_marker1_chain_8380_8192_v1`.

The public raw/typed Catalog coordinator selects the new profile internally,
independently of Description length or fixture case, within its existing single
CONFIG/PARAMS/record ownership graph. No public reader option, writes, BSL manager,
extra scan graph or retry is introduced. Description0 field/record layout stays
unchanged; the PARAMS admission policy is explicitly stronger than merely
ignoring the reserved header payload.

## Admission boundary

- Exact canonical profile fields and slot-policy primitive types are rechecked
  before source I/O, including forged frozen instances. The exact eight-key
  dictionary domain is validated before any lookup, so colliding custom keys,
  dictionary subclasses and comparison/string hooks cannot select a policy.
- Reserved marker must be one. Its four-byte offset-one u32LE head is validated
  even if no marker-one later slots exist; such an image requires head zero.
- Every later marker must be zero or one. All zero-marker filenames are decoded
  strictly and DBNames uniqueness established before selected transport reads.
- Marker-one rows expose only their four-byte candidate next link. Stale names,
  invalid UTF16, timestamps and old payload/pointers remain opaque.
- The reserved-rooted chain must terminate, stay in range, avoid cycles and zero
  markers, and contain every marker-one slot. Unlinked or other-marker layouts
  remain unsupported. No fixed number of removed slots is expected.
- Only after the complete scan and chain validation may the selected DBNames
  transport fields, BLOB chain and compressed body be read.

The existing slot ceiling and cumulative catalog budgets remain in force.
Before temporary arrays/set entries, reserve8192+512*slots representation bytes
and64*slots work bytes; each examined chain edge additionally charges8 work bytes,
including a failing edge. Scalar/UTF16/BLOB/inflate work retains its existing
charges. These are conservative representation weights, not exact Python heap
sizes. The slot bound independently limits allocations and traversal; exhausted
budgets and failed shared graph stages remain consumed/poisoned. No limits rise.

Finite new UnsupportedLayout labels are `dbnames_chain_reference`,
`dbnames_chain_cycle`, `dbnames_chain_zero_target`, `dbnames_chain_unlinked`.
No exception values, indices or chain data enter native reports.

## Evidence and bounded native acceptance

Authentic measurement run41038717311 on4078eb1de7bd7407a2781d2e0e1ae54d4c5ec693
(treeef9d8c0a8c786754a513fee9581b1b309e3ef323) observed, in both Description8/17
cases, an updated image with26 zero-marker rows and no later nonzero marker,
then an applied image with26 zero-marker rows and17 marker-one rows. All17 were
linked, with zero unlinked and a terminating offset-one u32LE hypothesis. Both
states had26 nonempty filename fields and one DBNames match. These are evidence
for this bounded profile, not an arbitrary database or platform specification.
The [measurement recipe and upstream caveats](params-slot-measurement.md) remain
separate, including inconsistent upstream deletion-writer code and conditional
little-endian interpretation. Original source/run receipts are not rebound to
this new implementation.

The reviewed workflow returns to the42-source public typed Description lane;
the44-source observational route remains explicitly selectable. The exact reviewed source
hashes and finite diagnostics were bound to fresh readiness and native validation.
The comparison-profile hash recipe explicitly binds
`params_slot_policy=closed_marker1_chain_v1`; the previous recipe hash is rejected.
Diagnostic exception dictionaries also require exact string keys before lookup;
foreign keys, subclasses or more than8 attributes produce fixed unknown results
without invoking hooks or exposing values.
Authenticated [run41045553007](https://github.com/Atridis/yadinassi/actions/runs/41045553007)
on commit `fb5c2e87e99b983cb65cc6f11fbb69ca8ecebbfa` (tree
`f4154045d578abac148fcbfb68cbb94d97b14c2e`) passed the strict42-source lane:
both Description8/17 cases matched actual Description, metadata and typed UUID
at created/updated/applied with Payload32/32/64. Baseline was absent; source,
postimage, handoff and all cleanup gates were verified. Recipe hash
`80718abb0df1a21de7dc00d43f57f2cefeaa0de80eb0a25a5bf7e7f7b016bbba` binds this policy.
The final Core/DB union preserves all42 input bytes exactly; this receipt remains
attributed to fb5c2e87, not a new execution on the union. Full current-head CI
and ordinary native gates remain required. Other Description lengths remain
a structural metadata-derived generalization, not additional native measurements.
Synthetic admission and the earlier44-source measurement are separate evidence;
earlier failed42 runs remain failures. This is not arbitrary removed-record,
write, multirow or platform-wide compatibility support.
