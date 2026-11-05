# Frozen smoke launch ownership

This reduction changes only the first successful six-route matrix in each family
below. All programs and expected output are unchanged. Each family still runs its
entire program twice in the actual packaged executable, outside the checkout:
UTF-8 BOM file in its original Cyrillic path, and incremental redirected console
with `/exit`. Console state and statement boundaries are deliberately not treated
as equivalent to one-shot execution.

For every row, the old commands were `-c PROGRAM`, Cyrillic `-с PROGRAM`,
`--command PROGRAM`, `CYRILLIC_FILE`, `-` with PROGRAM on stdin, and no arguments
with PROGRAM plus `/exit`. Only the three command aliases and `-` are removed
from this *success* matrix. All later loops in those helpers are unchanged.

| Frozen helper | Independent semantic owners (under tests/) | Retained observations |
| --- | --- | --- |
| check_eval | test_eval.py | scope/reference mutation, scalar conversions, parse/arity/depth errors |
| check_string_parity | test_string_occurrences.py, test_strings.py, plus supplement owners below | full string/composition program including all appended supplements |
| check_array_gap | test_array_gap_insert.py, test_multidimensional_array.py | dimensions, gap/alias insertion, fixed snapshot, serialization |
| check_array_defaults | test_array_defaults.py | omitted values, mutation, fixed snapshot, serialization |
| check_value_filled | test_value_filled.py | scalar and collection filled values, serialization |
| check_string_lines | test_string_lines.py | multiline boundaries and line operations |
| check_string_template | test_string_template.py | substitutions, conversions and errors |
| check_string_boundaries | test_string_boundaries.py | starts/ends checks, UTF-16 boundaries |
| check_characters | test_characters.py | character/code conversions and observed errors |
| check_numeric_helpers | test_numeric_helpers.py | bilingual integer/extrema operations, signs, precision, ties |
| check_numeric_boolean_comparisons | test_numeric_boolean_comparisons.py | six comparisons, exact values, typed map keys |
| check_goto | test_goto.py | labels, branches, loops and scope |
| check_rounding | test_rounding.py, test_round_modes.py, test_round_mode_iteration.py | aliases, signs, precision, numeric/enum modes, codecs |
| check_text_document | test_text_documents.py, test_text_documents_native.py | complete edits/separators/aliases, rejected file API and no-write check |
| check_tree_findrows | test_value_tree_findrows.py, test_value_tree_findrows_native.py | DFS/local order, shared row identity, flags and observed errors |

The independent owners do not import their assertions from this smoke program.
In addition, test_cli.py retains exact-program six-route regression coverage for
the first thirteen rows. test_text_document_smoke.py and
test_tree_findrows_build_smoke.py retain all six source-CLI routes for the last
two. These are supplementary checks, not substitutes for the retained frozen
execution or independent semantic owners.

### Complete string/composition supplement ownership

The historically named STRING_PARITY_PROGRAM also contains non-string probes.
None are shortened: initial StrTemplate placeholders/escapes → test_string_template.py,
XML lexical values → test_xml_values.py,
comparison → test_string_compare.py, default property-copy intersection, fixed-source,
Undefined, serialization and fixed-target no-op → test_property_values.py;
optional include/exclude property-copy lists → test_fill_include_runtime.py and
test_fill_exclude_runtime.py,
dynamic Execute → test_execute.py, dynamic New → test_dynamic_new.py,
by-reference arguments → test_reference_arguments.py and
test_reference_checkpoint.py, bit operations → test_bits.py,
unsigned/right and wrapping/left shifts → test_bitwise_shift_right.py and
test_bitwise_shift_left.py, deletion boundaries → test_array_delete_boundary.py,
uint128/radix grammar → test_numeric_radix.py, optional search and enum codecs →
test_search_directions.py and test_search_direction_checkpoint.py.
The exact full composed output is still asserted in both frozen routes.

## Frozen transport and boundary owners retained in full

- check_dates: all three command spellings, BOM file, stdin, incremental console,
  imported defaults, canonical source locations, failed assignments and recovery.
