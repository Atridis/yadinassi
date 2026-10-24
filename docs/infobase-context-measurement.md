# Infobase connection context: bounded measurement only

Status: local measurement candidate. Native execution and its independent audit
are pending. There is **no expected native token** and no new interpreter API,
CLI option, database session, authentication, or native runtime dependency.

The primary-source [1C release notes](https://downloads.v8.1c.ru/content/Comm/Platform/8_0_17_25/V8Update.htm)
establish the Russian global method's existence and purpose. The official
[administrator guide](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.24_Administrator_Guide/Appendix_7._The_parameters_of_the_command_line_to_launch_1C_Enterprise/7.3._General_startup_commands/7.3.1._Connection_parameters/)
refers to `InfoBaseConnectionString()` as the returned connection-string form.
These are not evidence of exact current formatting or the complete directive
availability matrix. This probe measures those narrow facts on the pinned
Linux/amd64 8.3.27.1508 managed thick client, not other platforms or clients.

## Direct calls and finite observations

The existing managed-form client probe appends one independent 37-byte ASCII
token after the entire unchanged strict136 prefix. It directly calls both
zero-argument aliases in `&AtClient`, `&AtServer`, `&AtServerNoContext` and
`&AtClientAtServerNoContext` routines, exercising the dual routine from both
sides. The ordered slots are client, server, no-context server, dual client,
dual server. Compilation or a failed lifecycle remains failure; catchable
direct-call errors are observations, not proof of positive availability.

Each six-digit slot encodes:

1. Preprocessor profile: AtClient bit 1 and AtServer bit 2, range 0..3.
2. Direct-call status: 1 caught error, 2 both results String, 3 non-String.
3. English string shape: 0 neither candidate, 1 exact
   `File="/tmp/onec-smoke/db";`, 2 the same without the final semicolon.
4. Alias equality: 0 false, 1 true.
5. English one-argument dynamic call: 1 returned, 2 caught rejection.
6. Russian one-argument dynamic call: 1 returned, 2 caught rejection.

For status 1 or 3 the last four digits must be zero. For status 2 the arity
digits must be 1 or 2. The token is `ibc.v1:` followed by five such slots.
No raw connection string, directory, exception text, credentials, or identity
is exported. Only internal comparisons use the known synthetic directory.
The actual `Platform.database` must equal that directory before native build.

Arity is deliberately dynamic: `Execute(text)` runs inside the dual no-context
observer on the same execution side. It does **not** establish arity or Execute
availability separately for each originating directive, nor static compiler
diagnostics. Every local, including `IBCArityTemporary`, is explicitly declared.
Exotic quoting, semicolons in paths, symlinks and arbitrary path normalization
are excluded; the initial question is one ordinary absolute directory only.

## Source binding and unchanged evidence

`infobase_context_measurement.json` pins the core, complete literal source,
generated BOM module and strict136 baseline. The native client executes the
complete new literal source. Its round-tripped module must match exactly.
Entered/completed marker identity, schema, nonce and witness remain strict.
The completed marker must contain exactly 137 values: the first 136 match by
exact JSON type and value, and the last independently satisfies this finite
grammar. An omitted, changed, malformed, partial or oversized tail cannot pass.

Host interpreter preflight is explicitly **shared-prefix parity**, not whole-new-
source parity. A uniquely exact inverse first checks the entire candidate hash,
removes exactly one pinned core and call, then verifies the complete historical
strict136 hash. That entire restored source executes in the bounded child; both
its temporary bytes and the staged candidate are rechecked. The interpreter
does not implement the proposed function and cannot supply its expected result.
The four legacy parity adapters use the same exact inverse; their generated
module hashes and all eight literal Async source identities remain unchanged.

The optional `client_probe.infobase_context` field is accepted only for this
exact source/module, full existing proof and successful stage. It is mandatory
for such a successful ordinary measurement, forbidden on other records, and
discarded on later input, process, stage, export, host or cleanup failure. The
discard never rewrites older proof fields or promotes a failed status. Existing
six-case outputs, typed136 expectations, source inventories, comparison modes,
caps and publication classes are not relaxed. A successful collection is still
only a measurement, not a claim that the new API has runtime parity.

## Offline bounds and verification

The existing native JSON writer remains compact, without a fallback. The full
marker model includes the complete prefix, nonce and metadata, not just token
bytes. Actual native marker bytes remain unmeasured until capture. Tests also
exercise the real stage codecs, production host validators and pretty CLI
report serializer with all optional-lane combinations. They include 32 parity
subsets, 80 successful Async paths, 240 client-failure partitions, 192 server-
failure partitions, 32 early-failure subsets, and the 18 unchanged Async
structural majorants. Failure size models use an explicit arithmetic overhead,
never a capture forbidden by validation.

Conservative upper models remain below unchanged caps: 8,043/8,192 stage wire
bytes and 32,228/32,768 pretty summary bytes. The parity wire bound is 8,015;
schema 2 without numbers is tighter than the all-options schema 3 case. These
are offline bounds, not native observations. Native capture and independent
source/nonce/module/roundtrip/lifecycle audit are required before deriving any
expected result or implementing a runtime function.

## Later runtime proposal, not implemented here

If the native result supports the bounded feature, optional `--f` would configure
a standalone read-only file-DB context using the existing header validator.
That means an explicitly configured physical attachment, **not** a platform
session, authenticated user or proof of logical DB validity. No file writes or
invented user identity are implied. The initial path subset must remain explicit.

Running without a database must preserve script, `-c`, stdin and console modes
and the default root AtClient profile. Only an actually executed DB operation
would raise catchable `BSLError("db required for further code execution")`;
unexecuted branches must not fail. Unsupported `--user`/`--psw`, including normal,
`=value`, empty and missing-value forms, must fail explicitly without echoing
secrets. CF/DT load/dump belong to future separate real subcommands, not stubs.
