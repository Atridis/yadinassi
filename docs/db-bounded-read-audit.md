# Bounded SQLite read audit

This checkpoint optimizes admitted local SQLite reads, not native 1C parity.

* Document header/section references and accumulation movements use per-operation
  catalog existence batches. Queries retain catalog filters and quoted physical
  layouts; chunks are bounded by 256 and SQLite's actual variable limit. Missing
  entries are not trusted. Ordered decoders still choose the observable error;
  speculative prefetch skips malformed JSON, including recursion overflow.
* Constant `get_many` exhausts its host iterator before choosing transaction
  ownership, admits schema once inside the resulting snapshot, and fetches values
  in bounded chunks. Name, missing-value and codec errors remain ordered. No
  handler or authorization path is granted a persistent admission cache.
* Scalar catalog reference getters admit the whole selected record (including
  section integrity) on a cold read, without materializing its object. Warm reads
  select only requested fields. Existing snapshot/source/schema/data invalidation
  expires the proof. `GetObject`, legacy/hierarchy paths, writer restrictions and
  explicit transaction transfer boundaries are unchanged.

Targeted evidence: repeated 256 document lines formerly performed 257 catalog
existence SELECTs, now 2; movement references formerly 512, now 2. Constant batches
of 16/64/256 names each perform one schema admission and one value SELECT. These
are focused tests and trace measurements, not full CI or Enterprise parity.

## Receipt retention follow-up

Receipt garbage collection is not implemented here. A root acknowledgement must
follow accepted outcome installation, not merely successful COMMIT. Deleting a
root receipt would permit operation-ID reuse and break replay protection. A future
cleanup therefore needs an atomic compact tombstone plus validated child cleanup,
crash/recovery tests, and compatibility with immutable history receipt bindings.
No current receipts or historical fixtures are removed by this checkpoint.
