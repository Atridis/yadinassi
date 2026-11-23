# Exact whole-client replay on the direct backend

Base `e00be58fa8b455f0247f382a8b24fcba7ec82edb` completed the original client
witness but emitted81 of138 records. Object transfer stopped at stage8 and the
Date/Null graph token ended in88 rather than77. This slice addresses two measured
causes without changing the native source, fixtures or strict verifier.

## Canonical TypeOf for direct collections

The direct service boundary maps exact `list`, `_DirectStructure` and `_TypedMap`
representations to the existing Array/Structure/Map type descriptors. Other values
still use canonical TypeOf. Plain dicts and subclasses do not acquire a type by
resemblance. The public canonical `type_of` API is unchanged; this is not a
conversion to BSLArray/BSLStructure/BSLMap and does not copy collections.

Only the frozen original function identity gets this adaptation, including aliases.
Custom host implementations stay custom. Current boundary policy, HostFunction
metadata and owner checks remain. Mutation of the bound implementation during
argument effects fails closed. No VM dispatch is introduced.

This resolves object-transfer stage8 and the Date/Null graph difference. The
original source then emits138 records, with three remaining mismatches at zero-based
indices89,100,103 caused by argument timing.

## Named Val arguments across the logical server boundary

For client→server calls, a syntactic name (including grouping) retains its address
until all argument effects finish, even for a Val formal parameter. The value is
then read into the existing transfer packet. Expression results, including property
and index expressions, keep their already evaluated values. Val parameters still
have no copyback. Same-side call lowering is unchanged.

This is a private capability on direct cross-side bindings, not a general change
to host calls. Each late reference read has pre/post boundary checks. Existing
copy budget, depth, independent copies, byref sink provenance, output validation,
transaction controls and owner lifetime remain unchanged. No scalar transfer fast
path or unrelated performance work is included.

## Results and limits

- 228 selected tests PASS on Python3.12 normal and Python3.10 `-O`.
- Independent review:52 focused optimized tests PASS, no blockers.
- The unmodified `verify_client_interpreter` passes with the genuine owned SQLite
  fixture and original whole client source:138/138 observations, exact output bytes.
  Both managed-thick-file and standalone/preprocessor-measurement modes passed.
- [Reproducer](https://github.com/Atridis/yadinassi/blob/713fb157cac984d8918681524848efa5f64f6b70/experiments/direct_native_types/replay.py) and
  [report](https://github.com/Atridis/yadinassi/blob/713fb157cac984d8918681524848efa5f64f6b70/experiments/direct_native_types/result.json) record source/output
  hashes, expected hashes and zero differences for both profiles. Fixture modes
  must run sequentially; an overlapping diagnostic attempt produced
  `fixture_collision` and was rerun successfully after the other jobs ended.

This is local exact replay of the bounded whole-client witness, not a new run of
1C, proof of arbitrary native compatibility, or a green full CI claim. Broader
`test_type_values` remains red (26 errors/2 failures in the independent check,
versus baseline30/2), including other constructor/presentation/collection gaps.
Source, schema and transaction gates were not relaxed. Errors/boundaries modules
and the parallel lazy-error performance candidate were not modified.

## Current Light CI coverage

Every Light platform discovers `test_pinned_sqlite_client_output_matches_exactly`.
It runs the byte-pinned managed-thick-file client witness against the same
embedded SQLite bytes in a private temporary directory, checks the exact
138-value JSON result, and requires the source and database bytes to stay
unchanged with no SQLite sidecars.

Linux Light additionally runs the original, unmodified
`verify_client_interpreter` in **Verify strict Linux-owned SQLite client
replay**, before it can produce a partition report. This also verifies the
owned fixed namespace, process census and cleanup; a failure blocks Light and
the exact-source verdict. The portable test does not substitute for or claim
those Linux-specific checks. The portable witness remains a normal required discovery ID on every
platform; no skip or platform exception was added to partition coverage.

Run this historical reproducer from [its archived source checkpoint](https://github.com/Atridis/yadinassi/tree/713fb157cac984d8918681524848efa5f64f6b70).

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_native_types test_python_direct_server_byref test_python_direct_regex_services
python experiments/direct_native_types/replay.py
```
