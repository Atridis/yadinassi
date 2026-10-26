# UUID scalar observation candidate — LOCAL, NOT NATIVE EVIDENCE

> Historical initial-candidate design below. For the subsequent authenticated
> PR112 observations and current bounded support, see [native alignment](uuid-native-alignment.md).

Base: `value-tree-post109-preview-v1`, expected future core tree
`ec130478a8620dc5e6d046ab02bed9bc26103b14` (not a claim of a merged commit).
This slice does not implement UUID and does not derive expected native answers
from the independent provisional runtime. It must remain outside PR110.

## Measurement matrix

`integrational_tests/tests/values.bsl` gains **30 scalar observations plus 9 independent deterministic codec observations**,
taking the standard complete values route from 402 to **441**.
The source-specific adapter preserves every fixed expression verbatim; only its
existing message-capture identifiers/directives/body wrapper change.

* Separate `Type` and constructor observations for `УникальныйИдентификатор`,
  `UUID`, and `UniqueIdentifier`. All unknown type/constructor names stay inside
  fixed dynamic `Выполнить` strings, not statically compiled module expressions.
* Lowercase and uppercase canonical text, value equality, unequal GUIDs and
  GUID-versus-string equality.
* Map and FixedMap same-value replacement, reconstructed-key lookup and a
  separate text key (count plus both retrieved scalar values).
* Zero and nonzero filled checks.
* Singleton TypeDescription membership/count; omitted and explicit Undefined
  defaults, adjustment of UUID and text. Values are projected to type and
  comparisons with the two fixed GUIDs, not emitted raw.
* Empty, invalid, truncated and braced strings; explicit Undefined constructor.
* Omitted/no-argument constructor: format, nonzero, roundtrip equality, distinctness
  and **observed version nibble**. The nibble is measured, not assumed to be 4.
  Each default probe generates its own value inside its own catch boundary.

Fixed GUIDs: zero, `01234567-89ab-4cde-8f01-23456789abcd` and
`01234567-89ab-4cde-8f01-23456789abce`. Random values never appear raw in output.
Potentially surprising empty-string/Undefined acceptance reports type/format/nil/equals-fixed/version, distinguishing zero from generated/other values without exposing raw UUID text. Canonical text is emitted only after normalized equality to the predetermined fixed input.
The format helper performs a bounded 36-character check, including hex/hyphens.
Each API or conversion failure yields one `[error]` record and cannot suppress
subsequent observations. Localized exception text is never output.

## Deterministic codec measurement extension (v3)

Nine individually caught records extend the same scalar family, without any
runtime codec implementation or claim of native support:

1. Internal encoding of the fixed UUID.
2. Internal encoding of the zero UUID.
3. Internal encoding of `TypeOf` the verified fixed UUID (not a guessed alias).
4–5. Internal roundtrip of fixed and zero UUIDs, independently.
6–7. XMLString of fixed and zero UUIDs, independently.
8–9. XML roundtrip of fixed and zero UUIDs, independently.

Every setup constructs an explicit predetermined value and verifies its canonical
text before calling a codec. Raw codec strings from these verified fixed inputs
are permitted up to **256 characters**. The probe rejects nonstrings/oversize
results, never truncates them. This is a new probe-local output guard, not a
production cap increase. Roundtrip outputs are only restored-type/equality
projections; no reconstructed UUID is emitted raw.

The helper distinguishes `[setup-error]`, `[encode-error]` and `[decode-error]`.
A failed constructor/input guard or encoder cannot be mistaken for a failed
reader: the next stage is not invoked. `[decode-error]` includes errors in the
reader or its final scalar projection. Each record has fresh local state; errors
cannot hide another fixed/zero observation. Unknown native API behavior remains
unmeasured; the source deliberately records failures rather than inventing an
expected codec format or relaxing current comparisons.

## Admission and historical replay

No client-probe marker, workflow/security change, cap increase, database route,
collections source or Map-exception change is included. Collections remain 866.
Current values source hash, all helper/end/message tables, line count, host count
and synthetic comparison fixtures are pinned to this complete 441-record source.
Every appended wire record is mandatory; old source, truncated output, malformed
captures, wrong nonce/witness and byte changes remain rejected.

Historical native fixture files are immutable. Offline historical replay has an
exact whole-input/whole-output SHA256 inverse, preserving their original source
and outputs instead of treating a new suffix as optional. The harness inverse is
test-only, independently pinned to the exact base and candidate. New checkout
normalization tests normalize CRLF only for simulated Windows offline fixtures;
production source/template admission still rejects raw CRLF, extra BOM and drift.

## Verification boundary

Local parser, adapter, historical replay, failure isolation and finite transport
budget tests establish instrumentation only. UUID errors from a runtime without
UUID support are **not** native expected values. No native execution, remote
publication or final native answer fixture is part of this slice. Before any
runtime/native alignment, collect and audit fresh complete server and managed-
client records through the existing standard values owner-PR route; investigate
any error or alias/version difference without weakening comparison.
