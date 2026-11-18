"""Owning profiles use direct AST code, preserving original public scenarios."""
import unittest
from unittest.mock import patch

class OwningProfilesTests(unittest.TestCase):
    def scenario(self,module,cls,name):
        from importlib import import_module
        original=getattr(import_module(module),cls)(name)
        self.addCleanup(original.doCleanups)
        with patch('yadinassi.experimental_naked_collections.prepare',side_effect=AssertionError('old compiler')):
            original.setUp()
            try:getattr(original,name)()
            finally:original.tearDown()

    def test_configuration_startup(self):
        self.scenario('test_python_direct_configuration','DirectConfigurationTests','test_exact_startup_and_one_packet_without_ast_dispatch')
    def test_configuration_command(self):
        self.scenario('test_python_direct_configuration_commands','DirectConfigurationCommandTests','test_cross_module_repeated_nested_calls_and_no_legacy')
    def test_form_event_and_catalog_preparation(self):
        self.scenario('test_python_direct_prepared_form_events','PreparedFormEventsTests','test_product_event_and_object_code_reused_with_fresh_cancellation')
    def test_posting(self):
        self.scenario('test_python_direct_posting_names','PostingNamesTests','test_number_call_keeps_field_read_and_ignores_parent_override')
    def test_catalog_original_write(self):
        self.scenario('test_python_direct_catalog_preparation','DirectCatalogPreparationTests','test_original_handler_writes_without_vm_execution')

    def test_posting_style_unknown_host_argument_never_leaks_sentinel(self):
        from yadinassi.experimental_direct_ast import compile_owned
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        from yadinassi.syntax.parser import parse
        from yadinassi.errors import BSLRuntimeError
        text='Procedure Event() Capture(Missing);EndProcedure Event();'
        plan=compile_owned(parse(text),source_text=text,source_name='<host-binding>',host_bindings=True)
        seen=[];context=BoundaryContext(services={'capture':seen.append})
        # Undeclared state does not become a routine-local binding or a grant.
        with self.assertRaises(BSLRuntimeError):plan.run({'missing':42},context=context)
        self.assertEqual(seen,[])
