"""The current module is a plain value, not an implicit dispatch capability."""
from cProfile import Profile
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import make_boundary
from yadinassi.runtime import _Module
from yadinassi.syntax.parser import parse


class DirectCurrentModuleTests(unittest.TestCase):
    def vm(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        return vm

    def test_source_ast_prepared_fragments_and_routine_share_one_value(self):
        vm = self.vm()
        code = '''Var SelfFromExecute;
Function Receiver() Return Eval("ЭтотОбъект"); EndFunction
Execute("SelfFromExecute=ThisObject;");
A=ThisObject;B=этотОбъект;C=Receiver();
'''
        legacy = Interpreter.semantic_name.__code__
        def profile(frame, event, arg):
            if event == 'call' and frame.f_code is legacy:
                raise AssertionError('old name resolver')
        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            vm.execute(code)
            vm.execute_program(parse(code))
            vm.execute_prepared(vm.prepare(code))
            receiver = vm.execute('Eval("ThisObject")')
        finally:
            sys.setprofile(previous)
        self.assertIs(type(receiver), _Module)
        self.assertIs(receiver, vm._self_module)
        for key in ('a','b','c','selffromexecute'):
            self.assertIs(vm.variables[key], receiver)
        self.assertNotIn('thisobject', vm.variables)
        self.assertNotIn('этотобъект', vm.variables)
        # A later separately compiled call still binds the owning module.
        self.assertIs(vm.execute('Receiver()'), receiver)
        self.assertIsNot(self.vm().execute('ThisObject'), receiver)

    def test_import_gets_child_receiver_without_plain_full_check(self):
        vm = self.vm()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root/'Child.bsl').write_text(
            'Function Receiver() Export Return ThisObject; EndFunction '
            'Function Alias() Export Return Eval("ЭтотОбъект"); EndFunction', encoding='utf-8')
        main = str(root/'Main.bsl')
        vm.execute('// #Import Child.bsl\n', main)
        code = 'Imported=Child.Receiver(); Parent=ThisObject;'
        plan = vm.prepare(code, main)
        profile = Profile()
        profile.runcall(vm.execute_prepared, plan)
        self.assertIs(vm.variables['parent'], vm._self_module)
        child = vm.imports['child']
        self.assertIs(vm.variables['imported'], child)
        self.assertIs(vm.execute('Child.Alias()', main), child)
        self.assertIsNot(child, vm._self_module)
        self.assertFalse(any(not isinstance(entry.code, str) and entry.code.co_name == '_check'
                             and entry.code.co_filename == make_boundary.__code__.co_filename
                             for entry in profile.getstats()))
        with self.assertRaises(BSLError):
            vm.execute('Child', main)  # import name still cannot be used as a value

    def test_shadowing_keeps_storage_and_readonly_rules(self):
        vm = self.vm()
        self.assertEqual(vm.execute('''Function Local(Val ЭтотОбъект) Var ThisObject;
ThisObject=3;Return Eval("ThisObject")+ЭтотОбъект; EndFunction Local(4)'''), 7)
        self.assertNotIn('thisobject', vm.variables)
        with self.assertRaisesRegex(BSLError, 'только для чтения'):
            vm.execute('ThisObject=3;')
        self.assertIs(vm.execute('ThisObject'), vm._self_module)
        self.assertEqual(vm.execute('Var ThisObject;ThisObject=4;ThisObject'), 4)
        self.assertIs(vm.execute('ЭтотОбъект'), vm._self_module)

    def test_contextual_server_read_is_not_a_cross_side_value_grant(self):
        vm = self.vm()
        self.assertTrue(vm.execute('''&AtServer
Function S() Return ThisObject=Eval("ЭтотОбъект"); EndFunction
S()'''))
        with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
            vm.execute('''&AtServer
Function TransferSelf() Return ThisObject; EndFunction
TransferSelf()''')
        for expression in ('ThisObject','Eval("ЭтотОбъект")'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute(f'''&AtServerNoContext
Function N() Return {expression}; EndFunction
N()''')

    def test_passive_callback_keeps_value_but_dispatch_and_private_members_stay_denied(self):
        vm = self.vm()
        vm.execute('''Var Count;
Function Handler(Val V, Val Extra) Export Count=Count+1;Return V;EndFunction
Count=0; D=New CallbackDescription("Handler",ThisObject);''')
        self.assertIs(vm.execute('D.Module'), vm._self_module)
        self.assertTrue(vm.execute('(D.Модуль=ЭтотОбъект)'))
        for script in ('ThisObject.Handler(3,4)', 'ThisObject.interpreter', 'RunCallback(D,3)'):
            with self.subTest(script=script), self.assertRaises((BSLError,BoundaryViolation)):
                vm.execute(script)
        self.assertEqual(vm.variables['count'], 0)


if __name__ == '__main__':
    unittest.main()
