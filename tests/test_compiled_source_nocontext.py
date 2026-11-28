"""Exact source NoContext authority and scalar calls under observed strict execution."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.execution_policy import execution_backend_policy
from yadinassi.forms.source_forms import _SourceNoContextInterpreter
from yadinassi.forms.form_runtime import FormLimitError
from yadinassi.syntax.parser import parse


class CompiledSourceNoContextTests(unittest.TestCase):
    def test_source_form_scalar_and_formless_calls_execute_strict_without_legacy(self):
        from test_compiled_contexts import StrictContextTests
        case=StrictContextTests()
        case.run_existing([
            'test_source_forms.SourceNoContextTests.test_nocontext_scalar_form_attribute_argument',
            'test_source_forms.SourceNoContextTests.test_same_server_call_uses_formless_activation',
            'test_source_forms.SourceNoContextTests.test_nocontext_cannot_read_form_state_or_parameters',
            'test_source_forms.SourceNoContextTests.test_same_server_does_not_inherit_bound_form_services',
            'test_source_forms.SourceNoContextTests.test_nocontext_cannot_activate_database_transaction',
        ],('_SourceNoContextInterpreter',))

    def test_inline_nocontext_node_budget_precedes_literal_execution(self):
        from test_source_forms import SourceNoContextTests
        fixture=SourceNoContextTests()
        with execution_backend_policy('python-direct'):
            controller=fixture.controller()
            vm=controller.nocontext.prototype
            program=parse('42;')
            vm._source_call_budget[0]=100000
            with self.assertRaisesRegex(FormLimitError,'Source NoContext execution limit'):
                vm.execute_program(program)
            self.assertEqual(vm._source_call_budget[0],100001)
