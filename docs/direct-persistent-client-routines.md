# Persistent direct client routines

Baseline: `e5cb5a688f952db6fe480a1448160b2249a1b868`.

The real native client verifier loads its module and then separately executes
`ВычислитьПробу()`. Direct execution previously rejected even the client-only
version of this load/call pattern. It now stores generated declaration code,
using the existing routine-export compiler mode. Each execution binds fresh
Python functions to current globals, host registrations and the active boundary;
no closure, VM activation or admission grant survives that execution. Module
statements and Var initialization are not replayed when binding routines.

Supported client calls retain byref copyback (including partial effects on error),
trailing defaults, recursion, current global state and definition source positions.
Prepared declarations own their AST snapshot and can bind to another compatible
interpreter. Separate modules resolve later routine replacements through the
current registry. Original same-module calls remain direct Python function calls.
Arity is checked before argument effects; prospective declaration/layout changes
are checked transitively before publication or module effects. No VM block or
call_routine dispatch is used.

## Actual progress and limits

The unchanged regex_family.bsl completes all 42 records under managed-thick-file.
Subsequent separate execution of `RFObserve(7);RFObserve(22);` adds two records
identical to original records 8 and 23 (zero-based indexes). This is a real source
load/reuse check, not a native parity assertion.

The exact full six-scenario verifier still raises `interpreter_failed` with zero
witness records: server declarations remain the first rejection. Server routines,
NoContext, dual execution, server initialization, transfer/copyback across server
calls and configuration ownership are **not implemented by this change**. The
original fixtures were not modified. Other prior constructor/Execute gaps remain.

Explicit limitations: omitted argument holes such as `F(,2)` still reject;
trailing defaults work. Changing profile, target or global-name layout requires
redeclaration. Replacing only part of a set of routines declared together requires
redeclaring that set; otherwise old lexical sibling calls would silently use old
code. These checks apply before effects for statically visible calls, and again
at resolution for live host changes. This is not a long-lived admission cache.

Isolated unchanged CatalogObject replay remains 156 bytes,
SHA256 `5a94916806539bfdd40517a7092b3a543ea6dc53d52f0f0cedbd8d37ba3b23f4`;
managed-form remains 541 bytes,
SHA256 `3cbf5b2e8dee544690cd560f3405ab9029dfd3e0d711b2410c59ba288d8acb34`.
Both children exit 0; this does not establish native comparison parity.

## Validation

117 targeted tests pass both normal and with `-O` on the final code. Reproduce:

```sh
PYTHONPATH=tests:scripts:. python -B -m unittest \
 test_python_direct_persistent test_python_direct_default \
 test_python_direct_prepared test_python_direct_prepared_admission \
 test_python_direct_configuration test_python_direct_database \
 test_experimental_naked_boundaries test_python_direct_managed_profile \
 test_python_direct_form_invocation
```

Independent review reproduced and closed arity-before-effects, prospective
registry/layout, and indirect HostFunction call regressions. Its 75 combined
optimized tests plus three focused final checks passed. Actual Python 3.10 also
passes the 20 persistent/admission tests with `-O`.

## Cost

Sources containing routines now compile an additional declaration export plan.
This is a functional support change, not a speedup. Prepared execution reuses both
code plans without parsing or compilation. Each later execution creates fresh
closures lazily on the first call to a stored module, then discards them.

Paired cold measurement on Python 3.12.14: five alternating before/after processes,
three fresh Interpreter + execute + close operations per process, unchanged
`integrational_tests/measurements/regex_family.bsl`, output sink `lambda x: None`,
managed-thick-file, elapsed perf_counter around the three operations divided by 3.
All validation processes were finished before this measurement. Baseline is the
commit above, candidate is this patch. Per-operation milliseconds:

| Pair | Before | After |
|---|---:|---:|
| 1 | 455.31 | 883.62 |
| 2 | 424.87 | 850.30 |
| 3 | 477.41 | 836.57 |
| 4 | 425.69 | 853.27 |
| 5 | 441.68 | 933.95 |

Medians: **441.68 → 853.27 ms (+93%)**. This includes parsing/compilation and
module execution, excluding interpreter process startup/import/source read. No
warm-speed claim is made; eliminating duplicate compilation is future work.
