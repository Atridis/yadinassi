# Infobase connection context: historical measurement and strict runtime contract

The original measurement was captured and independently audited in
[run 40137786320](https://github.com/Atridis/yadinassi/actions/runs/40137786320),
at commit `1d220ded50a6c2afa458b248bbaa66b3d53cd8db`. Its original
`infobase_context_measurement.json` is preserved as the pre-capture design, with
its then-unknown expectation still null. The separate
`infobase_context_native.json` records the observed token, source/module pins,
artifact identities and evidence limits. It does not retroactively change the
measurement into an implementation test.

The current bounded runtime and optional CLI context are documented in
[file-database-context.md](file-database-context.md). Current native admission
requires the entire original 137-value source and the captured exact token;
the historical 136-value inverse is not runtime admission.

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
exact JSON type and value, and the last equals the independently captured token
`ibc.v1:121122221122021122021122021122`. During the historical measurement only,
the last value was admitted by the finite grammar above. An omitted, changed, malformed, partial or oversized tail cannot pass.

The historical measurement used shared-prefix parity: an exact inverse restored
and executed all 136 old values because the new API did not yet exist. Current
host preflight instead executes the **unchanged whole137 source** in a bounded
Linux child with real `FileDBContext` and read-only `inspect_header`. No builtin
callback is substituted and no BSL source is rewritten. The 136-value constant
and exact inverse remain only for legacy adapters/history; the four legacy
module hashes and all eight literal Async identities remain unchanged.

The host exclusively creates `/tmp/onec-smoke` with mode 0700. Any pre-existing
pathname causes immediate failure without reading, reusing or removing it.
Pinned descriptors and identities guard an owned `db/1Cv8.1CD`, containing only
a bounded recognized synthetic header/layout. Exact content, link count, source
bytes and ownership are rechecked around the child. Only verified owned files
and empty directories are removed; uncertainty prevents success and cleanup.
This is a trusted single-job Linux test-host contract, not atomic isolation
against a malicious same-UID/root process. There is no lock/reuse fallback.
A bounded non-reaping child-exit observation preserves PID ownership through
process-group shutdown, then performs bounded reaping before fixture cleanup.

The optional `client_probe.infobase_context` field is accepted only for this
exact source/module, full existing proof, successful stage and captured exact
token. A merely grammar-valid observation is no longer runtime acceptance. It is mandatory
for such a successful ordinary measurement, forbidden on other records, and
discarded on later input, process, stage, export, host or cleanup failure. The
discard never rewrites older proof fields or promotes a failed status. Existing
six-case outputs, typed136 expectations, source inventories, comparison modes,
caps and publication classes are not relaxed. Historical capture alone remains measurement evidence. Runtime acceptance
requires the original whole137 preflight with real context as well as fresh
native lifecycle and comparison gates.

## Offline bounds and verification

The existing native JSON writer remains compact, without a fallback. The full
marker model includes the complete prefix, nonce and metadata, not just token
bytes. Private raw native marker bytes were not separately exported; the capture
audit verifies their source-bound producer and finite report evidence. Tests also
exercise the real stage codecs, production host validators and pretty CLI
report serializer with all optional-lane combinations. They include 32 parity
subsets, 80 successful Async paths, 240 client-failure partitions, 192 server-
failure partitions, 32 early-failure subsets, and the 18 unchanged Async
structural majorants. Failure size models use an explicit arithmetic overhead,
never a capture forbidden by validation.

Conservative upper models remain below unchanged caps: 8,043/8,192 stage wire
bytes and 32,228/32,768 pretty summary bytes. The parity wire bound is 8,015;
schema 2 without numbers is tighter than the all-options schema 3 case. These
are offline bounds, not native observations. The original native capture and independent
source/nonce/module/roundtrip/lifecycle audits preceded the runtime expectation.
Fresh runtime admission must still pass independently for each candidate.

## Bounded implementation, not a native database session

See [file-database-context.md](file-database-context.md) for actual `--f` modes,
lazy execution, immutable context propagation, fixed unsupported-auth errors,
path scope and deferred CF/DT commands. Recognized physical header geometry is
not proof of native database validity, authenticated user identity or a session.
The Linux capture does not establish native Windows function return formatting.
