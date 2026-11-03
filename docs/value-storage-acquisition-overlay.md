# Temporary ValueStorage acquisition overlay

This is an unexecuted temporary replacement of the `format-numbers-v1` lane.
The copied baseline has index tree `ded4ba4e052984dcf07856029b74f182ed9e209d`.
It does not claim a native observation or runtime compatibility. Do not publish,
run native/CI, or treat synthetic outputs as native evidence without separate
coordination. Restore the original lane, all temporary tests, and the original
contract after acquisition while preserving immutable capture and provenance.

The 27 fixed cases plus calibration exercise scalar round trips, original and
Get-result mutation, repeated Get, aliasing by mutation through shared children,
fixed collections, a table, compression, ordinary arity/type boundaries,
positive dynamic-evaluation controls, and a nested storage. A cycle is not in
this overlay: it is a separate risky source-only experiment requiring a
separately isolated process. Types and API availability depend on platform,
client/server context, and compatibility mode. Preserve all those details.

The original UTF-16 Format transport is replaced by a bounded, fixed-alphabet
ASCII protocol; each case has a separately enumerated payload and allowed stage
errors. `construct`, `get1`, and `get2` errors are separate observed action
outcomes; setup, mutation, inspection or observer failures reject acquisition.
Controls 01–04 must each produce `ok|1`; case 23 must produce `ok|A`, proving
both dynamic constructor and dynamic Get were successfully evaluated. Exactly
28 LF-terminated messages are required. The rectangular output bound is 854
bytes; the enclosing host's existing 8192-byte bound is not raised. Strict
source, staging, module and output identity remain mandatory. No exception text
or native results are predicted or disclosed.

The original client wrapper placed source module variables after helper
procedures, which is invalid here. For this exact source-hash-bound profile only,
the wrapper moves the unique `Перем VSPhase;` to the module prefix with
`&НаКлиенте`, verifies the inverse move, and captures the helper's print sites.
Other profiles follow their existing path. Both server and client stage validation require availability, and the host revalidates it before accepting or exporting; interpreter parity remains a separate gate. This does not establish real-client
availability; verify actual managed/thick mode and platform compatibility in
provenance. The historical Format capture tests use an immutable source prefix
and an unchanged copy of the old wire contract while this overlay exists.

## Proposed local checks, pending authorization

One targeted command, 90 test methods across eight modules; fixed wall-clock
budget 120 seconds. Historical timings for the matching old test inventory sum
to about 24 seconds, excluding new test methods and unknown execution overhead;
this is an estimate, not a measurement of this overlay. A timeout is a failure,
not a pass. Do not execute until approval:

```
PYTHONPATH=tests:. timeout 120s python -m scripts.run_tests \
  test_native_format_numbers_measurement test_native_format_numbers_profile \
  test_format_numbers_runtime test_format_extended_runtime \
  test_native_tree_profile_budget test_native_tree_profile_bootstrap \
  test_native_tree_profile_host test_native_tree_emitter_dispatch -v
```

The 90 count is the number of statically declared `test_` methods, including
possibly skipped methods; runtime discovery must confirm the actual count.
Native capture and CI are outside this local-check authorization.
