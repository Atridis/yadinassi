# Removing the retired direct-AST text oracle

Test-only migration. No runtime changes, fallback, skips or expected failures.
The obsolete `direct_ast_text_oracle.py` helper is no longer shipped.

## Independent checks

- Constructor, callable, dynamic construction, omitted-argument, external-name,
  native-method and extended-Raise cases now specify values, diagnostics and
  callback order explicitly. JSON content is checked structurally, not by
  imposing new whitespace requirements. Raise uses its functional syntax and
  independently checks metadata and argument evaluation order.
- Complex-index and static-module cases specify partial state, error sites,
  finalizer/callback observations and arithmetic results directly.
- Routine table/list loops specify independent counts/sums, recursion results,
  zero-trip behavior and state after partial failure. Removed gate-count
  assertions referred to the old host BSL collection representation, which no
  longer implements these native collections.
- Core code-generation checks retain source ownership, original source error
  locations, owner/policy revocation, host references, compile audit denial,
  asymptotic emission counts and unsupported-before-effects. Pure-AST versus
  roundtrip code-position equality is still meaningful: both are current
  compiler entry points, and this check is about code structure, not an oracle
  for product behavior.
- Exact operand/key temporary lifetime previously compared only two emitter
  implementations, with no independent language requirement. These cases now
  require one release, correct native operation result, and fatal owner closure.
  The separately explicit pre-handler argument-destruction assertion in native
  method tests remains strict and visibly fails where the runtime differs.

## Removed duplicate discovery

The old 770-line omnibus mixed differential-only language matrices with genuine
code-generation tests. Duplicate oracle-only matrices are not replaced with a
second direct compiler as a behavioral oracle. Existing independently asserted
suites remain in normal discovery:

| Behavior | Existing independent suites |
|---|---|
| Routines, branch/loop control, defaults, byref, procedure effects | `test_whole_routine_differential`, `test_direct_ast_native_cells` |
| Array/map methods, construction, index writes | `test_direct_ast_plain_array`, `test_direct_ast_plain_map`, `test_plain_fixed_map` |
| Structure schema/property output/reference writes | `test_direct_structure_literal_schema`, `test_direct_table_property_transfer` |
| Table/list graph and storage semantics | `test_plain_table_storage`, `test_plain_value_table_runtime`, `test_plain_value_list` |
| Try/Raise/error metadata | `test_python_direct_error_info` and migrated `test_experimental_direct_ast_raise` |
| Dynamic Execute/Eval and lexical host references | `test_direct_ast_dynamic_scopes`, `test_direct_ast_native_cells`, migrated core getter/revocation case |
| Collection admission/security corpus | `test_python_direct_collection_regions` (not manually rerun with excluded methods) |

The whole-source suite no longer manually instantiates/reruns other TestCases;
its own source audit, AST audit, mutation denial and code-position tests remain.
Inherited external suites use a non-TestCase helper, avoiding duplicate discovery
of the same external tests in every child module.

## Failures remain visible

No parity between two equally failing implementations is accepted. Method
name diagnostics, argument cleanup timing, unsupported foreign host references
and constructor override boundaries remain ordinary failing assertions/errors
where the implementation does not meet the explicit expectation. They are not
converted into successful unsupported assertions or hidden in snapshots.
