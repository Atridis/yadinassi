# Direct Execute / Выполнить

Implemented on base `c8999470fd057d229ea48586ceb8fccc2d1e4151`. Dynamic statement
text is fully parsed with the existing `parse_fragment`, admitted against current
constructor/routine bindings, and compiled to Python before fragment effects.
There is no VM dispatch or legacy fallback.

Existing module storage is addressed directly. Routine locals and parameters use
compiler-generated getters/setters, including live byref addresses; there is no
copy/flush of values. The set of visible existing names is captured on entry.
New names live only in the fragment's private dictionary. Nested fragments can
address their parent's names but cannot leak new names back. Writes before an
escaping runtime error remain; parse/compile failures produce no fragment effects.

Exact string/Undefined admission, the existing 65536-character and 16-level limits,
fragment declaration/directive restrictions and control-flow boundaries remain.
Source and schema/transaction checks use the current execution boundary. Query and
finite JSON/regex capabilities remain subject to their existing checks. No new
SQL writer or transaction bypass is introduced.

Host Reference reads/writes have checks immediately before and after callbacks.
Forwarded source-name provenance is preserved, so a property/index forwarded
through Execute cannot become an authorized server copyback sink. Fragment-owned
references retire when the fragment exits and cannot revive on a later execute.
These two lifecycle cases were found in independent review, fixed, and retained
as regressions. This remains the trusted direct backend, not a Python sandbox.

## Verification

- 219 selected tests PASS on Python3.12 normal and Python3.10 `-O`.
- `tests/test_python_direct_execute.py` covers source/AST/prepared routes with VM
  block/call disabled, locals/module/byref, nested/private storage, callbacks,
  restricted context, stale references, argument omissions and owned SQLite Query.
- Independent review covered focused Execute/regex/DB/live-state tests, original
  fragment tests and comparative direct/legacy probes; both lifecycle findings
  were rechecked and closed. `regex_binding_released_without_cyclic_gc` still passes.
- Existing `tests/test_execute.py`: 15/20 pass. Five remaining tests encounter
  unsupported imports/Goto/Label, direct Structure serialization, or expect
  catchable BSLError where an unregistered host service is fail-closed
  BoundaryViolation. Those tests and restrictions were not relaxed.

The original whole `client_probe.bsl` now compiles and executes its client
initializer. Its real owned-SQLite child completes with exit0 and no stderr:
81 records,1142 bytes; the unchanged verifier expects138 records and still fails.
First50 records match exactly. The object section still emits
`object.runtime-error`, stage8, instead of59 observations (the previous
TypeOf/direct Structure gap). After aligning section boundaries for diagnosis,
the remaining difference is Date/Null graph token `dn.v1:22222288` versus
`dn.v1:22222277`. Dual, infobase arity and preprocessor tokens match. This diagnostic
alignment is not used by the unchanged strict gate; native parity is not claimed.

[Reproducer](https://github.com/Atridis/yadinassi/blob/713fb157cac984d8918681524848efa5f64f6b70/experiments/direct_execute/replay.py) and
[exact observed report](https://github.com/Atridis/yadinassi/blob/713fb157cac984d8918681524848efa5f64f6b70/experiments/direct_execute/result.json) record the
source/output hashes and differences. Native source and expected fixtures are unchanged.

Run this historical reproducer from [its archived source checkpoint](https://github.com/Atridis/yadinassi/tree/713fb157cac984d8918681524848efa5f64f6b70).

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_execute test_python_direct_regex_services test_python_direct_error_description test_python_direct_server_byref test_python_direct_managed_profile
python experiments/direct_execute/replay.py
```
