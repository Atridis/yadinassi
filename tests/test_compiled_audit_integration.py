"""Audit optimizations retain strict execution, without legacy visitors."""
import unittest
import test_compiled_contexts as contexts

class CompiledAuditIntegrationTests(unittest.TestCase):
    def test_scalar_server_reuse(self):
        contexts.StrictContextTests().run_existing([
            'test_source_server_reuse.SourceServerReuseTests.test_session_cache_refresh_and_application_separation',
            'test_source_server_reuse.SourceServerReuseTests.test_request_boundary_and_failure_cleanup',
            'test_source_server_reuse.SourceServerReuseTests.test_native_event_sequence',
        ], ('_SourceInterpreter',))

    def test_constant_descriptors_keep_value_manager_context(self):
        contexts.StrictContextTests().run_existing([
            'test_source_constant_handlers.SourceConstantHandlerTests.test_value_passed_to_helper_by_reference_updates_typed_storage',
        ], ('_SourceInterpreter', '_ValueInterpreter'))
