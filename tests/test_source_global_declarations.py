import unittest
from test_source_global_modules import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_global_declarations import exported_names
from yadinassi.errors import BSLError


class SourceGlobalDeclarationTests(unittest.TestCase):
    def names(self, text, side='client'):
        return exported_names(text.encode(),'CommonModules/Test/Ext/Module.bsl',side,'standalone')

    def run_app(self, modules, code='Message(Answer());', server=False):
        output=[];app=SourceApplication(configuration(code,modules,server),output=output.append)
        self.addCleanup(app.close);app.start();return output

    def test_unused_body_parser_error_deferred(self):
        modules=[('A','Function Answer() Export\nReturn 42;\nEndFunction',False),
                 ('B','Function Unused() Export\nReturn If Then;\nEndFunction',False)]
        self.assertEqual(self.run_app(modules),['42'])

    def test_selected_body_error_not_hidden(self):
        modules=[('A','Function Answer() Export\nReturn If Then;\nEndFunction',False)]
        with self.assertRaises(BSLError):self.run_app(modules)

    def test_ambiguous_with_bad_body_still_ambiguous(self):
        modules=[('A','Function Answer() Export\nReturn 42;\nEndFunction',False),
                 ('B','Function Answer() Export\nReturn If Then;\nEndFunction',False)]
        with self.assertRaisesRegex(BSLError,'Ambiguous global'):self.run_app(modules)

    def test_strings_and_comments_do_not_add_exports(self):
        text='Function Yes() Export\nX="Function Fake() Export EndFunction"; // EndFunction\nReturn X;\nEndFunction'
        self.assertEqual(self.names(text),('Yes',))

    def test_private_names_not_exported(self):
        self.assertEqual(self.names('Function No()\nReturn 1;\nEndFunction'),())

    def test_parameter_defaults_use_parser(self):
        self.assertEqual(self.names('Function Yes(Val X="Export)", Y=-3) Export\nReturn X;\nEndFunction'),('Yes',))

    def test_bad_header_fails(self):
        with self.assertRaises(BSLError):self.names('Function Bad(Val X=Unknown()) Export\nEndFunction')

    def test_missing_ending_fails(self):
        with self.assertRaisesRegex(BSLError,'boundary'):self.names('Function Bad() Export\nReturn 1;')

    def test_mismatched_ending_fails(self):
        with self.assertRaisesRegex(BSLError,'boundary'):self.names('Function Bad() Export\nEndProcedure')

    def test_nested_routine_boundary_fails(self):
        with self.assertRaisesRegex(BSLError,'boundary'):self.names('Function Bad() Export\nFunction Inner()\nEndFunction\nEndFunction')

    def test_lexical_errors_not_hidden(self):
        with self.assertRaises(BSLError):self.names('Function Bad() Export\n@bad;\nEndFunction')

    def test_module_body_not_allowed(self):
        with self.assertRaises(ValueError):self.names('Message("not a declaration");')

    def test_preprocessor_uses_actual_side(self):
        text='#If Client Then\nFunction ClientOnly() Export\nEndFunction\n#Else\nFunction ServerOnly() Export\nEndFunction\n#EndIf'
        self.assertEqual(self.names(text),('ClientOnly',))
        self.assertEqual(self.names(text,'server'),('ServerOnly',))

    def test_regions_outside_and_inside(self):
        text='#Region Public\nFunction Yes() Export\n#Region Inner\nReturn 1;\n#EndRegion\nEndFunction\n#EndRegion'
        self.assertEqual(self.names(text),('Yes',))

    def test_server_unrelated_bad_body(self):
        modules=[('A','Function Answer() Export\nReturn 42;\nEndFunction',False),
                 ('B','Function Unused() Export\nReturn If Then;\nEndFunction',False)]
        self.assertEqual(self.run_app(modules,server=True),['42'])

    def test_import_in_selected_module_rejected(self):
        modules=[('A','Function Answer() Export\nImport "x.bsl";\nReturn 42;\nEndFunction',False)]
        with self.assertRaises(BSLError):self.run_app(modules)

    def test_russian_declarations(self):
        self.assertEqual(self.names('Функция Ответ(Знач Значение=1) Экспорт\nВозврат Значение;\nКонецФункции'),('Ответ',))

    def test_duplicate_parameter_error_not_hidden(self):
        with self.assertRaises(BSLError):self.names('Function Bad(X,X) Export\nEndFunction')
