"""Run the bounded fixed snapshot slice and neighboring direct boundaries."""
import sys
import unittest
sys.path[:0]=['tests','scripts','.']
fixed=('fixed_structure_empty_and_string_constructors','fixed_structure_string_constructor_matches_structure_key_rules',
 'direct_mutable_arrays_freeze_recursively_without_changing_source','structure_snapshot_preserves_key_spelling_and_casefold_lookup',
 'structure_property_outputs_keep_reference_and_missing_contracts','structure_property_output_can_rebind_receiver_and_forward_reference',
 'array_snapshot_is_independent_of_source_top_level_mutation','array_iteration_is_ordered_and_unchanged_when_source_mutates')
names=['test_fixed_collections.FixedCollectionTests.test_'+name for name in fixed]
names += ['test_source_session_types.SourceSessionTypesTests.test_'+name for name in
 ('fixed_array_nested_values','fixed_array_rejects_nested_mutable_structure','fixed_structure_nested_immutable')]
names += ['test_source_session_parameters.SourceFixedStructureSessionTests.test_'+name for name in
 ('actual_assigned_structure','mutable_structure_rejected','no_invented_default','lazy_handler_assigns_structure','client_access_not_granted')]
names += ['test_python_direct_fixed','test_python_direct_source_sessions_security',
          'test_python_direct_value_lists','test_python_direct_value_constructors','test_python_direct_strings_parity',
          'test_python_direct_source_catalog_no_vm','test_python_direct_source_catalog_security',
          'test_python_direct_source_document_no_vm','test_python_direct_source_document_handlers_security']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())