- check_clocks and check_fixed_offset_conversions: bundled timezone data, live
  clock bounds, imported clocks, offsets and source-bound timezone observations.
- check_saved_native_outputs, check_null, check_xml_checkpoint,
  check_table_checkpoint: full independently captured output and exact source
  binding, native supplement command limits, file/stdin/console parity.
- main: non-ASCII and relative paths, UTF-8/BOM and CP1251 encoding, sibling,
  nested/directory imports, import failures, stderr and exit codes, namespace and
  compilation behavior. Sanitized environment and unrelated working directory
  remain unchanged.
- check_ui and check_console: real bundled assets, child runtime lifecycle,
  terminal editing/history and multiline state. No launch removed here.
- Every family's failure matrix, recovery sequence and TextDocument no-write
  assertion remains exactly in its original helper.

## Deterministic count

The changed success matrices were 15 × 6 = **90** launches. They are now
15 × 2 = **30**, a reduction of **60** executable launches on every platform.
No other launch site changes. The inventory regression verifies the complete
list of reduced helpers and their exact file/console inputs. A separate instrumented plan census of the pre-change and post-change script
counts **588 → 528 subprocess.run calls**. It enumerates the same fixture/loop
paths with the executable mocked and result-dependent validation excluded;
it is not an execution or acceptance of the frozen program. All unaffected
helper counts match. Adding the unchanged direct UI parent launch and, on POSIX,
the unchanged PTY parent launch gives **590 → 530 direct parent launches on
POSIX**, or **589 → 529 on Windows**. Processes started internally by the UI
are excluded from these direct-parent counts and remain unchanged. Actual
frozen validation and timings must be reported separately; these counts are
not a wall-time claim.

## Exact removed-invocation ledger (60 entries in 15 groups)

Each row defines four entries, identified as `<row>-c`, `<row>-с`,
`<row>--command`, and `<row>-stdin`. For the first three the exact argv is
`[executable, FLAG, PROGRAM]` and stdin is None. For the fourth argv is
`[executable, '-']` and stdin is exactly PROGRAM. PROGRAM below names the
unchanged Python constant, or the source returned by the named function, in
scripts/smoke_test.py. No program is regenerated or shortened.

For **every** entry, the exact full success tuple `(0, OUTPUT, '')` remains
asserted twice by the same `check_<row>` helper, once for its original BOM file
and once for PROGRAM + `/exit\n` on the console. OUTPUT is the corresponding
`*_OUTPUT` constant, or the second value returned by the named source function.
The original cwd, sanitized environment, encoding and timeout remain unchanged.
The named source-CLI test retains this exact program through *all six* routes.
The independent semantic tests below use their own inputs/assertions and do not
import these smoke programs.

