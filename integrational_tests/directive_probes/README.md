# Logical execution directive probes and captured scalar subset

These are literal managed-form source modules, not dynamic Execute fragments.
The positive client/server and scalar-copyback bodies are integrated into the
ordinary source-bound client probe. Compile-negative and state probes remain
uncaptured independent modules. PR90 async code is unchanged.

- `client_server.bsl`: invoke literal `RunDirectiveProbe` on the client after
  module creation. Eleven labeled records observe call direction, default scalar
  Val arguments, context-specific preprocessing, same-side nested calls, scalar
  results and recovery after a controlled server exception.
- `server_to_client_negative.bsl`: isolated compilation-negative case. Record
  actual compiler phase and failure, not a synthetic runtime error.
- `conditional_availability_negative.bsl`: isolated compilation of a declaration
  excluded by the server preprocessor and by the client annotation filter.
- `scalar_copyback.bsl`: future extension discriminator. Invoke `Probe` on client;
  retain both operation class and caller value after success/failure.
- `server_variable_lifetime.bsl`: future annotated-variable discriminator. Invoke
  `Probe` on client and preserve both outer-call records plus nested state.

Compile each independently. Never suppress a compile error with a BSL Try;
compile failure is not a runtime observation and must not prevent other cases.
Keep version, source hash, client/server identity, full bounded raw records and
compiler phase. Do not update historical fixtures or loosen parity. The positive
source can be run locally by appending `RunDirectiveProbe();` only as a unit test
of the proposed model; such output must never become a native expected fixture.

The ordinary client probe executes the equivalent Val/context and scalar-copyback
bodies. Host preflight independently executes the exact whole staged source;
native must satisfy the same strict 50-value contract. Historical four-client
parity adapter modules and pins remain unchanged. Temporary capture-only public
payload and shared-source preflight exception have been removed.

`scalar_copyback_core.bsl` supplies twelve operations and 34 ordered records.
`scalar_copyback_core.native.json` stores the independently audited bounded
observations and exact source/tree/run/summary ZIP provenance, not generated
interpreter predictions. The capture itself intentionally failed old acceptance;
a new runtime/native PASS remains necessary. Its platform8.3.27.1508 target and
the official-guide discrepancy are documented in
`docs/scalar-copyback-measurement.md`. Negative/future modules above are not
included in this scalar acceptance claim.

## Object-transfer capture and strict parity

`object_transfer_core.bsl` contains nine direct client/server calls and58
observations captured on the pinned8.3.27.1508 target. The independently audited
fixture `object_transfer_native.json` binds labels/values to run39961116549,
artifact ZIP digest, source/module hashes and exact repository tree.
The full original staged source now executes in our interpreter and must match
the same109 typed values checked by native. Capture-only diagnostics and the
host shared-source inverse are removed. Four historical client adapters remain
byte-identical. Current-head native and CI gates are still required.
See [object-transfer-measurement.md](../../docs/object-transfer-measurement.md).
