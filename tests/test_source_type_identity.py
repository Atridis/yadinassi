import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLType


class SourceTypeIdentityTests(unittest.TestCase):
    def test_admitted_common_module_identity(self):
        xml = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>Helpers</Name><ClientManagedApplication>true</ClientManagedApplication></Properties></CommonModule></MetaDataObject>'
        output = []
        app = SourceApplication(source(b'Procedure OnStart() Message(TypeOf(Helpers)=Type("CommonModule")); EndProcedure', {
            'CommonModules/Helpers.xml': xml,
            'CommonModules/Helpers/Ext/Module.bsl': b'Function Answer() Export Return 1; EndFunction'}), output=output.append)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        self.assertEqual(output, ['Да'])

    def test_bilingual_lookup(self):
        self.assertIs(type_by_name('CommonModule'), BSLType.COMMON_MODULE)
        self.assertIs(type_by_name('ОбщийМодуль'), BSLType.COMMON_MODULE)
        self.assertIs(type_of(BSLType.COMMON_MODULE), BSLType.TYPE)

    def test_standalone_module_not_granted_metadata_identity(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaises(TypeError): type_of(vm._self_module)
