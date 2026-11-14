"""Source-only resource bridge: exact native resource replay, no storage grant."""
import json
import unittest
from pathlib import Path
from test_common_templates_recovery import files, ASSETS, FIXTURE
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.runtime import Interpreter
from yadinassi.common_templates import SourceTemplateCall

class SourceTemplateTests(unittest.TestCase):
    def app(self, changes=None):
        content=files("Procedure OnStart()\nEndProcedure")
        if changes: changes(content)
        app=SourceApplication(import_source(content),output=lambda _:None)
        self.addCleanup(app.close);app.start();return app

    def test_native_resource_observations(self):
        app=self.app()
        source=(ASSETS/'observe.bsl').read_text(encoding='utf-8').split('For CaseNo = 1 To 12 Do')[0]
        app.interpreter.execute(source)
        expected=json.loads(FIXTURE.read_bytes())['observations']
        for n,value in enumerate(expected,1):
            with self.subTest(case=n):self.assertEqual(app.interpreter.execute(f'ObserveCase({n}, "")'),value)

        from test_source_server_call import module
        for flags in ({'client': True, 'server': False, 'server_call': False}, {}):
            def add_module(content):
                extra=module('ResourceAPI', 'Function Read() Export\nReturn GetCommonTemplate("OwnedText").GetText();\nEndFunction', **flags)
                path='CommonModules/ResourceAPI.xml'
                extra[path]=extra[path].replace(b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000009999">')
                content.update(extra)
            nested=self.app(add_module)
            with self.subTest(flags=flags):
                self.assertEqual(nested.interpreter.execute('ResourceAPI.Read()'),expected[1])

    def test_unknown_and_wrong_arguments(self):
        app=self.app()
        for code in ['GetCommonTemplate("Absent")','GetCommonTemplate(42)','GetCommonTemplate()','GetCommonTemplate("OwnedText",1)']:
            with self.subTest(code=code),self.assertRaises(BSLError):app.interpreter.execute(code)

    def test_foreign_metadata_refused(self):
        app,other=self.app(),self.app()
        value=other.metadata.find_by_full_name('CommonTemplate.OwnedText')
        with self.assertRaisesRegex(ValueError,'foreign'):app.common_templates.get(app.interpreter,value)

    def test_same_app_wrong_family_refused(self):
        app=self.app()
        with self.assertRaises(TypeError):app.common_templates.get(app.interpreter,app.metadata)

    def test_closed_owner_refused(self):
        app=self.app();owner=app.common_templates;app.close()
        with self.assertRaises(ValueError):owner.get(app.interpreter,'OwnedText')

    def test_foreign_call_refused_before_argument_side_effect(self):
        app=self.app();vm=Interpreter(lambda _:None)
        vm.register_function('GetCommonTemplate',SourceTemplateCall(app.common_templates))
        vm.execute('Count=0; Function Touch()\nCount=Count+1; Return "OwnedText"; EndFunction')
        with self.assertRaises(BSLError):vm.execute('GetCommonTemplate(Touch())')
        self.assertEqual(vm.execute('Count'),0)

    def test_unsupported_unused_resource_preserved(self):
        def change(content):content['CommonTemplates/OwnedBinary.xml']=content['CommonTemplates/OwnedBinary.xml'].replace(b'BinaryData',b'SpreadsheetDocument')
        app=self.app(change)
        self.assertIsNotNone(app.interpreter.execute('GetCommonTemplate("OwnedText")'))
        with self.assertRaisesRegex(BSLError,'OwnedBinary.xml'):app.interpreter.execute('GetCommonTemplate("OwnedBinary")')

    def test_missing_resource_fails_lazily(self):
        app=self.app(lambda c:c.pop('CommonTemplates/OwnedBinary/Ext/Template.bin'))
        with self.assertRaisesRegex(BSLError,'missing common template resource'):app.interpreter.execute('GetCommonTemplate("OwnedBinary")')

    def test_bad_encoding_not_published_to_cache(self):
        app=self.app(lambda c:c.update({'CommonTemplates/OwnedText/Ext/Template.txt':b'\xff'}))
        with self.assertRaises(BSLError):app.interpreter.execute('GetCommonTemplate("OwnedText")')
        self.assertEqual(app.common_templates._loaded,{})

    def test_resource_bound(self):
        app=self.app(lambda c:c.update({'CommonTemplates/OwnedBinary/Ext/Template.bin':b'x'*(1024*1024+1)}))
        with self.assertRaisesRegex(BSLError,'resource bound'):app.interpreter.execute('GetCommonTemplate("OwnedBinary")')
        self.assertEqual(app.common_templates._bytes,0)

        from uuid import UUID
        for count,size,successful in ((9,1024*1024,8),(129,1,128)):
            def many(content):
                for n in range(count):
                    name='Resource'+str(n)
                    xml=content['CommonTemplates/OwnedBinary.xml'].replace(b'OwnedBinary',name.encode())
                    import re
                    xml=re.sub(rb'uuid="[^"]+"',('uuid="'+str(UUID(int=10000+n))+'"').encode(),xml)
                    content['CommonTemplates/'+name+'.xml']=xml
                    content['CommonTemplates/'+name+'/Ext/Template.bin']=b'x'*size
                    content['Configuration.xml']=content['Configuration.xml'].replace(b'</ChildObjects>',('<CommonTemplate>'+name+'</CommonTemplate></ChildObjects>').encode())
            bounded=self.app(many)
            for n in range(successful):bounded.interpreter.execute(f'GetCommonTemplate("Resource{n}")')
            with self.subTest(count=count),self.assertRaisesRegex(BSLError,'bound'):
                bounded.interpreter.execute(f'GetCommonTemplate("Resource{successful}")')
            self.assertEqual(len(bounded.common_templates._loaded),successful)
            self.assertEqual(bounded.common_templates._bytes,successful*size)

    def test_no_disk_lookup_or_undeclared_fallback(self):
        app=self.app(lambda c:c.update({'Elsewhere/secret.txt':b'private'}))
        for name in ['../Elsewhere/secret','Elsewhere/secret','OwnedText/Ext/Template.txt']:
            with self.assertRaises(BSLError):app.interpreter.execute(f'GetCommonTemplate("{name}")')

    def test_standalone_remains_closed(self):
        with self.assertRaises(BSLError):Interpreter(lambda _:None).execute('GetCommonTemplate("OwnedText")')
