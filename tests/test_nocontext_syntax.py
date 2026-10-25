"""Independent NoContext compilation without changing standalone target flags."""
from decimal import Decimal
import unittest

from yadinassi import ast
from yadinassi.errors import BSLError, IncompleteInput
from yadinassi.lexer import Lexer
from yadinassi.parser import Parser, parse, parse_expression, parse_fragment
from yadinassi.preprocessor import ConditionalCompilation


class NoContextSyntaxTests(unittest.TestCase):
    def routines(self, source):
        return {node.name: node for node in parse(source) if isinstance(node, ast.Routine)}

    def test_bilingual_case_insensitive_directives_and_default_field(self):
        for directive, header, ending in (
                ('&aTsErVeRnOcOnTeXt', 'Function F(Val X = 42) Export', 'EndFunction'),
                ('&нАсЕрВеРеБеЗкОнТеКсТа', 'Функция F(Знач X = 42) Экспорт', 'КонецФункции')):
            with self.subTest(directive=directive):
                routine = self.routines(f'{directive} // note\n{header}\nReturn X;\n{ending}')['F']
                self.assertEqual(routine.execution_context, 'server')
                self.assertFalse(routine.module_context)
                self.assertTrue(routine.exported)
                self.assertTrue(routine.parameters[0].by_value)
                self.assertEqual(routine.parameters[0].default.value, Decimal(42))
        routine = self.routines('Procedure P() EndProcedure')['P']
        self.assertTrue(routine.module_context)
        # New metadata is a final default, preserving existing positional callers.
        old_style = ast.Routine(routine.token, 'Old', [], False, False, [], 'server')
        self.assertTrue(old_style.module_context)

    def test_no_context_changes_only_logical_flags_of_server_profile(self):
        client = ConditionalCompilation('flags', 'client').symbols
        server = ConditionalCompilation('flags', 'server').symbols
        nocontext = ConditionalCompilation('flags', 'server_nocontext').symbols
        logical = {'atclient', 'наклиенте', 'atserver', 'насервере'}
        for name in logical:
            self.assertFalse(nocontext[name], name)
        self.assertEqual({key: value for key, value in nocontext.items() if key not in logical},
                         {key: value for key, value in server.items() if key not in logical})
        self.assertTrue(client['client'])
        self.assertFalse(client['server'])
        self.assertFalse(server['client'])
        self.assertTrue(server['server'])
        # Recognized application symbols remain false: this is standalone
        # policy, not the native six-bit target observation.
        for target in ('ThickClientManagedApplication', 'ThickClientOrdinaryApplication',
                       'ТолстыйКлиентУправляемоеПриложение', 'ТолстыйКлиентОбычноеПриложение'):
            with self.subTest(target=target):
                self.assertFalse(nocontext[target.casefold()])
                self.assertEqual(parse(f'#If {target} Then\ninvalid !!!\n#EndIf'), [])

    def test_no_context_name_is_not_a_preprocessor_symbol(self):
        for symbol in ('AtServerNoContext', 'НаСервереБезКонтекста'):
            with self.subTest(symbol=symbol), self.assertRaisesRegex(BSLError, 'Неподдерживаемый символ'):
                parse(f'&AtServerNoContext\nFunction F()\n#If {symbol} Then\nReturn 0;\n#EndIf\nEndFunction')

    def test_body_has_its_own_logical_and_target_preprocessing(self):
        routine = self.routines('''&AtServerNoContext
Function F()
#If AtClient Or AtServer Then
 Return 0;
#ElsIf Server And Not Client Then
 Return 42;
#Else
 Return 1;
#EndIf
EndFunction''')['F']
        self.assertEqual(len(routine.body), 1)
        self.assertEqual(routine.body[0].value.value, Decimal(42))
        self.assertEqual(routine.body[0].token.line, 6)

    def test_unselected_body_syntax_and_imports_do_not_run_in_other_profiles(self):
        source = '''&AtServerNoContext
Function F()
#If AtClient Or AtServer Then
 ignored !!! syntax
 "unclosed
 'not a date
 // #Import Missing.bsl
#Else
 Return 42;
#EndIf
EndFunction
'''
        self.assertEqual(self.routines(source)['F'].body[0].value.value, Decimal(42))

    def test_excluded_body_keywords_cannot_change_declaration_boundaries(self):
        for guard in ('AtClient', 'AtServer', 'AtClient Or AtServer'):
            with self.subTest(guard=guard):
                source = f"""&AtServerNoContext
Function F()
#If {guard} Then
 Function invalid_nested_declaration()
 &Unknown
#EndIf
 Return 42;
EndFunction
&AtServerNoContext
Function G() Return 7; EndFunction"""
                routines = self.routines(source)
                self.assertEqual(set(routines), {'F', 'G'})
                self.assertEqual(routines['F'].body[0].value.value, Decimal(42))

    def test_source_availability_follows_the_independent_profile(self):
        guards = (
            ('#If Server Then', True),
            ('#If Client Then', False),
            ('#If AtClient Then', False),
            ('#If AtServer Then', False),
            ('#If Not AtClient And Not AtServer Then', True),
            ('#If AtClient Then\n#Else', True),
            ('#If AtServer Then\n#Else', True),
            ('#If AtClient Then\n#ElsIf AtServer Then\n#Else', True),
            ('#If Client Then\n#ElsIf Server And Not AtServer Then', True),
            ('#Если Не НаКлиенте И Не НаСервере Тогда', True),
        )
        for guard, available in guards:
            with self.subTest(guard=guard):
                source = guard + '\n&AtServerNoContext\nFunction F() Return 42; EndFunction\n#EndIf'
                self.assertEqual('F' in self.routines(source), available)

    def test_nested_conditions_and_duplicate_name_in_excluded_branches(self):
        source = '''#If AtClient Then
&AtServerNoContext
Function F() Return 0; EndFunction
#Else
#If Server And (Not AtClient And Not AtServer) Then
&НаСервереБезКонтекста
Function F()
#If AtClient Then
 Return 1;
#Else
 Return 42;
#EndIf
EndFunction
#EndIf
#EndIf'''
        routines = self.routines(source)
        self.assertEqual(set(routines), {'F'})
        self.assertEqual(routines['F'].body[0].value.value, Decimal(42))

    def test_no_context_pass_retains_only_its_routines(self):
        source = '''Var ClientStorage;
// #Import ClientOnly.bsl
Message("client-root");
&AtServer
Var ServerStorage;
&AtServer
Function Ordinary() Return ServerStorage; EndFunction
#If AtClient Then
#Else
// #Import Missing.bsl
ServerStorage = 42;
#EndIf
#If Not AtClient And Not AtServer Then
Var NeverAStorage;
// #Import AlsoMissing.bsl
Raise "not an initializer";
#EndIf
&AtServerNoContext
Function F() Return 7; EndFunction'''
        nodes = Parser(Lexer(source, execution_context='server_nocontext').tokens(),
                       'server_nocontext').parse()
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], ast.Routine)
        self.assertEqual(nodes[0].name, 'F')
        combined = parse(source)
        self.assertEqual([node.filename for node in combined if isinstance(node, ast.Import)],
                         ['ClientOnly.bsl'])
        self.assertEqual([node.names for node in combined if isinstance(node, ast.Var)],
                         [['ClientStorage'], ['ServerStorage']])
        initializers = [node for node in combined if isinstance(node, ast.ServerInitializer)]
        self.assertEqual(len(initializers), 1)
        self.assertEqual(initializers[0].body[0].target.name, 'ServerStorage')

    def test_variables_cannot_receive_no_context_directive(self):
        for directive in ('&AtServerNoContext', '&НаСервереБезКонтекста'):
            for guard in ('', '#If Client Then\n', '#If Server Then\n',
                          '#If Not AtClient And Not AtServer Then\n'):
                with self.subTest(directive=directive, guard=guard), self.assertRaisesRegex(BSLError, 'переменной'):
                    parse(guard + directive + '\nVar Forbidden;' + ('\n#EndIf' if guard else ''))
        routine = self.routines('&AtServerNoContext\nFunction F() Var Local; Local=1; Return Local; EndFunction')['F']
        self.assertIsInstance(routine.body[0], ast.Var)

    def test_nested_annotations_are_rejected_in_compiled_bodies(self):
        for outer in ('', '&AtClient\n', '&AtServer\n', '&AtServerNoContext\n'):
            with self.subTest(outer=outer), self.assertRaises(BSLError):
                parse(outer + 'Procedure P()\n&AtServerNoContext\nProcedure Q() EndProcedure\nEndProcedure')
        for inner in ('&AtClient', '&AtServer', '&AtServerNoContext'):
            with self.subTest(inner=inner), self.assertRaisesRegex(BSLError, 'уровня модуля'):
                parse('&AtServerNoContext\nProcedure P()\n' + inner + '\nProcedure Q() EndProcedure\nEndProcedure')

    def test_selected_annotation_inside_omitted_root_block_is_not_promoted(self):
        for opening, ending in (('If True Then', 'EndIf'), ('While False Do', 'EndDo'),
                                ('For X=1 To 2 Do', 'EndDo'), ('Try', 'Except\nEndTry')):
            for guard in ('', '#If Server Then\n'):
                with self.subTest(opening=opening, guard=guard), self.assertRaisesRegex(BSLError, 'уровня модуля'):
                    parse(guard + opening + '\n&AtServerNoContext\nProcedure P() EndProcedure\n' + ending
                          + ('\n#EndIf' if guard else ''))

    def test_excluded_routines_cannot_promote_nested_no_context_declarations(self):
        for declaration in ('Procedure Hidden()', '&AtClient\nProcedure Hidden()',
                            '&AtServer\nProcedure Hidden()', 'ignored=1; Procedure Hidden()'):
            source = '#If Not AtClient And Not AtServer Then\n' + declaration + '''
&AtServerNoContext
Function Promoted() Return 9; EndFunction
EndProcedure
#EndIf'''
            with self.subTest(declaration=declaration):
                self.assertEqual(self.routines(source), {})

    def test_no_context_body_imports_are_rejected(self):
        for text in ('// #Import Missing.bsl', '#Import Missing.bsl'):
            with self.subTest(text=text), self.assertRaises(BSLError):
                parse('&AtServerNoContext\nFunction F()\n' + text + '\nEndFunction')

    def test_pending_annotations_and_no_context_bearing_dual_directives(self):
        for text in ('&AtServerNoContext', '&НаСервереБезКонтекста\n// comment',
                     '&AtServerNoContext\nFunction F()'):
            with self.subTest(text=text), self.assertRaises(IncompleteInput):
                parse(text)
        for directive in ('&AtClientAtServer', '&НаКлиентеНаСервере'):
            with self.subTest(directive=directive), self.assertRaises(BSLError):
                parse(directive + '\nProcedure P() EndProcedure')
        for prefix in ('&AtServerNoContext\n&AtClient', '&AtServer\n&AtServerNoContext',
                       '&AtServerNoContext\nx=1;', 'x=1; &AtServerNoContext'):
            with self.subTest(prefix=prefix), self.assertRaises(BSLError):
                parse(prefix + '\nProcedure P() EndProcedure')

    def test_dynamic_fragments_still_forbid_compilation_directives(self):
        for parser in (parse_expression, parse_fragment):
            with self.subTest(parser=parser.__name__), self.assertRaises(BSLError):
                parser('&AtServerNoContext\nProcedure P() EndProcedure')

    def test_original_positions_bom_crlf_and_source_lines_are_preserved(self):
        source = '\ufeff// comment\r\n&НаСервереБезКонтекста\r\nФункция F()\r\n#Если НаСервере Тогда\r\n Возврат 0;\r\n#Иначе\r\n  Возврат 42;\r\n#КонецЕсли\r\nКонецФункции'
        routine = next(node for node in parse(source, 'original.bsl') if isinstance(node, ast.Routine))
        token = routine.body[0].token
        self.assertEqual((token.source, token.line, token.column, token.source_line),
                         ('original.bsl', 7, 3, '  Возврат 42;'))
        broken = source.replace('Возврат 42;', 'Возврат +;')
        with self.assertRaises(BSLError) as caught:
            parse(broken, 'original.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('original.bsl', 7))

    def test_strings_comments_and_regions_do_not_introduce_no_context_routines(self):
        source = '''Message("ordinary\n|&AtServerNoContext\n|Function Fake() EndFunction");
// &AtServerNoContext
&AtServerNoContext
Function F()
#Region Local
 Return 42;
#EndRegion
EndFunction'''
        self.assertEqual(set(self.routines(source)), {'F'})

    def test_ordinary_compilation_and_initializer_fragments_are_unchanged(self):
        nodes = parse('''Function Plain() Return 1; EndFunction
&AtClient
Function Client()
#If AtClient Then
 Return 2;
#Else
 Return 0;
#EndIf
EndFunction
&AtServer
Var State;
&AtServer
Function Server()
#If AtServer Then
 Return 3;
#Else
 Return 0;
#EndIf
EndFunction
#If AtServer Then
If True Then
#If AtClient Then
 State=0;
#Else
 State=4;
#EndIf
EndIf;
#EndIf
&AtServerNoContext
Function NoContext() Return 5; EndFunction''')
        routines = {node.name: node for node in nodes if isinstance(node, ast.Routine)}
        self.assertEqual({name: (node.execution_context, node.module_context) for name, node in routines.items()},
                         {'Plain': ('client', True), 'Client': ('client', True),
                          'Server': ('server', True), 'NoContext': ('server', False)})
        self.assertEqual([routines[name].body[0].value.value for name in ('Plain', 'Client', 'Server', 'NoContext')],
                         [Decimal(1), Decimal(2), Decimal(3), Decimal(5)])
        initializer = next(node for node in nodes if isinstance(node, ast.ServerInitializer))
        self.assertIsInstance(initializer.body[0], ast.If)
        self.assertEqual(initializer.body[0].branches[0][1][0].value.value, Decimal(4))


if __name__ == '__main__':
    unittest.main()
