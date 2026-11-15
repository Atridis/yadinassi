# Measured local/file-mode common-module server reuse

Native 8.3.27.1508 run 43165393593 measured one file-mode application. Server
refresh and client refresh invalidate the same subsequent values. Two server
calls inside one client event share DuringRequest values; the next real event
starts a fresh request lifetime. These observations do not establish independent
client/server-process caches, server pools or remote cache invalidation.

Consequently reusable server modules are admitted only by side=None local
applications. Explicit split client/server applications refuse this metadata.
Both logical sides use one application-owned session cache/epoch and outer
scheduler request cache; unrelated apps and scheduler families remain isolated.
Qualified server-only and ServerCall functions reuse values. Unqualified calls
remain uncached. Server reusable functions require explicit Val parameters,
no defaults, and primitive scalar arguments/results. Global, dual-side, async,
privileged modules, procedures and collection transport stay closed.

The existing logical crossing still performs copy-in/out and transfer admission.
Warm hits cannot bypass transaction transfer checks. Failures do not publish
entries, refresh epochs reject stale publication, and request cleanup remains in
the outer synchronous scheduler boundary. No InvocationPort change is included.

The retained native fixture includes source hashes, output digest, summary,
provenance and artifact checksums. Its host verified nonce binding; raw nonce is
not exported by the source-bound host. Source replay and negative admission tests
must pass on these implementation bytes before this block is published.
