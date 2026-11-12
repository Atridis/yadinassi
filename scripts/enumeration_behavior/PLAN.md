# Owned enumeration measurement

Create a fresh isolated infobase from the existing minimal owned baseline.
Add only `Enum.OwnedStatus` with two declared values, `Active` and `Closed`,
explicit unique authored UUIDs and an English synonym on `Active`. Preserve
the baseline Role bytes: adding an Enum Read grant prevents this Designer
from completing LoadConfigFromFiles.
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

## Accepted native checkpoint

Run [43035110558](https://github.com/Atridis/yadinassi/actions/runs/43035110558)
accepted all 16 observations on 1C 8.3.27.1508, ru_RU, Etc/UTC.
Head `2a0cc671b72be56c93df352cf3d9ec4a7adee24a`, checkout merge
`6189a349` and exact tree `69768170e30564f64dbe211b8a513c3de7d86886`.
Output SHA256: `6de3af385896a915036fb97420b19f011328b69062309d14fffa183263f6e309`.
All 32 staged inputs, four host sources, nonce, generated module witness,
material configuration projection and cleanup were independently verified.
The copied canonical output is `tests/fixtures/native_enumeration_43035110558.json`.
The runtime replay executes the same case body and compares all 16 values.

Manager presentation differs from its Type presentation. In this Russian
profile the English synonym is ignored and the declared value name is used.
Russian synonyms, other UI languages, Ref type presentation, enum persistence,
Query and native UUID serialization are not inferred from these observations.

The successful acquisition validates the input fixture; it does not require
reproducing generated StandardAttributes/default nodes in a redump. The
application reader currently admits the original closed source envelope,
not arbitrary Designer-generated metadata.
