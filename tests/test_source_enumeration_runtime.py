import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


def package(body='', extra=None):
    root = source().files[0].content.replace(b'</Configuration>', b'<ChildObjects><Enum>Status</Enum></ChildObjects></Configuration>')
    enum = b'''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Enum uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Status</Name></Properties><ChildObjects><EnumValue uuid="00000000-0000-0000-0000-000000000003"><Properties><Name>Active</Name></Properties></EnumValue><EnumValue uuid="00000000-0000-0000-0000-000000000004"><Properties><Name>Inactive</Name></Properties></EnumValue></ChildObjects></Enum></MetaDataObject>'''
    files = {'Configuration.xml': root, 'Enums/Status.xml': enum}
    files.update(extra or {})
    return source(('Procedure OnStart() '+body+' EndProcedure').encode(), files)


class SourceEnumerationRuntimeTests(unittest.TestCase):
    def run_source(self, body):
        output = []
        app = SourceApplication(package(body), output=output.append)
        self.addCleanup(app.close)
        app.start()
        return app, output

    def test_values_order_identity_and_methods(self):
        _, output = self.run_source('Message(Enums.Status.Count()); Message(Enums.Status.Get(0)=Enums.Status.Active); Message(Enums.Status.IndexOf(Enums.Status.Inactive));')
        self.assertEqual(output, ['2', 'Да', '1'])

    def test_type_and_description_use_same_snapshot(self):
        _, output = self.run_source('Message(TypeOf(Enums.Status.Active)=Type("EnumRef.Status")); D=New TypeDescription("EnumRef.Status"); Message(D.ContainsType(TypeOf(Enums.Status.Active)));')
        self.assertEqual(output, ['Да', 'Да'])

    def test_bilingual_namespace_and_index(self):
        _, output = self.run_source('Message(Перечисления["Status"]["Active"]=Enums.Status.Active);')
        self.assertEqual(output, ['Да'])

    def test_no_values_created_for_unknown_name(self):
        app = SourceApplication(package('Message(Enums.Status.Unknown);'))
        self.addCleanup(app.close)
        with self.assertRaises(BSLError): app.start()

    def test_applications_do_not_share_reference_identity(self):
        first, _ = self.run_source('')
        second, _ = self.run_source('')
        a = first.enumerations.get_member('Status').get_member('Active')
        b = second.enumerations.get_member('Status').get_member('Active')
        self.assertNotEqual(a, b)

    def test_enum_data_does_not_need_a_database(self):
        app, _ = self.run_source('Message(Enums.Status.EmptyRef().IsEmpty());')
        self.assertIsNone(app.constant_store)
