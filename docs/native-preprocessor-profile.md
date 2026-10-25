# Managed-thick file compilation profile

The native fixture is Linux/amd64 1C 8.3.27.1508, a managed thick client and an
ordinary synthetic file infobase. This is not a thin/web/ordinary-client claim.

The separately retained native observation is
`integrational_tests/directive_probes/preprocessor_profiles_native.json`.
It records run 40208015242 at head 17493e0b4724c5a08829b996cc98778f20b76b87,
with the unchanged source/module hashes and the exact token:

`pp.v1:135135139139131131131131131131`

The five independent English/Russian sites are direct client, context server,
server without context, dual on client, and dual on server. Their masks are
135, 139, 131, 131, and 131. `Client`, `Server`, and
`ThickClientManagedApplication` are true throughout this measured profile.
`AtClient` is true only at the direct client site; `AtServer` is true only at
the context-server site. Other measured client-kind flags are false.
Compilation flags do not choose runtime dispatch or execution context.
The standalone profile remains unchanged.

## Current strict admission

Ordinary workflow commands do not select observation mode. The exact current
client source hash selects named schema 9, with lossless wire schemas 9–12.
Every strict record pins `compilation_profile` to `managed-thick-file` and has
`preprocessor_status` equal to `not_started`, `failed`, or `matched`.
Early input/bootstrap failures retain this strict schema/profile binding.
Only exact recognized historical source hashes select the historical lane.

The host executes the unchanged whole 138-value source with a real, exclusively
owned `FileDBContext` and explicitly selects `managed-thick-file`. The native
private marker and host output must match every typed value, including the
captured token. Neither a source inverse nor a callback substitutes for current
runtime execution. Source/module, cleanup, process, six-output and four-client
checks remain mandatory. Async identities are unchanged; no new native Async
claim is made by the earlier observation.

Public purpose is `client-preprocessor-runtime-v1`. A true
`preprocessor_parity_claimed` requires the strict native record, independent host
profile proof and final acceptance/cleanup. The six-output provenance uses the
same guarded claim. Observation schemas, forged statuses, missing/wrong profiles
and current-source downgrades are rejected by strict admission.

## Historical observation

The explicit `--client-preprocessor-measurement` route remains separate:
named schema 5, wire schemas 5–8, status `observed`, purpose
`client-preprocessor-observation-v1`, and parity always false. It verifies the
historical 137-value prefix plus a finite observed suffix. Its host preflight
uses standalone. The original unmeasured plan and its null expected token are
immutable; the captured record does not retroactively make that run strict
whole-138 parity. The retained audit JSON also keeps its original audit-time
reproduction status rather than being rewritten after later review.

Limits remain wire 8192, public report 32768, private marker 2048, and source
input 294912 bytes. Focused tests exercise complete production encoders, reports,
provenance and whole-marker bounds. Final integrated genuine execution and the
strict current-head native CI gate remain required before feature acceptance.

Future source/schema growth that exhausts a fixed wire/report/private limit must
reduce the representation and re-prove the complete bound, not silently raise
the cap. Current strict worst-case wire reserve is seven bytes.
