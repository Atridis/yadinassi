"""Standalone client compilation, execution context, and source diagnostics."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import IncompleteInput
from yadinassi.parser import parse


class ClientContextTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_root_unannotated_and_annotated_routines_are_client(self):
        self.vm.register_function('Context', lambda: self.vm.execution_context)
        self.vm.execute('''
            &нАкЛиЕнТе // комментарий
            Function F(Val x = 40) Export
                Return x + 2;
            EndFunction
            &aTcLiEnT
            Procedure P(x)
                x = F(); Message(Context());
            EndProcedure
            Function Plain() Return Context(); EndFunction
            Message(Context()); x = 0; P(x); Message(x); Message(Plain());
        ''')
        self.assertEqual(self.output, ['client', 'client', '42', 'client'])
        self.assertEqual(self.vm.execution_context, 'client')
        self.assertTrue(all(r.execution_context == 'client' for r in self.vm.routines.values()))
        with self.assertRaises(AttributeError):
            self.vm.execution_context = 'server'

    def test_client_annotation_pending_and_comments(self):
        for text in ['&AtClient', '&НаКлиенте\n// comment\n', '&AtClient\nFunction F()']:
            with self.subTest(text=text), self.assertRaises(IncompleteInput):
                parse(text)
        self.vm.execute('&AtClient\n\n// comment\nFunction F() Return 7; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(7))

    def test_invalid_annotations_fail_before_module_side_effects(self):
        directives = ['&НаСервереБезКонтекста',
                      '&AtServerNoContext', '&НаКлиентеНаСервере', '&AtClientAtServer',
                      '&НаКлиентеНаСервереБезКонтекста', '&AtClientAtServerNoContext',
                      '&Unknown', '&AtClient()', '&AtClient Procedure P() EndProcedure']
        for directive in directives:
            with self.subTest(directive=directive), self.assertRaises(BSLError) as caught:
                self.vm.execute('Message("bad");\n  ' + directive + '\nProcedure P() EndProcedure',
                                'invalid.bsl')
            self.assertEqual((caught.exception.source, caught.exception.line,
                              caught.exception.column), ('invalid.bsl', 2, 3))
        self.assertEqual(self.output, [])

    def test_annotation_placement_and_duplicates(self):
        for text in ['&AtClient\nx = 1;', '&AtClient\n// #Импорт Side.bsl',
                     '&AtClient\n&AtClient\nProcedure P() EndProcedure',
                     'Procedure P()\n&AtClient\nProcedure Q() EndProcedure\nEndProcedure',
                     'If True Then\n&AtClient\nProcedure P() EndProcedure\nEndIf',
                     'x = 1; &AtClient\nProcedure P() EndProcedure']:
            with self.subTest(text=text), self.assertRaises(BSLError):
                parse(text)

    def test_context_symbols_and_aliases(self):
        for name in ['Клиент', 'НаКлиенте', 'Client', 'AtClient', 'cLiEnT']:
            with self.subTest(name=name):
                self.assertEqual(self.vm.execute(f'#Если {name} Тогда\n42\n#Иначе\n0\n#КонецЕсли'),
                                 Decimal(42))
        for name in ['Сервер', 'НаСервере', 'Server', 'AtServer']:
            with self.subTest(name=name):
                self.assertEqual(self.vm.execute(f'#If {name} Then\n0\n#Else\n42\n#EndIf'),
                                 Decimal(42))

    def test_boolean_precedence_and_parentheses(self):
        expressions = {
            'Client Or Server And Server': True,
            '(Client Or Server) And Server': False,
            'Not Server And Client': True,
            'Not (Client Or Server)': False,
            'Не (Не Клиент) И (НаКлиенте Или Сервер)': True,
        }
        for expression, expected in expressions.items():
            with self.subTest(expression=expression):
                result = self.vm.execute(f'#If {expression} Then\n1\n#Else\n0\n#EndIf')
                self.assertEqual(result, Decimal(int(expected)))

    def test_nested_elsif_first_match_and_inactive_invalid_code(self):
        self.vm.execute('''
            #If Server Then
            // No server declaration: this is excluded root text.
            invalid !!! syntax "
            // #Импорт Missing.bsl
            #If Client Then
            Message("bad nested");
            #Else
            Message("bad else");
            #EndIf
            #ElsIf Client Then
            #If Server Then
            bad ???
            #Else
            Message("selected");
            #EndIf
            #ElsIf AtClient Then
            Message("bad later");
            #Else
            Message("bad fallback");
            #EndIf
        ''')
        self.assertEqual(self.output, ['selected'])
        self.assertEqual(self.vm.imports, {})

    def test_no_selected_branch(self):
        self.assertIsNone(self.vm.execute('#If Server Then\ninvalid\n#ElsIf AtServer Then\nbad\n#EndIf'))

    def test_preprocessor_inside_routine_and_expression(self):
        self.vm.execute('''
            &AtClient
            Function F()
                Return
                #If Client Then
                    42
                #Else
                    invalid !
                #EndIf
                ;
            EndFunction
            Message(F());
        ''')
        self.assertEqual(self.output, ['42'])

    def test_directives_in_active_strings_and_comments_are_literal(self):
        self.vm.execute('''// #If Server Then
            Message("&AtServer");
            Message("#If Server Then
            |#Else
            |#EndIf");
            // &Unknown
        ''')
        self.assertEqual(self.output, ['&AtServer', '#If Server Then\n#Else\n#EndIf'])

    def test_bom_crlf_comments_and_source_lines(self):
        text = '\ufeff# Если Сервер Тогда // no\r\ninvalid !!!\r\n# Иначе\r\n\r\n  1 / 0;\r\n# КонецЕсли'
        with self.assertRaises(BSLError) as caught:
            self.vm.execute(text, 'client.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line,
                          caught.exception.column), ('client.bsl', 5, 5))

    def test_malformed_conditions_are_not_short_circuited(self):
        for condition in ['Client Or Unknown', 'Server And Unknown', 'Client',
                          '(Client Then', 'Client) Then', 'Then', 'True Then',
                          'Client Then extra', 'Not Not Client Then', 'ThinClient Then',
                          'Client = Server Then', 'Client & Server Then']:
            with self.subTest(condition=condition), self.assertRaises(BSLError):
                self.vm.execute(f'Message("bad");\n#If {condition}\n42\n#EndIf')
        self.assertEqual(self.output, [])

    def test_invalid_branch_structure(self):
        for text in ['#Else', '#ElsIf Client Then', '#EndIf',
                     '#If Client Then\n#Else\n#Else\n#EndIf',
                     '#If Client Then\n#Else\n#ElsIf Client Then\n#EndIf',
                     '#If Client Then\n#Else extra\n#EndIf',
                     '#If Client Then\n#EndIf extra',
                     'Message(1); #If Client Then\n#EndIf',
                     '#If Server Then\n#If Unknown Then\n#EndIf\n#EndIf']:
            with self.subTest(text=text), self.assertRaises(BSLError):
                parse(text)

    def test_unfinished_conditionals_request_repl_continuation(self):
        for text in ['#If Client Then', '#If Server Then\ninvalid !',
                     '#If Client Then\n#If Server Then\n#EndIf']:
            with self.subTest(text=text), self.assertRaises(IncompleteInput):
                parse(text)

    def test_server_annotation_cut_out_by_server_preprocessor_is_unavailable(self):
        self.vm.execute('#If Client Then\n&AtServer\nProcedure P() EndProcedure\n#EndIf')
        self.assertNotIn('p', self.vm.routines)
        self.assertNotIn('p', self.vm.server_routines)

    def test_imported_client_modules_and_excluded_imports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Side.bsl').write_text('''#If Client Then
&НаКлиенте
Function F(Val x = 40) Export
    Return x + 2;
EndFunction
#Else
// Excluded root text, not an explicit server declaration.
server-only !!!
#EndIf
''', encoding='utf-8')
            main = root / 'Main.bsl'
            self.vm.execute('#If Client Then\n// #Импорт Side.bsl\n#Else\n'
                            '// #Импорт Missing.bsl\n#EndIf\nMessage(Side.F());', str(main))
            self.assertEqual(self.output, ['42'])
            self.assertEqual(self.vm.imports['side'].interpreter.execution_context, 'client')

    def test_imported_annotation_error_preserves_module_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            side = root / 'Side.bsl'
            side.write_text('Message("bad");\n&AtServerNoContext\nProcedure P() EndProcedure', encoding='utf-8')
            with self.assertRaises(BSLError) as caught:
                self.vm.execute('// #Импорт Side.bsl\nMessage("bad root");', str(root / 'Main.bsl'))
            self.assertEqual((caught.exception.source, caught.exception.line), (str(side.resolve()), 2))
            self.assertEqual(self.output, [])
