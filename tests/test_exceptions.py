"""Bilingual exceptions, dynamic handler state, and source-aware diagnostics."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi import ast
from yadinassi.errors import BSLRuntimeError, IncompleteInput
from yadinassi.parser import parse


ROOT = Path(__file__).resolve().parents[1]


class ExceptionTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_russian_english_and_mixed_case_statements(self):
        self.vm.execute('''
            пОпЫтКа ВызватьИсключение "русский";
            иСкЛюЧеНиЕ Сообщить(ОписаниеОшибки()); кОнЕцПоПыТкИ;
            tRy Raise "english"; eXcEpT Message(ErrorDescription()); eNdTrY;
            Попытка Raise "mixed"; Except Сообщить(ErrorDescription()); КонецПопытки;
        ''', 'aliases.bsl')
        self.assertEqual(len(self.output), 3)
        for description, message in zip(self.output, ['русский', 'english', 'mixed']):
            self.assertTrue(description.startswith('aliases.bsl:'))
            self.assertTrue(description.endswith(': ' + message))

    def test_success_skips_handler_and_empty_blocks_are_valid(self):
        self.vm.execute('''
            Try x = 7; Except Message("bad"); EndTry;
            Try Except Message("bad"); EndTry;
            Try Raise "ignored"; Except EndTry;
            Message(x); Message("done");
        ''')
        self.assertEqual(self.output, ['7', 'done'])

    def test_raise_stops_body_and_execution_resumes_after_handler(self):
        self.vm.execute('''
            Message("before");
            Try
                Message("body"); Raise "stop"; Message("unreachable");
            Except
                Message("handler");
            EndTry;
            Message("after");
        ''')
        self.assertEqual(self.output, ['before', 'body', 'handler', 'after'])

    def test_raise_value_uses_bsl_string_conversion(self):
        for expression, expected in [('42.500', '42.5'), ('True', 'Да'),
                                     ('False', 'Нет'), ('Undefined', ''),
                                     ('"a" + 2', 'a2')]:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError) as caught:
                self.vm.execute('Raise ' + expression + ';', 'raise.bsl')
            self.assertEqual(caught.exception.message, expected)
            self.assertEqual((caught.exception.source, caught.exception.line,
                              caught.exception.column), ('raise.bsl', 1, 1))

    def test_raised_expression_is_evaluated_once(self):
        self.vm.execute('''
            Var calls; calls = 0;
            Function Description() calls = calls + 1; Return "once"; EndFunction
            Try Raise Description(); Except EndTry;
            Message(calls);
        ''')
        self.assertEqual(self.output, ['1'])

    def test_error_in_raise_expression_keeps_expression_location(self):
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Raise 1 / 0;', 'expression.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line,
                          caught.exception.column), ('expression.bsl', 1, 9))
        self.assertEqual(caught.exception.message, 'Деление на ноль')

    def test_error_description_is_exact_source_aware_error_string(self):
        error = BSLRuntimeError('host message', 'original.bsl', 9, 4)

        def fail():
            raise error

        self.vm.register_function('Fail', fail)
        self.vm.execute('Try Fail(); Except Message(ErrorDescription()); EndTry;', 'caller.bsl')
        self.assertEqual(self.output, [str(error)])

    def test_error_description_empty_outside_handler_and_after_separate_execute(self):
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')
        self.vm.execute('Try Raise "caught"; Except Message(ОписаниеОшибки()); EndTry;', 'once.bsl')
        self.assertTrue(self.output[0].endswith(': caught'))
        self.assertEqual(self.vm.execute('ОписаниеОшибки()'), '')
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_error_description_requires_zero_arguments(self):
        self.vm.execute('Try ErrorDescription(1); Except Message("caught"); EndTry;')
        self.assertEqual(self.output, ['caught'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_nested_handler_discards_outer_description_but_successful_try_does_not(self):
        self.vm.execute('''
            Try Raise "outer";
            Except
                outerDescription = ErrorDescription();
                Try x = 1; Except Message("bad"); EndTry;
                Message(ErrorDescription() = outerDescription);
                Try Raise "inner";
                Except
                    Message(ErrorDescription());
                EndTry;
                Message(ErrorDescription() = "");
                Try x = 1; Except Message("bad"); EndTry;
                Message(ErrorDescription() = "");
            EndTry;
            Message(ErrorDescription() = "");
        ''', 'nested.bsl')
        self.assertEqual(self.output[0], 'Да')
        self.assertTrue(self.output[1].endswith(': inner'))
        self.assertEqual(self.output[2:], ['Да', 'Да', 'Да'])

    def test_error_description_is_dynamic_inside_called_routines(self):
        self.vm.execute('''
            Function Describe() Return ErrorDescription(); EndFunction
            Function Indirect() Return Describe(); EndFunction
            Message(Indirect() = "");
            Try Raise "dynamic";
            Except Message(Indirect() = ErrorDescription()); EndTry;
            Message(Indirect() = "");
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да'])

    def test_new_handler_failure_is_caught_only_by_outer_try(self):
        self.vm.execute('''
            Try
                Try Raise "first";
                Except
                    Message("inner handler");
                    Raise "second";
                    Message("unreachable");
                EndTry;
            Except
                Message(ErrorDescription());
            EndTry;
            Message(ErrorDescription() = "");
        ''', 'replacement.bsl')
        self.assertEqual(self.output[0], 'inner handler')
        self.assertTrue(self.output[1].endswith(': second'))
        self.assertEqual(self.output[2], 'Да')

    def test_uncaught_handler_failure_clears_dynamic_context(self):
        with self.assertRaisesRegex(BSLRuntimeError, 'second'):
            self.vm.execute('Try Raise "first"; Except Raise "second"; EndTry;')
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')
        self.vm.execute('Try Raise "third"; Except Message(ErrorDescription()); EndTry;')
        self.assertTrue(self.output[0].endswith(': third'))
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_rethrow_preserves_original_error_object_and_source(self):
        error = BSLRuntimeError('original', 'definition.bsl', 12, 8)

        def fail():
            raise error

        self.vm.register_function('Fail', fail)
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('''
                Try
                    Try Fail(); Except Raise; EndTry;
                Except
                    ВызватьИсключение;
                EndTry;
            ''', 'caller.bsl')
        self.assertIs(caught.exception, error)
        self.assertEqual(str(caught.exception), 'definition.bsl:12:8: original')
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_rethrow_after_inner_handler_fails_clearly_without_stale_outer_error(self):
        self.vm.execute('''
            Try
                Try Raise "outer";
                Except
                    Try Raise "inner"; Except EndTry;
                    Raise;
                EndTry;
            Except Message(ErrorDescription()); EndTry;
        ''', 'rethrow.bsl')
        self.assertEqual(len(self.output), 1)
        self.assertIn('после вложенного обработчика пока не поддерживается', self.output[0])
        self.assertTrue(self.output[0].startswith('rethrow.bsl:6:'))

    def test_explicit_raise_remains_available_after_nested_handler(self):
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('''
                Try Raise "outer";
                Except
                    Try Raise "inner"; Except EndTry;
                    Raise "explicit replacement";
                EndTry;
            ''', 'replacement.bsl')
        self.assertEqual(caught.exception.message, 'explicit replacement')
        self.assertEqual((caught.exception.source, caught.exception.line), ('replacement.bsl', 5))
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_nested_handler_in_called_routine_invalidates_parent_rethrow(self):
        self.vm.execute('''
            Procedure Catch()
                Try Raise "inner"; Except EndTry;
            EndProcedure
        ''')
        with self.assertRaisesRegex(BSLRuntimeError, 'после вложенного обработчика пока не поддерживается'):
            self.vm.execute('Try Raise "outer"; Except Catch(); Raise; EndTry;')
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_rethrow_nested_in_handler_condition_and_loop(self):
        with self.assertRaisesRegex(BSLRuntimeError, ': original$'):
            self.vm.execute('''
                Try Raise "original";
                Except
                    If True Then
                        For i = 1 To 1 Do
                            Try Raise; Except Raise; EndTry;
                        EndDo;
                    EndIf;
                EndTry;
            ''')
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_runtime_error_types_are_catchable(self):
        cases = [
            ('x = 1 / 0;', 'Деление на ноль'),
            ('x = missing;', 'не определена'),
            ('x = -"text";', 'Ожидается число'),
            ('x = Number("not a number");', ''),
            ('a = New Array; x = a[0];', 'Индекс массива'),
            ('a = New Array; a[0] = 1;', 'Индекс массива'),
            ('a = New Array; a.Unknown();', 'Метод или свойство'),
            ('x = New Missing;', 'Тип не определен'),
            ('StrConcat(1);', 'ожидает массив'),
            ('For Each x In 1 Do EndDo;', 'ожидает массив'),
            ('If "text" Then EndIf;', 'Ожидается булево'),
        ]
        for body, message in cases:
            with self.subTest(body=body):
                output = []
                vm = Interpreter(output=output.append)
                vm.execute('Try ' + body + ' Except Message(ErrorDescription()); EndTry;', 'runtime.bsl')
                self.assertEqual(len(output), 1)
                self.assertTrue(output[0].startswith('runtime.bsl:1:'))
                self.assertIn(message, output[0])
                self.assertEqual(vm.execute('ErrorDescription()'), '')

    def test_known_host_exceptions_are_wrapped_and_catchable(self):
        for exception_type in (ArithmeticError, ValueError, TypeError, IndexError, RecursionError):
            with self.subTest(exception_type=exception_type):
                def fail():
                    raise exception_type('host failure')

                self.vm.register_function('Fail', fail)
                self.vm.execute('Try Fail(); Except Message(ErrorDescription()); EndTry;', 'host.bsl')
                self.assertTrue(self.output[-1].startswith('host.bsl:1:'))
                self.assertTrue(self.output[-1].endswith(': host failure'))
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('Fail()')

    def test_empty_host_exception_message_uses_type_name(self):
        def fail():
            raise ValueError()

        self.vm.register_function('Fail', fail)
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Fail()', 'host.bsl')
        self.assertEqual(caught.exception.message, 'ValueError')

    def test_unwrapped_host_errors_and_process_signals_are_not_caught(self):
        for exception_type in (RuntimeError, KeyboardInterrupt, SystemExit):
            for in_handler in (False, True):
                with self.subTest(exception_type=exception_type, in_handler=in_handler):
                    error = exception_type('stop')

                    def fail():
                        raise error

                    self.vm.register_function('Fail', fail)
                    body = ('Try Raise "first"; Except Fail(); EndTry;' if in_handler else 'Fail();')
                    with self.assertRaises(exception_type) as caught:
                        self.vm.execute('Try ' + body + ' Except Message("bad"); EndTry;')
                    self.assertIs(caught.exception, error)
                    self.assertEqual(self.vm.execute('ErrorDescription()'), '')
        self.assertEqual(self.output, [])

    def test_syntax_errors_from_host_are_never_caught(self):
        for error in (BSLError('syntax', 'bad.bsl', 3, 5),
                      IncompleteInput('unfinished', 'bad.bsl', 4, 1)):
            with self.subTest(error=type(error)):
                def fail():
                    raise error

                self.vm.register_function('Fail', fail)
                with self.assertRaises(type(error)) as caught:
                    self.vm.execute('Try Fail(); Except Message("bad"); EndTry;')
                self.assertIs(caught.exception, error)
        self.assertEqual(self.output, [])

    def test_syntax_errors_in_unreachable_blocks_precede_all_effects(self):
        for code in ['Try x = ; Except Message("bad"); EndTry;',
                     'Try x = 1; Except x = ; EndTry;',
                     'Try x = 1; Except @ EndTry;']:
            with self.subTest(code=code), self.assertRaises(BSLError) as caught:
                self.vm.execute('Message("bad"); ' + code, 'syntax.bsl')
            self.assertNotIsInstance(caught.exception, BSLRuntimeError)
        self.assertEqual(self.output, [])

    def test_runtime_error_is_a_public_bsl_error_subclass(self):
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('1 / 0')
        self.assertIsInstance(caught.exception, BSLRuntimeError)

    def test_handler_does_not_rollback_variables_or_create_a_new_scope(self):
        self.vm.execute('''
            x = 1;
            Try x = 2; Raise "failure";
            Except x = x + 1; newValue = 9; EndTry;
            Message(x); Message(newValue);
        ''')
        self.assertEqual(self.output, ['3', '9'])

    def test_routine_failure_restores_caller_frame_and_declaration_source(self):
        self.vm.execute('Function Fail()\n localOnly = 1;\n Raise "routine";\nEndFunction', 'definition.bsl')
        self.vm.execute('''
            Function Caller()
                localValue = "caller";
                Try Fail();
                Except
                    Message(localValue); Message(ErrorDescription());
                EndTry;
                Return localValue;
            EndFunction
            Message(Caller());
        ''', 'caller.bsl')
        self.assertEqual(self.output, ['caller', 'definition.bsl:3:2: routine', 'caller'])
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.variables, {})
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_function_and_procedure_return_from_try_are_not_caught(self):
        self.vm.execute('''
            Function F()
                Try Return 42; Except Message("bad"); EndTry;
                Return 0;
            EndFunction
            Procedure P()
                Try Return Except Message("bad"); EndTry;
                Message("bad");
            EndProcedure
            Message(F()); P(); Message("done");
        ''')
        self.assertEqual(self.output, ['42', 'done'])
        self.assertIsNone(self.vm.locals)

    def test_return_from_nested_handler_clears_description_without_restoring_parent(self):
        self.vm.execute('''
            Function F()
                Try Raise "inner"; Except Return ErrorDescription(); EndTry;
            EndFunction
            Procedure P()
                Try Raise "procedure"; Except Return EndTry;
            EndProcedure
            Try Raise "outer";
            Except
                original = ErrorDescription();
                Message(F()); P();
                Message(ErrorDescription() = "");
            EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertTrue(self.output[0].endswith(': inner'))
        self.assertEqual(self.output[1:], ['Да', 'Да'])
        self.assertIsNone(self.vm.locals)

    def test_break_and_continue_from_try_are_not_caught(self):
        self.vm.execute('''
            For i = 1 To 3 Do
                Try
                    If i = 1 Then Continue; EndIf;
                    Message(i); Break;
                Except Message("bad"); EndTry;
                Message("bad");
            EndDo;
            Message("done");
        ''')
        self.assertEqual(self.output, ['2', 'done'])

    def test_break_and_continue_from_handler_clear_description(self):
        self.vm.execute('''
            Try Raise "outer";
            Except
                original = ErrorDescription();
                For i = 1 To 3 Do
                    Try Raise "inner";
                    Except
                        If i = 1 Then Continue; EndIf;
                        Break;
                    EndTry;
                    Message("bad");
                EndDo;
                Message(i); Message(ErrorDescription() = "");
            EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['2', 'Да', 'Да'])

    def test_independent_interpreters_do_not_share_handler_state(self):
        other = Interpreter(output=self.output.append)
        self.vm.register_function('OtherDescription', lambda: other.execute('ErrorDescription()'))
        self.vm.execute('Try Raise "first"; Except Message(OtherDescription() = ""); EndTry;')
        self.assertEqual(self.output, ['Да'])
        self.assertEqual(other.execute('ErrorDescription()'), '')


class ExceptionParserTests(unittest.TestCase):
    def test_ast_nodes_preserve_source_and_expression(self):
        statement = parse('\n  Try Raise 2 + 3; Except Raise; EndTry;', 'tree.bsl')[0]
        self.assertIsInstance(statement, ast.Try)
        self.assertEqual((statement.token.source, statement.token.line,
                          statement.token.column), ('tree.bsl', 2, 3))
        self.assertEqual(len(statement.body), 1)
        self.assertEqual(len(statement.handler), 1)
        self.assertIsInstance(statement.body[0], ast.Raise)
        self.assertIsInstance(statement.body[0].value, ast.Binary)
        self.assertIsInstance(statement.handler[0], ast.Raise)
        self.assertIsNone(statement.handler[0].value)

    def test_bare_raise_before_block_delimiters(self):
        for code in ['Try Raise "x"; Except Raise EndTry;',
                     'Try Raise "x"; Except If True Then Raise EndIf; EndTry;',
                     'Try Raise "x"; Except For i = 1 To 1 Do Raise EndDo; EndTry;',
                     'Try Raise "x"; Except If False Then Raise Else Raise EndIf; EndTry;']:
            with self.subTest(code=code):
                parse(code)

    def test_bare_raise_requires_lexically_enclosing_handler(self):
        for code in ['Raise;', 'ВызватьИсключение;',
                     'Try Raise; Except EndTry;',
                     'Try Except EndTry; Raise;',
                     'Function F() Raise; EndFunction',
                     'Function F() Try Except EndTry; Raise; EndFunction',
                     'Try Except EndTry; Function F() Raise; EndFunction']:
            with self.subTest(code=code), self.assertRaises(BSLError) as caught:
                parse(code, 'bare.bsl')
            self.assertNotIsInstance(caught.exception, BSLRuntimeError)
            self.assertEqual(caught.exception.source, 'bare.bsl')

    def test_malformed_try_blocks(self):
        cases = ['Except;', 'EndTry;',
                 'Try Message(1); EndTry;',
                 'Try Except Except EndTry;',
                 'Try Except EndIf;',
                 'Try Raise "x" Raise "y"; Except EndTry;',
                 'Try Except EndTry Message(1);',
                 'Try Function F() EndFunction Except EndTry;',
                 'Try Except\n// #Импорт Side.bsl\nEndTry;']
        for code in cases:
            with self.subTest(code=code), self.assertRaises(BSLError) as caught:
                parse(code, 'malformed.bsl')
            self.assertNotIsInstance(caught.exception, BSLRuntimeError)
            self.assertEqual(caught.exception.source, 'malformed.bsl')

    def test_unfinished_try_and_raise_expressions_need_more_input(self):
        for code in ['Try', 'Try x = 1;', 'Try Except',
                     'Try Raise "x"; Except Message(',
                     'Try Raise "x"; Except Raise',
                     'Попытка\nВызватьИсключение "ошибка";\nИсключение',
                     'Raise (', 'Raise "x" +']:
            with self.subTest(code=code), self.assertRaises(IncompleteInput):
                parse(code)

    def test_return_break_and_continue_context_rules_still_apply(self):
        for code in ['Try Return; Except EndTry;',
                     'Try Except Return; EndTry;',
                     'Try Break; Except EndTry;',
                     'Try Except Continue; EndTry;',
                     'Procedure P() Try Except Return 1; EndTry; EndProcedure']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                parse(code)


class ExceptionImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.main = self.directory / 'Main.bsl'
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def write(self, name, code):
        path = self.directory / name
        path.write_text(code, encoding='utf-8')
        return path

    def execute(self, code):
        self.main.write_text(code, encoding='utf-8')
        return self.vm.execute(code, str(self.main))

    def test_imported_routine_error_is_caught_at_original_source(self):
        side = self.write('Side.bsl', 'Function Fail() Export\n Raise "module";\nEndFunction')
        self.execute('// #Импорт Side.bsl\nTry Side.Fail(); Except Message(ErrorDescription()); EndTry;')
        self.assertEqual(self.output, [str(side.resolve()) + ':2:2: module'])
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')
        self.assertEqual(self.vm.variables, {})

    def test_handler_description_is_shared_across_transitive_module_calls(self):
        self.write('Leaf.bsl', 'Function Describe() Export Return ErrorDescription(); EndFunction')
        self.write('Side.bsl', '''// #Импорт Leaf.bsl
            Function Describe() Export Return Leaf.Describe(); EndFunction
            Function Catch() Export
                Try Raise "side";
                Except Return Leaf.Describe() = ErrorDescription(); EndTry;
            EndFunction
        ''')
        self.execute('''// #Импорт Side.bsl
            Message(Side.Describe() = "");
            Try Raise "main";
            Except
                original = ErrorDescription();
                Message(Side.Describe() = original);
                Message(Side.Catch());
                Message(ErrorDescription() = "");
                Message(Side.Describe() = "");
            EndTry;
            Message(Side.Describe() = "");
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['Да'] * 7)

    def test_nested_handler_in_imported_routine_invalidates_parent_rethrow(self):
        self.write('Side.bsl', '''
            Procedure Catch() Export
                Try Raise "inner"; Except EndTry;
            EndProcedure
        ''')
        self.execute('// #Импорт Side.bsl\n')
        with self.assertRaisesRegex(BSLRuntimeError, 'после вложенного обработчика пока не поддерживается'):
            self.vm.execute('Try Raise "outer"; Except Side.Catch(); Raise; EndTry;')
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')
        self.assertIsNone(self.vm.imports['side'].interpreter.locals)

    def test_imported_rethrow_preserves_source_and_restores_frames(self):
        side = self.write('Side.bsl', 'Function Fail() Export\n'
                                    ' Try Raise "module"; Except Raise; EndTry;\nEndFunction')
        self.execute('// #Импорт Side.bsl\n')
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Try Side.Fail(); Except Raise; EndTry;', 'caller.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), (str(side.resolve()), 2))
        self.assertEqual(caught.exception.message, 'module')
        self.assertIsNone(self.vm.locals)
        self.assertIsNone(self.vm.imports['side'].interpreter.locals)
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_imported_module_handles_its_initialization_failure(self):
        side = self.write('Side.bsl', 'Var value;\n'
                                    'Try Raise "startup"; Except value = ErrorDescription(); EndTry;\n'
                                    'Function Value() Export Return value; EndFunction\n'
                                    'Function Describe() Export Return ErrorDescription(); EndFunction')
        self.execute('// #Импорт Side.bsl\nMessage(Side.Value()); Message(Side.Describe() = "");')
        self.assertEqual(self.output, [str(side.resolve()) + ':2:5: startup', 'Да'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_imported_syntax_error_is_not_converted_to_runtime_error(self):
        side = self.write('Side.bsl', 'Try\n x = ;\nExcept Message("bad"); EndTry;')
        with self.assertRaises(BSLError) as caught:
            self.execute('// #Импорт Side.bsl\nTry Message("bad"); Except EndTry;')
        self.assertNotIsInstance(caught.exception, BSLRuntimeError)
        self.assertEqual(caught.exception.source, str(side.resolve()))
        self.assertEqual(caught.exception.line, 2)
        self.assertEqual(self.output, [])

    def test_uncaught_module_initialization_failure_can_be_retried(self):
        self.write('Side.bsl', 'Raise "startup";')
        with self.assertRaises(BSLRuntimeError):
            self.execute('// #Импорт Side.bsl\n')
        self.assertNotIn('side', self.vm.imports)
        self.write('Side.bsl', 'Function Answer() Export Return 42; EndFunction')
        self.execute('// #Импорт Side.bsl\nMessage(Side.Answer());')
        self.assertEqual(self.output, ['42'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')


class ExceptionCLITests(unittest.TestCase):
    def run_cli(self, *arguments, stdin=None, cwd=ROOT):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(
            filter(None, [str(ROOT), environment.get('PYTHONPATH')]))
        return subprocess.run([sys.executable, '-m', 'yadinassi', *arguments],
                              input=stdin, capture_output=True, encoding='utf-8',
                              cwd=cwd, env=environment, timeout=10)

    def test_caught_error_succeeds_in_command_and_stdin(self):
        code = 'Попытка ВызватьИсключение "ошибка"; Исключение Сообщить("готово"); КонецПопытки;'
        for arguments, stdin in [(('-c', code), None), (('-',), code)]:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, stdin=stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'готово\n', ''))

    def test_uncaught_raise_has_clean_source_aware_failure(self):
        result = self.run_cli('-c', 'Raise "failure";')
        self.assertEqual((result.returncode, result.stdout), (1, ''))
        self.assertIn('<команда>:1:1: failure', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_multiline_repl_handles_then_clears_exception_context(self):
        result = self.run_cli(stdin='Try\nRaise "failure";\nExcept\n'
                                   'Message("handled");\nEndTry;\n'
                                   '(ErrorDescription() = "")\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'handled\nДа\n', ''))

    def test_repl_recovers_after_uncaught_raise(self):
        result = self.run_cli(stdin='Raise "failure";\n(ErrorDescription() = "")\n'
                                   'Message("alive");\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, 'Да\nalive\n'))
        self.assertIn('<консоль>:1:1: failure', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_incomplete_try_at_repl_eof_reports_without_executing_body(self):
        for code in ['Try\nMessage("bad");\n',
                     'Try\nMessage("bad");\nExcept\n']:
            with self.subTest(code=code):
                result = self.run_cli(stdin=code)
                self.assertEqual((result.returncode, result.stdout), (1, ''))
                self.assertIn('Не завершен блок', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_imported_error_handled_by_file_from_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = directory / 'project'
            project.mkdir()
            side = project / 'Side.bsl'
            side.write_text('Function Fail() Export\n Raise "module";\nEndFunction', encoding='utf-8')
            main = project / 'Main.bsl'
            main.write_text('// #Импорт Side.bsl\n'
                            'Try Side.Fail(); Except Message(ErrorDescription()); EndTry;', encoding='utf-8-sig')
            result = self.run_cli(str(main), cwd=directory)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, str(side.resolve()) + ':2:2: module\n', ''))


if __name__ == '__main__':
    unittest.main()
