"""SearchDirection has values but no constructor; failure stays catchable."""
import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.direct_collections import UnsupportedNakedSyntax

class SearchConstructorTests(unittest.TestCase):
    def test_routes_aliases_and_rejection_before_argument_effects(self):
        for name in ('SearchDirection','НаправлениеПоиска'):
            for route in ('source','ast','prepared','execute'):
                vm=Interpreter(allow_extensions=True);effects=[]
                vm.register_function('Effect',lambda:effects.append(1))
                text='Try New '+name+'(Effect());Except Caught=True;EndTry;'
                if route=='source':vm.execute(text)
                elif route=='ast':vm.execute_program(parse(text))
                elif route=='prepared':vm.execute_prepared(vm.prepare(text))
                else:vm.execute('Caught=False;Execute("'+text+'");')
                self.assertTrue(vm.variables['caught']);self.assertEqual(effects,[])

    def test_unsupported_constructor_still_rejects_whole_fragment(self):
        vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1))
        with self.assertRaises(UnsupportedNakedSyntax):
            vm.execute('Try Execute("Effect();New UnsupportedConstructor;");Except Caught=True;EndTry;')
        self.assertEqual(effects,[]);self.assertNotIn('caught',vm.variables)

    def test_server_contexts_reject_without_vm(self):
        for directive in ('AtServer','AtServerNoContext','AtClientAtServerNoContext'):
            vm=Interpreter(compilation_profile='managed-thick-file')
            vm.execute('&'+directive+'\nFunction F() Try New SearchDirection;Except Return True;EndTry;Return False;EndFunction')
            self.assertTrue(vm.execute('F();'))
