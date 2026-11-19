# Collection tests after text-compiler retirement

Base tree: `cb6527d1f7161bf7f92f271ed0f56fefd4ca80f1`.

This test-only tranche removes the retired generator imports, repair-toggle
matrices and generated-text assertions from the nine assigned direct collection
test modules. Public source/AST/prepared/Execute/Eval assertions, callback order,
identity, bounded admission and live-owner tests remain. Array specialization now
asserts actual loop results through execute and prepared APIs, not retired source
spelling. Array read cases assert product observations directly rather than
comparing two runs through an inactive proof hook (native arrays have identity
equality).

Explicit current contracts replace obsolete comparisons: scalar Map keys use
Python numeric collisions and reject collection keys; PlainValueList TypeOf is
currently unsupported. Constructor failure preservation uses an unknown target,
not negative array size, whose current Python semantics differ. No runtime,
backend, serializer or constructor implementation is changed.

Validation: 104 tests in normal and optimized Python, 102 pass and two fail.
These unchanged product assertions also fail when loaded from the original base
file against the same runtime:

- `DirectCollectionStringTests.test_exact_containers_aliases_and_nested_cycles_do_not_visit_payload`
- `DirectCollectionStringTests.test_adapter_keeps_captured_exact_class_identity_after_rebinding`

Both expose String(PlainMap) falling through `values.to_string` to Python `str`,
which visits an opaque payload's `__repr__`. They remain failing assertions,
not skips or expected failures. This migration is not a green-suite claim.

## Prepared/call/form follow-up tranche

The five additional assigned modules now use only direct execution. Fixed receiver
Find retains its independent expected values and all owner/policy checks. Prepared
reuse instruments the actual `python_direct._compile` entry. Retired backend
selection is explicitly rejected at construction. Parser PreparedBlock shape
checks remain, while interpreter-only mutable execution-plan/cache tests are
removed (direct Goto and prepared immutable AST coverage already exist).

Call-shape assertions retain result/effect expectations. Partial routine-module
replacement now asserts explicit rejection and successful whole-module
redeclaration. The old InterpreterCall adapter is explicitly rejected before its
authorize/dispatch or argument hooks; it does not grant direct callable authority.
An unscoped source-form interpreter factory explicitly rejects, while supported
controller-owned source forms remain covered in their existing security suite.

Follow-up validation: 34 tests normal and -O, 31 pass, three genuine direct-path
errors retained without skips or expected failures:

- `TranslatedFormTableIndexTests.test_original_nested_call_case_direct`
- `TranslatedFormTableIndexTests.test_each_generated_table_read_runs_once`
  Both fail on form-table bracket access with missing `__getitem__`.
- `CallShapeContracts.test_byref_default_grouped_and_member_actuals`
  Grouped by-reference call reports `n` undefined after `n=7` in the same module.

These are test-only migrations exposing current product behavior, not assertions
that these suites are green.
