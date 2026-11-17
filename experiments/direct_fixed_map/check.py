"""Focused FixedMap regressions; explicit remaining source gaps below."""
import sys
import unittest
sys.path[:0]=['tests','scripts','.']
names=['test_python_direct_fixed_map','test_python_direct_fixed','test_python_direct_value_lists',
 'test_python_direct_strings_parity','test_python_direct_source_sessions_security',
 'test_python_direct_source_catalog_no_vm','test_python_direct_source_catalog_security',
 'test_python_direct_source_document_no_vm','test_python_direct_source_document_handlers_security']
names += ['test_fixed_collections.FixedCollectionTests.test_'+name for name in (
 'source_constructors_are_bilingual_case_insensitive_and_presentable',
 'constructor_source_is_evaluated_once','invalid_constructors_preserve_existing_assignment',
 'read_method_aliases_are_case_insensitive_for_all_fixed_types',
 'map_snapshot_is_independent_of_source_replacement_deletion_and_insert',
 'map_keys_are_not_dot_properties_even_when_named_like_methods',
 'same_fixed_source_constructor_is_rejected_and_preserves_original',
 'all_mutating_methods_and_index_assignments_are_rejected',
 'read_method_arities_and_omitted_arguments_are_checked',
 'structure_and_map_iteration_keep_original_pairs_after_source_mutation',
 'iteration_pairs_are_readonly_but_nested_values_remain_mutable',
 'failed_mutation_reports_source_line_and_remains_catchable',
 'fixed_errors_report_source_location_and_restore_routine_scope',
 'routine_returns_aliases_and_val_rebinding_does_not_mutate_fixed_values')]
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
# Unchanged tests outside this slice: reusable source routines, ValueStorage,
# standalone read lookup and catchable-versus-fail-closed exception expectations.
excluded={'test_caches_do_not_leak_between_source_applications','test_closed_source_cannot_lend_handle',
 'test_foreign_live_source_cannot_lend_handle','test_refresh_invalidates_source_cache',
 'test_request_reuse_expires_at_next_request','test_same_side_cached_fixed_map_is_reused',
 'test_session_reuse_survives_next_request','test_value_storage_snapshot_isolation','test_zero_parameter_lazy_handler'}
def leaves(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite):yield from leaves(test)
        else:yield test
for module in ('test_source_session_parameters','test_source_session_types'):
    suite.addTests(test for test in leaves(unittest.defaultTestLoader.loadTestsFromName(module))
                   if test._testMethodName not in excluded)
raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())
