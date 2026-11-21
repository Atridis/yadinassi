"""Live context authority after removal of the experimental Engine views.

Private owned-view creation/fingerprints are retired. Original AST admission,
foreign declaration denial and actual direct source/posting effects remain tests.
"""
from types import SimpleNamespace
import unittest

from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.types.errors import BSLError
from yadinassi.execution.execution_policy import execution_backend_policy
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse


class OwnedContextGuardTests(unittest.TestCase):
    def run_direct_cases(self, names):
        with execution_backend_policy('python-direct'):
            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromNames(names).run(result)
        self.assertEqual(result.skipped, [], 'live ownership cases must not skip')
        self.assertTrue(result.wasSuccessful(), '\n'.join(
            f'{test.id()}\n{trace}' for test, trace in result.errors + result.failures))

    def test_event_and_object_guards_preserve_real_execution_budgets(self):
        self.run_direct_cases([
            'tests.test_compiled_contexts.StrictContextTests.test_known_event_adapter_budget_not_unregistered_subclass',
            'tests.test_catalog_object_preparation.CatalogObjectPreparationTests.test_bounded_text_expansion',
        ])

    def test_constant_and_posting_arguments_preserve_live_references(self):
        # Actual owned source execution replaces hand-made legacy argument generators.
        self.run_direct_cases([
            'tests.test_source_constant_handlers.SourceConstantHandlerTests.test_value_passed_to_helper_by_reference_updates_typed_storage',
            'tests.test_document_posting_runtime.PostingRuntimeTests.test_fourteen_measured_outcomes',
            'tests.test_document_posting_runtime.PostingRuntimeTests.test_cancel_must_remain_boolean',
            'tests.test_document_posting_runtime.PostingRuntimeTests.test_handler_queries_types_and_temp_tables_share_owner_snapshot',
        ])

    def test_configured_program_retains_original_authority_and_import_guard(self):
        original = parse('Procedure Protected() EndProcedure')[0]
        owner = SimpleNamespace(require_open=lambda: None,
            _definitions={'protected': object()}, _global_names=set(), _events={},
            _declared_routines={id(original): original})
        ConfigurationApplication.check_program(owner, [original])
        unrelated = parse('Procedure Protected() EndProcedure')[0]
        with self.assertRaisesRegex(BSLError, 'declaration conflicts'):
            ConfigurationApplication.check_program(owner, [unrelated])
        with self.assertRaisesRegex(BSLError, 'file imports are unavailable'):
            ConfigurationApplication.check_program(owner, [ast.Import(original.token, 'foreign.bsl')])

    def test_foreign_ast_kind_cannot_gain_direct_execution_authority(self):
        from yadinassi import Interpreter
        from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
        program = parse('Touch(); answer=42;')
        original = program[1].value
        class Foreign(ast.Literal):
            pass
        program[1].value = Foreign(original.token, original.value)
        effects = []
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        vm.register_function('Touch', lambda: effects.append('called'))
        with self.assertRaises(PythonDirectUnsupported):
            vm.execute_program(program)
        self.assertEqual(effects, [])
        self.assertNotIn('answer', vm.variables)
