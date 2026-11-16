# Owner-local pure scalar source preparation

Base `01306fc2` (public `07d52635`). This slice does not include the separate
coherent SQLite source-pair optimization. It changes form_module_analysis and
form_event_simulation only.

Private analysis returns the checked analysis plus its parsed program. Public
analyze_form_module still returns only FormModuleAnalysis. A backend-local last
scalar source unit holds owned program/signature metadata and pure analysis;
standalone drafts use their own slot. The existing separately keyed generated
code plan is unchanged. No global cache or receiver/authority cache is added.

Every use checks exact input types, identity shape, canonical paths, source/XML
byte limits and hashes. The key contains source and three XML byte strings,
primitive binding field values and the static profile/limits. A binding UUID is
validated to contain an exact int before any truth/equality operation. On a miss,
a detached binding is reconstructed with fresh UUID instances; the analysis does
not alias the caller's frozen binding. XML and AST analysis run once per miss,
and the direct event no longer reparses the same source a second time.

Current backend reads/identity/source checks before AND after the event, revision
checks and adoption remain untouched. Receivers, scalar input validation,
messages, cancellation and execution contexts remain fresh. Legacy backends keep
their previous admission/execution path. The cache is private trusted-host code
metadata, not support for mutating its private AST or monkeypatching validators.

Tests: 94 focused tests pass normally and under `-O`. Coverage includes new verified sessions
sharing only pure/code metadata, no parse/XML on a hit, detached binding,
malicious UUID payload without hooks, source/XML drift, profile/limit invalidation,
public analysis result compatibility, current owner closure and failure after a
private setter without adoption/replay. Two previous instrumentation tests now
observe fresh cheap input validation rather than requiring repeated XML parsing;
their original-byte/BOM/CRLF/binding and current-storage assertions remain.

## Real original UI, seven alternating pairs

Run `paired.py BASE_REPO CANDIDATE_REPO --python PYTHON`. Six cycles per process;
warm medians exclude iteration zero. All source/runtime hashes and samples are in
results.json. Actual MainDemoHost original form Description/Save actions check
saved names and final warehouse rows. No Chromium or native 1C parity claim.

| Action | Baseline ms | Candidate ms |
| --- | ---: | ---: |
| Kind Description | 24.898 | 19.987 |
| Kind Save | 46.775 | 42.264 |
| Product Description (unchanged control) | 18.579 | 18.306 |
| Product Save (unchanged control) | 55.133 | 54.551 |

The scalar kind benefits from eliminating repeated static parsing. Small product
control differences are noise, not an optimization claim.

After measurement, one stale reparse comment was corrected. Python ASTs before
and after that comment-only edit were checked equal; raw hashes describe the
measured file before that comment correction. No executable code changed.
