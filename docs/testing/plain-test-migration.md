# Retired plain-engine test migration

This migration changes tests only. It does not restore `compiled_backend`,
`plain_routines`, `plain_modules`, the compiled-strict adapter, or a fallback.

## Product behavior retained

- `test_whole_routine_differential.py` now contains `WholeRoutineBehaviorTests`.
  Despite the historical filename, there is no differential oracle. Constants
  independently specify arithmetic, strings, scalar expressions, branch/loop
  results, bounds and counter mutation, byref aliases, collection writeback,
  optional arguments, procedures, host effect order, module variables,
  Execute/Eval, server copyback, prepared snapshots and routine redefinition.
  Public execute and prepared execution are both checked, with an explicit
  `python-direct` backend assertion. No old-engine option is supplied.
- `test_plain_module_entry.py` checks public direct-module results, partial state
  after an error, bounds, control flow, lazy expressions, declarations, Try,
  repeated prepared execution and state visible to a host callback.
- `test_plain_hostile_eligibility.py` retains foreign-metaclass non-observation
  and foreign-literal rejection before source effects. Live permission checks
  are now tested through `ConfigurationApplication.check_call` and
  `check_host_service`, including revocation after a warm call and revocation
  during a callback. No security assertion is replaced by interpreter parity.
- `test_plain_fixed_map.py`, `test_plain_table_storage.py`,
  `test_plain_value_list.py`, `test_plain_value_table_runtime.py` are unchanged:
  those storage implementations still exist.

## Removed implementation-only coverage

The following retired files' product cases are covered by the three migrated
suites above; their deleted implementation assertions concern unavailable
engines, not requirements for the new direct runtime:

| Retired file | Removed machinery |
|---|---|
| `test_plain_calls_research.py` | Plain tail-call adapter counters/live adapter locals |
| `test_plain_control_research.py` | `lower()` generator/prefix plan flags and injected yields |
| `test_plain_module_dispatch.py` | Optional module admission, shared old-source budgets, plan registries |
| `test_plain_prefix_activation.py` | Injected suspension into old `call_routine` generator; live authority checks migrated |
| `test_plain_prefix_research.py` | Prefix/suffix adapter selection and already-admitted old nodes |
| `test_plain_procedures_research.py` | Plain-option execution counters |
| `test_plain_routine_research.py` | Plain-option inheritance, optional cache/source budgets, old compiled hooks and trace mutation of adapter-local dictionaries |
| `test_plain_scalars_research.py` | Old optimized-vs-adapter selection counters |
| `test_plain_segments_research.py` | Resume gates, scope snapshots, hostile private cache keys/descriptors, segment counters |

Old private `vm.locals` mutation through a synthetic suspended adapter is not
recreated. Supported host-visible module state is checked explicitly. Boolean-counter rejection, conditional local shadowing of a module counter,
and conditional backward Goto remain explicit product tests, separate from
removed eligibility decisions. Existing relevant product suites remain in place.

## Visible gap

Product cases still require their independently specified results, including
async/await (promise result 5), conditional backward Goto, module-counter
shadowing and Boolean-counter rejection. Unsupported or divergent behavior
fails explicitly in these named tests. There is no
skip, expectedFailure, broad exception capture, or fallback to hide this gap.

Decimal division assertions use the documented native BSL division scale and
check isolation of the host Decimal context, rather than erroneously treating
ambient Python precision as the script's precision.