| Row / unchanged PROGRAM | Exact retained source-CLI test (tests/) | Independent semantic test methods (module: method) |
| --- | --- | --- |
| eval / EVAL_PROGRAM | test_cli.CLITests.test_eval_all_cli_inputs | test_eval: test_native_scalar_examples_and_aliases; test_native_number_argument_and_undefined_error; test_native_local_module_parameter_and_nested_scopes; test_native_reference_mutation_reaches_caller; test_native_comment_and_rejected_semicolon; test_arity_before_argument_side_effects; test_dynamic_errors_are_catchable_not_incomplete_outer_input; test_eval_result_uses_existing_serialization_both_directions; test_recursive_eval_resource_guard_and_recovery |
| string_parity / STRING_PARITY_PROGRAM | test_cli.CLITests.test_native_string_parity_all_cli_inputs | Exact composition sub-ledger below; this row includes every appended non-string supplement |
| array_gap / ARRAY_GAP_PROGRAM | test_cli.CLITests.test_array_gap_all_cli_inputs | test_array_gap_insert: test_aliases_empty_and_nonempty_gap; test_omitted_and_explicit_undefined; test_repeated_gap_and_inrange_shift; test_alias_snapshot_write_find_and_iteration; test_serialization_both_directions; test_invalid_indices_are_atomic_and_catchable; test_multidimensional_array: test_names_shape_and_undefined_leaves; test_every_branch_is_independent_and_mutable; test_zero_dimensions_and_existing_default; test_fixed_constructor_and_snapshot_preserved; test_both_serialization_directions; test_validation_and_catchable_recovery |
| array_defaults / ARRAY_DEFAULT_PROGRAM | test_cli.CLITests.test_array_defaults_all_cli_inputs | test_array_defaults: test_add_aliases_and_repeated_calls; test_insert_aliases_shift_without_overwrite; test_omitted_and_explicit_undefined_have_same_serialization; test_defaults_remain_writable_and_collection_aliases_are_live; test_fixed_snapshot_and_fixed_methods_unchanged; test_invalid_calls_preserve_contents_and_recover |
| value_filled / VALUE_FILLED_PROGRAM | test_cli.CLITests.test_value_filled_all_cli_inputs | test_value_filled: test_documented_scalars; test_bilingual_case_insensitive_names_and_boolean_type; test_arrays_count_entries_not_filled_elements; test_structure_and_map_count_not_values; test_existing_whitespace_contract_not_native_evidence; test_serialization_uses_existing_boolean_format; test_current_unsupported_types_do_not_guess_native_defaults; test_errors_preserve_assignment_and_recover; test_runtime_mutation_and_fixed_snapshots |
| string_lines / STRING_LINES_PROGRAM | test_cli.CLITests.test_string_lines_all_cli_inputs | test_string_lines: test_native_line_boundaries; test_native_index_and_conversion_observations; test_bilingual_case_insensitive_names_and_types; test_existing_internal_serialization; test_arity_errors_preserve_assignment_and_recover; test_shared_utf16_and_coercion_contracts_not_new_native_evidence |
| string_template / STRING_TEMPLATE_PROGRAM | test_cli.CLITests.test_string_template_all_cli_inputs | test_string_template: test_bilingual_case_insensitive_names; test_official_example; test_empty_literal_and_escaped_percent; test_repeated_reordered_and_sparse_numbering; test_tenth_parameter_and_digit_disambiguation; test_undefined_is_empty; test_substitutions_are_not_recursively_interpreted; test_shared_presentations_are_not_new_native_evidence; test_utf16_and_nul_shared_contract_not_new_native_evidence; test_existing_string_serialization_round_trip; test_missing_values_are_empty_and_excess_arguments_fail; test_malformed_markers_are_rejected_not_claimed_native_diagnostics; test_errors_preserve_assignment_and_recover_in_try |
| string_boundaries / STRING_BOUNDARY_PROGRAM | test_cli.CLITests.test_string_boundaries_all_cli_inputs | test_string_boundaries: test_bilingual_case_insensitive_aliases_and_boolean_type; test_documented_exact_case_sensitive_boundaries; test_empty_search_is_an_error_even_with_empty_source; test_shared_utf16_contract_not_separate_native_observations; test_shared_string_conversion_contract_not_native_observations; test_composition_and_existing_boolean_serialization; test_arity_errors_and_recovery_preserve_assignment |
| characters / CHARACTER_PROGRAM | test_cli.CLITests.test_characters_all_cli_inputs | test_characters: test_bilingual_case_insensitive_aliases; test_native_character_code_units; test_native_character_invalid_range_returns_empty; test_native_character_fraction_and_conversions; test_native_code_default_and_position; test_native_code_empty_and_bounds; test_native_surrogate_pair; test_character_composes_with_utf16_string_operations; test_existing_internal_serialization_preserves_units; test_arity_and_conversion_errors_are_catchable |
| numeric_helpers / NUMERIC_HELPERS_PROGRAM | test_cli.CLITests.test_numeric_helpers_all_cli_inputs | test_numeric_helpers: test_owner_native_numeric_subset; test_integer_part_bilingual_and_toward_zero; test_integer_part_preserves_long_coefficient; test_integer_part_numeric_conversion; test_extrema_bilingual_variadic_numeric_results; test_extrema_keep_winning_type_and_first_tie; test_extrema_reject_invalid_types_and_mixed_numeric_strings; test_string_extrema; test_integer_part_arity_errors_are_bsl_errors |
| numeric_boolean_comparisons / COMPARISON_PROGRAM | test_cli.CLITests.test_numeric_boolean_comparisons_all_cli_inputs | test_numeric_boolean_comparisons: test_all_operators_in_both_orders_exact_numeric_conversion; test_comparisons_ignore_decimal_context_and_never_round; test_bilingual_literals_control_flow_and_result_types; test_operands_evaluate_once_in_order_and_errors_recover; test_no_new_string_undefined_object_or_enum_coercion; test_map_keys_and_array_lookup_do_not_inherit_operator_conversion |
| goto / GOTO_PROGRAM | test_cli.CLITests.test_goto_all_cli_inputs | test_goto: test_bilingual_mixed_case_keywords_and_labels; test_backward_jump_revisits_statements_with_current_state; test_recursive_routine_jumps_keep_invocation_local_frames; test_outward_jump_exits_all_loop_kinds_without_final_increment; test_jump_out_of_all_nested_loops_and_try_body_is_not_caught; test_jump_out_of_handler_unwinds_error_context |
| rounding / ROUNDING_PROGRAM | test_cli.CLITests.test_rounding_all_cli_inputs | test_rounding: test_native_defaults_and_bilingual_names; test_native_modes_and_precision; test_native_enum_modes; test_native_rejections; test_arity_and_errors_remain_catchable; test_exact_long_coefficients_and_carry_defense; test_round_modes: test_namespace_members_are_bilingual_and_case_insensitive; test_native_presentations_and_type_identities; test_observed_enum_payloads_roundtrip_to_canonical_identities; test_observed_enum_type_payload_roundtrips; test_observed_namespace_payload_reads_back_as_undefined; test_observed_namespace_type_payload_roundtrips; test_modes_and_namespace_have_no_accidental_operators_or_methods; test_round_mode_iteration: test_namespace_iterators_are_independent_and_unique; test_bilingual_names_alias_and_expression_evaluated_once; test_values_keep_identity_type_rounding_and_serialization; test_closed_runtime_boundary_rejects_host_iterables_and_individual_modes |
| text_document / text_document_smoke_program()[0] | test_text_document_smoke.TextDocumentSmokeTests.test_all_cli_transports_preserve_output_and_never_create_write_target | test_text_documents_native.TextDocumentNativeObservations.test_all_44_native_witnesses_through_independent_raw_field_reads; test_text_documents: test_aliases_dynamic_constructor_and_displays; test_unmeasured_indices_fail_without_mutation; test_unmeasured_line_delimiters_are_local_errors_not_native_claims; test_no_file_ui_properties_indexer_iteration_or_host_members; test_same_side_aliases_keep_one_mutable_document_without_properties |
| tree_findrows / tree_findrows_smoke_program()[0] | test_tree_findrows_build_smoke.TreeFindRowsBuildSmokeTests.test_exact_program_across_command_aliases_bom_file_stdin_and_console | test_value_tree_findrows_native.FindRowsNativeObservations.test_unchanged36_probes_match_exact_native_bytes_without_filtering; test_value_tree_findrows: test_hierarchy_not_registry_order_and_local_receiver; test_reference_array_is_new_list_with_same_row_objects; test_unknown_schema_is_checked_before_empty_receiver_or_short_circuit; test_decimal_flag_extension_is_separately_evidenced_conversion_policy; test_flag_rejection_precedes_converter_and_empty_filter_shortcut |

