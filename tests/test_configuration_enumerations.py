"""Authored local contract tests; not native enumeration observations."""
from decimal import Decimal
from uuid import uuid4
import unittest
from configuration_runtime_fixture import module_files
from yadinassi.configuration_xml import import_configuration
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.enum_types import BSLEnumReference
from yadinassi.errors import BSLRuntimeError


def enum_files():
    files=module_files((('Tools','Function Pick() Export Return Enums.Status.Active; EndFunction',{}),))
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Enum>Status</Enum></ChildObjects>')
    values=''.join('<EnumValue uuid="'+str(uuid4())+'"><Properties><Name>'+n+'</Name></Properties></EnumValue>' for n in ('Active','Closed'))
    files['Enums/Status.xml']=('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20"><Enum uuid="'+str(uuid4())+'"><Properties><Name>Status</Name></Properties><ChildObjects>'+values+'</ChildObjects></Enum></MetaDataObject>').encode()
    return files


class ConfigurationEnumerationTests(unittest.TestCase):
    def application(self,files=None):
        app=ConfigurationApplication.from_files(enum_files() if files is None else files)
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_source_is_explicit_and_preserved(self):
        files=enum_files();result=import_configuration(files,module_runtime=MODULE_RUNTIME)
        self.assertFalse(result.activation_issues)
        self.assertEqual([v.name for v in result.enumerations[0].values],['Active','Closed'])
        self.assertEqual({f.path:f.content for f in result.files},files)
        closed=import_configuration(files)
        self.assertTrue(any('Enum' in x for x in closed.activation_issues))

    def test_duplicate_name_rejected(self):
        files=enum_files();files['Enums/Status.xml']=files['Enums/Status.xml'].replace(b'<Name>Closed</Name>',b'<Name>ACTIVE</Name>')
        with self.assertRaises(ValueError):import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_unknown_component_rejected(self):
        files=enum_files();files['Enums/Status.xml']=files['Enums/Status.xml'].replace(b'</Enum>',b'<HiddenBehavior/></Enum>')
        with self.assertRaises(ValueError):import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_constants_type_and_empty_reference(self):
        app=self.application();v=app.execute('Enums.Status.Active')
        self.assertIs(type(v),BSLEnumReference)
        self.assertTrue(app.execute('(TypeOf(Enums.Status.Active)=Type("EnumRef.Status"))'))
        self.assertTrue(app.execute('Enums.Status.EmptyRef().IsEmpty()'))
        self.assertFalse(app.execute('Enums.Status.Active.IsEmpty()'))
        self.assertEqual(app.execute('Enums.Status.Count()'),Decimal(2))

    def test_common_module_shares_identity(self):
        app=self.application()
        self.assertTrue(app.execute('(Tools.Pick()=Enums.Status.Active)'))
        self.assertEqual(hash(app.execute('Tools.Pick()')),hash(app.execute('Enums.Status.Active')))

    def test_independent_applications_remain_distinct(self):
        files=enum_files();a=self.application(files);b=self.application(files)
        self.assertNotEqual(a.execute('Enums.Status.Active'),b.execute('Enums.Status.Active'))

    def test_metadata_declared_order(self):
        app=self.application()
        self.assertEqual(app.execute('Metadata.Enums.Status.EnumValues.Get(0).Name'),'Active')
        self.assertEqual(app.execute('Metadata.Enums.Status.EnumValues.Count()'),Decimal(2))

    def test_value_mutation_denied(self):
        app=self.application()
        with self.assertRaises(Exception):app.execute('Enums.Status.Active=Enums.Status.Closed;')
        self.assertFalse(app.execute('(Enums.Status.Active=Enums.Status.Closed)'))

    def test_type_description_retains_exact_reference(self):
        app=self.application()
        app.execute('A=New Array; A.Add(Type("EnumRef.Status")); D=New TypeDescription(A);')
        self.assertTrue(app.execute('D.ContainsType(TypeOf(Enums.Status.Active))'))
        self.assertTrue(app.execute('(D.AdjustValue(Enums.Status.Active)=Enums.Status.Active)'))

    def test_metadata_find_by_type_and_full_name(self):
        app=self.application()
        self.assertTrue(app.execute('(Metadata.FindByType(Type("EnumRef.Status"))=Metadata.Enums.Status)'))
        self.assertTrue(app.execute('(Metadata.FindByFullName("Enum.Status")=Metadata.Enums.Status)'))

    def test_ordered_manager_and_dynamic_lookup(self):
        app=self.application()
        self.assertTrue(app.execute('(Enums["status"][0]=Enums.Status.Active)'))
        self.assertEqual(app.execute('Enums.Status.IndexOf(Enums.Status.Closed)'),Decimal(1))
        app.execute('A=New Array; For Each V In Enums.Status Do A.Add(V); EndDo;')
        self.assertEqual(app.execute('A.Count()'),Decimal(2))

    def test_incomplete_names_and_indices_rejected(self):
        app=self.application()
        for source in ('Enums.Missing','Enums.Status[9]','Enums.Status[-1]','Enums.Status[0.5]','Enums.Status["Missing"]'):
            with self.subTest(source=source), self.assertRaises(Exception):app.execute(source)

    def test_persistence_codec_remains_closed(self):
        app=self.application()
        with self.assertRaisesRegex(BSLRuntimeError,'сериализация типов и ссылок перечислений'):
            app.execute('ValueToStringInternal(Enums.Status.Active)')

    def test_duplicate_value_uuid_rejected(self):
        import re
        files=enum_files();raw=files['Enums/Status.xml'];ids=re.findall(b'EnumValue uuid="([^"]+)"',raw)
        files['Enums/Status.xml']=raw.replace(ids[1],ids[0])
        with self.assertRaises(ValueError):import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_unknown_reference_type_not_coerced(self):
        app=self.application()
        with self.assertRaises(Exception):app.execute('Type("EnumRef.Unknown")')

    def test_descriptors_reject_independent_scope(self):
        files=enum_files();app=self.application(files);other=self.application(files)
        app.interpreter.variables['foreign']=other.execute('Enums.Status.Active')
        app.execute('A=New Array; A.Add(Type("EnumRef.Status")); D=New TypeDescription(A);')
        with self.assertRaises(Exception):app.execute('D.AdjustValue(Foreign)')

    def test_scalar_description_cannot_convert_enum_reference(self):
        app=self.application()
        for source in ('New TypeDescription("String").AdjustValue(Enums.Status.EmptyRef())',
                       'New TypeDescription("String").AdjustValue(Type("EnumRef.Status"))'):
            with self.subTest(source=source),self.assertRaises(Exception):app.execute(source)

    def test_named_description_resolves_active_application_type(self):
        app=self.application()
        for name in ('EnumRef.Status','ПеречислениеСсылка.Status',' enumref.status '):
            with self.subTest(name=name):
                app.execute('D=New TypeDescription("'+name+'");')
                self.assertTrue(app.execute('D.ContainsType(TypeOf(Enums.Status.Active))'))
                self.assertTrue(app.execute('(D.AdjustValue(Enums.Status.Active)=Enums.Status.Active)'))

    def test_named_description_dynamic_constructor(self):
        app=self.application()
        app.execute('Args=New Array; Args.Add("EnumRef.Status"); D=New (Type("TypeDescription"), Args);')
        self.assertTrue(app.execute('D.ContainsType(TypeOf(Enums.Status.Active))'))

    def test_named_description_common_module_context(self):
        files=enum_files()
        key='CommonModules/Tools/Ext/Module.bsl'
        files[key]=b'Function Pick() Export Return New TypeDescription("EnumRef.Status"); EndFunction'
        app=self.application(files)
        self.assertTrue(app.execute('Tools.Pick().ContainsType(TypeOf(Enums.Status.Active))'))

    def test_named_description_preserves_independent_family(self):
        files=enum_files();a=self.application(files);b=self.application(files)
        description=a.execute('New TypeDescription("EnumRef.Status")')
        b.interpreter.variables['foreign']=description
        self.assertFalse(b.execute('Foreign.ContainsType(TypeOf(Enums.Status.Active))'))
        with self.assertRaises(Exception):b.execute('Foreign.AdjustValue(Enums.Status.Active)')

    def test_named_description_does_not_expand_unions_or_managers(self):
        app=self.application()
        for name in ('EnumRef.Status,Number','EnumManager.Status','EnumRef.Unknown', 'EnumRef.Status,' ):
            with self.subTest(name=name),self.assertRaises(Exception):
                app.execute('New TypeDescription("'+name+'")')

    def test_named_description_keeps_qualifier_admission(self):
        app=self.application()
        with self.assertRaises(Exception):
            app.execute('New TypeDescription("EnumRef.Status",,,)')
        with self.assertRaises(Exception):
            app.execute('New TypeDescription("EnumRef.Status", New NumberQualifiers(10,2))')

    def rich_files(self):
        from pathlib import Path
        files=enum_files()
        raw=(Path(__file__).resolve().parents[1]/'scripts/enumeration_behavior/Enum.xml').read_bytes()
        files['Enums/Status.xml']=raw.replace(b'OwnedStatus',b'Status')
        return files

    def test_closed_designer_envelope_preserves_source_and_values(self):
        files=self.rich_files();app=self.application(files)
        self.assertEqual({f.path:f.content for f in app.configuration.files},files)
        self.assertTrue(app.execute('(Tools.Pick()=Enums.Status.Active)'))
        self.assertEqual(app.execute('Metadata.Enums.Status.EnumValues.Count()'),Decimal(2))

    def test_generated_identity_collision_rejected(self):
        import re
        files=self.rich_files();raw=files['Enums/Status.xml']
        ids=re.findall(b'<xr:TypeId>([^<]+)</xr:TypeId>',raw)
        files['Enums/Status.xml']=raw.replace(ids[1],ids[0])
        with self.assertRaisesRegex(ValueError,'duplicate generated metadata UUID'):
            import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_generated_family_is_bound_to_declaration(self):
        files=self.rich_files()
        files['Enums/Status.xml']=files['Enums/Status.xml'].replace(b'EnumRef.Status',b'EnumRef.Other')
        with self.assertRaises(ValueError):import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_generated_envelope_does_not_grant_forms_or_commands(self):
        for before,after in ((b'<DefaultListForm/>',b'<DefaultListForm>Enum.Status.Form.List</DefaultListForm>'),
                             (b'<UseStandardCommands>false',b'<UseStandardCommands>true'),
                             (b'<Characteristics/>',b'<Characteristics><Code>Run</Code></Characteristics>')):
            files=self.rich_files();self.assertIn(before,files['Enums/Status.xml'])
            files['Enums/Status.xml']=files['Enums/Status.xml'].replace(before,after)
            with self.subTest(before=before),self.assertRaises(ValueError):
                import_configuration(files,module_runtime=MODULE_RUNTIME)

    def test_native_sixteen_case_replay(self):
        import hashlib,json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        raw=(root/'tests/fixtures/native_enumeration_43035110558.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'6de3af385896a915036fb97420b19f011328b69062309d14fffa183263f6e309')
        source=(root/'scripts/enumeration_behavior/observe.bsl').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'642dc1df68be4af0845e3eac44087cae47039d244d621aee6f5657c4d4779232')
        # Only export visibility changes; execute the measured case body itself.
        declarations=source.decode().split('For CaseNo = 1 To 16 Do')[0]
        declarations=declarations.replace('Function ObserveCase(CaseNo, Stage)',
                                           'Function ObserveCase(CaseNo, Stage) Export')
        files=module_files((('Tools',declarations,{}),))
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Enum>OwnedStatus</Enum></ChildObjects>')
        files['Enums/OwnedStatus.xml']=(root/'scripts/enumeration_behavior/Enum.xml').read_bytes()
        app=self.application(files)
        actual=[]
        for case in range(1,17):
            with self.subTest(case=case):
                actual.append(app.execute('Tools.ObserveCase('+str(case)+',"read")'))
        self.assertEqual(actual,json.loads(raw))

    def test_unmeasured_synonym_presentation_not_guessed(self):
        files=self.rich_files()
        files['Enums/Status.xml']=files['Enums/Status.xml'].replace(b'<v8:lang>en</v8:lang>',b'<v8:lang>ru</v8:lang>')
        app=self.application(files)
        with self.assertRaisesRegex(BSLRuntimeError,'synonym presentation'):
            app.execute('String(Enums.Status.Active)')
        self.assertEqual(app.execute('String(Enums.Status.EmptyRef())'),'')

    def test_measured_filled_and_metadata_aliases(self):
        app=self.application()
        self.assertFalse(app.execute('ЗначениеЗаполнено(Перечисления.Status.ПустаяСсылка())'))
        self.assertTrue(app.execute('ЗначениеЗаполнено(Перечисления.Status.Active)'))
        self.assertEqual(app.execute('Метаданные.Перечисления.Status.ПолноеИмя()'),'Перечисление.Status')

    def test_catalog_only_dump_inventory_cannot_cover_enum_declarations(self):
        from test_configuration_dump_info import with_dump_info
        files=with_dump_info()
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Enum>Status</Enum></ChildObjects>')
        files['Enums/Status.xml']=enum_files()['Enums/Status.xml']
        result=import_configuration(files,module_runtime=MODULE_RUNTIME)
        self.assertIn('unsupported configuration file:ConfigDumpInfo.xml',result.activation_issues)
        self.assertEqual({f.path:f.content for f in result.files},files)
