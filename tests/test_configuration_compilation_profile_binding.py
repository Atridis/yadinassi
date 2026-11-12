"""Profile plumbing only: configuration native matrix remains unconfirmed."""
from dataclasses import FrozenInstanceError, replace
import unittest
from configuration_runtime_fixture import module_files, CLIENT
from yadinassi.configuration_modules import (MODULE_RUNTIME, compile_module,
    compile_session_module, validate_module_sources,
    validate_configuration_compilation_profile)
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_xml import import_configuration


class ProfileBindingTests(unittest.TestCase):
    def config(self):
        return import_configuration(module_files([CLIENT]), module_runtime=MODULE_RUNTIME)

    def test_closed_configuration_admission(self):
        self.assertEqual(validate_configuration_compilation_profile('standalone'), 'standalone')
        for value in ('managed-thick-file','thin','server','',None,True,{}):
            with self.subTest(value=value), self.assertRaises((ValueError,TypeError)):
                validate_configuration_compilation_profile(value)

    def test_frozen_import_identity(self):
        config=self.config()
        self.assertEqual(config.compilation_profile,'standalone')
        with self.assertRaises(FrozenInstanceError):config.compilation_profile='managed-thick-file'

    def test_default_and_explicit_same_import(self):
        files=module_files([CLIENT])
        self.assertEqual(import_configuration(files,module_runtime=MODULE_RUNTIME),
            import_configuration(files,module_runtime=MODULE_RUNTIME,compilation_profile='standalone'))

    def test_import_refuses_unknown_before_source_reads(self):
        with self.assertRaises(ValueError):
            import_configuration({},compilation_profile='managed-thick-file')

    def test_forged_profile_refused_before_activation(self):
        for value in ('managed-thick-file',True,None):
            with self.subTest(value=value),self.assertRaises((TypeError,ValueError)):
                ConfigurationApplication(replace(self.config(),compilation_profile=value))

    def test_preflight_refuses_forged_profile(self):
        with self.assertRaises(ValueError):
            validate_module_sources(replace(self.config(),compilation_profile='managed-thick-file'))

    def test_common_compiler_explicit_equals_default(self):
        raw=CLIENT[1].encode()
        self.assertEqual(compile_module(raw,'CommonModules/Tools/Ext/Module.bsl','client',common=True),
            compile_module(raw,'CommonModules/Tools/Ext/Module.bsl','client',common=True,compilation_profile='standalone'))

    def test_session_compiler_explicit_equals_default(self):
        raw=b'Procedure SessionParametersSetting(Names) EndProcedure'
        self.assertEqual(compile_session_module(raw),compile_session_module(raw,compilation_profile='standalone'))

    def test_common_compiler_rejects_unmeasured_mode(self):
        with self.assertRaises(ValueError):
            compile_module(CLIENT[1].encode(),'x','client',common=True,compilation_profile='managed-thick-file')

    def test_session_compiler_rejects_unmeasured_mode(self):
        with self.assertRaises(ValueError):
            compile_session_module(b'',compilation_profile='managed-thick-file')

    def test_root_profile_bound(self):
        app=ConfigurationApplication(self.config())
        self.assertEqual(app.interpreter.compilation_profile,app.configuration.compilation_profile)
        self.assertEqual(app.interpreter._logical_side,'client')

    def test_from_files_explicit_profile(self):
        app=ConfigurationApplication.from_files(module_files([CLIENT]),compilation_profile='standalone')
        self.assertEqual(app.configuration.compilation_profile,'standalone')

    def test_factory_profile_cannot_override(self):
        app=ConfigurationApplication(self.config())
        for value in ('managed-thick-file',True,None):
            with self.subTest(value=value),self.assertRaises((TypeError,ValueError)):
                app._factory_compilation_profile({'compilation_profile':value})
        kwargs={};app._factory_compilation_profile(kwargs)
        self.assertEqual(kwargs,{'compilation_profile':'standalone'})

    def test_module_kind_does_not_change_execution_authority(self):
        raw=b'#If Server Then\nFunction P() Export Return 1; EndFunction\n#EndIf'
        self.assertEqual(compile_module(raw,'x','client',common=True),[])
        server=compile_module(raw,'x','server',common=True)
        self.assertEqual(len(server),1)
        self.assertEqual(server[0].execution_context,'server')

    def test_bound_child_cannot_change_profile(self):
        from yadinassi.runtime import Interpreter
        app=ConfigurationApplication(self.config())
        child=Interpreter(lambda value:None,family_owner=app.interpreter,
                          compilation_profile='managed-thick-file')
        with self.assertRaises(ValueError):app.bind_interpreter(child)

    def test_actual_child_inherits_profile(self):
        app=ConfigurationApplication(self.config())
        child=app.interpreter_factory(lambda value:None)
        self.assertEqual(child.compilation_profile,app.interpreter.compilation_profile)
        self.assertIs(child._family_owner,app.interpreter)
