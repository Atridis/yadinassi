"""Session-parameter lifecycle and metadata contracts for their respective hosts."""
from decimal import Decimal
from uuid import uuid4
import unittest
from unittest.mock import patch
from configuration_runtime_fixture import module_files, SERVER
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.types.errors import BSLRuntimeError


ACCESS='''Function Read(Val Name) Export Return SessionParameters[Name]; EndFunction
Procedure Write(Val Name, Val Value) Export SessionParameters[Name]=Value; EndProcedure
Function Handle() Export Return SessionParameters; EndFunction'''
TYPES={
 'Ready':'<v8:Type>xs:boolean</v8:Type>',
 'Flag':'<v8:Type>xs:boolean</v8:Type>',
 'Other':'<v8:Type>xs:boolean</v8:Type>',
 'Text':'<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>64</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>',
 'Calls':'<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>8</v8:Digits><v8:FractionDigits>0</v8:FractionDigits><v8:AllowedSign>Nonnegative</v8:AllowedSign></v8:NumberQualifiers>',
}
DEFAULT='''Procedure SessionParametersSetting(RequiredParameters)
If RequiredParameters=Undefined Then
 SessionParameters.Ready=True; SessionParameters.Calls=0;
Else
 SessionParameters.Calls=SessionParameters.Calls+1;
 If RequiredParameters[0]="Flag" Then SessionParameters.Flag=False; EndIf;
EndIf;
EndProcedure'''


def files_for_session(source=DEFAULT, application=''):
    files=module_files((('Access',ACCESS,SERVER),),application=application)
    for name,definition in TYPES.items():
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',('<SessionParameter>'+name+'</SessionParameter></ChildObjects>').encode())
        files['SessionParameters/'+name+'.xml']=('''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema" version="2.20"><SessionParameter uuid="'''+str(uuid4())+'"><Properties><Name>'+name+'</Name><Synonym/><Comment/><Type>'+definition+'</Type></Properties></SessionParameter></MetaDataObject>').encode()
    files['Ext/SessionModule.bsl']=source.encode()
    return files


