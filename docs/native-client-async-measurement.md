# Native client Async/Await measurement (opt-in)

This is a measurement harness, not interpreter Async/Await support or a parity claim. The existing server postCreate contract, six server scenarios, simple client witness, and standard CI parity/watchdog invocation are unchanged.

A separately approved invocation can use:

```sh
python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --client-probe \
  --client-async-measurement --output native-smoke/report.json \
  --export-native-outputs --native-target linux-8.3.27.1508 \
  --comparison-mode typed-map-order-v1
```

The measurement flag cannot be combined with optional client parity or watchdog flags. This does not replace standard CI coverage. The owner-only manual workflow requires an explicit true measurement flag and a reviewed commit SHA matching the dispatched same-repository branch revision. False/missing flags, forks, tags, and mismatched revisions are rejected. Running the command requires the existing approved native image and execution environment.

## Fixed language-only observations

Eight freshly built managed client forms measure:

1. Async function return type and explicit joining.
2. Await of a settled Promise and actual caller/callee event order.
3. Multiple retained branches and explicit completion of every branch.
4. Await of scalar values, preserving results or caught errors.
5. Nested Promise return behavior, preserving actual type and result.
6. Val/default-parameter behavior and unmarked scalar observations.
7. Error timing at call versus first/repeated Await and propagation.
8. English/mixed-case core grammar and a handled Async procedure.

No UI, network, or file-async API families are measured. Completion transport uses synchronous private file I/O only. Compiler-negative cases, task-local context, Decimal behavior, and import diagnostics are deferred.

The fixed per-case event inventory, conditional branches, and partial-order edges are independently specified by the protocol tests. An accepted trace contains every required event exactly once, in its actual native order; it is not rewritten into an expected schedule. Values retain finite type tags and actual bounded payloads. Unsupported types or out-of-bound observations produce an inconclusive result, not a normalized success. Expected error paths preserve selected exact descriptors privately; public evidence contains finite field classifications and SHA-256, never free-form error text. Recursive error/source parity is not claimed. Unexpected root or sibling failures fail closed with no accepted trace; they produce finite failure evidence and only the available private platform logs, not a dedicated caught-error sidecar.

## Completion and evidence

Only the Async root writes completed and exits. It joins all retained Promises, including cleanup paths; no sleep proves completion. Each launch uses a fresh directory, exact canonical request, invocation nonce, client witness, exact generated-module and native roundtrip hashes, clean process/session checks, and strict complete markers. Early exit, partial/noisy markers, wrong witness/nonce, stale files, and unexpected processes fail closed.

Private continuity evidence records fixed-path metadata identities and byte hashes. Schema 4 carries its SHA-256 from the stage to the final emitter; final export verifies the digest and every fixed entry again. Replacing evidence and rebasing the private manifest cannot satisfy the retained report digest. A failed/inconclusive/unreached measurement carries no continuity digest.

The old process timeout remains exactly 120 seconds. Async-only operations use at most 120 seconds each, bounded further by the remaining shared deadline; the deadline is conservatively anchored to shell start with finalization reserve. Deadline exhaustion fails without accepting partial traces.

## Public boundary

The staged input inventory remains 24 paths. The stage wire cap remains 8192 bytes; summary and provenance caps remain 32768 bytes each. Public output classes remain six existing `.out` files, finite provenance, and finite report. No raw logs, marker files, continuity manifest, database, EPF, or screenshots are exported. Reports explicitly mark measurement purpose and `client_async_parity_claimed: false`.

Offline tests exercise synthetic observations and transport failures. They do not establish native compilation, scheduling, or platform API behavior. Native execution and independent artifact audit remain a separate gate.
