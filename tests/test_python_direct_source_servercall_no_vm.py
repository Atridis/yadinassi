"""Bounded source ServerCall uses generated code, never VM routine dispatch."""
import unittest
from unittest.mock import patch
import test_source_server_call as existing
from yadinassi.runtime import Interpreter


class DirectSourceServerCallNoVM(unittest.TestCase):
    run_app = existing.SourceServerCallTests.run_app
    with_extra = existing.SourceServerCallTests.with_extra

    def setUp(self):
        for name in ('_execute_program', 'call_routine', '_planned_routine_block'):
            poison = patch.object(Interpreter, name, side_effect=AssertionError('legacy ' + name))
            poison.start()
            self.addCleanup(poison.stop)

    test_client_server_function = existing.SourceServerCallTests.test_client_server_function
    test_server_metadata_retained = existing.SourceServerCallTests.test_server_metadata_retained
    test_same_module_private_helper = existing.SourceServerCallTests.test_same_module_private_helper
    test_private_export_not_exposed = existing.SourceServerCallTests.test_private_export_not_exposed
    test_server_call_flag_required = existing.SourceServerCallTests.test_server_call_flag_required
    test_privileged_not_granted = existing.SourceServerCallTests.test_privileged_not_granted
    test_named_global_not_granted = existing.SourceServerCallTests.test_named_global_not_granted
    test_val_isolated_collection = existing.SourceServerCallTests.test_val_isolated_collection
    test_safe_mode_cannot_cross = existing.SourceServerCallTests.test_safe_mode_cannot_cross
    test_server_no_client_access = existing.SourceServerCallTests.test_server_no_client_access
    test_profile_retained_in_server_helpers = existing.SourceServerCallTests.test_profile_retained_in_server_helpers
    test_foreign_caller_rejected = existing.SourceServerCallTests.test_foreign_caller_rejected
    test_closed_cached_module_rejected = existing.SourceServerCallTests.test_closed_cached_module_rejected
    test_nested_server_module_without_external_servercall = existing.SourceServerCallTests.test_nested_server_module_without_external_servercall
    test_cached_internal_server_not_exposed_to_client = existing.SourceServerCallTests.test_cached_internal_server_not_exposed_to_client
    test_server_global_available_in_activation = existing.SourceServerCallTests.test_server_global_available_in_activation
    test_both_sides_remain_client_local = existing.SourceServerCallTests.test_both_sides_remain_client_local
    test_server_safe_counter_cleans_on_return_and_error = existing.SourceServerCallTests.test_server_safe_counter_cleans_on_return_and_error

    def test_named_val_read_after_later_argument_effect(self):
        app, output = self.run_app(existing.configuration('',
            'Function Read(Val First, Val Second) Export Return First; EndFunction'))
        app.interpreter.execute('Var X; Function Touch() X=2; Return 0; EndFunction')
        app.interpreter.execute('X=1; Message(ServerAPI.Read(X,Touch())); Message(X);')
        self.assertEqual(output, ['2', '2'])

    def test_return_is_detached_and_activation_is_closed(self):
        app, output = self.run_app(existing.configuration('',
            'Function Make() Export A=New Array; A.Add(1); Return A; EndFunction'))
        app.interpreter.execute('A=ServerAPI.Make(); A.Add(2); Message(ServerAPI.Make().Count());')
        self.assertEqual(output, ['1'])
        self.assertEqual(app.interpreter.execution_context, 'client')
        self.assertEqual(app.interpreter._module_context_stack, [True])

    def test_unsupported_packet_and_throw_restore_side(self):
        app, output = self.run_app(existing.configuration('',
            'Function Bad() Export Return Metadata; EndFunction\n'
            'Function Throw() Export Raise "stop"; EndFunction\n'
            'Function Good() Export Return 7; EndFunction'))
        app.interpreter.execute('Try X=ServerAPI.Bad(); Except Message("rejected"); EndTry;'
                                'Try X=ServerAPI.Throw(); Except Message("thrown"); EndTry;'
                                'Message(ServerAPI.Good());')
        self.assertEqual(output, ['rejected', 'thrown', '7'])
        self.assertEqual(app.interpreter.execution_context, 'client')
        self.assertEqual(app.interpreter._module_context_stack, [True])

    def test_byref_and_default_rejected_before_effects(self):
        for body, call in (
            ('Function Bad(X) Export Return X; EndFunction', 'ServerAPI.Bad(Touch())'),
            ('Function Bad(Val X=1) Export Return X; EndFunction', 'ServerAPI.Bad(Touch())'),
        ):
            with self.subTest(body=body):
                app, output = self.run_app(existing.configuration('', body))
                app.interpreter.execute('Function Touch() Message("wrong"); Return 1; EndFunction')
                app.interpreter.execute('Try X=' + call + '; Except Message("rejected"); EndTry;')
                self.assertEqual(output, ['rejected'])


if __name__ == '__main__':
    unittest.main()
