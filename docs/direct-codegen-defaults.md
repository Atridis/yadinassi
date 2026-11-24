# Default to direct Python

Lower ordinary BSL syntax to the corresponding Python construct first. Do not
select the basic lowering by predicting a receiver's type in the BSL program.
An adapter should handle only a concrete semantic difference demonstrated by
a regression test. Preserve existing host, database, and transfer admission:
a Python protocol is not permission to call it on an arbitrary host object.

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
| Native text concatenation can rejoin UTF-16 halves and convert the right operand | `test_experimental_naked_scalar_semantics.test_surrogate_pair_join`, `test_direct_scalar_prefix.test_string_prefix_uses_bsl_concat_with_unknown_or_native_int_rhs` |
| BSL numeric division and remainder must not become binary float or Python's signed integer remainder | `test_direct_integer_lane.test_fraction_mixed_and_division_stay_decimal`, `test_direct_integer_lane.test_remainder_has_dividend_sign_and_decimal_errors` |
| Owner/alias-aware array indexing has different bracket and method rules | `test_mutable_array_index_semantics` |
| A live named call can rebind and change which arguments must be references | `DirectBuiltinCallsTests.test_prepared_call_uses_later_bsl_routine_and_its_byref_signature` |
| A live database reference may read newer fields than the query projection | `QueryReferenceProjectionTests.test_script_ref_is_live_but_explicit_projected_column_is_captured` |

External member admission, callback effects, database ownership and
client/server isolation are execution boundaries, not a compiler optimization
heuristic. Ordinary syntax can still be lowered directly inside those
profiles without bypassing the boundary at a real effect.
