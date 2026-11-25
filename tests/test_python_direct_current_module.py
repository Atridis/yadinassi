"""The current module is a plain value, not an implicit dispatch capability."""
from cProfile import Profile
from pathlib import Path
from tempfile import TemporaryDirectory
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
        vm.execute(code)
        vm.execute_program(parse(code))
        vm.execute_prepared(vm.prepare(code))
        receiver = vm.execute('Eval("ThisObject")')
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

    def test_foreign_and_forged_module_values_are_not_public_receivers(self):
        own, foreign = self.vm(), self.vm()
        foreign.execute('Var Field Export; Field=41; Function Read() Export Return Field; EndFunction')
        own.execute('Var Field Export; Field=17;')
        forged = _Module(own)
        forged.ready = True
        for value in (foreign._self_module, forged):
            own.variables['receiver'] = value
            for source in ('Receiver.Field', 'Receiver.Field=42;', 'Receiver.Read()'):
                with self.subTest(source=source), self.assertRaises(BoundaryViolation):
                    own.execute(source)
        self.assertEqual(own.execute('Field'),17)
        self.assertEqual(foreign.execute('Field'),41)

    def test_module_member_semantic_failure_and_post_argument_lifecycle_differ(self):
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        vm.execute('Var Field Export; Field=17; Procedure Write(Val NewValue) Export Field=NewValue; EndProcedure')
        self.assertEqual(vm.execute('Try ThisObject.Private=42; Except Caught=True; EndTry; Caught'),True)
        def close():
            vm.close()
            return 42
        vm.register_function('CloseOwner',close)
        with self.assertRaises(BoundaryViolation):
            vm.execute('Try ThisObject.Write(CloseOwner()); Except Escaped=True; EndTry;')
        self.assertNotIn('escaped',vm.variables)
        self.assertEqual(vm.variables['field'],17)

    def test_declared_receiver_name_shadows_module_methods_as_well(self):
        vm = self.vm()
        self.assertEqual(vm.execute('Var ThisObject; ThisObject=New Array; ThisObject.Add(1); ThisObject.Count()'),1)
        self.assertIs(vm.execute('ЭтотОбъект'),vm._self_module)

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

    def test_passive_callback_keeps_value_and_dispatches_only_public_handlers(self):
        vm = self.vm()
        vm.execute('''Var Count;
Function Handler(Val V, Val Extra) Export Count=Count+1;Return V;EndFunction
Function Hidden() Count=Count+1;Return Count;EndFunction
Count=0; D=New CallbackDescription("Handler",ThisObject);''')
        self.assertIs(vm.execute('D.Module'), vm._self_module)
        self.assertTrue(vm.execute('(D.Модуль=ЭтотОбъект)'))
        for script in ('ThisObject.Hidden()', 'ThisObject.interpreter', 'RunCallback(New CallbackDescription("Hidden",ThisObject),3)'):
            with self.subTest(script=script), self.assertRaises((BSLError,BoundaryViolation)):
                vm.execute(script)
        self.assertEqual(vm.variables['count'], 0)
        self.assertEqual(vm.execute('RunCallback(D,3)'), 3)
        self.assertEqual(vm.variables['count'], 1)


if __name__ == '__main__':
    unittest.main()
