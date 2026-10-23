# Logical execution directive measurements (not captured)

These are independent managed-form module sources for a future explicitly
reviewed native runner. They are not dynamic Execute fragments. Nothing in the
current trusted launcher, CI inputs, expected outputs or PR90 async harness was
changed to execute them. No source here is accepted native evidence.

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

The automated ordinary client probe now carries an equivalent eleven-observation
positive witness in `scripts/native_1c_bootstrap/client_probe.bsl`. The host
independently executes that exact form source through the interpreter before the
native invocation. Both must satisfy the same finite typed contract. Existing
client proof and four client parity scenarios remain intact; no async branch or
new runner is used. See `docs/execution-directives.md` for source binding and the
strict inverse that preserves the original parity template. Negative/future
modules above remain independent measurements, not part of this positive gate.
