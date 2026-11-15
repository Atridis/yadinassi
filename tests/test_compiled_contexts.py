"""Contextual strict execution: preserved policies, factories and no old visitors.

Existing behavioral oracles are rerun with explicit strict selection. The helper
asserts every constructed VM uses strict mode, and poisons legacy visit_* routes;
shared semantic adapters and the original before/after-node policy wrappers remain.
"""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine
from yadinassi.execution_policy import execution_backend_policy


class StrictContextTests(unittest.TestCase):
    def run_existing(self, names, required_types=(), *, explicit_cli=False):
        from yadinassi import cli
        from yadinassi.configuration_source_runtime import _SourceInterpreter
        from yadinassi.form_runtime import _FormInterpreter
        from yadinassi.form_event_simulation import _EventInterpreter
        from yadinassi.catalog_object_preparation import _ObjectInterpreter
        from yadinassi.document_posting import _PostingInterpreter
        from yadinassi.source_constant_managers import _ValueInterpreter
        from yadinassi.source_catalog_runtime import _ObjectInterpreter as CatalogInterpreter
        from yadinassi.source_document_runtime import _ObjectInterpreter as DocumentInterpreter
        created=[];executed=set()
        original_init=Interpreter.__init__
        original_node=Engine.run_node
        original_cli=cli.main
        def initialize(vm,*args,**kwargs):
            original_init(vm,*args,**kwargs)
            created.append((type(vm).__name__,vm.execution_backend))
            self.assertEqual(vm.execution_backend,'compiled-strict',
                             'factory silently chose the old interpreter')
        def run_node(engine,node):
            executed.add(type(engine.vm).__name__)
            return (yield from original_node(engine,node))
        def old_visitor(*args,**kwargs):
            raise AssertionError('legacy visit_* used during strict context test')
        def run_cli(args=None):
            return original_cli(['--execution-backend','compiled-strict',*(args or [])])
        with ExitStack() as stack:
            stack.enter_context(execution_backend_policy('compiled-strict'))
            stack.enter_context(patch.object(Interpreter,'__init__',initialize))
            stack.enter_context(patch.object(Engine,'run_node',run_node))
            for cls in (Interpreter,_SourceInterpreter,_FormInterpreter,_EventInterpreter,
                        _ObjectInterpreter,_PostingInterpreter,_ValueInterpreter,
                        CatalogInterpreter,DocumentInterpreter):
                for name in tuple(cls.__dict__):
                    if name.startswith('visit_'):
                        stack.enter_context(patch.object(cls,name,old_visitor))
            if explicit_cli:
                # Discovery may already have bound the CLI function in this module.
                import test_configuration_runtime
                stack.enter_context(patch.object(cli,'main',run_cli))
                stack.enter_context(patch.object(test_configuration_runtime,'main',run_cli))
            suite=unittest.defaultTestLoader.loadTestsFromNames(names)
            result=unittest.TestResult();suite.run(result)
        self.assertTrue(result.wasSuccessful(), '\n'.join(
            f'{test.id()}\n{trace}' for test,trace in result.errors+result.failures))
        self.assertTrue(created,'fixture did not construct any VM')
        self.assertTrue(set(required_types)<=executed,(required_types,executed))

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
        from yadinassi.form_event_simulation import _EventInterpreter
        with execution_backend_policy('compiled-strict'):
            vm=_EventInterpreter(lambda value: None)
            vm._remaining=0
            with self.assertRaisesRegex(ValueError,'execution budget or node'):
                vm.execute('x=1;')
            self.assertEqual(vm._remaining,-1)
            self.assertNotIn('x',vm.variables)
            self.assertGreater(vm.compiled_backend_stats['prepared_nodes'],0)
            self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)

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
