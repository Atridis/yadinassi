"""Integration of explicit module execution with owned v8 register schemas."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from configuration_runtime_fixture import CLIENT, module_files
from test_information_registers import register_files


def combined_files():
    files = register_files()
    modules = module_files([CLIENT])
    files['Configuration.xml'] = files['Configuration.xml'].replace(
        b'</ChildObjects>', b'<CommonModule>Tools</CommonModule></ChildObjects>')
    files.update({k: v for k, v in modules.items() if k.startswith('CommonModules/')})
    return files


class RegisterConfigurationRuntimeTests(unittest.TestCase):
    def test_explicit_runtime_keeps_v8_records_and_query(self):
        files = combined_files()
        config = import_configuration(files, numbering_policy='decimal_v1', module_runtime=MODULE_RUNTIME)
        self.assertEqual(len(config.information_registers), 1)
        self.assertEqual(len(config.common_modules), 1)
        with tempfile.TemporaryDirectory() as folder:
            context = SQLiteDBContext.create(Path(folder) / 'application.sqlite', config)
            try:
                self.assertEqual(context.backend.storage_version, 8)
                out = []
                app = ConfigurationApplication.from_database(context, output=out.append)
                app.interpreter.execute('R=InformationRegisters.Prices.CreateRecordManager();'
                    'R.Item="A";R.Region="North";R.Price=Tools.Double(5);R.Enabled=True;R.Write();'
                    'Q=New Query("SELECT Price FROM InformationRegister.Prices");'
                    'S=Q.Execute().Select();S.Next();Message(S.Price);')
                self.assertEqual(out, ['10'])
                self.assertEqual(context.backend.export_configuration(), files)
            finally:
                context.close()

    def test_runtime_rejects_register_schema_mismatch_and_closes_view(self):
        config = import_configuration(combined_files(), numbering_policy='decimal_v1', module_runtime=MODULE_RUNTIME)
        with tempfile.TemporaryDirectory() as folder:
            context = SQLiteDBContext.create(Path(folder) / 'application.sqlite', config)
            try:
                view = Mock()
                view.registers.return_value = (replace(config.information_registers[0], name='Other'),)
                with patch.object(context.backend, 'begin_register_read', return_value=view):
                    with self.assertRaisesRegex(ValueError, 'information-register schema'):
                        ConfigurationApplication(config, database_context=context)
                view.close.assert_called_once_with()
            finally:
                context.close()

    def test_module_opt_in_and_authority_rejections_survive_register_import(self):
        files = combined_files()
        self.assertTrue(import_configuration(files).activation_issues)
        for fragment, replacement in ((b'<Privileged>false', b'<Privileged>true'),
                (b'<ReturnValuesReuse>DontUse', b'<ReturnValuesReuse>DuringSession')):
            candidate = dict(files)
            candidate['CommonModules/Tools.xml'] = candidate['CommonModules/Tools.xml'].replace(fragment, replacement)
            with self.subTest(fragment=fragment), self.assertRaises(ValueError):
                import_configuration(candidate, module_runtime=MODULE_RUNTIME)
        files['Ext/SessionModule.bsl'] = b'Procedure OnSessionStart() EndProcedure'
        with self.assertRaises(ValueError): ConfigurationApplication.from_files(files)
