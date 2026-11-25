"""Direct session startup uses an isolated server initializer, not client RPC."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_configuration_session_parameters import files_for_session
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.direct.python_direct_configuration_sessions import SessionStartup
from yadinassi.execution.direct import python_direct_configuration_metadata as readers
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import HostFunction


class DirectConfigurationSessionTests(unittest.TestCase):
    def app(self,files=None,**kwargs):
        files=files_for_session() if files is None else files
        app=ConfigurationApplication.from_files(files,**kwargs)
        self.addCleanup(lambda:app.close(force=True))
        return app

    def test_startup_failure_clears_values_and_closes_family(self):
        app=self.app(files_for_session('Procedure SessionParametersSetting(P) '
            'SessionParameters.Flag=True; Raise "fail after write"; EndProcedure'))
        self.assertEqual(app.state,'prepared')
        with self.assertRaisesRegex(BSLRuntimeError,'fail after write'):app.start()
        self.assertEqual(app.state,'failed')
        self.assertEqual(app.session_parameters._values,{})
        self.assertTrue(app.session_parameters._closed)
        self.assertTrue(app.interpreter._family_closed)

    def test_sqlite_owned_application_can_start_without_db_operations(self):
        files=files_for_session()
        config=import_configuration(files,module_runtime=MODULE_RUNTIME)
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        context=SQLiteDBContext.create(Path(folder.name)/'config.sqlite',config)
        self.addCleanup(context.close)
        app=self.app(files,database_context=context)
        self.assertTrue(app.start())
        self.assertTrue(app.session_parameters._values['ready'])
        self.assertEqual(app.session_parameters._values['calls'],Decimal(0))
        self.assertIsNone(context.backend._active)

    def test_absent_handler_leaves_declared_parameters_unset(self):
        app=self.app(files_for_session(''))
        self.assertTrue(app.start())
        from yadinassi.application.session_parameters import _UNSET
        self.assertIs(app.session_parameters._values['flag'],_UNSET)
        self.assertIsNone(app._session_owner)

    def test_client_metadata_names_are_readonly_and_do_not_read_session_values(self):
        app=self.app(files_for_session(''))
        self.assertTrue(app.start())
        before=dict(app.session_parameters._values)
        with patch.object(readers,'validate_definition',side_effect=AssertionError('unrelated common module')):
            self.assertEqual(app.execute('Metadata.SessionParameters.Count()'), Decimal(5))
            self.assertEqual(app.execute('Метаданные.ПараметрыСеанса.Получить(0).Имя'), 'Ready')
            self.assertEqual(app.execute('Metadata.SessionParameters["text"].FullName()'), 'ПараметрСеанса.Text')
            self.assertTrue(app.execute(
                '(Metadata.FindByFullName("ПараметрСеанса.FLAG")=Metadata.SessionParameters.Flag)'))
            with self.assertRaises(PythonDirectUnsupported):
                app.execute('Tmp=Metadata.SessionParameters.Flag;')
        self.assertNotIn('tmp',app.interpreter.variables)
        self.assertEqual(app.session_parameters._values,before)

    def test_fullname_dispatch_preserves_existing_enum_metadata(self):
        from test_configuration_enumerations import enum_files
        files=files_for_session('')
        files['Configuration.xml']=files['Configuration.xml'].replace(
            b'</ChildObjects>',b'<Enum>Status</Enum></ChildObjects>')
        files['Enums/Status.xml']=enum_files()['Enums/Status.xml']
        app=self.app(files); self.assertTrue(app.start())
        self.assertEqual(app.execute('Metadata.FindByFullName("Enum.Status").Name'),'Status')
        self.assertEqual(app.execute('Metadata.FindByFullName("SessionParameter.Flag").Name'),'Flag')

    def test_startup_uses_canonical_message_without_inheriting_host_services(self):
        messages, calls = [], []
        app=self.app(files_for_session('Procedure SessionParametersSetting(P) '
            'Message("first"); Сообщить("second"); EndProcedure'), output=messages.append)
        self.assertTrue(app.start())
        self.assertEqual(messages,['first','second'])

        denied=self.app(files_for_session('Procedure SessionParametersSetting(P) '
            'OtherService(); EndProcedure'),
            host_services={'OtherService':HostFunction('OtherService', lambda:calls.append(True))})
        with self.assertRaisesRegex(BoundaryViolation,'unsupported session initializer host service'):
            denied.start()
        self.assertEqual(calls,[])

    def test_pure_startup_loop_has_no_routine_context_checks(self):
        check=SessionStartup._check
        counts=[]
        for iterations in (1,128):
            source=('Procedure УстановкаПараметровСеанса(P) '
                    'Total=0; For I=1 To '+str(iterations)+' Do Total=Total+1; EndDo; '
                    'SessionParameters["Calls"]=Total; '
                    'ПараметрыСеанса.Ready=SessionParameters.Calls=Total; EndProcedure')
            app=self.app(files_for_session(source))
            calls=[]
            def observe(context):
                calls.append(None)
                return check(context)
            with patch.object(SessionStartup,'_check',observe), \
                 patch.object(BoundaryContext,'checkpoint',side_effect=AssertionError('routine checkpoint')):
                self.assertTrue(app.start())
            self.assertEqual(app.session_parameters._values['calls'],Decimal(iterations))
            self.assertTrue(app.session_parameters._values['ready'])
            counts.append(len(calls))
        self.assertEqual(counts,[2,2])

    def endpoint(self,app):
        from yadinassi.execution.invocation import InvocationPort, InvocationServer
        self.assertTrue(app.start())
        server=InvocationServer.from_handlers(app.server_endpoints,message_scope=app.event_messages)
        port=InvocationPort(server.exchange)
        bindings={binding.name:binding for binding in app.server_bindings}
        return lambda name,*arguments:port.invoke(bindings[name],list(arguments))

    def test_explicit_server_reads_and_writes_its_own_session(self):
        from yadinassi.execution.invocation import InvocationError
        files=files_for_session()
        first=self.app(files,side='server')
        second=self.app(files,side='server')
        invoke=self.endpoint(first)
        other=self.endpoint(second)
        self.assertIs(invoke('Read','Ready'),True)
        self.assertIs(invoke('Read','Flag'),False)
        self.assertIs(invoke('Read','FLAG'),False)
        self.assertEqual(invoke('Read','Calls'),Decimal(1))
        with self.assertRaisesRegex(InvocationError,'server_error'):
            invoke('Read','Missing')
        self.assertEqual(invoke('Read','Calls'),Decimal(1))

        invoke('Write','Text','value')
        with self.assertRaisesRegex(InvocationError,'server_error'):
            invoke('Write','Text',Decimal(3))
        self.assertEqual(invoke('Read','Text'),'value')
        self.assertEqual(other('Read','Calls'),Decimal(0))
        with self.assertRaisesRegex(InvocationError,'server_error'):
            other('Read','Text')
        with self.assertRaisesRegex(InvocationError,'result_unavailable'):
            invoke('Handle') # the existing transport must never export the namespace
        self.assertEqual(first.session_parameters._initializing,set())
        self.assertEqual(second.session_parameters._initializing,set())

    def test_revoked_configured_wire_endpoint_gives_a_finite_unknown_outcome(self):
        from yadinassi.execution.invocation import InvocationError, InvocationPort, InvocationServer

        app = self.app(files_for_session(), side='server')
        self.assertTrue(app.start())
        server = InvocationServer.from_handlers(app.server_endpoints, message_scope=app.event_messages)
        binding = next(item for item in app.server_bindings if item.name == 'Read')
        owner = app._modules['access', 'server'].interpreter
        before = dict(app.session_parameters._values)
        with patch.object(server, 'exchange', wraps=server.exchange) as exchange:
            port = InvocationPort(exchange)
            with patch.dict(owner.server_routines):
                del owner.server_routines['read']
                with self.assertRaisesRegex(InvocationError, 'result_unavailable'):
                    port.invoke(binding, ['Ready'])
            self.assertTrue(port.uncertain)
            with self.assertRaisesRegex(InvocationError, 'outcome_unknown'):
                port.invoke(binding, ['Ready'])
            exchange.assert_called_once()
        self.assertEqual(app.session_parameters._values, before)

    def test_configured_wire_discards_output_from_revoked_endpoint(self):
        from yadinassi.application.session_parameters import BSLSessionParameters
        from yadinassi.execution.invocation import InvocationError, InvocationPort, InvocationServer

        files = files_for_session()
        files['CommonModules/Access/Ext/Module.bsl'] += b"""
