"""Native-backed Eval and explicit standalone expression/resource boundaries."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.errors import BSLRuntimeError, IncompleteInput
from yadinassi.parser import parse_expression
from yadinassi.runtime import EVAL_MAX_DEPTH, EVAL_MAX_SOURCE
from yadinassi.serialization import value_to_string_internal, value_from_string_internal


def quote(text):
    return '"' + text.replace('"', '""').replace('\n', '\n|') + '"'


class EvalTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def evaluate(self, text, name='Eval'):
        return self.vm.execute(f'{name}({quote(text)})')

    def test_native_scalar_examples_and_aliases(self):
        for name in ('Eval', 'Вычислить', 'eVaL', 'вЫчИсЛиТь'):
            for text, expected in [('500 + 500*20/100', Decimal(600)),
                                   ('Истина И Ложь', False), ('"Я" + "😀"', 'Я😀'),
                                   ('?(Истина, 7, 1 / 0)', Decimal(7)),
                                   ('СтрДлина("Я😀")', Decimal(3)),
                                   ('ТипЗнч(Новый Массив) = Тип("Массив")', True)]:
                with self.subTest(name=name, text=text):
                    self.assertEqual(self.evaluate(text, name), expected)

    def test_native_number_argument_and_undefined_error(self):
        self.assertEqual(self.vm.execute('Eval(12)'), Decimal(12))
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('Eval(Undefined)')

    def test_native_local_module_parameter_and_nested_scopes(self):
        self.vm.execute('''
        Var shared;
        Function Read(parameter)
            local = 14;
            Return Eval("local + shared + parameter + Eval(""local"")");
        EndFunction
        shared = 23;
        result = Read(3);
        ''')
        self.assertEqual(self.vm.execute('result'), Decimal(54))
        self.assertIsNone(self.vm.locals)

    def test_native_reference_mutation_reaches_caller(self):
        self.vm.execute('''
        Function Bump(value)
            value = value + 1;
            Return value;
        EndFunction
        Procedure Check(parameter)
            result = Eval("Bump(parameter)");
            Message(result); Message(parameter);
        EndProcedure
        x = 10; Check(x);
        ''')
        self.assertEqual(self.output, ['11', '11'])
        self.assertEqual(self.vm.execute('x'), Decimal(11))

    def test_equality_is_not_assignment(self):
        self.vm.execute('x = 5;')
        self.assertIs(self.evaluate('x = 99'), False)
        self.assertEqual(self.vm.execute('x'), Decimal(5))

    def test_native_comment_and_rejected_semicolon(self):
        self.assertEqual(self.evaluate('1 + 2 // комментарий'), Decimal(3))
        with self.assertRaises(BSLRuntimeError):
            self.evaluate('1 + 2;')

    def test_whole_expression_parsed_before_side_effects(self):
        self.vm.execute('''Function Bump(value) value = value + 1; Return value; EndFunction
                           x = 5;''')
        for text in ('Bump(x); x = 99;', 'Bump(x) +', 'Bump(x) 1',
                     'Bump(x) // comment\n;'):
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError):
                self.evaluate(text)
            self.assertEqual(self.vm.execute('x'), Decimal(5))

    def test_arity_before_argument_side_effects(self):
        self.vm.execute('''Function Bump(value) value = value + 1; Return value; EndFunction
                           x = 5;''')
        for call in ('Eval()', 'Eval("1", Bump(x))', 'Вычислить(Bump(x), "1")'):
            with self.subTest(call=call), self.assertRaises(BSLRuntimeError):
                self.vm.execute(call)
            self.assertEqual(self.vm.execute('x'), Decimal(5))
        with self.assertRaises(BSLRuntimeError):
            self.evaluate('Eval("1", Bump(x))')
        self.assertEqual(self.vm.execute('x'), Decimal(5))

    def test_argument_evaluated_once(self):
        self.vm.execute('''Var count;
            Function Text() count = count + 1; Return "2 + 3"; EndFunction
            count = 0; result = Eval(Text());''')
        self.assertEqual(self.vm.execute('count'), Decimal(1))
        self.assertEqual(self.vm.execute('result'), Decimal(5))

    def test_dynamic_errors_are_catchable_not_incomplete_outer_input(self):
        for text in ('', '1 +', '(', '1 / 0', 'unknown', '"unfinished', 'Eval()'):
            self.vm.execute('saved = 42;')
            with self.subTest(text=text):
                self.vm.execute('Try saved = Eval(' + quote(text) + '); '
                                'Except Message("caught"); EndTry;')
                self.assertEqual(self.vm.execute('saved'), Decimal(42))
                self.assertEqual(self.vm.execute('Eval("3")'), Decimal(3))
        self.assertEqual(self.output, ['caught'] * 7)

    def test_dynamic_syntax_error_has_bounded_synthetic_source(self):
        with self.assertRaises(BSLRuntimeError) as caught:
            self.evaluate('1 +')
        self.assertNotIsInstance(caught.exception, IncompleteInput)
        self.assertEqual(caught.exception.source, '<Вычислить>')
        self.assertNotIn('Traceback', str(caught.exception))

    def test_no_module_or_preprocessor_syntax_even_in_inactive_regions(self):
        for text in ('Var x;', 'Function F() Return 1; EndFunction',
                     'Return 1', 'If True Then 1; EndIf', '~label: 1',
                     '#If Client Then\n1\n#EndIf',
                     '#If Server Then\nignored\n#EndIf\n1',
                     '#Region R\n1\n#EndRegion', '&AtClient\n1',
                     '// #Import missing.bsl\n1'):
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError):
                self.evaluate(text)
        self.assertEqual(self.vm.imports, {})
        self.assertEqual(self.vm.routines, {})
        self.assertEqual(self.vm.variables, {})

    def test_directive_text_inside_string_and_ordinary_comment_allowed(self):
        for value in ('#If Client Then', '// #Import no.bsl', '&AtClient'):
            self.assertEqual(self.evaluate(quote(value)), value)
        self.assertEqual(self.evaluate('1 // ordinary #Import no.bsl'), Decimal(1))

    def test_no_python_host_escape(self):
        for text in ('__import__("os")', 'Eval.function', 'Eval.__class__',
                     '(New Array).__class__', 'open("secret")', 'lambda: 1'):
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError):
                self.evaluate(text)
        self.assertEqual(self.evaluate('2 + 3'), Decimal(5))

    def test_non_native_host_values_cannot_run_conversion_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('Must not call Python conversion')
        for value in (Hostile(), [], {}, Decimal('NaN'), Decimal('Infinity'), True):
            self.vm.variables['payload'] = value
            with self.subTest(value=type(value)), self.assertRaises(BSLRuntimeError):
                self.vm.execute('Eval(payload)')

    def test_eval_result_uses_existing_serialization_both_directions(self):
        for text in ('12', 'True', '"Я😀"', 'Undefined', 'New Array'):
            value = self.evaluate(text)
            encoded = value_to_string_internal(value)
            restored = value_from_string_internal(encoded)
            self.assertEqual(value_to_string_internal(restored), encoded)

    def test_standalone_module_scope_and_custom_function_shadowing(self):
        self.vm.execute('x = 9;')
        self.assertEqual(self.evaluate('x'), Decimal(9))
        self.vm.execute('Function Eval(Val x) Return x + 1; EndFunction')
        self.assertEqual(self.vm.execute('Eval(4)'), Decimal(5))
        self.assertEqual(self.vm.execute('Вычислить("x")'), Decimal(9))

    def test_imported_eval_uses_own_frame_and_module_not_parent(self):
        # Imports are a Yadinassi extension; this checks its existing isolation.
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw).resolve()
            (folder / 'Lib.bsl').write_text('''Var shared;
                Function Read(Val x) Export
                    local = 3; Return Eval("shared + local + x");
                EndFunction
                shared = 20;''', encoding='utf-8')
            self.vm.execute('// #Import Lib.bsl\nshared = 900; result = Lib.Read(4);',
                            str(folder / 'Main.bsl'))
            self.assertEqual(self.vm.execute('result'), Decimal(27))
            self.assertEqual(self.vm.execute('shared'), Decimal(900))

    def test_source_resource_boundary_and_recovery(self):
        self.assertEqual(self.evaluate('1' + ' ' * (EVAL_MAX_SOURCE - 1)), Decimal(1))
        with self.assertRaisesRegex(BSLRuntimeError, 'предел текста'):
            self.evaluate('1' + ' ' * EVAL_MAX_SOURCE)
        self.assertEqual(self.vm._eval_depth, [0])
        self.assertEqual(self.evaluate('1'), Decimal(1))

    def test_recursive_eval_resource_guard_and_recovery(self):
        self.vm.execute('text = "Eval(text)";')
        with self.assertRaisesRegex(BSLRuntimeError, 'предел вложенности'):
            self.vm.execute('Eval(text)')
        self.assertEqual(self.vm._eval_depth, [0])
        self.assertEqual(self.evaluate('1'), Decimal(1))

    def test_exact_nesting_budget(self):
        self.vm.execute('''
            Function Recurse(n)
                If n = 0 Then Return 0; EndIf;
                Return Eval("Recurse(n - 1)");
            EndFunction
        ''')
        self.assertEqual(self.evaluate(f'Recurse({EVAL_MAX_DEPTH - 1})'), Decimal(0))
        with self.assertRaisesRegex(BSLRuntimeError, 'предел вложенности'):
            self.evaluate(f'Recurse({EVAL_MAX_DEPTH})')
        self.assertEqual(self.vm._eval_depth, [0])

    def test_deep_parse_and_deep_ast_errors_are_recoverable(self):
        for text in ('(' * 2000 + '1' + ')' * 2000, '+'.join(['1'] * 2000)):
            with self.subTest(length=len(text)), self.assertRaises(BSLRuntimeError):
                self.evaluate(text)
            self.assertEqual(self.vm._eval_depth, [0])
            self.assertEqual(self.evaluate('1'), Decimal(1))

    def test_parser_entry_point_consumes_input_and_rejects_statements(self):
        for text in ('1;', '1 2', 'x = 1; x = 2', '// #Import missing.bsl\n1'):
            with self.subTest(text=text), self.assertRaises(BSLError):
                parse_expression(text)
