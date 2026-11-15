import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


def configuration(code='Message(Answer());', modules=None, server=False):
    modules = modules or [('Helpers','Function Answer() Export\nReturn 42;\nEndFunction',False)]
    files = {}
    for index,(name,body,privileged) in enumerate(modules,2):
        files['CommonModules/'+name+'.xml'] = ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-%012d"><Properties><Name>%s</Name><Global>true</Global><ClientManagedApplication>true</ClientManagedApplication><Server>true</Server><Privileged>%s</Privileged></Properties></CommonModule></MetaDataObject>'%(index,name,str(privileged).lower())).encode()
        files['CommonModules/'+name+'/Ext/Module.bsl'] = body.encode()
    if server:
        files['Ext/SessionModule.bsl'] = ('Procedure SessionParametersSetting(Names)\n'+code+'\nEndProcedure').encode()
    return source(b'' if server else ('Procedure OnStart()\n'+code+'\nEndProcedure').encode(),files)


class SourceGlobalModuleTests(unittest.TestCase):
    def run_app(self, config):
        output=[]
        app=SourceApplication(config,output=output.append)
        self.addCleanup(app.close)
        app.start()
        return output

    def test_client_export(self):
        self.assertEqual(self.run_app(configuration()), ['42'])

    def test_server_export(self):
        self.assertEqual(self.run_app(configuration(server=True)), ['42'])

    def test_private_export_absent(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration(modules=[('Helpers','Function Answer()\nReturn 42;\nEndFunction',False)]))

    def test_duplicate_exports_explicit(self):
        body='Function Answer() Export\nReturn 42;\nEndFunction'
        with self.assertRaisesRegex(BSLError,'Ambiguous global'):
            self.run_app(configuration(modules=[('A',body,False),('B',body,False)]))

    def test_privileged_not_granted(self):
        with self.assertRaisesRegex(BSLError,'Режим общего модуля'):
            self.run_app(configuration(modules=[('Helpers','Function Answer() Export\nReturn 42;\nEndFunction',True)]))

    def test_optional_argument(self):
        body='Function Answer(Val X=7, Val Y=9) Export\nReturn X+Y;\nEndFunction'
        self.assertEqual(self.run_app(configuration('Message(Answer(,3));',[('Helpers',body,False)])),['10'])

    def test_named_global_access_remains_rejected_after_cache(self):
        with self.assertRaisesRegex(BSLError,'Режим общего модуля'):
            self.run_app(configuration('Message(Answer()); Message(Helpers.Answer());'))

    def test_local_routine_precedence(self):
        config=configuration('Message(Answer());')
        from yadinassi.configuration_source import import_source
        files={f.path:f.content for f in config.files}
        files['Ext/ManagedApplicationModule.bsl']+=b'\nFunction Answer()\nReturn 9;\nEndFunction'
        self.assertEqual(self.run_app(import_source(files)),['9'])

    def test_unused_global_source_not_compiled(self):
        self.assertEqual(self.run_app(configuration('', [('Helpers','invalid ???',False)])), [])

    def test_cross_global_call(self):
        a='Function Answer() Export\nReturn OtherAnswer();\nEndFunction'
        b='Function OtherAnswer() Export\nReturn 43;\nEndFunction'
        self.assertEqual(self.run_app(configuration(modules=[('A',a,False),('B',b,False)])),['43'])

    def test_variable_binding_precedes_global_function(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration('Answer = 9; Message(Answer());'))

    def test_global_reuse_mode_not_silently_ignored(self):
        from yadinassi.configuration_source import import_source
        config=configuration()
        files={f.path:f.content for f in config.files}
        path='CommonModules/Helpers.xml'
        files[path]=files[path].replace(b'</Properties>',b'<ReturnValuesReuse>DuringSession</ReturnValuesReuse></Properties>')
        with self.assertRaisesRegex(BSLError,'Режим общего модуля'):
            self.run_app(import_source(files))
