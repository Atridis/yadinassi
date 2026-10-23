# Dual NoContext: finite measurement only

This candidate does not implement `&AtClientAtServerNoContext` or
`&НаКлиентеНаСервереБезКонтекста` in the interpreter. It adds an uncaptured,
literal managed-form measurement to the existing native runner. Native compilation,
execution, observed values, and parity are not claimed. The JSON plan keeps
`native_values` and `accepted_native_values` null.

The baseline is main `69e9df834975b9b6e3036aace579bb7ee1491ec7`, tree
`d817ebf4c29cc7fa42ded80a8cc29150a82e5a09`. The complete strict134 contract,
all interpreter runtime files, all eight Async sources and identities, the four
historical parity modules, and existing transport/reader caps remain unchanged.

## Source and observations

`integrational_tests/directive_probes/dual_directive_core.bsl` is the exact
unexecuted design source, SHA-256
`761b25578c9327dd3cf76a1f9ff81002c1c02d3e5df96f6c5616379a1058a345`.
Its labels and integration identity are in `dual_directive_measurement.json`.

The source collects nine ordered integer observations:

1. Client caller: profile mask, Val/returned-container alias, escaping scalar.
2. Server-context caller: profile mask, escaping scalar, caller module-state access.
3. Server-NoContext caller: profile mask, Val/returned-container alias, escaping scalar.

`Client`, `Server`, `AtClient`, and `AtServer` contribute separate mask bits.
Their actual values are unknown; a target mask must not be treated as a runtime
side. The mask fields are bounded to 0..15 by construction; the remaining
integer fields are bounded to 0..999, without asserting any expected values.
The controlled failure is matched exactly by its fixed substring; unexpected
errors are rethrown and a missing failure raises a separate fixed error.

The integration mechanically moves the annotated server variable into the module
variable prefix, preserves all six standalone routines byte-for-byte, and adds
only a literal digit encoder and one append procedure. Both helpers precede the
unchanged module initializer suffix. All new routine locals are explicit.
The two outer server wrappers remain real client/server boundaries; observations
are made within each caller before its result array crosses that boundary.

## Bounded capture, deliberate nonacceptance

The completed marker has the exact typed strict134 baseline plus ONE string:
`dual.v1:` followed by nine fixed-width three-digit ASCII decimal fields, without
separators. The complete marker has 135 entries. The literal BSL encoder checks
count, numeric type, integrality and each range before building digits with
`Int` and `Mid`. It does not use new JSON writer settings, enums or formatting
APIs. The existing JSON writer is byte-for-byte unchanged.

Only an exact completed marker with the existing schema, nonce and client witness,
the full typed baseline, and the exact token grammar can expose a temporary
`dual` diagnostic containing nine integers. Booleans, strings in the integer
slots, signs, Unicode digits, fractions, wrong lengths, wrong masks and private
text are rejected. No native error text or arbitrary string is exported.

The ordinary marker verifier still accepts exactly 134 values. The appended
measurement is deliberately rejected with failed/invalid_result and
`witness_verified=false`; it cannot produce acceptance, parity or output artifacts.
The native source/module/roundtrip hashes, staging checks, nonce, bounded private
reader and process/quiescence gates remain in force. A failure diagnostic alone
is not native evidence; a later capture needs an independent complete audit.

## Exact inverses and regression gates

The identical `dual_shared_source` inverse used by host preflight and the native
historical-adapter route requires the exact integrated hash, prefix, helper block
and call. It restores every byte of strict134 source
`b79c23abb756c3b3965e3a46ad7212e582db917ff319facc70a1efb18a470e14`.
The host executes only this restored source in its real isolated interpreter child.
All four historical adapter module hashes remain pinned to their previous bytes.
This projection is not used to remove the new source from the native measurement.

Focused tests cover the mechanical integration, section ordering, explicit locals,
all inverse mutations, strict134 acceptance, dense token grammar, synthetic digit
encoding, private reader failures, typed diagnostic failure-only behavior and
actual production report serializers. Test-only exact inverses restore the
baseline host/stage Python sources before older Async source projections, retaining
all historical whole-source and Async8 pins rather than rebasing them.

The private marker's synthetic two-space/LF upper bound is 2041 bytes, including
all nine maximum-width fields, under the unchanged 2048-byte read cap. This is a
conservative formatting calculation, not a native run. The existing combined
Async proof includes both ordinary and dual diagnostic shapes in every early,
late and failed-marker partition. Its exact production serialization results are
recorded in the accompanying local validation report; no cap is raised.

## Limits and next gate

This measurement does not add forms, database access, networking, module capability
support or runtime dispatch. Positive caller observations do not prove forbidden
module access or export/call rejection. Native capability-negative behavior and
Async-dual declaration legality remain unknown and outside this positive source.
No intentionally uncompilable native fixtures or new compiler-classification route
are added.

After source-bound native evidence is independently captured and audited, remove
the temporary capture diagnostics/encoding, derive only the supported narrow
contract, and implement it separately with real context-restoration and Async
composition tests. A later implementation still needs fresh strict134 and Async8
native gates plus normal required CI. Historical captures cannot substitute for
current-source validation.
