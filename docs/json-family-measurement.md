# Whole-family JSON native measurement

This is one feature-family batch, not an edge-only supplement. Native execution
has **not** yet been performed. Local captures and synthetic runner envelopes
are test inputs, never platform evidence.

## Fixed input and wire

- Profile: `json-family-v1`, artifact: `json-family`.
- Source: `integrational_tests/measurements/json_family.bsl`.
- Source SHA-256: `ac6acd4a5af2b93c3d6b3b2e7ffdc95f8024e3fbd52482cd4c814b3f2020b00b`.
- 31 workflow observations plus 2 independent observer calibrations.
- Every result is a bounded string encoded as its UTF-16 units, or the literal
  `action-error` / `observer-error`. Error wording and file paths are not exposed.
- Maximum 56 UTF-16 units per string; rectangular output bound 7,521 bytes,
  below the unchanged 8,192-byte per-context limit.
- Both ordinary server and generated-client lanes retain exact source binding,
  closed dispatch, client roundtrip, process cleanup and envelope validation.

## Cases

| Cases | Workflow |
| --- | --- |
| 1–5 | Compact/default/Unix/Windows output, nested collections, manual Russian API |
| 6–7 | Arbitrary string-keyed Map and fixed Array/Structure/Map |
| 8–12 | Token walk, initial/end/container current value, nested Skip |
| 13–14 | ReadJSON subtree and repeated scalar cursor behavior |
| 15–19 | Invalid structure key, map key, Null value, JSON text, writer state |
| 20–22 | Unicode/numeric/null tokens, reader reset, writer reuse |
| 23–24 | Owned temporary UTF-8 files without/with BOM, close and readback |
| 25–27 | Exact decimal, Type/TypeOf, escaping and supplementary Unicode |
| 28 | Read after close |
| 29–31 | Exponent WriteValue, omitted/default writer settings |

Map case 6 projects values by fixed keys rather than assuming an iteration
order. There are no callbacks, configuration objects or external input sources.
Deferred features are marked `// !todo` near the fixture header.

## Local replay and temporary paths

Native case 23/24 uses only platform-generated temporary filenames. Files are
closed and deleted on success and on exceptions. The compared local interpreter
has no general temporary-file API added by this measurement. Instead, the
source-bound host replay installs two fixture-only helpers through
`scripts/native_1c_json_family_replay.py`:

- at most two `.json` paths inside one private TemporaryDirectory;
- deletion only of those exact allocated paths, with symlinks rejected;
- automatic directory cleanup even if execution raises;
- no paths returned in captured output.

The replay adapter is included in host source provenance. It is not shipped
into the native bootstrap or added to public BSL runtime registrations.

## Verification and execution

Focused local tests:

```sh
PYTHONPATH=tests:scripts:scripts/native_1c_bootstrap python -m unittest \
  test_native_json_family_measurement test_native_json_family_profile
```

They verify source pins, generated-client inversion/capture, both dispatch
allowlists, observer failure/availability distinctions, owned temporary paths,
real isolated local replay, and all existing report/transport budgets.

The existing isolated native workflow matrix includes the new closed profile.
Root coordinates publication and native dispatch; no separate credential,
permission, image or security-setting changes are introduced here. The usual
profile driver is `scripts/native_1c_tree_profile.py --profile json-family-v1`
with the same existing explicit image-execution option. A valid measurement is
not runtime acceptance: final acceptance additionally requires available APIs,
matching exact outputs and all unchanged envelope/lifecycle gates.