Function Check() Export
    Message("before denial");
    Try
        Return SessionParameters.Ready;
    Except
        Mark();
        Return False;
    EndTry;
EndFunction
"""
        caught = []
        app = self.app(files, side='server', host_services={
            'Mark': HostFunction('Mark', lambda: caught.append(True), returns_value=False)})
        self.assertTrue(app.start())
        server = InvocationServer.from_handlers(app.server_endpoints, message_scope=app.event_messages)
        port = InvocationPort(server.exchange)
        binding = next(item for item in app.server_bindings if item.name == 'Check')
        messages = []
        with patch.object(server, '_message', wraps=server._message) as emit, \
                patch.object(BSLSessionParameters, 'read', side_effect=AssertionError('unadmitted read')):
            with self.assertRaisesRegex(InvocationError, 'result_unavailable'):
                port.invoke(binding, [], output=messages.append)
            emit.assert_called_once_with('before denial')
        self.assertEqual(caught, [])
        self.assertEqual(messages, [])
        self.assertTrue(port.uncertain)

    def test_explicit_server_lazy_failure_releases_initializer(self):
        from yadinassi.execution.invocation import InvocationError
        app=self.app(files_for_session('''Procedure SessionParametersSetting(P)
        If P<>Undefined Then
            SessionParameters.Calls=SessionParameters.Calls+1;
            X=ПараметрыСеанса.Flag;
        Else
            SessionParameters.Calls=0;
        EndIf;
        EndProcedure'''),side='server')
        invoke=self.endpoint(app)
        for expected in (1,2):
            with self.assertRaisesRegex(InvocationError,'server_error'):
                invoke('Read','Flag')
            self.assertEqual(app.session_parameters._initializing,set())
            self.assertEqual(invoke('Read','Calls'),Decimal(expected))
        app.close(force=True)
        with self.assertRaisesRegex(InvocationError,'server_error'):
            invoke('Read','Calls')

    def test_explicit_server_rejects_another_applications_session_store(self):
        from yadinassi.execution.invocation import InvocationError
        first=self.app(files_for_session(''),side='server')
        second=self.app(files_for_session(''),side='server')
        invoke=self.endpoint(first)
        other=self.endpoint(second)
        other('Write','Flag',False)
        with patch.object(first,'session_parameters',second.session_parameters):
            with self.assertRaisesRegex(InvocationError,'server_error'):
                invoke('Read','Flag')
            with self.assertRaisesRegex(InvocationError,'server_error'):
                invoke('Write','Flag',True)
        self.assertIs(other('Read','Flag'),False)
        with self.assertRaisesRegex(InvocationError,'server_error'):
            invoke('Read','Flag')


    def test_explicit_lazy_admission_does_not_wait_for_iteration(self):
        from yadinassi.types.values import BSLArray
        for files in (files_for_session(),files_for_session('')):
            app=self.app(files,side='server')
            self.assertTrue(app.start())
            before=dict(app.session_parameters._values)
            request=BSLArray()
            request.items.append('Flag')  # not an active read of Flag
            for argument in (None,request):
                with self.subTest(initializer=bool(app._session_binding),argument=argument):
                    with self.assertRaisesRegex(BoundaryViolation,'invalid lazy session parameter request'):
                        app.initialize_session_parameters(app.interpreter,argument)
            self.assertEqual(app.session_parameters._values,before)


    def test_explicit_endpoint_absent_initializer_keeps_native_unset_error(self):
        app=self.app(files_for_session(''),side='server')
        self.assertTrue(app.start())
        binding=next(item for item in app.server_bindings if item.name=='Read')
        _,invoke=app.server_endpoints[binding.endpoint]
        with self.assertRaisesRegex(BSLRuntimeError,'not set'):
            invoke(['Flag'])
        self.assertEqual(app.session_parameters._initializing,set())