### Packaging proof for each of the four removed routes

This mapping applies independently to every one of the 15 ledger rows, rather
than assuming that source-CLI tests are packaged tests:

| Removed route | Retained actual frozen observation | Why the family's packaging observation survives |
| --- | --- | --- |
| `-c PROGRAM` | check_dates with `-c DATE_PROGRAM`; main `-c` Cyrillic string, string_code, maps/types/structures; native XML/table command samples | Family's entire program still executes in frozen file and console processes, loading its actual bundled runtime dependencies. Argument parsing and command execution remain frozen-tested with independent programs. |
| Cyrillic `-с PROGRAM` | check_dates with Cyrillic `-с DATE_PROGRAM`; main exact `Кириллица` output; native XML/table Cyrillic command samples | Same family resource/dependency observations remain in its two frozen runs; Cyrillic flag decoding and argument transport remain explicit frozen assertions. |
| `--command PROGRAM` | check_dates with `--command DATE_PROGRAM`; native XML/table `--command` samples with UTF-16 command-length guard | Long-option dispatch and nontrivial multiline native programs remain frozen-tested. No family-specific command parsing exists: yadinassi.cli.main registers the three spellings as one argparse action and executes args.command through the same interpreter. |
| stdin `-` with PROGRAM | check_dates stdin DATE_PROGRAM; main stdin string_code, types/maps/structures and client/region programs; complete native checkpoint stdin | UTF-8 stream reconfiguration, full-stream read and source identity remain frozen-tested. Family-specific dependencies are loaded by its unchanged BOM-file and console executions. File and stdin converge at interpreter.execute in cli.main; the source-name difference remains covered by the unchanged negative matrices. |

