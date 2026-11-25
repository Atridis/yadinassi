"""Application-owned welcome form, without broad host-object grants."""
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.forms.form_runtime import FormSession
from yadinassi.ui.configuration_app import load_application
from yadinassi.ui.main_demo import form_family
from yadinassi.configuration.configuration_main_demo import import_main_demo_configuration,PROFILE
from yadinassi.execution.invocation import InvocationServer
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from test_main_demo_configuration import source
ROOT=Path(__file__).resolve().parents[1]/'examples/demo'

class BoundFormTests(unittest.TestCase):
    def setup_apps(self):
        config=import_main_demo_configuration(source(),profile=PROFILE)
        server=form_family(config,side='server');self.addCleanup(lambda:server.close(force=True));server.start()
        endpoint=InvocationServer.from_handlers(server.server_endpoints,message_scope=server.event_messages)
        self.requests=[];self.output=[];self.opens=[]
        def exchange(raw):self.requests.append(raw);return endpoint.exchange(raw)
        client=form_family(config,side='client',server_exchange=exchange,output=self.output.append,
            host_services={'OpenForm':HostFunction('OpenForm',lambda name:self.opens.append(name),returns_value=False),
                           'ОткрытьФорму':HostFunction('ОткрытьФорму',lambda name:self.opens.append(name),returns_value=False)})
        self.addCleanup(lambda:client.close(force=True));client.start()
        return server,client
    def test_real_welcome_created_and_details_common_calls_no_vm(self):
        with patch.object(Interpreter,'execute_program',side_effect=AssertionError('VM execute')):
            server,client=self.setup_apps()
            definition=load_application(ROOT,main_demo_application=True).forms['commonform.demowelcome']
            remote=definition.create_server(interpreter_factory=server.form_interpreter_factory).session
            remote._begin(0)
            try:
                self.assertEqual(remote._event('oncreateatserver',[False,True]),[False,True])
                self.assertIn('одной базе',remote.form.get_member('Greeting'))
            finally:remote._busy=False;remote._gate.release()
            session=FormSession(definition.program.client,interpreter_factory=client.form_interpreter_factory,output=self.output.append)
            session._begin(0)
            try:session._invoke('ShowDetails','client',[None])
            finally:session._busy=False;session._gate.release()
        self.assertEqual(self.output[-2:],['Вычислено в серверном процессе приложения','5'])
        self.assertEqual(self.opens,['CommonForm.OperationDraft'])
        self.assertEqual(len(self.requests),2) # startup and Add, not retries
    def test_closed_application_denies(self):
        _,client=self.setup_apps()
        session=FormSession('Procedure Event() Message("bad");EndProcedure',interpreter_factory=client.form_interpreter_factory)
        session._begin(0)
        try:
            client.close(force=True)
            with self.assertRaises((ValueError,BoundaryViolation)):session._invoke('Event','client',[])
        finally:session._busy=False;session._gate.release()
    def test_form_and_arbitrary_host_members_still_deny(self):
        _,client=self.setup_apps()
        session=FormSession('Procedure Event() x=ThisObject._session;EndProcedure',interpreter_factory=client.form_interpreter_factory)
        session._begin(0)
        try:
            with self.assertRaises(BoundaryViolation):session._invoke('Event','client',[])
        finally:session._busy=False;session._gate.release()
