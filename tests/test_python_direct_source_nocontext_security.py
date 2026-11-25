"""NoContext activation cannot gain form or mutable host capabilities."""
import unittest
from unittest.mock import patch
import test_source_forms as existing
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class SourceNoContextSecurity(unittest.TestCase):
    app=existing.SourceFormTests.app
    controller=existing.SourceNoContextTests.controller
    run_command=existing.SourceNoContextTests.run_command

    def test_prototype_signature_tampering_does_not_run(self):
        for server in (False,True):
            with self.subTest(server=server):
                controller=self.controller(server_call=server)
                routine=controller.nocontext.prototype.server_routines['calculate']
                routine.parameters[0].by_value=False
                with self.assertRaises(BoundaryViolation):
                    self.run_command(controller)
                self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'initial')
                self.assertEqual(controller.application.interpreter.execution_context,'client')

    def test_host_registration_tampering_does_not_invoke_callback(self):
        for server in (False,True):
            with self.subTest(server=server):
                controller=self.controller('Return String(StrLen(Value));',server_call=server)
                callback=unittest.mock.Mock(return_value=999)
                controller.nocontext.prototype.functions['strlen'].function=callback
                with self.assertRaises(BoundaryViolation):
                    self.run_command(controller)
                callback.assert_not_called()
                self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'initial')

    def test_constructor_tampering_rejected_before_callback(self):
        from yadinassi.forms.source_forms import _SourceNoContextInterpreter
        controller=self.controller()
        callback=unittest.mock.Mock(side_effect=AssertionError('wrong-constructor'))
        with patch.object(_SourceNoContextInterpreter,'__init__',callback):
            with self.assertRaises(BoundaryViolation):
                self.run_command(controller)
        callback.assert_not_called()

    def test_same_app_foreign_controller_executor_rejected(self):
        from yadinassi.forms.source_forms import SourceFormController
        for server in (False,True):
            with self.subTest(server=server):
                controller=self.controller(server_call=server)
                other=SourceFormController(controller.application,'CommonForm.Main')
                self.assertIsNone(other.exchange(existing.request())['result']['error'])
                session=controller.server.session if server else controller.client.session
                session._direct_source_nocontext_server=other.nocontext
                with self.assertRaises(BoundaryViolation):
                    self.run_command(controller)
                self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'initial')

    def test_installed_port_callback_cannot_be_replaced(self):
        controller=self.controller()
        vm=controller.client.session.interpreter
        stub,_=vm._invocation_bindings['calculate']
        callback=unittest.mock.Mock(return_value='wrong')
        vm._invocation_bindings['calculate']=(stub,callback)
        with self.assertRaises(BoundaryViolation):
            self.run_command(controller)
        callback.assert_not_called()
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'initial')

    def test_wire_or_endpoint_callback_cannot_be_retargeted(self):
        for replacement in ('wire','endpoint','scope'):
            with self.subTest(replacement=replacement):
                controller=self.controller()
                callback=unittest.mock.Mock(return_value='wrong')
                wire=controller.nocontext.server
                if replacement == 'wire':
                    from types import SimpleNamespace
                    controller.nocontext.server=SimpleNamespace(exchange=callback)
                elif replacement == 'endpoint':
                    endpoint=next(iter(wire._callbacks))
                    wire._callbacks[endpoint]=callback
                else:
                    wire._message_scope=callback
                with self.assertRaises(BoundaryViolation):
                    self.run_command(controller)
                callback.assert_not_called()
                self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'initial')


if __name__ == '__main__':
    unittest.main()
