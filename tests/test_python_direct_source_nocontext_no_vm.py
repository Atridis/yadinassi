"""Source NoContext RPC and same-server paths never dispatch VM routine bodies."""
import unittest
import test_source_forms as existing


class SourceNoContextNoVM(existing.SourceNoContextTests):
    def test_same_server_result_stays_scalar(self):
        controller=self.controller('Return New Array;',server_call=True)
        self.assertIsNotNone(self.run_command(controller)['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'initial')

    def test_event_error_does_not_leave_nocontext_side(self):
        for server in (False,True):
            with self.subTest(server=server):
                controller=self.controller('Raise "failure";',server_call=server)
                self.assertIsNotNone(self.run_command(controller)['error'])
                app=controller.application
                self.assertEqual(app.interpreter.execution_context,'client')
                self.assertEqual(app.interpreter._module_context_stack,[True])
                self.assertIsNotNone(self.run_command(controller)['error'])
                self.assertEqual(app.interpreter.execution_context,'client')


if __name__ == '__main__':
    unittest.main()
