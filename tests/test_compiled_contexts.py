"""Live contextual behavior after retirement of the old execution engines.

Original semantic fixtures run under explicit python-direct selection. Profiling
observes context construction without replacing sealed Interpreter methods.
Behavioral outcomes, not a retired runner entrypoint, establish execution.
Unsupported behavior remains an ordinary test failure, not a skipped oracle.
"""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.execution_policy import execution_backend_policy


class StrictContextTests(unittest.TestCase):
    def run_existing(self, names, required_types=(), *, explicit_cli=False):
        import sys
        from yadinassi import cli
        created=[]
        init_code=Interpreter.__init__.__code__
        original_cli=cli.main
        old_profile=sys.getprofile()
        def profile(frame,event,arg):
            if event=='return' and frame.f_code is init_code:
                vm=frame.f_locals['self']
                created.append((type(vm).__name__,vm.execution_backend))
        def run_cli(args=None):
            return original_cli(['--execution-backend','python-direct',*(args or [])])
        with ExitStack() as stack:
            stack.enter_context(execution_backend_policy('python-direct'))
            if explicit_cli:
                import test_configuration_runtime
                stack.enter_context(patch.object(cli,'main',run_cli))
                stack.enter_context(patch.object(test_configuration_runtime,'main',run_cli))
            suite=unittest.defaultTestLoader.loadTestsFromNames(names)
            result=unittest.TestResult()
            try:
                sys.setprofile(profile)
                suite.run(result)
            finally:
                sys.setprofile(old_profile)
        self.assertTrue(result.wasSuccessful(), '\n'.join(f'{test.id()}\n{trace}' for test,trace in result.errors+result.failures))
        self.assertTrue(created,'fixture did not construct any VM')
        self.assertTrue(all(mode=='python-direct' for _,mode in created),created)
        constructed={name for name,_ in created}
        self.assertTrue(set(required_types)<=constructed,(required_types,constructed))

    def test_source_lazy_session_synthetic_actuals(self):
        self.run_existing([
            'test_source_session_parameters.SourceFixedStructureSessionTests.test_lazy_handler_assigns_structure',
            'test_source_session_parameters.SourceSessionTests.test_recursive_initialization_still_bounded',
        ],('_SourceInterpreter',))

    def test_configuration_cross_owner_defaults_and_callbacks(self):
        self.run_existing([
            'test_configuration_runtime.ConfiguredCallsTests.test_same_side_byref_defaults_and_procedure',
            'test_configuration_runtime.ConfiguredCallsTests.test_callback_by_receiver_and_string',
        ],('Interpreter',))

    def test_source_value_manager_references(self):
        self.run_existing([
            'test_source_constant_handlers.SourceConstantHandlerTests.test_value_passed_to_helper_by_reference_updates_typed_storage',
        ],('_SourceInterpreter','_ValueInterpreter'))

    def test_form_step_budget_is_preserved(self):
        self.run_existing(['test_form_runtime.FormRuntimeTests.test_execution_budget'],('_FormInterpreter',))

    def test_event_allowlist_budget_and_recovery(self):
        self.run_existing([
            'test_form_event_simulation.FormEventSimulationTests.test_client_trims_original_handler',
        ],('_EventInterpreter',))

    def test_known_event_adapter_budget_not_unregistered_subclass(self):
        from yadinassi.forms.form_event_simulation import _EventInterpreter
        with execution_backend_policy('python-direct'):
            vm=_EventInterpreter(lambda value: None)
            vm._remaining=0
            with self.assertRaisesRegex(ValueError,'execution budget or node'):
                vm.execute('x=1;')
            self.assertEqual(vm._remaining,-1)
            self.assertNotIn('x',vm.variables)

    def test_object_post_result_budget_and_live_reference(self):
        self.run_existing([
            'test_catalog_object_preparation.CatalogObjectPreparationTests.test_bounded_text_expansion',
            'test_catalog_object_preparation.CatalogObjectPreparationTests.test_direct_field_arguments_are_live_references',
        ],('_ObjectInterpreter',))

    def test_posting_step_budget_and_measured_outcomes(self):
        self.run_existing([
            'test_document_posting_runtime.PostingRuntimeTests.test_budget_failure_cannot_be_caught_and_leaves_no_rows',
            'test_document_posting_runtime.PostingRuntimeTests.test_fourteen_measured_outcomes',
        ],('_PostingInterpreter',))

    def test_source_form_activation_keeps_strict_backend(self):
        self.run_existing(['test_source_forms.SourceFormTests.test_real_server_create_and_command_roundtrip'],
                          ('_SourceFormInterpreter',))

    def test_product_server_event_uses_trusted_compiled_adapter(self):
        self.run_existing([
            'test_product_form_events.ProductFormEventTests.test_server_calls_original_object_preparation_and_never_writes',
        ],('ProductInterpreter','_ObjectInterpreter'))

    def test_product_list_uses_trusted_compiled_adapter(self):
        self.run_existing([
            'test_product_list_check.ProductListCheckTests.test_all_record_reads_share_source_snapshot',
        ],('ListInterpreter',))

    def test_configuration_cli_is_explicitly_strict_not_default(self):
        self.run_existing([
            'test_configuration_runtime.ConfigurationRuntimeStorageTests.test_cli_explicit_activation_and_ordinary_database_open',
        ],('Interpreter',),explicit_cli=True)



    def test_merged_source_object_guards_and_sections(self):
        self.run_existing([
            'test_source_document_sections',
            'test_source_document_module_guards',
            'test_source_document_object_modules',
            'test_source_catalog_object_modules',
            'test_source_constant_handlers',
        ], ('_SourceInterpreter', '_ObjectInterpreter'))

if __name__=='__main__':unittest.main()
