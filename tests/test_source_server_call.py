"""Source common-module crossing uses the existing interpreter packet boundary."""
import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.runtime import Interpreter


def module(name, body, *, client=False, server=True, server_call=True,
           global_module=False, privileged=False, reuse='DontUse'):
    properties = {'Name': name, 'ClientManagedApplication': str(client).lower(),
        'Server': str(server).lower(), 'ServerCall': str(server_call).lower(),
        'Global': str(global_module).lower(), 'Privileged': str(privileged).lower(),
        'ReturnValuesReuse': reuse}
    xml = '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule><Properties>'
    xml += ''.join('<'+k+'>'+v+'</'+k+'>' for k,v in properties.items())
    xml += '</Properties></CommonModule></MetaDataObject>'
    return {'CommonModules/'+name+'.xml': xml.encode(),
            'CommonModules/'+name+'/Ext/Module.bsl': body.encode()}


def configuration(code, body='Function Answer() Export\nReturn 42;\nEndFunction', **flags):
    files = module('ServerAPI', body, **flags)
    # Source admission requires metadata identities, including every module.
    files['CommonModules/ServerAPI.xml'] = files['CommonModules/ServerAPI.xml'].replace(
        b'<CommonModule>', b'<CommonModule uuid="00000000-0000-0000-0000-000000000002">')
    return source(('Procedure OnStart()\n'+code+'\nEndProcedure').encode(), files)


