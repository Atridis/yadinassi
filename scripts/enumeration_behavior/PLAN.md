# Owned enumeration measurement (not yet acquired)

Create a fresh isolated infobase from the existing minimal owned baseline.
Add only `Enum.OwnedStatus` with two declared values, `Active` and `Closed`,
explicit unique authored UUIDs, an English synonym on `Active`, and Read rights.
No catalog/document/register field is added, no existing user database opened.

Run the 16 cases in observe.bsl with per-case bounded framing and an invocation
nonce. Keep error status distinguishable from successful returned text, including
empty strings. Do not bake expected results into the acquisition. Native type
presentation, synonym use, empty-value index and iteration remain observations.

Reuse existing approved pinned-image isolation and teardown guarantees through
an explicit owned profile. Validate exact source inventory and material XML
projection after Designer loads the configuration; generated UI/default nodes
need not be made byte-identical. Do not print private container payloads or
native unrestricted diagnostics. Return bounded observations/provenance only.

Runtime replay and accepted source projection are added only after inspecting
the actual output. A successful load is not enum storage/codec/Query parity.

## Prepared acquisition route

The branch-specific workflow is `native-1c-enumeration.yml` on
`codex/configuration-enumerations`. It runs the dedicated
`native_1c_enumeration_profile.py` and isolated `native_1c_enumeration_probe.sh`;
existing accumulation/native workflows and captured evidence are unchanged.
The bootstrap uses an explicit small `run_owned_case` adapter with the ordinary
launcher templates and guarded process/result helpers, not shared-module patching.

Artifacts are `native-enumeration-summary` and, only on verified acquisition,
`native-enumeration-observations` containing `enumeration.out` plus provenance.
The canonical observation is a JSON array of exactly 16 bounded strings.
Successful empty strings and Unicode are preserved; missing/error cases are not
converted to empty values. Any case error prevents successful acquisition.

Before treating an output as evidence, verify repository commit/tree, observer
and every staged source hash, generated-module witness, invocation nonce,
material configuration projection, final process census and both container/private
cleanup flags. `native_measurement_accepted` does not set `runtime_parity_accepted`;
the latter remains false until the language implementation is separately compared.

No native acquisition has been run or accepted as part of preparing these files.