class ConfigurationSessionParameterTests(unittest.TestCase):
    def application(self,files=None,*,start=True,side=None,output=lambda value:None):
        app=ConfigurationApplication.from_files(files_for_session() if files is None else files,side=side,output=output)
        self.addCleanup(lambda:app.close(force=True))
        if start:app.start()
        return app

    def source_application(self,files=None,*,output=lambda value:None):
        # Tests of the BSL application lifecycle use the source host. The
        # separate explicit ConfigurationApplication API has different entry
        # and transport contracts; keep its activation/negative tests there.
        files=dict(files_for_session() if files is None else files)
        files.setdefault('Ext/ManagedApplicationModule.bsl',b'')
        app=SourceApplication(import_source(files),output=output)
        self.addCleanup(app.close)
        app.start()
        return app

    def test_import_is_inert_and_requires_explicit_profile(self):
        files=files_for_session();result=import_configuration(files,module_runtime=MODULE_RUNTIME)
        self.assertEqual(len(result.session_parameters),5)
        self.assertEqual(result.activation_issues,())
        self.assertEqual({f.path:f.content for f in result.files},files)
        self.assertTrue(import_configuration(files).activation_issues)

    def test_construction_does_not_execute_handler(self):
        app=self.application(files_for_session('Procedure SessionParametersSetting(P) Raise "not construction"; EndProcedure'),start=False)
        self.assertEqual(app.state,'prepared')
        with self.assertRaisesRegex(BSLRuntimeError,'not construction'):app.start()
        self.assertEqual(app.state,'failed')

    def test_startup_precedes_application_event(self):
        output=[]
        app=self.source_application(files_for_session(application='Procedure BeforeStart(Cancel) Message(Access.Read("Ready")); EndProcedure'),output=output.append)
        self.assertEqual(output,['Да'])
        self.assertTrue(app.interpreter.execute('Access.Read("Ready")'))

    def test_lazy_false_is_a_set_value_and_does_not_repeat(self):
        app=self.source_application()
        self.assertFalse(app.interpreter.execute('Access.Read("Flag")'))
        self.assertFalse(app.interpreter.execute('Access.Read("Flag")'))
        self.assertEqual(app.interpreter.execute('Access.Read("Calls")'),Decimal(1))

    def test_unset_is_not_scalar_default(self):
        app=self.source_application()
        with self.assertRaisesRegex(BSLRuntimeError,'not set'):app.interpreter.execute('Access.Read("Other")')

    def test_unknown_name_rejected_without_handler(self):
        app=self.source_application()
        with self.assertRaisesRegex(BSLRuntimeError,'unknown session parameter'):app.interpreter.execute('Access.Read("Missing")')
        self.assertEqual(app.interpreter.execute('Access.Read("Calls")'),Decimal(0))

    def test_server_dot_and_index_share_values(self):
        from yadinassi.execution.invocation import InvocationPort, InvocationServer

        files = files_for_session()
        files['CommonModules/Access/Ext/Module.bsl'] += b"\n" + '''Function DotToIndex() Export
            SessionParameters.Text="value";
            Return ПараметрыСеанса["text"];
        EndFunction
        Function IndexToDot() Export
            SessionParameters["Flag"]=True;
            Return ПараметрыСеанса.Flag;
        EndFunction'''.encode()
        app = self.application(files,side='server')
        server = InvocationServer.from_handlers(app.server_endpoints,message_scope=app.event_messages)
        port = InvocationPort(server.exchange)
        bindings = {binding.name:binding for binding in app.server_bindings}
        self.assertEqual(port.invoke(bindings['DotToIndex'],[]),'value')
        self.assertIs(port.invoke(bindings['IndexToDot'],[]),True)
        self.assertEqual(port.invoke(bindings['Read'],['Text']),'value')
        self.assertIs(port.invoke(bindings['Read'],['Flag']),True)

    def test_server_facade_denies_direct_command_without_running_it(self):
        from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
        from yadinassi.execution.invocation import InvocationPort, InvocationServer

        output = []
        app = self.application(side='server',output=output.append)
        before = dict(app.session_parameters._values)
        with self.assertRaisesRegex(PythonDirectUnsupported,'require a client application'):
            app.execute('Message("must not emit");SessionParameters.Text="must not write";')
        self.assertEqual(app.session_parameters._values,before)
        self.assertEqual(output,[])
        self.assertEqual(app.state,'running')
        server = InvocationServer.from_handlers(app.server_endpoints,message_scope=app.event_messages)
        binding = next(binding for binding in app.server_bindings if binding.name=='Read')
        self.assertIs(InvocationPort(server.exchange).invoke(binding,['Ready']),True)

    def test_logical_client_has_no_session_parameter_global(self):
        app=self.source_application()
        with self.assertRaisesRegex(BSLRuntimeError,'server application context'):app.interpreter.execute('SessionParameters.Flag')
        with self.assertRaises(BSLRuntimeError):app.interpreter.execute('Access.Handle()')

    def test_typed_assignment_preserves_value_on_failure(self):
        app=self.source_application()
        app.interpreter.execute('Access.Write("Flag",True);')
        with self.assertRaises(BSLRuntimeError):app.interpreter.execute('Access.Write("Flag",3);')
        self.assertTrue(app.interpreter.execute('Access.Read("Flag")'))

    def test_sessions_do_not_share_state(self):
        files=files_for_session();a=self.source_application(files);b=self.source_application(files)
        a.interpreter.execute('Access.Write("Text","only a");')
        with self.assertRaisesRegex(BSLRuntimeError,'not set'):b.interpreter.execute('Access.Read("Text")')
        self.assertEqual(a.interpreter.execute('Access.Read("Text")'),'only a')

    def test_closed_namespace_cannot_be_reused_in_another_application(self):
        app = self.application(side='server')
        namespace = app.session_parameters
        app.close(force=True)
        other = self.application(side='server')
        binding = next(binding for binding in other.server_bindings if binding.name=='Read')
        _, invoke = other.server_endpoints[binding.endpoint]
        before = dict(other.session_parameters._values)
        # Enter the still-running second application through its admitted
        # server endpoint, with the retired first application's store.
        with patch.object(other,'session_parameters',namespace):
            with self.assertRaisesRegex(BSLRuntimeError,'another or closed application'):
                invoke(['Flag'])
        self.assertEqual(namespace._values,{})
        self.assertEqual(other.session_parameters._values,before)
        self.assertFalse(invoke(['Flag']))

    def test_recursive_lazy_access_is_bounded(self):
        source='''Procedure SessionParametersSetting(P)
If P<>Undefined Then X=SessionParameters.Flag; EndIf;
EndProcedure'''
        app=self.source_application(files_for_session(source))
        with self.assertRaisesRegex(BSLRuntimeError,'recursive session parameter'):app.interpreter.execute('Access.Read("Flag")')
        self.assertEqual(app.session_parameters._initializing,set())

    def test_session_module_exports_and_top_level_code_rejected(self):
        for source in ('Procedure X() Export EndProcedure','Message("should not run");','Var Counter;'):
            with self.subTest(source=source),self.assertRaises(ValueError):
                self.application(files_for_session(source),start=False)

    def test_ambiguous_handler_alias_rejected(self):
        source='Procedure SessionParametersSetting(P) EndProcedure\nProcedure УстановкаПараметровСеанса(P) EndProcedure'
        with self.assertRaises(ValueError):self.application(files_for_session(source),start=False)

    def test_session_module_can_use_server_common_module(self):
        source='''Procedure SessionParametersSetting(P)
If P=Undefined Then Access.Write("Ready",True); EndIf;
EndProcedure'''
        app=self.source_application(files_for_session(source))
        self.assertTrue(app.interpreter.execute('Access.Read("Ready")'))

    def test_missing_handler_keeps_parameters_unset(self):
        app=self.source_application(files_for_session(''))
        with self.assertRaisesRegex(BSLRuntimeError,'not set'):app.interpreter.execute('Access.Read("Flag")')

    def test_foreign_schema_type_and_unknown_component_rejected(self):
        for before,after in ((b'xs:boolean',b'xs:base64Binary'),(b'</SessionParameter>',b'<ChildObjects/></SessionParameter>')):
            files=files_for_session();files['SessionParameters/Flag.xml']=files['SessionParameters/Flag.xml'].replace(before,after)
            with self.subTest(before=before),self.assertRaises(ValueError):
                import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_double_start_is_rejected(self):
        app=self.application()
        with self.assertRaises(ValueError):app.start()

    def test_declared_metadata_is_ordered_without_initializing_values(self):
        app=self.source_application()
        self.assertEqual(app.interpreter.execute('Metadata.SessionParameters.Count()'),Decimal(5))
        self.assertEqual(app.interpreter.execute('Метаданные.ПараметрыСеанса.Get(0).Name'),'Ready')
        self.assertEqual(app.interpreter.execute('Access.Read("Calls")'),Decimal(0))

    def test_parameter_metadata_exposes_qualified_type_not_runtime_value(self):
        app=self.source_application()
        vm=app.interpreter
        self.assertTrue(vm.execute('Metadata.SessionParameters.Flag.Type.ContainsType(Type("Boolean"))'))
        self.assertEqual(vm.execute('Metadata.SessionParameters.Text.Type.StringQualifiers.Length'),Decimal(64))
        self.assertEqual(vm.execute('Metadata.SessionParameters.Calls.Type.NumberQualifiers.Digits'),Decimal(8))

    def test_source_parameter_metadata_type_is_readonly_and_does_not_initialize(self):
        app=self.source_application()
        before=dict(app.session_parameters._values)
        vm=app.interpreter
        self.assertFalse(vm.execute('Метаданные.ПараметрыСеанса["Flag"].Тип.СодержитТип(Тип("String"))'))
        self.assertEqual(vm.execute('Metadata.SessionParameters.Calls.Type.NumberQualifiers.FractionDigits'),Decimal(0))
        vm.execute('D=Metadata.SessionParameters.Text.Type;')
        self.assertEqual(vm.execute('D.StringQualifiers.Length'),Decimal(64))
        with self.assertRaisesRegex(BSLRuntimeError,'read-only'):
            vm.execute('D.StringQualifiers.Length=1;')
        self.assertEqual(vm.execute('D.StringQualifiers.Length'),Decimal(64))
        self.assertEqual(app.session_parameters._values,before)

    def test_parameter_metadata_lookup_and_readonly(self):
        app=self.application()
        self.assertTrue(app.execute('(Metadata.FindByFullName("SessionParameter.Flag")=Metadata.SessionParameters.Flag)'))
        self.assertEqual(app.execute('Metadata.SessionParameters.Flag.FullName()'),'ПараметрСеанса.Flag')
        with self.assertRaises(BSLRuntimeError):app.execute('Metadata.SessionParameters.Flag.Name="Other";')

    def test_native_sixteen_case_replay(self):
        import hashlib,json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        raw=(root/'tests/fixtures/native_session_parameters_43052415203.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'060e950d8cd29765bbc3f2c5f534333d953647aa6c54dbd93e941d882ee06e06')
        source=(root/'scripts/session_parameter_behavior/observe.bsl').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'3228c91147c125d1998f53362c9704b11a7738976955161254cf647636bb8f08')
        declarations=source.decode().split('For CaseNo = 1 To 16 Do')[0]
        # A by-value remote wrapper preserves the original case declarations.
        declarations+='\nFunction Run(Val CaseNo) Export Stage="read"; Return ObserveCase(CaseNo,Stage); EndFunction'
        files=module_files((('NativeCases',declarations,SERVER),))
        parameters=sorted((root/'scripts/session_parameter_behavior').glob('Owned*.xml'))
        self.assertEqual(len(parameters),13)
        for parameter in parameters:
            name=parameter.stem
            files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',
                ('<SessionParameter>'+name+'</SessionParameter></ChildObjects>').encode())
            files['SessionParameters/'+name+'.xml']=parameter.read_bytes()
        files['Ext/SessionModule.bsl']=(root/'scripts/session_parameter_behavior/SessionModule.bsl').read_bytes()
        app=self.source_application(files)
        actual=[]
        for case in range(1,17):
            with self.subTest(case=case):
                actual.append(app.interpreter.execute('NativeCases.Run('+str(case)+')'))
        self.assertEqual(actual,json.loads(raw))
