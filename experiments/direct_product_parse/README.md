# Direct product-form parsed source reuse

Base: `6a11d1f5` (public `9eac22e0`). One runtime edit in
form_event_simulation.py. No generated-handler factory/closure reuse.

The existing catalog manager retains at most one private parsed program keyed by
exact product-form bytes and the fixed parser source name/standalone profile.
All current source hashes, schema, reference targets, pending-write state, row
limits and current-row attachment checks still run before lookup. The parser AST
is created internally from the admitted original bytes, never supplied by a
caller; generated code preparation still snapshots before its transformation.
The top-level list is private per invocation, with owned declaration metadata.

VMs, receiver buffers, controls, cancellation cells, output messages, contexts and
exports remain fresh. No current backend/source permission checks or SQL writer
checks were removed. The source hash check rejects changed bytes before reuse.
The legacy branch still parses each call and neither reads nor fills this slot.
Private syntax is not an API for arbitrary host mutation. There is no global
identity cache, generic compatibility layer or execution fallback.

Tests: 39 focused product/list/prepared-event tests PASS; six new regressions also
PASS under `-O`. New controls cover one parse across repeated events with fresh
messages, changed form/object source, current schema/reference-target/row checks,
fresh receiver and cancellation, pending writes and the unchanged legacy path.
Existing SQL refusal/no-adoption and original source event checks are retained.

## Final measurement

`paired.py BASE_REPO CANDIDATE_REPO --python PYTHON` uses real MainDemoHost kind
and product editors, six Description+Save cycles, seven alternating fresh-process
pairs in the same current environment. Every saved name/state and final product
warehouse row are checked. Iteration zero is retained but excluded from warm
medians. This measures the production patch against its baseline, without the
earlier diagnostic parser monkeypatch. Raw samples include exact runtime hashes.

No Chromium, full-suite, native 1C parity or handler-factory speed claims.

Warm medians in milliseconds:

| Action | Baseline | Candidate |
| --- | ---: | ---: |
| Product Description | 11.441 | 6.819 |
| Product Save | 44.713 | 39.051 |
| Kind Description (unchanged control) | 18.294 | 17.924 |
| Kind Save (unchanged control) | 38.551 | 37.838 |

Product savings are about 40% for Description and 13% for Save. The roughly 2%
control differences are noise, not an additional optimization claim.
