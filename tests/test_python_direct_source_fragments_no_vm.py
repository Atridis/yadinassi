"""Source dynamic fragments retain safe mode and live addresses without VM."""
import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration.configuration_source_runtime import SourceApplication


class SourceFragmentsNoVM(unittest.TestCase):
    def app(self, *, allow_extensions=False):
        app=SourceApplication(source(b''),output=lambda _:None, allow_extensions=allow_extensions)
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
        vm=self.app(allow_extensions=True).interpreter;effects=[]
        vm.register_function('Effect',lambda:effects.append(1))
        for fragment in ('Effect(); Var X;','Effect(); Procedure P() EndProcedure','Effect(); Import "x";'):
            with self.subTest(fragment=fragment),self.assertRaises(Exception):
                vm.execute('Execute "'+fragment.replace('"','""')+'";')
            self.assertEqual(effects,[])
