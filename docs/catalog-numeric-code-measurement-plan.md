# Numeric Catalog Code: standalone measurement preparation

Base: merged main `6134989a6054ac1312eff83cf23cdbb2ac047438`, tree
`459967398ee01f03d55ee7014da31594f9168431`. This change adds standalone fixtures,
observation code and synthetic tests only. No injector, runner, workflow,
production storage reader or existing source is changed. It is not a native
execution or Numeric Code runtime-support claim.

## Existing evidence and unresolved semantics

The accepted owned CONFIG matrix [run40759955663](https://github.com/Atridis/yadinassi/actions/runs/40759955663)
on `f4ed7c9e49e735a5056c3758185299e3dbe55c64` admitted an empty Number-code catalog
with CodeLength2 and DescriptionLength16. Its exact transform uses
`<CodeType>Number</CodeType>` and the original template's
`<Autonumbering>false</Autonumbering>`. The XML-to-CONFIG identity/scalar join is
recorded in [the original matrix evidence](config-catalog-field-matrix.md).
This establishes an owned use of the XML literal, not row encoding, lengths3/6,
a general maximum, or automatic numbering behavior.

Official [1C numbering guidance](https://1c-dn.com/library/length_of_configuration_object_codes_and_numbers/)
explains that code length is a configuration choice, and length0 disables it.
The [EDT Catalog metadata API](https://edt.1c.ru/dev/edt/2024.2/apidocs/com/_1c/g5/v8/dt/metadata/mdclass/Catalog.html)
exposes length, type and autonumbering properties. EDT enumeration identities
are not physical CONFIG or record-format evidence. No numeric-specific native
maximum is claimed here. The physical observer's38-digit ceiling is its local
bounded decoder scope, not a newly verified platform limit.

Zero, negative, fractional, overflowing and automatically allocated assignments,
length0, prefix behavior and String-to-Number conversion are deferred. The private
witness parser can represent bounded negative/fractional/zero readback without
asserting that those assignments are supported. Native compilation and readback
must still verify the proposed BSL metadata property use and new XML variants.

## Exactly two independent cases

Each case starts a fresh disposable infobase. Never convert an existing String
catalog into Number. Both use Description8, Payload String32 (later64), Amount
Number(9,2), one active row, no hierarchy, no extra metadata or CRUD rights.
Autonumbering stays false; uniqueness stays enabled.

| Case | Configured CodeLength | Create assignment | Update assignment |
| --- | --- | --- | --- |
| number3 | 3 | 987 | 12 |
| number6 | 6 | 654321 | 42 |

Lengths and assignments are fixture inputs, never runtime gates or expected
physical values. Odd/even precision tests the candidate BCD padding boundary.
Description assignments are fixed short controls. Actual post-commit readback,
not equality to these assignments, is the comparison witness.

Raw, hash-bound transformations of the original Catalog XML and server module
have exact inverses. The appended observer is separately hash-pinned. Old templates
and existing schema2/schema3 witnesses remain unchanged. The transformed
logical report uses `observed_number` as a finite role tag, not a numeric value or
pretend K1. **It is intentionally not compatible with the old K1 protocol and is
not registered for execution.** Integration needs an explicit closed mapped-core
view; no old protocol may silently start accepting new tags.

## Independent physical observation

`read_numeric_code(read_at, file_size, *, catalog_name, limits=None)` has no case,
length, seed or native-witness argument. One generic catalog and one binding
graph own all CONFIG, PARAMS, DBNames and record work. CONFIG supplies CodeType0,
CodeLength and attribute qualifiers. PARAMS uses the explicitly accepted
`closed_marker1_chain_v1` policy and existing cumulative ownership/budget gates.

A private counterfactual String-code identity is used only to reuse the existing
metadata/DBNames/table/attribute join. It is never returned as a real binding.
After generic catalog admission, the fixed-role hypothesis replaces only _CODE
with N(precision=CONFIG CodeLength,scale=0), width `(length+2)//2`, retaining the
exact surrounding descriptor. A different valid layout yields `layout_unresolved`
without reading row data. No search for a matching witness value or alternative
winning format occurs. The existing Number decoder is used only after the exact
N descriptor match, with strict sign/digit/padding checks. This remains a format
hypothesis, not approval for arbitrary Number-code layouts.

Only the bounded reserved+one-active/no-freed catalog profile is decoded.
The admitted _IDRREF supplies a private typed UUID without a second graph.
All failure paths poison the shared graph; no retry, extra graph or native write
API is introduced. The production compiler still rejects Number codes.

## Private witness and finite projection

`numeric-code-observation.json` is a distinct private schema1 sidecar. It carries
nonce, observe token, case, operation, explicit presence, actual Number-type
predicate, XML decimal text, UUID, Description and actual metadata lengths plus
autonumbering. The observer reselects the committed row in that same session,
checks saved-reference identity, then writes a fresh-only sidecar. The comparison
consumes this only after physical observation; it is not itself proof of a
same-postimage handshake.

Private input is capped at2048 bytes; decimal lexical text at80 characters and
Description at128 UTF16 units are transport bounds. No floats, exponent notation,
NaN, duplicate JSON keys, stale tokens, noncanonical UUIDs or ambiguous absent
values are accepted. Public output contains finite verdicts, descriptor/witness
hashes, metadata widths and offsets and counts only. It does not emit actual Code,
UUID, Description, descriptor bytes, or a brute-forceable hash of Code alone.
Valid layout/value differences remain measurement results, with
`runtime_support=not_claimed`, not runtime admission.

## Required next integration review (not implemented)

1. Allocate a unique invocation/report/capture/aggregate schema family after
   checking the actual registry. Prove the exact import/source closure, including
   all lazy imports and rendered observer hashes; do not assume the old42 count.
2. Retain the existing two credential jobs and fixed per-case host paths. No new
   rights, jobs, native commands or lifecycle stages. Existing baseline/create/
   update/applied snapshots can supply absence and three present observations;
   account honestly for Payload32/32/64 and PARAMS migration.
3. Bind each witness to that observer's nonce/token and verified immutable
   postimage. Preserve frozen-owner inspection, quiescence, source checks,
   handoff, failed-capture scrubbing and all four cleanup gates. Do not reuse a
   create/update sidecar for applied. Keep actual values private until deletion.
4. Define closed policy/protocol projection and fail-closed metadata gates;
   observational unresolved/difference outcomes must never mean runtime support.
   Preserve every old route and its original evidence attribution.
5. Prove complete rectangular serialized envelopes at actual source count,
   all stages/snapshots/failure paths and full capture reservation. Caps remain
   8192 capture and32768 full report, with separate captures for the two cases.
   Current standalone projection/private bounds do NOT establish that integrated
   report fits. If it cannot fit, reduce the measurement projection, not gates.
6. Independent source review, normal/-O tests, strict cold readiness, root-owned
   publication and authenticated native acquisition are required before facts
   can justify a later small production-binding proposal.

## Integrated lane (pre-native preparation)

The separate `catalog-numeric-code-measurement-v1` lane uses invocation schema30,
report59, capture60 and aggregate61, with an exact42-source cold-import closure.
It reuses the existing two credential jobs, commands and lifecycle stages. Four
same-observer states are baseline/created/updated/applied; the last uses Payload64.
The private schema1 sidecar is consumed before its completion marker and removed
on every transport path. Observer failure and final cleanup also clear in-memory
witness/pending evidence. No seed value is supplied to the physical selector.

The closed `observed_number` logical tag is required in every present numeric
logical state. A detached validated view maps that tag to the old core's K1 only
for lifecycle checks; the emitted report retains the numeric tag. Neither lane
accepts the other lane's tag. Native metadata/type and same-row UUID are mandatory;
Code/Description differences or an unresolved valid layout remain measurements,
not runtime approval. Baseline is explicitly absent.

Independent rectangular constructors reserve the entire8192-byte capture inside
an otherwise maximal report: capture5992, fullreport28555, aggregate619 bytes
(including their newline), private witness1207 including BOM. Limits remain
8192/32768/2048, and no schema or resource limits are increased. Native availability
and actual Number metadata still require a fresh exact-source Designer/native run.
Historical Description and PARAMS receipts keep their original source attribution;
shared harness changes require fresh provenance, not relabeling previous evidence.
