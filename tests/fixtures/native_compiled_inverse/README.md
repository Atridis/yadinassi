`native_async_comparison.py.txt` is the exact byte sequence of
`scripts/native_async_comparison.py` in commit
`6633dba58b9ad5f38f2eae816205c8fea1a6af8a` (blob
`8cc5a165c036461af5f3d54fd9873e13c2c97365`). It is historical test input only;
it is never imported or executed. Its SHA-256 is verified against the existing
candidate pin in `tests/native_compiled_source_inverse.json`.

The full-host and smoke candidates can still be recovered using the existing
exact test-only source inverses. The current async harness no longer contains
the retired compiled-backend instrumentation, so its candidate must come from
this historical snapshot.
