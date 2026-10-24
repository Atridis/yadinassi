# Terminal omitted arguments

Ordinary BSL routine calls now accept an explicit empty final argument. `P()`
remains a zero-argument call; `P(,)` has two omitted positions, `P(,,)` has three,
and `P(1,)` has two positions. An omitted position uses the formal's declared
default, or Undefined when no default exists. Explicit Undefined is a value and
is not replaced by a declared default. Entirely absent required formals and
excess arguments remain arity errors before argument or body effects.

Only `Parser.arguments` changes. Existing routine binding, default values,
references, and arity checks are reused. Host functions, methods and constructors
retain their existing individual omission contracts; this grammar change does
not generally enable optional host arguments. Functional `New(...)` and the
separate functional Raise grammar are unchanged. Async composition is covered
locally, not claimed as another native Async measurement.

## Audited native capture

Nine ordinary-function observations were captured through Execute on
**Linux 1C 8.3.27.1508**, in the existing functions.bsl scenario. The
[source-bound fixture](../tests/fixtures/trailing_omitted_linux.json) preserves
run, commit, tree, source/module/output and artifact digests. It records native
run [40029817101](https://github.com/Atridis/yadinassi/actions/runs/40029817101),
PR head `438d1ef25ebea7cfeb39776abb4d7fede9608dd6`, synthetic checkout
`d0f1ee7227d34607e0fbb49a8600864b70b3effc`, tree
`f1cd2282dcd40abf0b20ff2b3dd7b1702c05182a`.

The [8.3.27 Developer Guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/),
section 4.7.4.4, describes omitted positions and defaults. The finite capture
resolves terminal comma counting rather than inferring it from prose examples.

Each five-character record is success/error, argument-call count, body-call
count and a two-digit result initialized to 99. Undefined is encoded as zero
only inside the pair helper. The unchanged token is:

`omit.v1:S0112E0099S0100E0099S0152S0150E0099E0099E0099`

1. `Defaults()`: success, body once, result 12.
2. `Required()`: error, no argument/body effects.
3. `Required(,)`: success, two Undefined formals, result 00.
4. `Required(,,)`: excess-arity error, no effects.
5. `Defaults(5,)`: success, declared second default, result 52.
6. `Defaults(5,Undefined)`: success, explicit Undefined, result 50.
7. `One(Tick(),)`: excess-arity error before Tick or body.
8. `One(Tick(),2,)`: excess-arity error before Tick or body.
9. `Required(Tick(),,)`: excess-arity error before Tick or body.

Every disputed measurement call was a literal string inside Execute/Try, so
invalid dynamic calls could not prevent the outer module from compiling. No
private error descriptions or paths are recorded. The single output line is
53 ASCII characters; the existing client135, protocol schemas and size limits
are unchanged.

This diagnostic capture was complete and independently audited, but its original
interpreter comparison was **rejected**, not accepted parity. All five other
outputs and all previous functions records stayed byte-exact. Requested native
client and watchdog gates completed. No fresh Async8 claim follows from this run.

## Direct syntax witness and final acceptance

The implementation source additionally assigns `OmitProbeDefaults(5,)` directly
and checks result 52, zero argument calls and one body call. This positive literal
call emits nothing. The nine observations reset counters afterward and retain
exactly the audited token. Native compilation and full execution of this changed
source are still required: **fresh direct-source native validation is pending**.

The first-line post-create directive and declaration/routine/body order remain
intact. Functions output still has 157 records: 136 old initialization records,
the token, a begin marker, 18 old post-create observations, and an end marker.
Tests replay the complete measured and current sources against the audited full
20,380-byte output digest, not merely the token or a truncated prefix.

Historical replay has an exact hash-bound inverse from the direct witness source
to the captured measurement source (including its historical observation note),
then the original three-part inverse to the prior source. Captured source SHA256
`b1862eb7569e23e054c4abc14711a4faa53b1e26fd16212502317e592caf98a3`
and prior source SHA256
`21d53297530d86c260b75659f7fdab2e35acddf82e53ab9056f9991a4195a3ab`
remain unchanged. These inverses are never applied by live native comparison.
Frozen native output files remain untouched.

Final acceptance requires full-current-source native parity and the existing
release gates. No forms, server transfer, RPC, database or event behavior is
introduced or inferred.