`cli.main` reconfigures stdin/stdout/stderr to UTF-8, registers all three aliases
as one argument, uses `sys.stdin.read()` for `-`, and passes either the command or
loaded source text to the same Interpreter. This code was inspected, not changed.
The exact family program is never removed from the packaged interpreter.
The console route is deliberately retained because incremental parsing and
state persistence do not share one-shot execution semantics.

Distinct negative-path scope remains unchanged: array gap capacity and state;
filled-value/string/character arity and conversion errors; Goto static errors;
rounding assignment recovery; every source location, stderr substring and exit
code assertion. TextDocument still checks the actual working directory for
`must-not-write` after both frozen runs. These are not delegated to the shared
transport matrix.

### Exact string/composition semantic sub-ledger

All names below are methods in the indicated test module; each has independent
inputs/expected results. The retained smoke program continues to check their
composition and complete ordered output in the frozen executable.

| STRING_PARITY_PROGRAM segment | Independent semantic methods |
| --- | --- |
| StrOccurrenceCount including aliases, coercion, UTF-16, arity and codec | test_string_occurrences: test_native_observations; test_aliases_and_result_type; test_nonoverlap_no_match_and_edges; test_shared_utf16_nul_and_surrogate_contract; test_existing_conversion_contract; test_serialization_both_directions; test_arity_errors_preserve_assignment_and_recover |
| Initial template missing/reordered slots and escaped percent | test_string_template: test_empty_literal_and_escaped_percent; test_repeated_reordered_and_sparse_numbering; test_missing_values_are_empty_and_excess_arguments_fail |
| Two-argument StrFind, missing direction and recovery | test_str_find: test_aliases_and_documented_search_contract; test_existing_find_utf16_and_conversion_contract; test_serialization_both_directions; test_invalid_arity_direction_and_recovery |
| XML String/Boolean read/write, exact lexical tokens, no XML parsing, preserved assignment | test_xml_values: test_writer_aliases_and_types; test_reader_aliases_and_type_identities; test_strings_are_unchanged_and_never_parsed; test_boolean_reader_rejects_whitespace_and_invalid_tokens; test_roundtrip_and_internal_serialization_both_directions; test_arity_errors_preservation_and_recovery |
| Secondary-strength string comparison and invalid-type recovery | test_string_compare: test_native_cases_aliases_and_reverse; test_case_weights_not_unicode_casefold; test_internal_serialization_both_directions; test_strict_types_do_not_call_host_hooks; test_arity_errors_and_recovery |
| Two-argument property copy, fixed source, Undefined, codec, fixed-target no-op | test_property_values: test_aliases_case_and_intersection; test_fixed_source_and_undefined_copy; test_validation_before_mutation_and_recovery; test_fixed_target_is_accepted_without_mutation; test_existing_serialization_both_directions_and_aliases |
| Execute mutation, temporary name scope, error state, selected/excluded property copy | test_execute: test_aliases_and_existing_binding; test_new_names_disappear_after_success_and_error; test_collection_mutations_and_existing_serialization; test_runtime_error_retains_effects_and_recovers; test_whole_fragment_parsed_before_effects; test_empty_undefined_and_exact_type_validation; test_property_values: test_selected_copy_preserves_other_properties; test_exclusion_with_omitted_or_undefined_selection |
| Dynamic New, parameter Array, fixed constructors, ignored nonarray arg, failure state | test_dynamic_new: test_keyword_and_type_aliases; test_constructor_parameter_array_and_multidimensional_shape; test_all_fixed_constructors_and_mutable_inverse; test_non_array_second_argument_is_ignored_as_documented; test_existing_target_preserved_on_constructor_error_and_recovery; test_internal_serialization_both_directions_all_collection_types |
| Live Array/Structure/Map reference arguments, missing Map slot, fixed write rejection, codec | test_reference_arguments: test_live_reads_in_both_directions_for_each_mutable_slot; test_mutable_map_missing_slot_can_be_read_then_created; test_fixed_slots_enter_and_read_before_assignment_error; test_property_output_assigns_existing_slot_and_missing_value; test_reference_type_serialization_dereferences_live_value; test_nested_slots_and_parentheses; test_eval_and_execute_keep_live_slot_and_forwarding |
| Bit truth tables, complement, masks, set/clear, fraction failure, Eval/Execute composition | test_bits: test_truth_tables; test_complement_is_unsigned_32_bit; test_every_bit_can_be_set_cleared_and_checked; test_mask_means_all_selected_bits; test_all_numeric_parameters_reject_fractions_and_out_of_range; test_eval_execute_and_routine_composition; test_catchable_error_preserves_assignment_and_recovers |
| Unsigned right shift, failure state and codec | test_bitwise_shift_right: test_all_bit_positions_and_offsets_against_division; test_mixed_bits_and_boundaries; test_internal_roundtrip_and_type; test_catchable_error_preserves_assignment_and_recovers |
| Empty/out-of-bound Array deletion, fractional index and preserved state | test_array_delete_boundary: test_bilingual_empty_and_above_upper_bound; test_valid_deletion_through_bilingual_aliases; test_huge_positive_indices_never_expand_to_host_integer; test_existing_unsupported_index_contract_is_atomic; test_error_preserves_serialization_aliases_and_snapshot; test_error_recovery_enters_except_and_allows_valid_deletion |
| Numeric grammar, exact uint128, wrapping left shift and error recovery | test_numeric_radix: test_native_checkpoint_numeric_output_exact; test_uint128_preserves_all_39_decimal_digits; test_native_invalid_grammar; test_decimal_context_is_not_observed_or_changed; test_catchable_errors_preserve_assignment_and_recover; test_bitwise_shift_left: test_all_bit_positions_and_offsets_against_modular_multiplication; test_mixed_bits_and_boundaries; test_catchable_error_preserves_assignment_and_recovers |
| Optional StrFind direction/start/occurrence, empty needles, omitted slots and boundary errors | test_str_find_extended: test_owner_nonempty_search_observations; test_owner_empty_needle_orthogonal_observations; test_observed_argument_conversion_and_defaults; test_bilingual_aliases_and_optional_holes; test_position_validation_precedes_early_result; test_errors_are_atomic_and_recovery_eval_execute_work; test_result_type_and_bidirectional_serialization |
| SearchDirection presentation/type/enum and namespace codecs, iteration, unsupported type | test_search_directions: test_bilingual_case_insensitive_members; test_observed_presentations_and_type_identities; test_type_names_resolve_values_but_neither_namespace_name; test_native_order_and_independent_iterators; test_exact_native_payloads_restore_canonical_identities; test_namespace_payload_restores_undefined; test_both_type_records_roundtrip_despite_namespace_name_lookup_failure |
