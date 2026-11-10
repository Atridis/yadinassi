# Ordinary property-transfer measurement

`property-transfer-v1` is an independent, fixed 48-case measurement for
`FillPropertyValues` / `ЗаполнитьЗначенияСвойств`. The source and its archived
copy are byte-bound by the profile registry and `original48-mapping.json`.
No native run or runtime parity is claimed by these input files. The mapping's
`not_acquired` state describes the original input checkpoint, not future runs.

## Coverage

- 01–04: ordinary table/tree setter and bilingual structure procedure controls.
- 05–14: Structure and FixedStructure sources, ordinary ValueTableRow and
  ValueTreeRow receivers/sources, both cross-row directions, and row-to-Structure.
- 15–34: explicit Undefined/default, INCLUDE order/case/duplicate, missing source
  or target properties, empty INCLUDE, valid/missing EXCLUDE, INCLUDE/EXCLUDE
  conflict, and a non-string excluded-properties argument when INCLUDE is set.
- 35–40: typed numeric/string columns, qualifier adjustment, Undefined defaults,
  invalid numeric input, and an independently observed ordinary setter.
- 41–46: TreeRow Parent/Rows in default, explicit INCLUDE and EXCLUDE, and as
  source values copied into ordinary structure properties.
- 47–48: a shared Array in an unindexed column, observed before and after a
  controlled mutation of that original array.

Each fixture is fresh. Source and receiver snapshots expose First/Last/Keep,
Parent/Rows presence or values, collection shape, tree parent/child relationships,
and indexed table FindRows counts and first/last identity flags. The source-only
Extra property discriminates missing-target selection from missing-source Keep.
Only First is indexed. This keeps the shallow-reference cases independent of
unsupported array index keys.

Table mutations must use the existing row setter, preserving index maintenance
and type adjustment. The observer measures those consequences; it does not
prescribe FillPropertyValues traversal order or read-only behavior. Historical
Structure INCLUDE/EXCLUDE evidence does not establish the behavior of rows.
The separate ordinary setter result is a comparison observation, not a native
expected-value oracle.

## Finite wire and trust boundary

The fixed calibration is followed by 48 ordered `PV-01` through `PV-48` records.
Successful actions (`S`) and action exceptions (`E`) retain three 43-byte ASCII
snapshots: before, after, and after shared-array mutation. `X0` through `X3`
identify observer/setup failure independently; no exception text is exported.
Snapshot cells use a closed typed vocabulary. Unexpected values fail the
observer instead of being truncated, stringified, or silently accepted.

The complete rectangular output bound is 39 + 48 × 143 = **6903 bytes**, below
unchanged 8192-byte output and stage-report caps. Transport and host/provenance
caps remain 65536 and 32768 bytes. The existing source-bound client adapter,
server/client equality, approved image, credentials, isolation, lifecycle and
cleanup checks are unchanged. Four positive controls must succeed and every
observer must complete before native measurement is accepted.

The ordinary host distinction remains `native_measurement_accepted` versus
`runtime_parity_accepted`. Valid native outputs are retained on runtime mismatch;
the job still requires exact runtime parity for success. There is no
acquisition-only bypass or new host-report field.

## First Linux acquisition

[Run 42814632887](https://github.com/Atridis/yadinassi/actions/runs/42814632887)
on PR #261 measured this unchanged source on Linux 1C 8.3.27.1508, configured
UTC. Its merge checkout was `a10240123e1c65284ffd4c0b0b9b64e63ac0a7d6`, tree
`0439b7d8de7d55b4d8acef44706b7ef5efaff3ce`. The client and server emitted
identical 6903-byte captures: 36 successful operations, 12 operation errors,
and no observer errors. Native measurement and cleanup were accepted;
**initial runtime parity was false**.

`tests/fixtures/property_transfer/original48-linux.out` and
`original48-linux-provenance.json` preserve the exact native artifact bytes.
The separate `original48-linux-receipt.json` binds their hashes, the verified
artifact archive digests, source, merge parents, and initial runtime identity
(165 source files). The input source, mapping, contract and profile are unchanged.
The mapping's original `not_acquired` attribution remains an input checkpoint,
not the status of this later run.

One replay of the acquisition tree reproduced the CI interpreter digest and
14 differing records. The native observations show:

- 17/18/27/28/42/43: `Last` is copied before an INCLUDE missing-property or
  read-only-property error; `First` remains unchanged. These forms are consistent
  with right-to-left Linux traversal, not atomic preflight validation.
- 19/29: empty INCLUDE succeeds without assignment.
- 21/31: excluding source-only `Extra` fails after copying `First` and `Last`.
  In contrast, 22/32 exclude source-missing `Keep` without changing the receiver.
- 24/34: a non-string EXCLUDE raises before writes even with INCLUDE present.
  Valid INCLUDE/EXCLUDE overlap in 23/33 still copies the included `First`.
- 45/46: a tree row's `Parent` and `Rows` can both be copied by reference into
  existing Structure properties, with default or explicit selection.

The other 34 records already matched, including cross-row transfers, typed
setter adjustments/defaults, index maintenance and shared-array mutation.
The dedicated capture tests pin these observations and require a complete,
explicit-Linux replay with no projection or replacement of native records.
Later local replay or a later CI run is separate evidence: neither rewrites
the immutable first run's rejected runtime comparison.

## Evidence limits

The official RU/EN contract comes from archive SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`, members
`nl/{ru,en}/html/SyntaxHelperContext/objects/Global_context/methods/catalog1762/FillPropertyValues2304.html`.
Its INCLUDE-priority description does not settle traversal, partial-write,
read-only, or ignored-argument validation details; these are measured here.

This profile uses only ordinary in-memory collections. It does not acquire
catalog/document metadata, persist objects, perform database writes, or claim
native compatibility for catalog/document adapters. Existing collections
checkpoints, captured bytes, historical reconstruction, Windows/default target
rules and all other profile acceptance rules remain unchanged. New Linux
observations must not be presented as Windows evidence.
