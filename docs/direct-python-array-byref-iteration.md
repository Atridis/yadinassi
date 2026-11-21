# Array and source-reference iteration

Built after c69ca915. This remains a breaking direct-backend Draft, not a full
compatibility or sandbox claim. It does not restore the previous VM runtime.

## Source by-reference arguments

The compiler creates one Python-local slot-address object per static module
name and invocation. Source calls reuse that address. Every binding still checks
that the name exists and whether its current value is a canonical Reference;
canonical forwarding is not cached. No value snapshot, shared cache or generic
lookup table is added. Separate module invocations have separate address objects.
See [measurements and counterexamples](python-direct-cached-source-refs.md).

## Trusted embedding limitation

Compile-time facts assume host objects do not use finalizers to mutate the module
dictionary between ordinary Python instructions. An injected object's __del__
can run after replacement and rewrite that same slot, defeating both scalar and
array facts. This is explicitly unsupported, not protected by a per-store guard
or a scan of the object graph. Registered host callbacks remain supported and
invalidate facts according to their actual evaluation order.

Ordinary direct list/dict/Decimal and direct Map/Structure storage has no such
finalizer. A source scan found five explicit project __del__ methods in
binary_streams, file_io, http_client, json_processing and xml_writer. They close
resources and do not themselves write module dictionaries. A custom embedded
stream/close implementation can still have arbitrary effects; this is not a
proof that every possible host object is harmless.

Existing Python 3.10 source-position incompatibility, unsupported application
contexts and prior default-backend compatibility gaps remain. Focused checks and
synthetic benchmarks do not establish full native-1C or application parity.

## Arrays

[The array proof](direct-array-specialization.md) removes generic receiver dispatch
for known list operations and uses native list indexing for statically bounded,
nonnegative integer indexes. Huge or otherwise unproved Decimal indexes retain
the original comparison-before-int check. Native bounds still apply. Facts are
invalidated between effectful receivers/arguments, not merely after a statement.
No alias graph or hidden VM fallback is introduced. Unknown cases use the same
existing direct dynamic operations. Routine bodies and complex control flow are
not specialized by this first pass.

## Exact combined checks

112 focused tests ran: 111 passed, one failed because native list indexing now
reports `list index out of range` instead of the old Russian text. The failure
is `NakedErrorIntegrationTests.test_exact_source_errors_and_partial_effects`;
exception class and BSL location remain the same. The old exact-wording assertion
is left visible, not rewritten to conceal the intentional difference.
Inventory 358 is verified, with the new analysis module in byte-drift probes.

A clean combined source `85f14191` ran the default public triplet harness for
10,000 iterations and three rounds; all 45 timed controls matched. Median ms,
native Python / classes / BSL: arithmetic 2.331 / 12.052 / 5.603;
calls 1.999 / 10.438 / 6.558; byref 1.182 / 6.946 / 7.161;
array 1.818 / 11.236 / 9.907; map 6.309 / 15.711 / 22.574.
This short combined run is not a paired speedup claim. Public execution includes
its repeated lowering/compile cost. Raw source hashes, setup/first execution and
samples are in [`experiments/array_byref/default-triplet.json`](https://github.com/Atridis/yadinassi/blob/713fb157cac984d8918681524848efa5f64f6b70/experiments/array_byref/default-triplet.json).
