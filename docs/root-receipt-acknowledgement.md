# Explicit host-root receipt acknowledgement v2

**Experimental, opt-in host API; not automatic cleanup, not native 1C parity.**
This acknowledgement compacts only duplicated root outcome bytes. It does not
remove a receipt row, a child outcome, an operation identity, or a history epoch.
The number of retained identities remains unbounded by design: there is no
retention horizon or permission to replay an old UUID.

## Version compatibility decision

Existing v1 receipts and their exact hashes are unchanged until explicitly
acknowledged. This implementation resolves both v1 and v2. An older binary can
still refuse operation-ID reuse, but its old resolver cannot recover a v2 root:
it fails closed instead of returning absence. Do not enable this API where
recovery using the old binary must remain supported. Retaining a full v1 duplicate
would preserve that compatibility but defeat this payload compaction.

No application host invokes acknowledgement automatically. Deployment must choose
this version boundary explicitly; an accepted UI operation alone does not opt in.
Formats 11/12/14 are not admitted by this API. In particular, historical v12
receipt epochs keep their byte-for-byte contract.

## Host API and storage

For the same exact admitted host and retained operation:

```python
ack = host.acknowledge(operation_id)
# ack.version == 2; children, original_bytes, compact_bytes are diagnostic sizes.
```

The host retains its intent and root object. Unknown/foreign IDs are unavailable,
not permission to manufacture an acknowledged root. The root must hold its exact
preallocated accepted image after participant installation, with no live lease or
uncertain owner. COMMIT alone and a copied `accepted=True` envelope do not suffice.
Existing source grants are rechecked: v13 posting application and v15/v16 exact
inventory application roots. BSL/form code receives no new entrypoint or grant.

A v2 root `outcomes_json` is a canonical tagged envelope containing the ordered
kind, child UUID, intent digest and child receipt digest. Child payloads remain in
their existing tables. The root `request_hash` remains the original v1 digest.
Resolver rehydrates the exact v1 bindings from bounded child reads and checks the
same original digest, child bytes, request order and typed outcome resolvers.
It returns the original outcomes, not a new absence or acknowledged sentinel.

A document child is read only after SQL type and byte-size checks. Its revision is
materialized only as an integer using a guarded CASE expression. Generic payloads
and the root payload likewise have same-snapshot SQL size preflight. Rehydrated
payloads retain the existing transaction byte limit.

## Atomicity and recovery

Acknowledgement first resolves the exact typed outcomes. It then acquires a
normal admitted writer and compares the frozen root plus every child again under
that lock; a prior read is not cached authorization. A compare-and-update changes
only the root envelope in one transaction. The result object is prepared before
COMMIT. All child rows and collision guards remain untouched.

Before-COMMIT failure rolls back. A lost COMMIT response is reported as uncertain
for the acknowledgement, not as loss of the already accepted business operation.
Retry compares the same bindings and returns the same size result without handler
replay or rewriting an already compact envelope. Interruption preserves recovery
on either side of COMMIT. Missing/corrupt children fail closed; a v2 root never
turns into `None`. Fresh reopen resolves the original outcome from the DB alone
when the caller retained the original requests.

This is duplicate-payload compaction, not deletion-based GC or an implementation
of durable application intent storage. See `database-entrypoints-and-retention.md`
for the wider retention boundary.
