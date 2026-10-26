"""Source grouping, syntax boundaries, and standalone preprocessing policy."""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import IncompleteInput
from yadinassi.syntax.lexer import Lexer
from yadinassi.syntax.parser import parse


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_nested_aliases_case_whitespace_comments_and_empty_regions(self):
        self.vm.execute('''
            # ОбЛаСтЬ _Внешняя2 // outer
            #rEgIoN Inner
            Message("nested");
            #кОнЕцОбЛаСтИ // mixed closing alias
            #Область Empty
            #EndRegion
            # EndRegion
        ''')
        self.assertEqual(self.output, ['nested'])

    def test_regions_do_not_create_variable_or_routine_scopes(self):
        self.vm.execute('''
            #Область API
            &НаКлиенте
            Функция Ответ(Знач число = 40) Экспорт
                #Область Вычисление
                Перем результат;
                результат = число + 2;
                #КонецОбласти
                Возврат результат;
            КонецФункции
            #КонецОбласти
            #Region Initialization
            x = Ответ();
            #EndRegion
            Message(x);
        ''')
        self.assertEqual(self.output, ['42'])
        self.assertEqual(self.vm.execute('Ответ(1)'), Decimal(3))
        with self.assertRaisesRegex(BSLError, 'Повторное объявление'):
            parse('#Region A\nProcedure P() EndProcedure\n#EndRegion\n'
                  '#Region B\nProcedure P() EndProcedure\n#EndRegion')

    def test_region_names_are_identifiers_not_runtime_bindings(self):
        for name in ['Имя', '_', '_Работа2', 'Name42', 'Область', 'EndRegion', 'Client', 'Server']:
            with self.subTest(name=name):
                self.assertEqual(self.vm.execute(f'#Region {name}\n42\n#EndRegion'), Decimal(42))
        self.vm.execute('#Region x\n#Region x\n#EndRegion\n#EndRegion\nx = 1;')
        self.assertEqual(self.vm.execute('x'), Decimal(1))

    def test_region_inside_each_statement_block(self):
        self.vm.execute('''
            #Region WholeLoop
            For i = 1 To 1 Do
                #Region Iteration
                If True Then
                    #Region Selected
                    Message(i);
                    #EndRegion
                Else
                    #Region Otherwise
                    Message("bad");
                    #EndRegion
                EndIf;
                #EndRegion
            EndDo;
            #EndRegion
            Try
                #Region Attempt
                Raise "caught";
                #EndRegion
            Except
                #Region Handler
                Message("handled");
                #EndRegion
            EndTry;
            While False Do
                #Region Never
                Break;
                #EndRegion
            EndDo;
        ''')
        self.assertEqual(self.output, ['1', 'handled'])

    def test_complete_expression_regions_follow_edt_expression_grammar(self):
        self.vm.execute('''
            x =
            #Область Значение
                1 + 2
            #КонецОбласти
            ;
            Message(x);
            Message(
                #Region Argument
                #Region Nested
                    40 + 2;
                #EndRegion
                #EndRegion
            );
            If
                #Region Condition
                    x = 3
                #EndRegion
            Then Message("yes"); EndIf;
        ''')
        self.assertEqual(self.output, ['3', '42', 'yes'])

    def test_expression_region_is_one_primary_without_runtime_wrapper(self):
        # EDT models this as a primary expression; native precedence is not yet compared.
        self.assertEqual(self.vm.execute('x =\n#Region Sum\n1 + 2\n#EndRegion\n* 3; x'),
                         Decimal(9))
        self.assertEqual(self.vm.execute('Message(\n#Region Safe\n?(True, 42, 1 / 0)\n#EndRegion\n)'), None)
        self.assertEqual(self.output, ['42'])

    def test_region_closing_does_not_replace_statement_separator(self):
        for code in ['#Region R\nx = 1\n#EndRegion\nMessage(x);',
                     'x = 1\n#Region Empty\n#EndRegion\nMessage(x);',
                     'Procedure P()\n#Region R\nx = 1\n#EndRegion\nx = 2;\nEndProcedure']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, "Ожидается ';'"):
                parse(code)
        self.assertEqual(self.vm.execute('#Region R\n42\n#EndRegion'), Decimal(42))
        self.vm.execute('Procedure P()\n#Region R\nReturn\n#EndRegion\nEndProcedure\nP();')

    def test_region_end_after_bare_reraise_preserves_handler_context(self):
        self.vm.execute('''
            Try
                Try Raise "original";
                Except
                    #Region Rethrow
                    Raise
                    #EndRegion
                EndTry;
            Except Message("caught again"); EndTry;
        ''')
        self.assertEqual(self.output, ['caught again'])

    def test_comments_and_multiline_strings_do_not_open_regions(self):
        self.vm.execute('''
            // #Region Comment
            Message("#Область Строка
            |#КонецОбласти
            |#EndRegion");
            Message("#Region Another"); // #EndRegion
        ''')
        self.assertEqual(self.output, ['#Область Строка\n#КонецОбласти\n#EndRegion',
                                       '#Region Another'])

    def test_malformed_region_names_are_rejected_before_side_effects(self):
        for name in ['', '123', '1Name', 'Two Names', 'A.B', 'A-B', '"Name"',
                     'Name;', 'Name()', 'Имя,', 'Если', 'If', 'Then', 'Procedure']:
            with self.subTest(name=name), self.assertRaisesRegex(BSLError, 'имя-идентификатор'):
                self.vm.execute('Message("bad");\n#Region ' + name + '\n#EndRegion')
        self.assertEqual(self.output, [])

    def test_malformed_closings_and_non_standalone_directives(self):
        for code in ['#EndRegion', '#КонецОбласти', '#Region R\n#EndRegion R',
                     '#Region R\n#EndRegion;', '#Region R\n#EndRegion Message(1);',
                     'Message(1); #Region R\n#EndRegion',
                     '#Region R\nMessage(1); #EndRegion']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                parse(code)

    def test_unclosed_regions_request_continuation_at_opening_location(self):
        for code, line, column, name in [('#Region Open', 1, 1, 'Open'),
                                       ('\n  #Область Внешняя\n#Region Inner\n#EndRegion', 2, 3, 'Внешняя'),
                                       ('x =\n#Region Value\n40 + 2', 2, 1, 'Value')]:
            with self.subTest(code=code), self.assertRaises(IncompleteInput) as caught:
                parse(code, 'unfinished.bsl')
            self.assertEqual((caught.exception.source, caught.exception.line, caught.exception.column),
                             ('unfinished.bsl', line, column))
            self.assertIn(name, str(caught.exception))
            self.assertIn('#КонецОбласти', str(caught.exception))

    def test_regions_cannot_cross_routines_or_statement_branches(self):
        cases = [
            '#Region R\nProcedure P()\n#EndRegion\nEndProcedure',
            'Procedure P()\n#Region R\nEndProcedure\n#EndRegion',
            '#Region R\nIf True Then\n#EndRegion\nEndIf;',
            'If True Then\n#Region R\nEndIf;\n#EndRegion',
            'If True Then\n#Region R\nElse\n#EndRegion\nEndIf;',
            'If True Then\n#Region R\nElsIf False Then\n#EndRegion\nEndIf;',
            'Try\n#Region R\nExcept\n#EndRegion\nEndTry;',
            'For i = 1 To 1 Do\n#Region R\nEndDo;\n#EndRegion',
        ]
        for code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'пересекает границу'):
                parse(code)

    def test_regions_cannot_split_declaration_headers_or_expression_fragments(self):
        cases = [
            'Procedure P(\n#Region Params\nx\n#EndRegion\n) EndProcedure',
            '&AtClient\n#Region R\nProcedure P() EndProcedure\n#EndRegion',
            'x =\n#Region Partial\n1 +\n#EndRegion\n2;',
            'x =\n#Region Empty\n#EndRegion\n;',
            'Message(\n#Region Arguments\n1, 2\n#EndRegion\n);',
        ]
        for code in cases:
            with self.subTest(code=code), self.assertRaises(BSLError):
                parse(code)

    def test_regions_and_conditionals_nest_without_changing_selected_source(self):
        self.vm.execute('''
            #Region Outer
            #If Server Then
                #Region Ignored
                unsupported " !
                #EndRegion
            #ElsIf Client Then
                #Область Выбрано
                Message("client");
                #If Server Then
                    ignored !!!
                #Else
                    Message("nested");
                #EndIf
                #КонецОбласти
            #Else
                ignored !!!
            #EndIf
            #EndRegion
        ''')
        self.assertEqual(self.output, ['client', 'nested'])

    def test_regions_cannot_cross_conditional_boundaries(self):
        cases = [
            '#Region R\n#If Client Then\n#EndRegion\n#EndIf',
            '#If Client Then\n#Region R\n#EndIf\n#EndRegion',
            '#If Client Then\n#Region R\n#Else\n#EndRegion\n#EndIf',
            '#If Client Then\n#Region R\n#ElsIf Server Then\n#EndRegion\n#EndIf',
        ]
        for code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'условной компиляции'):
                parse(code)

    def test_inactive_region_lines_follow_excluded_source_policy(self):
        # Native behavior of malformed inactive regions remains explicitly unverified.
        self.vm.execute('''
            #If Server Then
                #Region
                #Region 123 multiple names
                #EndRegion extra
                #EndRegion
                #Region NeverClosed
                // #Импорт Missing.bsl
            #Else
                #Region Active
                Message("selected");
                #EndRegion
            #EndIf
        ''')
        self.assertEqual(self.output, ['selected'])
        self.assertEqual(self.vm.imports, {})
        with self.assertRaisesRegex(BSLError, 'соответствующей #Область'):
            parse('#If Server Then\n#Region R\n#Else\n#EndRegion\n#EndIf')

    def test_bom_crlf_and_token_positions_are_preserved(self):
        source = '\ufeff  #Область R\r\n\t#Region Inner\r\n  x = 42;\r\n#EndRegion\r\n#КонецОбласти'
        tokens = Lexer(source, 'positions.bsl').tokens()
        token = next(token for token in tokens if token.kind == 'IDENT')
        self.assertEqual((token.source, token.line, token.column, token.value),
                         ('positions.bsl', 3, 3, 'x'))
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('\ufeff#Область R\r\n  Сообщить(1 / 0);\r\n#КонецОбласти', 'error.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line, caught.exception.column),
                         ('error.bsl', 2, 14))

    def test_region_does_not_allow_import_inside_routine(self):
        with self.assertRaisesRegex(BSLError, 'только на уровне модуля'):
            parse('Procedure P()\n#Region Imports\n// #Импорт Side.bsl\n#EndRegion\nEndProcedure')
        with self.assertRaisesRegex(BSLError, 'комментарий // #Импорт'):
            parse('#Region Imports\n#Импорт Side.bsl\n#EndRegion')

    def test_imported_region_validation_happens_before_module_initialization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / 'Side.bsl'
            module.write_text('Message("bad");\n#Region Broken\n', encoding='utf-8')
            with self.assertRaises(IncompleteInput) as caught:
                self.vm.execute('#Region Imports\n// #Импорт Side.bsl\n#EndRegion', str(root / 'Main.bsl'))
            self.assertEqual((caught.exception.source, caught.exception.line), (str(module.resolve()), 2))
            self.assertEqual(self.output, [])


if __name__ == '__main__':
    unittest.main()
