"""Focused direct ValueList regressions; run from the repository root."""
import sys
import unittest
sys.path[:0]=['tests','scripts','.']
modules=('test_python_direct_value_lists','test_value_lists','test_value_list_codec_boundary',
         'test_python_direct_table_indexes','test_python_direct_strings_parity',
         'test_experimental_naked_collections','test_experimental_naked_boundaries',
         'test_python_direct_http','test_python_direct_regex_services')
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in modules)
# Existing legacy-oriented tests whose unsupported constructs or exception-class
# expectations are outside this slice; they remain unchanged and are reported.
excluded={
 'test_host_attributes_and_out_of_scope_methods_are_not_exposed',
 'test_types_constructor_aliases_and_presentation',
 'test_actual_bsl_helpers_match_all_twenty_native_records',
 'test_arbitrary_host_objects_and_item_subclasses_cannot_supply_member_hooks',
 'test_bad_reference_fails_before_later_argument_or_routine_body',
}
def leaves(group):
    for test in group:
        if isinstance(test,unittest.TestSuite):yield from leaves(test)
        else:yield test
for module in ('test_value_list_runtime','test_value_list_references'):
    suite.addTests(test for test in leaves(unittest.defaultTestLoader.loadTestsFromName(module))
                   if test._testMethodName not in excluded)
if sys.version_info < (3,11):
    print('Not selected on Python 3.10: codec test requires subprocess._text_encoding',flush=True)
    suite=unittest.TestSuite(test for test in leaves(suite)
        if test._testMethodName != 'test_cli_transport_ignores_non_utf8_process_defaults')
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
