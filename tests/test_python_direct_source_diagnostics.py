"""Source diagnostics retain authored names without changing admission."""
import unittest
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLError
from test_configuration_source_runtime import source
from test_source_references import package


class SourceDiagnosticsTests(unittest.TestCase):
    def app(self,configuration):
        output=[];app=SourceApplication(configuration,output=output.append)
        self.addCleanup(app.close)
        return app,output

    def test_unknown_service_preserves_authored_name_before_arguments(self):
        for name in ('MissingService','НеИзвестныйСервис','mIxEdName'):
            app,output=self.app(source(('Procedure OnStart() '+name+'(Touch()); EndProcedure\n'
                'Function Touch() Message("wrong");Return 1;EndFunction').encode()))
            with self.assertRaisesRegex(BSLError,name):app.start()
            self.assertEqual(output,[])

    def test_known_services_remain_case_insensitive(self):
        app,output=self.app(source(b'Procedure OnStart() mEsSaGe(sTrLeN("abc"));EndProcedure'))
        app.start();self.assertEqual(output,['3'])

    def test_fragment_unknown_service_preserves_spelling(self):
        for expression in ('Execute("MissingFragment();");','X=Eval("MissingFragment()");'):
            app,_=self.app(source(('Procedure OnStart() '+expression+' EndProcedure').encode()))
            with self.assertRaisesRegex(BSLError,'MissingFragment'):app.start()

    def test_getref_requires_explicit_uuid_before_argument_effects(self):
        for method,args in (('GetRef',''),('GetRef','Touch(),Touch()'),('ПолучитьСсылку','Touch(),Touch()')):
            config=package('Catalogs.Items.'+method+'('+args+');')
            from yadinassi.configuration.configuration_source import import_source
            files={f.path:f.content for f in config.files}
            files['Ext/SessionModule.bsl']+=b'\nFunction Touch() Message("wrong");Return 1;EndFunction'
            app,output=self.app(import_source(files))
            with self.assertRaisesRegex(BSLError,'one explicit UUID'):app.start()
            self.assertEqual(output,[])

    def test_emptyref_still_takes_no_arguments(self):
        app,_=self.app(package('Catalogs.Items.EmptyRef(1);'))
        with self.assertRaisesRegex(BSLError,'take no arguments'):app.start()

    def test_shell_inventory_and_diagnostic(self):
        from test_source_shell import SourceShellTests
        case=SourceShellTests();self.addCleanup(case.doCleanups)
        case.test_error_keeps_inventory()
