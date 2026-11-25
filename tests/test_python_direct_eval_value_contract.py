"""Eval always consumes an expression value, even as an outer statement."""
from pathlib import Path
import unittest
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse


def quoted(text):return '"'+text.replace('"','""')+'"'


class DirectEvalValueContractTests(unittest.TestCase):
    def test_procedure_rejection_precedes_effects_for_all_outer_routes(self):
        for route in ('source','ast','prepared','execute'):
            vm=Interpreter(allow_extensions=True);seen=[]
            vm.register_function('Effect',lambda:seen.append('arg') or 'argument')
            vm.register_function('Proc',lambda value:seen.append('proc'),returns_value=False)
            text='Eval("Proc(Effect())");'
            with self.subTest(route=route):
                with self.assertRaisesRegex(BSLError,'не возвращает значение'):
                    if route=='source':vm.execute(text)
                    elif route=='ast':vm.execute_program(parse(text))
                    elif route=='prepared':vm.execute_prepared(vm.prepare(text))
                    else:vm.execute('Execute('+quoted(text)+');')
            self.assertEqual(seen,[])
            self.assertEqual(vm.execute('Eval("1+2")'),3)

    def test_alias_group_nested_eval_and_persistent_procedure(self):
        vm=Interpreter();vm.execute('Var Count;Count=0;Procedure Proc(X) Count=Count+1;EndProcedure Function Effect() Count=Count+10;Return 1;EndFunction')
        for expression in ('Proc(Effect())','(Proc(Effect()))','Eval("Proc(Effect())")'):
            for name in ('Eval','Вычислить'):
                with self.subTest(expression=expression,name=name),self.assertRaisesRegex(BSLError,'не возвращает значение'):
                    vm.execute(name+'('+quoted(expression)+');')
                self.assertEqual(vm.variables['count'],0)

    def test_captured_host_procedure_is_not_invoked(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Proc',lambda value:seen.append('proc'),returns_value=False)
        vm.register_function('Effect',lambda:seen.append('arg'))
        vm.variables['saved']=vm.functions['proc']
        with self.assertRaisesRegex(BSLError,'не возвращает значение'):vm.execute('Eval("Saved(Effect())");')
        self.assertEqual(seen,[])

    def test_reused_eval_revalidates_live_procedure_metadata(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Call',lambda value:seen.append('call') or value)
        vm.register_function('Effect',lambda:seen.append('arg') or 7)
        vm.register_function('MakeProcedure',lambda:setattr(vm.functions['call'],'returns_value',False))
        with self.assertRaisesRegex(BSLError,'не возвращает значение'):
            vm.execute('First=Eval("Call(Effect())");MakeProcedure();Second=Eval("Call(Effect())");')
        self.assertEqual(seen,['arg','call']);self.assertEqual(vm.variables['first'],7);self.assertNotIn('second',vm.variables)

    def test_function_undefined_is_valid_and_custom_eval_is_unchanged(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('FunctionReturningUndefined',lambda:seen.append('function'))
        self.assertIsNone(vm.execute('Eval("FunctionReturningUndefined()")'))
        vm.register_function('Eval',lambda text:seen.append('custom'))
        self.assertIsNone(vm.execute('Eval("invalid text")'))
        self.assertEqual(seen,['function','custom'])

    def test_plain_execute_statement_still_accepts_procedure(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Proc',lambda:seen.append('proc'),returns_value=False)
        vm.execute('Proc();Execute("Proc();");')
        self.assertEqual(seen,['proc','proc'])

    def test_existing_native_eval_checkpoint_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8-sig')
        helpers=source[source.index('Процедура ПроверитьВычисление('):source.index('// Выполнить: ошибки компиляции')]
        start=source.index('// Вычислить / Eval: наблюдения до реализации')
        end=source.index('// Нативный checkpoint перед реализацией Выполнить;',start)
        program='Перем МодульноеВычисления;\n'+helpers+source[start:end]
        expected=[line for line in (root/'tests/fixtures/native_windows/functions.out').read_text(encoding='utf-8-sig').splitlines() if line.startswith('eval.')]
        output=[];Interpreter(output=output.append).execute(program)
        self.assertEqual(output,expected);self.assertEqual(len(output),30)
