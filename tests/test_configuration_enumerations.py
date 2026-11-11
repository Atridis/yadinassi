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
