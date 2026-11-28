# Default to direct Python

Lower ordinary BSL syntax to the corresponding Python construct first. Do not
select the basic lowering by predicting a receiver's type in the BSL program.
An adapter should handle only a concrete semantic difference demonstrated by
a regression test. Preserve existing host, database, and transfer admission:
a Python protocol is not permission to call it on an arbitrary host object.

### Scope of an exception

An exception to direct lowering must have a behavioral witness, a named
operation or boundary, and the smallest scope that preserves that behavior.
For example, BSL string addition may convert the right operand and rejoin
UTF-16 halves. Adapt that addition only; do not recompile its loop, routine,
or module with a different generator. A test for an exception should show
both the different result and that adjacent ordinary operations still use
their normal lowering. Do not use a whole-program proof, alternate program
body, or legacy evaluator as the default complement to an exception.

The ordinary `For Each` lowering is a Python `for`, including when a prepared
program does not know the collection type. The loop asks for the iterable at
entry; its body does not call `next()` or handle exhaustion manually. Normal
arrays use their native iterator, and an empty loop does not assign its target.

The entry adapter preserves tested BSL behavior: a correspondence produces
entry objects, not dict keys; changing its shape during iteration raises a
catchable BSL error without rerunning the body. Foreign iteration still goes
through the existing member admission. Interpreter-owned reference cells and external setters retain the
existing assignment protocol. Profiles that meter each attempted step use
the same checkpoint at the iterator boundary, including exhaustion; the
generated loop is still a Python `for`.

Regression witnesses: `test_python_direct_for_each_lowering`,
`test_python_direct_table_iteration`,
`test_experimental_naked_method_arity`, and
`test_python_direct_source_loop_checks`.

Keep live counted loops as Python `while`: unlike Python `range`, BSL observes
writes to the loop variable from the body and can count with a fractional
start. The end expression is evaluated once. These are exercised by
`WholeRoutineBehaviorTests.test_loop_control_and_bound_order`,
`test_val_decimal_fractional_loop` and
`DefiniteReadsTests.test_loop_callback_counter_mutation`. A stable integral
range can still be emitted as Python `for range(...)`.

`If`, `While`, `Break`, `Continue`, and `Return` use the Python constructs.
Keep BSL Boolean/number condition conversion where Python truthiness would
accept values the language rejects. `Try` and `Raise` need the BSL error record
and must not absorb interpreter-control or permission failures. Python has
no `Goto`; only a reached source label/transfer needs the existing dispatch.

Ordinary expression lowering does not require a closed-module type proof.
Keep the Python expression where value representation gives the same result.
The remaining language adapters have concrete witnesses:

| Difference from Python | Witness |
| --- | --- |
| A numeric counter can be fractional or changed in the loop body | `test_whole_routine_differential` |
| Native text concatenation can rejoin UTF-16 halves and convert the right operand | `test_direct_scalar_semantics.test_surrogate_pair_join`, `test_direct_scalar_prefix.test_string_prefix_uses_bsl_concat_with_unknown_or_native_int_rhs` |
| BSL numeric division and remainder must not become binary float or Python's signed integer remainder | `test_direct_integer_lane.test_fraction_mixed_and_division_stay_decimal`, `test_direct_integer_lane.test_remainder_has_dividend_sign_and_decimal_errors` |
| Owner/alias-aware array indexing has different bracket and method rules | `test_mutable_array_index_semantics` |
| A live named call can rebind and change which arguments must be references | `DirectBuiltinCallsTests.test_prepared_call_uses_later_bsl_routine_and_its_byref_signature` |
| A live database reference may read newer fields than the query projection | `QueryReferenceProjectionTests.test_script_ref_is_live_but_explicit_projected_column_is_captured` |

External member admission, callback effects, database ownership and
client/server isolation are execution boundaries, not a compiler optimization
heuristic. Ordinary syntax can still be lowered directly inside those
profiles without bypassing the boundary at a real effect.

### Typed database field assignments

Keep the generated right-hand side unchanged. The shared database field
assignment accepts an exact Python `int` for a declared Number field and
converts it to `Decimal` once, before existing precision and range handling.
An existing `Decimal` is not converted; Boolean is not an integer here.
Catalogs, documents, their tabular rows, and register fields use the shared
assignment path. The measured enum-field adjustment treats native integers
like other numbers and produces the target enum’s empty value, not a numeric
field value. Keep that rule inside enum assignment, not storage admission.
Do not reintroduce a receiver-type table or conversion in
the emitter or the generic property dispatcher. Persisted data validation
and owner/access checks are unchanged.

Regression witness:
`RuntimeQualifierTests.test_numeric_fields_accept_native_integer_without_dispatcher`.
It exercises catalog header and tabular row setters directly, compares
qualification and Decimal representation with the existing Decimal path, and
checks that a rejected Boolean does not mutate the field.
`InventoryEnumRuntimeBindingTests.test_measured_adjustment_across_catalog_header_line_and_movements`
checks the separate enum assignment rule.

Local CPython 3.12 measurement: prepared BSL, nine runs of 4,096 assignments
per case, without database I/O or preparation inside the timed loop.
Median microseconds per assignment, before → after:

| Field | Catalog header | Tabular row |
| --- | ---: | ---: |
| Number from `23` | 15.34 → 15.16 | 20.50 → 19.67 |
| Number from `23.25` | 15.36 → 15.40 | 20.14 → 19.98 |
| String from `"abc"` | 12.70 → 12.28 | 15.90 → 16.07 |

Sample ranges overlap. Reversing the two guards did not yield a consistent
improvement either; the field-local rule is selected for simplicity, not
a general speedup claim.

### Direct property read and write

The emitter uses Python subscription for property storage, with an admission
step for the receiver. Structure owns case-invariant field lookup, missing
fields, and writes; KeyAndValue owns the read-only aliases. There is no
context-wide fallback from that operation. Other property receivers fail
closed until they have an explicit property surface that preserves their
boundary contract. Import writes, references, and method calls are distinct
operations, not alternate engines for ordinary dot access.

Local detached ValueTable rows and columns reuse their existing named cell and
column operations, including schema qualification, slice restrictions and
index updates. A fixed structure reuses its read-only lookup. These admissions
do not authorize property operations in a verified crossing or Python extension
context; those require their own boundary contracts.

ValueTree property storage checks the addressed object's provenance and keeps
its own row, column, and cleared-state semantics; it does not call generic
member dispatch. For native read-only objects an attempted write uses the
object's normal catchable error, not a failed access-authority check.
