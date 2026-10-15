"""The initial, zero-parameter subset of BSL module routines."""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import IncompleteInput
from yadinassi.parser import parse


class RoutineTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_function_procedure_forward_call_export_and_aliases(self):
        self.vm.execute('''
            Процедура Показать() Экспорт
                Сообщить(оТвЕт());
            КонецПроцедуры
            Function Ответ() Export
                Return 42;
            EndFunction
            Показать(); Ответ();
        ''')
        self.assertEqual(self.output, ['42'])
        self.assertTrue(self.vm.routines['ответ'].exported)

    def test_declarations_do_not_execute_bodies(self):
        self.vm.execute('Процедура P() Сообщить("bad"); КонецПроцедуры')
        self.assertEqual(self.output, [])

    def test_return_exits_nested_loops_and_procedure(self):
        self.vm.execute('''
            Функция F()
                Для i = 1 По 3 Цикл
                    Пока Истина Цикл
                        Если i = 1 Тогда Возврат i + 6; КонецЕсли;
                    КонецЦикла;
                КонецЦикла;
                Сообщить("bad");
            КонецФункции
            Процедура P()
                Сообщить(F()); Возврат; Сообщить("bad");
            КонецПроцедуры
            P(); Сообщить("done");
        ''')
        self.assertEqual(self.output, ['7', 'done'])
        self.assertNotIn('i', self.vm.variables)

    def test_missing_return_and_bare_return_are_undefined(self):
        self.vm.execute('''
            Function F() x = 7; EndFunction
            Function G() Return; EndFunction
            Message(F() = Undefined); Message(G() = Undefined);
        ''')
        self.assertEqual(self.output, ['Да', 'Да'])

    def test_module_variables_and_explicit_local_shadowing(self):
        self.vm.execute('''
            Перем x;
            Процедура GlobalWrite() x = x + 1; КонецПроцедуры
            Процедура LocalWrite() Перем x; x = 99; КонецПроцедуры
            x = 7; GlobalWrite(); LocalWrite(); Сообщить(x);
        ''')
        self.assertEqual(self.output, ['8'])

    def test_implicit_root_variables_not_visible_to_routines(self):
        self.vm.execute('x = 7; Function F() Return x; EndFunction')
        with self.assertRaisesRegex(BSLError, 'не определена'):
            self.vm.execute('F()')
        self.assertEqual(self.vm.variables['x'], Decimal(7))

    def test_fresh_locals_and_no_caller_scope_leak(self):
        self.vm.execute('''
            Function Inner() Перем x; Return x; EndFunction
            Function Outer() x = 7; Return Inner(); EndFunction
            Message(Outer() = Undefined); Message(Outer() = Undefined);
        ''')
        self.assertEqual(self.output, ['Да', 'Да'])
        self.assertNotIn('x', self.vm.variables)

    def test_recursion_restores_local_frames(self):
        self.vm.execute('''
            Var depth;
            Function F()
                localDepth = depth;
                depth = depth - 1;
                If depth > 0 Then F(); EndIf;
                Return localDepth;
            EndFunction
            depth = 4; Message(F()); Message(depth);
        ''')
        self.assertEqual(self.output, ['4', '0'])
        self.assertIsNone(self.vm.locals)

    def test_local_for_and_foreach_variables(self):
        self.vm.execute('''
            Function F()
                result = 0; a = New Array; a.Add(3); a.Add(5);
                For Each x In a Do result = result + x; EndDo;
                For i = 1 To 2 Do result = result + i; EndDo;
                Return result;
            EndFunction
            Message(F());
        ''')
        self.assertEqual(self.output, ['11'])
        self.assertEqual(self.vm.variables, {})

    def test_function_return_keeps_object_identity(self):
        self.vm.execute('''
            Var a;
            Function F() Return a; EndFunction
            a = New Array; F().Add(7); Message(a[0]);
        ''')
        self.assertEqual(self.output, ['7'])

    def test_procedure_as_value_rejected_without_body_side_effects(self):
        self.vm.execute('Procedure P() Message("bad"); EndProcedure')
        for code in ['x = P();', 'Message(P());', '?(True, P(), 0);']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'не возвращает значение'):
                self.vm.execute(code)
        self.assertEqual(self.output, [])

    def test_routines_cannot_be_used_as_first_class_values(self):
        self.vm.execute('Procedure P() EndProcedure Function F() Return 42; EndFunction')
        for code in ['Message(P);', 'x = F;', 'F;', 'Message(?(True, F, 0));',
                     'a = New Array; a.Add(P);']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'необходимо вызвать'):
                self.vm.execute(code)
        self.assertEqual(self.output, [])
        self.assertNotIn('x', self.vm.variables)

    def test_wrong_arity_does_not_execute_arguments_or_body(self):
        self.vm.execute('Function F() Message("body"); Return 1; EndFunction')
        with self.assertRaisesRegex(BSLError, '0 аргументов'):
            self.vm.execute('F(Message("argument"));')
        self.assertEqual(self.output, [])

    def test_error_restores_frame_and_preserves_declaration_source(self):
        self.vm.execute('Function F()\n localValue = 1;\n Return 1 / 0;\nEndFunction', 'definition.bsl')
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('F()', 'caller.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('definition.bsl', 3))
        self.assertIsNone(self.vm.locals)
        self.vm.execute('x = 9;')
        self.assertEqual(self.vm.variables, {'x': Decimal(9)})

    def test_invalid_routines_fail_before_side_effects(self):
        cases = [
            'Return 1;',
            'Procedure P() Return 1; EndProcedure',
            'Function F() EndProcedure',
            'Function F() EndFunction Function f() EndFunction',
            'If True Then Procedure P() EndProcedure EndIf',
            'Function F() Function G() EndFunction EndFunction',
            'Function F() Break; EndFunction',
            'Function F() Continue; EndFunction',
        ]
        for code in cases:
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute('Message("bad"); ' + code, 'bad.bsl')
        self.assertEqual(self.output, [])

    def test_incomplete_routines(self):
        for code in ['Function F(', 'Function F()', 'Function F() Return',
                     'Procedure P()\nReturn;', 'Function F() If True Then Return 1;']:
            with self.subTest(code=code), self.assertRaises(IncompleteInput):
                parse(code)

    def test_persistent_routines_and_redefinition(self):
        self.vm.execute('Function F() Return 1; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(1))
        self.vm.execute('Function F() Return 2; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(2))


if __name__ == '__main__':
    unittest.main()
