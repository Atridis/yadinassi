# Owned Catalog reference identity measurement v1

This is a measurement lane, **not** a runtime UUID codec, BSL Catalog API,
general file-database writer, or permission to open a caller's database. Existing
read-only Catalog admission remains one active record, with no freed slots.

## Two independent cases

`catalog-reference-identity-v1` uses closed cases `distinct_a` and `distinct_b`.
Each case has a different controlled UUID with sixteen distinct bytes. The
source-pinned native hook constructs the UUID, obtains a Catalog reference, and
calls `УстановитьСсылкуНового` before the existing create/write transaction.
Installation errors stop that invocation: there is no generated-ID fallback.
The committed reference is then obtained through the existing private saved
reference witness, not copied from the requested UUID into a reader result.

The hook is an exact guarded transformation of the unchanged historical server
template. Ordinary and previous closed lanes retain their old rendered bytes.
Case-dependent rendered server identity is independently recomputed and bound in
the capture. Its SHA-256 domain is UTF-8 text without BOM, with universal LF
newlines, matching the existing redump text-comparison domain. Source provenance
continues to hash the actual staged source bytes.

A private, bounded 1024-byte sidecar binds nonce, native invocation token, case,
operation and observed committed UUID. The host reads it through the existing
regular-file guard, validates it, retains only its digest and finite observations,
and unlinks it even on failure. Installation is recorded only after both the
native completion and ordinary result markers pass; its token is distinct from
the audit and all three observer tokens. The installation witness must agree with
the later created-state witness.

## Logical observations

Before and after each protected native operation, twelve ordered probes yield
`T` (true), `F` (false), or `E` (evaluation/type error). `N` is permitted only for
the final three probes when no committed-reference witness exists:

1. Empty reference UUID equals zero UUID.
2. Empty reference `.Пустая()`.
3. Empty reference `ЗначениеЗаполнено`.
4. Reference obtained from zero UUID equals empty reference.
5. Zero-UUID reference `.Пустая()`.
6. Zero-UUID reference `ЗначениеЗаполнено`.
7. Controlled-UUID reference UUID round trip.
8. Controlled-UUID reference `.Пустая()`.
9. Controlled-UUID reference `ЗначениеЗаполнено`.
10. Committed-reference UUID round trip.
11. Committed reference `.Пустая()`.
12. Committed reference `ЗначениеЗаполнено`.

The report does not prescribe the truth values. Baseline, created and updated
observer captures retain actual finite observations. After physical deletion the
private saved reference may still exist; reference presence and row presence are
separate facts. Neither empty-reference observations nor reserved zero-filled
slots establish a persisted zero-reference encoding.

## Physical comparison and preregistered hypothesis

Both the original frozen image and its independently frozen observer postimage
are read for baseline, created and updated: six reads, unchanged lifecycle.
The completed reader receives only the closed Catalog selector and limits.
CONFIG-derived identity/declarations, DBNames mapping and native metadata are
compared before selecting the mapped reference field. Each image digest is
verified before the private UUID is compared to that field. No expected UUID,
field offset or guessed physical name is supplied to the reader.

A physical value must be exactly sixteen bytes. Its byte set must equal the
sixteen distinct canonical UUID bytes, producing a unique bijection. The report
stores the permutation in the direction **canonical UUID byte i = physical byte
permutation[i]**. Original and observer images, and created and updated states,
must agree. Structural failure, ambiguous mapping and witness mismatch fail
closed with finite diagnostics.

The preregistered hypothesis is `[12,13,14,15,10,11,8,9,0,1,2,3,4,5,6,7]`, from
[Tool1CD BinaryGuid.cpp at d5e31816](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/BinaryGuid.cpp)
(blob `59ae49a5224a86a961d58f992edb1e0e5db73fb7`). It is not Python
`bytes_le`, nor an acceptance assumption. A valid unexpected permutation is
retained with `hypothesis_match=false`. Two different controlled cases must
produce the same permutation before any future codec proposal; this lane never
sets `codec_approved=true`.

## Handoff, artifacts and bounds

The reviewed workflow runs two dependent jobs, each retaining the existing
50-minute outer and 2400-second host budgets. A completes native/process/container
and private-staging cleanup before B can start. B receives only A's exact artifact
ID from the same workflow run, with action digest verification and no added token
permissions. Before package credentials are exposed, B verifies run/attempt,
exact one-file inventory (no symlinks or extra files), exact report SHA-256,
source/case identity and accepted cleanup. The host repeats that check before
its independently fresh temporary root, nonce and container invocation.

The fixed artifacts are `distinct_a.json`, `distinct_b.json`, and
`reference-aggregate.json`. The aggregate hashes the exact two report files,
requires A+B with distinct nonces and common provenance/native version, and
records both permutations and their agreement. A mismatch preserves the finite
aggregate but fails the job. A failed A prevents B; a failed B can export only its
validated finite failure report. No raw UUIDs, logs, metadata dumps or images are
uploaded. The finite reports cannot independently prove CI execution order;
that evidence is supplied by the source-pinned dependent job boundary.

Invocation schema is 24, report/capture schemas are 39/40, aggregate schema is 41.
The closed inventory has 40 files. Existing capture/report caps remain
12288/32768 bytes. The independent worst-case complete report bound, charging the
entire capture allowance and final newline, is **32551 bytes**; the current
success-capture envelope is 3469 bytes. The aggregate has its own 2048-byte cap
and does not embed either full report. These are synthetic protocol proofs, not
claims that either case has run successfully on real 1C.
