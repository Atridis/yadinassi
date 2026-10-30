# Closed Columns.Clear measurement profile

`tree-columns-clear-v1` fixes source `tree_columns_clear.bsl`, artifact
`tree-columns-clear`, twelve cases plus calibration, and one self-contained
strict decoder. This is measurement infrastructure, not a new Clear runtime.
The existing nonempty Clear and last-column Delete guards remain unchanged.

The [standalone observer](value-tree-columns-clear-measurement.md) retains
independent active and retained-reference observations. Integration strengthens
positive-control admission: both EN/RU controls must start with nonempty active
schema and reachable rows, then succeed **and** leave no active columns or
reachable rows, as specified by the primary API. Empty-before captures remain
observations but cannot establish this nonempty Clear capability. Retained
reference outcomes are not constrained. Noop and columns-only synthetic models
still strict-decode, but exact matching output cannot make acceptance green.
A valid exported observation is distinct from availability and runtime parity.

The fixed registry, CLI and real shell emitter admit only named profiles. Both
emitter allowlists and the profile mapping include Clear; partial additions,
unknown/duplicate/mixed modes and cross-profile artifacts are rejected. Decoder
imports remain profile-local, so old staged containers require no new dependency.
The Clear stage contains exactly 22 approved sources; a cold `-I -B` subprocess
executes its actual staged closure, and removal of the decoder fails.

The existing Copy/Sort/Columns.Move matrix receives one literal Clear row with
fixed case/artifact values. This creates one additional job/container, not a
second workflow. Fill, permissions, immutable-source/actor/parent checks, cleanup,
credentials and the required matrix aggregate are unchanged. Manual dynamic
profile/source inputs are not added. Earlier boundary/tail Move profiles remain
reproducible but are not reactivated in the matrix.

## Actual integrated size bounds

| Object | Proven upper bound | Existing cap |
| --- | ---: | ---: |
| Capture | 4406 | 8192 |
| Completed marker, including conservative escaping/spacing/BOM | 4620 | 16384 |
| Stage report | 4187 | 8192 |
| Native report | 9313 | 32768 |
| Transport envelope, reserving the full 8192-byte capture cap | 20517 | 65536 |
| Host report | 14731 | 32768 |
| Provenance | 14527 | 32768 |

Bounds use the actual registered inventory and complete existing report layouts,
not just the capture size. No cap or `full_suite.py` change is needed. All six
preceding generated client modules remain byte-identical.

## Local verification and limits

Tests exercise the real producer-to-host success/failure paths, exact parity and
both positive controls, source-hash drift, artifact mixing, cold staged imports,
real embedded emitter routing and both partial-route negative controls.

Synthetic source fixtures are explicitly UTF-8/LF before hashing; production
readers and source pins do not normalize checkout or acquired bytes. Windows
static fixtures use the established scoped test reader rather than claiming
POSIX descriptor metadata equivalence. Actual Bash tests use the reviewed
Git-for-Windows Bash selector (never the System32 WSL launcher), in-process shell
stubs, no startup hooks, and no executable temporary-file/shebang assumptions.
They execute only bounded setup/flag/workflow fragments, never native processes
or the shared native fixture directory.

No native observation or runtime Clear compatibility is claimed. Publication,
fresh real client/server acquisition and subsequent runtime decisions remain
separate gates.
