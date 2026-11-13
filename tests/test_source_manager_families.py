"""Declared manager code across metadata families, without persistence grants."""
import unittest
from test_source_manager_modules import configuration
from test_source_server_call import module
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.runtime import Interpreter
from yadinassi.source_manager_modules import SourceManagers

FAMILIES = (
    ('Catalog','Catalogs','Справочники'), ('Document','Documents','Документы'),
    ('Report','Reports','Отчеты'), ('DataProcessor','DataProcessors','Обработки'),
    ('InformationRegister','InformationRegisters','РегистрыСведений'),
    ('AccumulationRegister','AccumulationRegisters','РегистрыНакопления'),
    ('AccountingRegister','AccountingRegisters','РегистрыБухгалтерии'),
    ('CalculationRegister','CalculationRegisters','РегистрыРасчета'),
    ('ChartOfAccounts','ChartsOfAccounts','ПланыСчетов'),
    ('ChartOfCharacteristicTypes','ChartsOfCharacteristicTypes','ПланыВидовХарактеристик'),
    ('ChartOfCalculationTypes','ChartsOfCalculationTypes','ПланыВидовРасчета'),
    ('BusinessProcess','BusinessProcesses','БизнесПроцессы'), ('Task','Tasks','Задачи'),
    ('ExchangePlan','ExchangePlans','ПланыОбмена'),
)

class SourceManagerFamiliesTests(unittest.TestCase):
    def run_app(self, config):
        output=[]
        app=SourceApplication(config,output=output.append)
        self.addCleanup(app.close)
        app.start()
        return app,output

    def test_all_families_bilingual_exports(self):
        for family,folder,ru in FAMILIES:
            for namespace in (folder,ru):
                with self.subTest(family=family,namespace=namespace):
                    _,out=self.run_app(configuration('Message('+namespace+'.Items.Answer());',family=family,folder=folder))
                    self.assertEqual(out,['42'])

    def test_all_families_dynamic_names(self):
        for family,folder,_ in FAMILIES:
            with self.subTest(family=family):
                _,out=self.run_app(configuration('Name="iTeMs"; Message('+folder+'[Name].Answer());',family=family,folder=folder))
                self.assertEqual(out,['42'])

    def test_all_families_client_denied(self):
        for family,folder,_ in FAMILIES:
            with self.subTest(family=family),self.assertRaisesRegex(BSLError,'synchronous server'):
                self.run_app(configuration('Message('+folder+'.Items.Answer());',family=family,folder=folder,session=False))

    def test_no_record_set_is_synthesized(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration('InformationRegisters.Items.CreateRecordSet();',family='InformationRegister',folder='InformationRegisters'))

    def test_missing_manager_module_is_explicit(self):
        with self.assertRaisesRegex(BSLError,'storage operations are not activated'):
            self.run_app(configuration('Tasks.Items.Answer();',body=None,family='Task',folder='Tasks'))

    def test_module_variables_remain_forbidden(self):
        with self.assertRaisesRegex(BSLError,'initialization'):
            self.run_app(configuration(body='Var State;\nFunction Answer() Export\nReturn 1;\nEndFunction'))

    def test_names_are_strings_only(self):
        for name in ('1','Undefined','True','New Array'):
            with self.subTest(name=name),self.assertRaisesRegex(BSLError,'name must be a string'):
                self.run_app(configuration('Catalogs['+name+'].Answer();'))

    def test_missing_dynamic_name(self):
        with self.assertRaisesRegex(BSLError,'Unknown source manager'):
            self.run_app(configuration('Catalogs["Missing"].Answer();'))

    def test_private_export_remains_private(self):
        with self.assertRaises(BSLError):
            self.run_app(configuration('Tasks["Items"].Answer();',body='Function Answer()\nReturn 1;\nEndFunction',family='Task',folder='Tasks'))

    def test_dynamic_name_evaluated_once(self):
        body='Function Answer() Export\nReturn 42;\nEndFunction'
        cfg=configuration('Message(Catalogs[Name()].Answer());',body=body)
        files={item.path:item.content for item in cfg.files}
        files['Ext/SessionModule.bsl']+=b'\nFunction Name()\nMessage("index"); Return "Items";\nEndFunction'
        _,out=self.run_app(import_source(files))
        self.assertEqual(out,['index','42'])

    def test_client_dynamic_name_has_no_side_effect(self):
        cfg=configuration('Try Catalogs[Name()].Answer(); Except Message("denied"); EndTry;',session=False)
        files={item.path:item.content for item in cfg.files}
        files['Ext/ManagedApplicationModule.bsl']+=b'\nFunction Name()\nMessage("wrong"); Return "Items";\nEndFunction'
        _,out=self.run_app(import_source(files))
        self.assertEqual(out,['denied'])

    def test_foreign_and_closed_family(self):
        app,_=self.run_app(configuration(''))
        namespace=SourceManagers(app,'Catalog')
        foreign=Interpreter();self.addCleanup(foreign.close)
        with self.assertRaisesRegex(ValueError,'synchronous server'):
            namespace.member(foreign,'Items')
        app.close()
        with self.assertRaisesRegex(ValueError,'not running'):
            namespace.member(app.interpreter,'Items')

    def test_cached_server_manager_stays_denied_to_client(self):
        app,out=self.run_app(configuration())
        self.assertEqual(out,['42'])
        with self.assertRaisesRegex(BSLError,'synchronous server'):
            app.interpreter.execute('Catalogs.Items.Answer();')

    def test_server_call_can_reach_register_manager(self):
        cfg=configuration('',family='InformationRegister',folder='InformationRegisters',body='Function Answer() Export\nReturn Metadata.Name;\nEndFunction')
        files={item.path:item.content for item in cfg.files}
        files.update(module('API','Function Answer() Export\nReturn InformationRegisters["Items"].Answer();\nEndFunction'))
        files['CommonModules/API.xml']=files['CommonModules/API.xml'].replace(b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000003">')
        files['Ext/ManagedApplicationModule.bsl']=b'Procedure OnStart()\nMessage(API.Answer());\nEndProcedure'
        _,out=self.run_app(import_source(files))
        self.assertEqual(out,['Demo'])

    def test_selected_source_form_server_dynamic_manager(self):
        from test_source_forms import files, request
        from test_source_metadata import xml
        from yadinassi.source_forms import SourceFormController
        mapping=files(b'&AtServer\nProcedure Created(Cancel, StandardProcessing) Greeting=InformationRegisters["Items"].Answer(); EndProcedure\n&AtClient\nProcedure Go(Command) EndProcedure')
        mapping['InformationRegisters/Items.xml']=xml('InformationRegister','Items')
        mapping['InformationRegisters/Items/Ext/ManagerModule.bsl']=b'Function Answer() Export Return "manager"; EndFunction'
        app,_=self.run_app(import_source(mapping))
        controller=SourceFormController(app,'CommonForm.Main')
        self.assertIsNone(controller.exchange(request())['result']['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'manager')