class SourceServerCallTests(unittest.TestCase):
    def run_app(self, config, **kwargs):
        output=[]
        app=SourceApplication(config, output=output.append, **kwargs)
        self.addCleanup(app.close)
        app.start()
        return app, output

    def test_client_server_function(self):
        _, output=self.run_app(configuration('Message(ServerAPI.Answer());'))
        self.assertEqual(output,['42'])

    def test_server_metadata_retained(self):
        _, output=self.run_app(configuration('Message(ServerAPI.Answer());',
            'Function Answer() Export\nReturn Metadata.Name;\nEndFunction'))
        self.assertEqual(output,['Demo'])

    def test_same_module_private_helper(self):
        _, output=self.run_app(configuration('Message(ServerAPI.Answer());',
            'Function Answer() Export\nReturn Hidden();\nEndFunction\nFunction Hidden()\nReturn 8;\nEndFunction'))
        self.assertEqual(output,['8'])

    def test_private_export_not_exposed(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration('ServerAPI.Hidden();', 'Procedure Hidden()\nEndProcedure'))

    def test_server_call_flag_required(self):
        with self.assertRaisesRegex(BSLError,'Режим общего модуля'):
            self.run_app(configuration('ServerAPI.Answer();',server_call=False))

    def test_privileged_not_granted(self):
        with self.assertRaisesRegex(BSLError,'Режим общего модуля'):
            self.run_app(configuration('ServerAPI.Answer();',privileged=True))

    def test_named_global_not_granted(self):
        with self.assertRaisesRegex(BSLError,'Режим общего модуля'):
            self.run_app(configuration('ServerAPI.Answer();',global_module=True))

    def test_reuse_crossing_explicitly_rejected(self):
        with self.assertRaisesRegex(BSLError,'return-value reuse'):
            self.run_app(configuration('ServerAPI.Answer();',reuse='DuringSession'))

    def test_scalar_copyback(self):
        _, output=self.run_app(configuration('X=1; ServerAPI.Change(X); Message(X);',
            'Procedure Change(X) Export\nX=X+2;\nEndProcedure'))
        self.assertEqual(output,['3'])

    def test_val_isolated_collection(self):
        _, output=self.run_app(configuration('X=New Array; X.Add(1); Message(ServerAPI.Change(X)); Message(X.Count());',
            'Function Change(Val X) Export\nX.Add(2); Return X.Count();\nEndFunction'))
        self.assertEqual(output,['2','1'])

    def test_collection_copyback(self):
        _, output=self.run_app(configuration('X=New Array; X.Add(1); ServerAPI.Change(X); Message(X.Count());',
            'Procedure Change(X) Export\nX.Add(2);\nEndProcedure'))
        self.assertEqual(output,['2'])

    def test_error_has_no_copyback(self):
        _, output=self.run_app(configuration('X=1; Try ServerAPI.Change(X); Except Message(X); EndTry;',
            'Procedure Change(X) Export\nX=9; Raise "failure";\nEndProcedure'))
        self.assertEqual(output,['1'])

    def test_unsupported_return_no_copyback(self):
        _, output=self.run_app(configuration('X=1; Try Y=ServerAPI.Change(X); Except Message(X); EndTry;',
            'Function Change(X) Export\nX=9; Return Metadata;\nEndFunction'))
        self.assertEqual(output,['1'])

    def test_optional_val_hole(self):
        _, output=self.run_app(configuration('Message(ServerAPI.Answer(,3));',
            'Function Answer(Val X=4, Val Y=8) Export\nReturn X+Y;\nEndFunction'))
        self.assertEqual(output,['7'])

    def test_byref_expression_rejected_before_effects(self):
        _, output=self.run_app(configuration('Try ServerAPI.Change(1+1); Except Message("rejected"); EndTry;',
            'Procedure Change(X) Export\nMessage("wrong");\nEndProcedure'))
        self.assertEqual(output,['rejected'])

    def test_safe_mode_cannot_cross(self):
        _, output=self.run_app(configuration('SetSafeMode(True); Try ServerAPI.Answer(); Except Message("rejected"); EndTry;'))
        self.assertEqual(output,['rejected'])

    def test_server_no_client_access(self):
        from yadinassi.configuration_source import import_source
        config=configuration('Try ServerAPI.Answer(); Except Message("rejected"); EndTry;',
            'Function Answer() Export\nReturn ClientOnly.Answer();\nEndFunction')
        files={item.path:item.content for item in config.files}
        extra=module('ClientOnly','Function Answer() Export\nReturn 1;\nEndFunction',client=True,server=False,server_call=False)
        extra['CommonModules/ClientOnly.xml']=extra['CommonModules/ClientOnly.xml'].replace(b'<CommonModule>', b'<CommonModule uuid="00000000-0000-0000-0000-000000000003">')
        files.update(extra)
        _, output=self.run_app(import_source(files))
        self.assertEqual(output,['rejected'])

    def test_profile_retained_in_server_helpers(self):
        body='Function Answer() Export\n#If ThickClientManagedApplication Then\nReturn 10;\n#Else\nReturn 20;\n#EndIf\nEndFunction'
        _, output=self.run_app(configuration('Message(ServerAPI.Answer());',body), compilation_profile='managed-thick-file')
        self.assertEqual(output,['10'])

    def test_foreign_caller_rejected(self):
        app,_=self.run_app(configuration(''))
        foreign=Interpreter();self.addCleanup(foreign.close)
        with self.assertRaisesRegex(ValueError,'foreign source'):
            app.module('serverapi',foreign)

    def test_closed_cached_module_rejected(self):
        app,_=self.run_app(configuration('Message(ServerAPI.Answer());'))
        app.close()
        with self.assertRaisesRegex(ValueError,'not running'):
            app.module('serverapi',app.interpreter)

    def with_extra(self, config, name, body, **flags):
        from yadinassi.configuration_source import import_source
        files={item.path:item.content for item in config.files}
        extra=module(name,body,**flags)
        extra['CommonModules/'+name+'.xml']=extra['CommonModules/'+name+'.xml'].replace(
            b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000003">')
        files.update(extra)
        return import_source(files)

    def test_nested_server_module_without_external_servercall(self):
        config=configuration('Message(ServerAPI.Answer());',
            'Function Answer() Export\nReturn Internal.Answer();\nEndFunction')
        config=self.with_extra(config,'Internal','Function Answer() Export\nReturn Metadata.Name;\nEndFunction',server_call=False)
        _, output=self.run_app(config)
        self.assertEqual(output,['Demo'])

    def test_cached_internal_server_not_exposed_to_client(self):
        config=configuration('Message(ServerAPI.Answer()); Try Internal.Answer(); Except Message("rejected"); EndTry;',
            'Function Answer() Export\nReturn Internal.Answer();\nEndFunction')
        config=self.with_extra(config,'Internal','Function Answer() Export\nReturn 7;\nEndFunction',server_call=False)
        _, output=self.run_app(config)
        self.assertEqual(output,['7','rejected'])

    def test_server_global_available_in_activation(self):
        config=configuration('Message(ServerAPI.Answer());',
            'Function Answer() Export\nReturn GlobalAnswer();\nEndFunction')
        config=self.with_extra(config,'Globals','Function GlobalAnswer() Export\nReturn Metadata.Name;\nEndFunction',global_module=True)
        _, output=self.run_app(config)
        self.assertEqual(output,['Demo'])

    def test_both_sides_remain_client_local(self):
        config=configuration('Message(ServerAPI.Answer());',
            'Function Answer() Export\nReturn ClientOnly.Answer();\nEndFunction',client=True)
        config=self.with_extra(config,'ClientOnly','Function Answer() Export\nReturn 5;\nEndFunction',client=True,server=False)
        _, output=self.run_app(config)
        self.assertEqual(output,['5'])

    def test_session_environment_retained(self):
        from test_source_session_parameters import declaration
        from yadinassi.configuration_source import import_source
        config=configuration('Message(ServerAPI.Answer());',
            'Function Answer() Export\nReturn SessionParameters.State.Get("key");\nEndFunction')
        files={item.path:item.content for item in config.files}
        files['SessionParameters/State.xml']=declaration('State','<v8:Type>v8:FixedMap</v8:Type>')
        files['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting(Names)\nM=New Map; M.Insert("key","ready"); SessionParameters.State=New FixedMap(M);\nEndProcedure'
        _,output=self.run_app(import_source(files))
        self.assertEqual(output,['ready'])

    def test_server_safe_counter_cleans_on_return_and_error(self):
        for finish in ('Return 1;', 'Raise "failure";'):
            with self.subTest(finish=finish):
                _, output=self.run_app(configuration('Try ServerAPI.Answer(); Except EndTry; Message(SafeMode());',
                    'Function Answer() Export\nSetSafeMode(True); '+finish+'\nEndFunction'))
                self.assertEqual(output,['Нет'])
