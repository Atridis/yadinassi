"""Source dynamic fragments retain safe mode and live addresses without VM."""
import unittest
from unittest.mock import patch
import test_source_safe_mode as safe
import test_source_application_exports as exports
from test_configuration_source_runtime import source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter


class SourceFragmentsNoVM(unittest.TestCase):
    def setUp(self):
        old=patch('yadinassi.execution.codegen.experimental_naked_collections.prepare',create=True,side_effect=AssertionError('old compiler'))
        old.start();self.addCleanup(old.stop)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            guard.start();self.addCleanup(guard.stop)

    def test_existing_safemode_and_exports(self):
        for cls,names in ((safe.SourceSafeModeTests,('test_execute_and_eval_inherit_safe_mode',
                'test_dynamic_fragment_cannot_disable_caller','test_dynamic_fragment_counter_is_local_and_cleaned_on_error')),
                (exports.SourceApplicationExportsTests,('test_eval_and_execute_share_slot',))):
            original=cls();self.addCleanup(original.doCleanups)
            for name in names:
                with self.subTest(name=name):getattr(original,name)()

    def app(self):
        app=SourceApplication(source(b''),output=lambda _:None)
        self.addCleanup(app.close);app.start();return app

    def test_source_constructors_and_nested_private_names(self):
        vm=self.app().interpreter
        vm.execute('X=1;Execute "X=X+1;Private=42;Execute ""X=X+1;"";";')
        self.assertEqual(vm.variables['x'],3);self.assertNotIn('private',vm.variables)
        self.assertEqual(vm.execute('Eval("New ValueStorage(5)").Get()'),5)
        vm.execute('Execute "D=New TextDocument; D.SetText(""text"");";')
        self.assertNotIn('d',vm.variables)

    def test_repeated_fragments_keep_live_byref_addresses(self):
        vm=self.app().interpreter
        vm.execute('Procedure P(X) Execute "X=X+1;"; Execute "X=X+1;"; EndProcedure\nA=1;P(A);')
        self.assertEqual(vm.variables['a'],3)

    def test_declarations_and_imports_rejected_before_effects(self):
        vm=self.app().interpreter;effects=[]
        vm.register_function('Effect',lambda:effects.append(1))
        for fragment in ('Effect(); Var X;','Effect(); Procedure P() EndProcedure','Effect(); Import "x";'):
            with self.subTest(fragment=fragment),self.assertRaises(Exception):
                vm.execute('Execute "'+fragment.replace('"','""')+'";')
            self.assertEqual(effects,[])
