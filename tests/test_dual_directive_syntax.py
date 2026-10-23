"""Bounded dual-NoContext compiler model; not native legality evidence."""
from dataclasses import fields
from decimal import Decimal
import unittest

from yadinassi import ast
from yadinassi.errors import BSLError, IncompleteInput
from yadinassi.lexer import Lexer
from yadinassi.parser import Parser, parse, parse_expression, parse_fragment, validate_async
from yadinassi.preprocessor import ConditionalCompilation


class DualDirectiveSyntaxTests(unittest.TestCase):
    def routines(self, source):
        return [node for node in parse(source) if isinstance(node, ast.Routine)]

    def test_bilingual_case_insensitive_function_and_procedure_pairs(self):
        for directive, declaration, ending, is_function in (
                ('&aTcLiEnTaTsErVeRnOcOnTeXt', 'Function F(Val X = 42) Export', 'EndFunction', True),
                ('&нАкЛиЕнТеНаСеРвЕрЕбЕзКоНтЕкСтА', 'Функция F(Знач X = 42) Экспорт', 'КонецФункции', True),
                ('&AtClientAtServerNoContext', 'Procedure F(Val X = 42) Export', 'EndProcedure', False),
                ('&НаКлиентеНаСервереБезКонтекста', 'Процедура F(Знач X = 42) Экспорт', 'КонецПроцедуры', False)):
            with self.subTest(directive=directive, declaration=declaration):
                pair = self.routines(f'{directive} // note\n{declaration}\n{ending}')
                self.assertEqual([node.execution_context for node in pair], ['client', 'server'])
                for node in pair:
                    self.assertTrue(node.is_dual)
                    self.assertFalse(node.module_context)
                    self.assertFalse(node.is_async)
                    self.assertEqual(node.is_function, is_function)
                    self.assertTrue(node.exported)
                    self.assertTrue(node.parameters[0].by_value)
                    self.assertEqual(node.parameters[0].default.value, Decimal(42))
                self.assertEqual(pair[0].token, pair[1].token)
                self.assertIsNot(pair[0].parameters, pair[1].parameters)

    def test_new_field_is_appended_with_legacy_positional_defaults_preserved(self):
        routine, = self.routines('Function F() Return 1; EndFunction')
        self.assertEqual([field.name for field in fields(ast.Routine)][-3:],
                         ['is_async', 'module_context', 'is_dual'])
        legacy = ast.Routine(routine.token, 'Legacy', [], True, False, [], 'client', True, True)
        self.assertTrue(legacy.is_async)
        self.assertTrue(legacy.module_context)
        self.assertFalse(legacy.is_dual)
        self.assertFalse(routine.is_dual)
        self.assertEqual(routine.execution_context, 'client')

    def test_profiles_retain_standalone_targets_and_clear_both_logical_flags(self):
        logical = {'atclient', 'наклиенте', 'atserver', 'насервере'}
        for side in ('client', 'server'):
            ordinary = ConditionalCompilation('flags', side).symbols
            dual = ConditionalCompilation('flags', 'dual_' + side).symbols
            with self.subTest(side=side):
                self.assertEqual(set(ordinary), set(dual))
                self.assertTrue(all(not dual[name] for name in logical))
                self.assertEqual({k: v for k, v in ordinary.items() if k not in logical},
                                 {k: v for k, v in dual.items() if k not in logical})
        client = ConditionalCompilation('flags', 'client').symbols
        server = ConditionalCompilation('flags', 'server').symbols
        self.assertEqual((client['client'], client['server'], client['atclient'], client['atserver']),
                         (True, False, True, False))
        self.assertEqual((server['client'], server['server'], server['atclient'], server['atserver']),
                         (False, True, False, True))

    def test_no_new_preprocessor_symbols_or_targets(self):
        for symbol in ('AtClientAtServerNoContext', 'НаКлиентеНаСервереБезКонтекста',
                       'dual_client', 'dual_server', 'ThickClientManagedApplication'):
            with self.subTest(symbol=symbol), self.assertRaisesRegex(BSLError, 'Неподдерживаемый символ'):
                parse(f'&AtClientAtServerNoContext\nFunction F()\n#If {symbol} Then\n#EndIf\nEndFunction')

    def test_each_body_is_independently_preprocessed_with_same_provenance(self):
        source = '''// header
&AtClientAtServerNoContext
  Function F()
#If AtClient Or AtServer Then
 ignored !!!
#ElsIf Client And Not Server Then
 Return 11;
#Else
 Return 22;
#EndIf
EndFunction'''
        client, server = parse(source, 'source.bsl')
        self.assertEqual([client.body[0].value.value, server.body[0].value.value], [11, 22])
        self.assertEqual([client.body[0].token.line, server.body[0].token.line], [7, 9])
        self.assertIsNot(client.body, server.body)
        self.assertIsNot(client.body[0], server.body[0])
        self.assertEqual(client.token, server.token)
        self.assertEqual((client.token.source, client.token.line, client.token.column,
                          client.token.source_line), ('source.bsl', 3, 3, '  Function F()'))

    def test_bom_crlf_source_positions_and_errors_survive_all_passes(self):
        source = '\ufeff// header\r\n&НаКлиентеНаСервереБезКонтекста\r\nФункция F()\r\n#Если Клиент Тогда\r\n Возврат 1;\r\n#Иначе\r\n  Возврат 2;\r\n#КонецЕсли\r\nКонецФункции'
        client, server = parse(source, 'original.bsl')
        self.assertEqual(client.token, server.token)
        self.assertEqual((server.body[0].token.source, server.body[0].token.line,
                          server.body[0].token.column, server.body[0].token.source_line),
                         ('original.bsl', 7, 3, '  Возврат 2;'))
        with self.assertRaises(BSLError) as caught:
            parse(source.replace('Возврат 2;', 'Возврат +;'), 'original.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('original.bsl', 7))

    def test_declaration_availability_is_independent_per_side(self):
        for guard, sides in (
                ('Client', ['client']), ('Server', ['server']),
                ('AtClient', []), ('AtServer', []), ('AtClient Or AtServer', []),
                ('Not AtClient And Not AtServer', ['client', 'server']),
                ('Клиент И Не НаКлиенте', ['client']), ('Сервер И Не НаСервере', ['server'])):
            with self.subTest(guard=guard):
                routines = self.routines(f'#If {guard} Then\n&AtClientAtServerNoContext\nFunction F() Return 1; EndFunction\n#EndIf')
                self.assertEqual([node.execution_context for node in routines], sides)

    def test_nested_elsif_branches_do_not_make_false_duplicates(self):
        source = '''#If AtClient Then
&AtClientAtServerNoContext
Function F() Return 0; EndFunction
#ElsIf AtServer Then
&AtClientAtServerNoContext
Function F() Return 0; EndFunction
#Else
#If Client Or Server Then
&AtClientAtServerNoContext
Function F() Return 42; EndFunction
#EndIf
#EndIf'''
        pair = self.routines(source)
        self.assertEqual(len(pair), 2)
        self.assertTrue(all(node.body[0].value.value == 42 for node in pair))
        self.assertEqual(pair[0].token, pair[1].token)

    def test_same_profile_duplicate_names_remain_rejected(self):
        for guard in ('', '#If Client Then\n', '#If Server Then\n'):
            with self.subTest(guard=guard), self.assertRaisesRegex(BSLError, 'Повторное объявление'):
                parse(guard + '&AtClientAtServerNoContext\nFunction F() EndFunction\n'
                      '&НаКлиентеНаСервереБезКонтекста\nProcedure f() EndProcedure' +
                      ('\n#EndIf' if guard else ''))
        with self.assertRaisesRegex(BSLError, 'Повторное объявление'):
            parse('Procedure F() EndProcedure\nProcedure f() EndProcedure')

    def test_nested_target_branches_keep_independent_routine_boundaries(self):
        source = """&AtClientAtServerNoContext
Function F()
#If Client Then
 #If Server Then
  Function ExcludedAndUnfinished()
 #Else
  Return 11;
 #EndIf
#Else
 #If Client Then
  Procedure ExcludedAndUnfinished()
 #Else
  Return 22;
 #EndIf
#EndIf
EndFunction
&AtClientAtServerNoContext
Function G() Return 33; EndFunction"""
        nodes = self.routines(source)
        self.assertEqual([(node.name, node.execution_context) for node in nodes],
                         [('F', 'client'), ('G', 'client'), ('F', 'server'), ('G', 'server')])
        self.assertEqual([node.body[0].value.value for node in nodes], [11, 33, 22, 33])

    def test_disjoint_declarations_keep_distinct_provenance_for_runtime_validation(self):
        nodes = self.routines('''#If Client Then
&AtClientAtServerNoContext
Function F() Return 1; EndFunction
#Else
&AtClientAtServerNoContext
Function F() Return 2; EndFunction
#EndIf''')
        self.assertEqual([node.execution_context for node in nodes], ['client', 'server'])
        self.assertNotEqual(nodes[0].token.line, nodes[1].token.line)

    def test_dual_passes_emit_no_root_state_imports_or_initializers(self):
        source = '''Var ClientState;
// #Import ClientOnly.bsl
Message("client-root");
&AtServer
Var ServerState;
#If AtServer Then
 ServerState = 42;
#EndIf
#If Not AtClient And Not AtServer Then
Var NotModuleState;
// #Import Missing.bsl
Raise "not an initializer";
#EndIf
&AtServerNoContext
Function Detached() Return 3; EndFunction
&AtClientAtServerNoContext
Function F() Return 7; EndFunction'''
        for profile, side in (('dual_client', 'client'), ('dual_server', 'server')):
            with self.subTest(profile=profile):
                nodes = Parser(Lexer(source, execution_context=profile).tokens(), profile).parse()
                self.assertEqual(len(nodes), 1)
                self.assertIsInstance(nodes[0], ast.Routine)
                self.assertEqual((nodes[0].name, nodes[0].execution_context), ('F', side))
        nodes = parse(source)
        self.assertEqual([node.filename for node in nodes if isinstance(node, ast.Import)], ['ClientOnly.bsl'])
        self.assertEqual([node.names for node in nodes if isinstance(node, ast.Var)], [['ClientState'], ['ServerState']])
        roots = [node for node in nodes if isinstance(node, ast.ServerInitializer)]
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0].body[0].target.name, 'ServerState')
        self.assertEqual(len([node for node in nodes if isinstance(node, ast.ExpressionStatement)]), 1)

    def test_excluded_body_keywords_and_imports_cannot_change_boundaries(self):
        for guard in ('AtClient', 'AtServer', 'AtClient Or AtServer'):
            with self.subTest(guard=guard):
                source = f'''&AtClientAtServerNoContext
Function F()
#If {guard} Then
 Async Function Broken()
 &Unknown
 "unclosed
 'not a date
 // #Import Missing.bsl
#Else
 Return 42;
#EndIf
EndFunction
&AtClientAtServerNoContext
Function G() Return 7; EndFunction'''
                nodes = self.routines(source)
                self.assertEqual([(node.name, node.execution_context) for node in nodes],
                                 [('F', 'client'), ('G', 'client'), ('F', 'server'), ('G', 'server')])
                self.assertEqual([node.body[0].value.value for node in nodes], [42, 7, 42, 7])

    def test_unselected_foreign_routines_cannot_promote_nested_dual(self):
        for declaration in ('Procedure Hidden()', 'Async Procedure Hidden()',
                            '&AtClient\nProcedure Hidden()', '&AtServer\nProcedure Hidden()',
                            '&AtServerNoContext\nProcedure Hidden()', 'ignored=1; Procedure Hidden()'):
            source = '#If Not AtClient And Not AtServer Then\n' + declaration + '''
&AtClientAtServerNoContext
Function Promoted() Return 99; EndFunction
EndProcedure
#EndIf
&AtClientAtServerNoContext
Function Real() Return 42; EndFunction'''
            with self.subTest(declaration=declaration):
                if declaration.startswith('&AtServerNoContext'):
                    # Its own independent pass sees invalid nesting and rejects.
                    with self.assertRaisesRegex(BSLError, 'уровня модуля'):
                        parse(source)
                else:
                    self.assertEqual([node.name for node in self.routines(source)], ['Real', 'Real'])

    def test_nested_annotations_are_rejected_in_selected_bodies(self):
        for outer in ('', '&AtClient\n', '&AtServer\n', '&AtServerNoContext\n', '&AtClientAtServerNoContext\n'):
            with self.subTest(outer=outer), self.assertRaises(BSLError):
                parse(outer + 'Procedure P()\n&AtClientAtServerNoContext\nProcedure Q() EndProcedure\nEndProcedure')
        for inner in ('&AtClient', '&AtServer', '&AtServerNoContext', '&AtClientAtServerNoContext'):
            with self.subTest(inner=inner), self.assertRaisesRegex(BSLError, 'уровня модуля'):
                parse('&AtClientAtServerNoContext\nProcedure P()\n' + inner + '\nProcedure Q() EndProcedure\nEndProcedure')

    def test_annotations_in_omitted_root_blocks_are_not_promoted(self):
        for opening, ending in (('If True Then', 'EndIf'), ('While False Do', 'EndDo'),
                                ('For X=1 To 2 Do', 'EndDo'), ('Try', 'Except\nEndTry')):
            for guard in ('', '#If Client Then\n', '#If Server Then\n',
                          '#If Not AtClient And Not AtServer Then\n'):
                with self.subTest(opening=opening, guard=guard), self.assertRaisesRegex(BSLError, 'уровня модуля'):
                    parse(guard + opening + '\n&AtClientAtServerNoContext\nProcedure P() EndProcedure\n'
                          + ending + ('\n#EndIf' if guard else ''))

    def test_variable_annotations_are_rejected_but_locals_remain_valid(self):
        for directive in ('&AtClientAtServerNoContext', '&НаКлиентеНаСервереБезКонтекста'):
            for guard in ('', '#If Client Then\n', '#If Server Then\n', '#If AtClient Then\n'):
                with self.subTest(directive=directive, guard=guard), self.assertRaisesRegex(BSLError, 'переменной'):
                    parse(guard + directive + '\nVar Forbidden;' + ('\n#EndIf' if guard else ''))
        nodes = self.routines('&AtClientAtServerNoContext\nFunction F() Var Local; Local=1; Return Local; EndFunction')
        self.assertTrue(all(isinstance(node.body[0], ast.Var) for node in nodes))

    def test_async_dual_is_a_bounded_rejection_including_client_only_guards(self):
        for directive, declaration in (
                ('&AtClientAtServerNoContext', 'Async Function F() Return 1; EndFunction'),
                ('&НаКлиентеНаСервереБезКонтекста', 'Асинх Процедура F() КонецПроцедуры')):
            for guard in ('', '#If Client Then\n', '#If AtClient Then\n',
                          '#If Server Then\n', '#If Not AtClient And Not AtServer Then\n'):
                with self.subTest(directive=directive, guard=guard), self.assertRaisesRegex(BSLError, 'пока не поддерживается'):
                    parse(guard + directive + '\n' + declaration + ('\n#EndIf' if guard else ''))

    def test_await_rejected_in_dual_body_even_unreachable_or_side_specific(self):
        for body in ('Return Await 1;', 'Возврат Ждать 1;',
                     'If False Then Return Await 1; EndIf; Return 2;',
                     '#If Server Then\nReturn Await 1;\n#Else\nReturn 2;\n#EndIf'):
            with self.subTest(body=body), self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
                parse('&AtClientAtServerNoContext\nFunction F()\n' + body + '\nEndFunction')
        pair = self.routines('&AtClientAtServerNoContext\nFunction F()\n#If AtClient Or AtServer Then\nReturn Await 1;\n#Else\nReturn 2;\n#EndIf\nEndFunction')
        self.assertEqual([node.body[0].value.value for node in pair], [2, 2])

    def test_direct_ast_rejects_async_capability_and_invalid_dual_metadata(self):
        for context in ('client', 'server'):
            routine = next(node for node in self.routines('&AtClientAtServerNoContext\nFunction F() Return 1; EndFunction')
                           if node.execution_context == context)
            routine.is_async = True
            with self.subTest(context=context), self.assertRaisesRegex(BSLError, 'пока не поддерживается'):
                validate_async([routine])
            routine.is_async = False
            routine.module_context = True
            with self.assertRaisesRegex(BSLError, 'без контекста'):
                validate_async([routine])
            routine.module_context = False
            routine.execution_context = 'dual_client'
            with self.assertRaisesRegex(BSLError, 'сторону клиента или сервера'):
                validate_async([routine])
        routine, = self.routines('Function F() Return 1; EndFunction')
        routine.is_dual = 1
        with self.assertRaisesRegex(BSLError, 'должен быть булевым'):
            validate_async([routine])

    def test_direct_ast_await_cannot_acquire_async_permission(self):
        routine = self.routines('&AtClientAtServerNoContext\nFunction F() Return 1; EndFunction')[0]
        routine.body[0].value = ast.Await(routine.token, routine.body[0].value)
        with self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
            validate_async([routine])

    def test_pending_malformed_and_command_module_annotations_rejected(self):
        for source in ('&AtClientAtServerNoContext', '&НаКлиентеНаСервереБезКонтекста\n// comment',
                       '&AtClientAtServerNoContext\nFunction F()'):
            with self.subTest(source=source), self.assertRaises(IncompleteInput):
                parse(source)
        for directive in ('&AtClientAtServer', '&НаКлиентеНаСервере'):
            with self.subTest(directive=directive), self.assertRaisesRegex(BSLError, 'не поддерживается'):
                parse(directive + '\nProcedure P() EndProcedure')
        for prefix in ('&AtClientAtServerNoContext\n&AtClient', '&AtServer\n&AtClientAtServerNoContext',
                       '&AtClientAtServerNoContext\nx=1;', 'x=1; &AtClientAtServerNoContext'):
            with self.subTest(prefix=prefix), self.assertRaises(BSLError):
                parse(prefix + '\nProcedure P() EndProcedure')

    def test_dynamic_fragments_reject_dual_compilation_directives(self):
        for parser in (parse_expression, parse_fragment):
            with self.subTest(parser=parser.__name__), self.assertRaises(BSLError):
                parser('&AtClientAtServerNoContext\nProcedure P() EndProcedure')

    def test_selected_body_imports_are_rejected_on_each_side(self):
        for guard in ('Client', 'Server'):
            for text in ('// #Import Missing.bsl', '#Import Missing.bsl'):
                with self.subTest(guard=guard, text=text), self.assertRaises(BSLError):
                    parse('&AtClientAtServerNoContext\nFunction F()\n#If ' + guard + ' Then\n'
                          + text + '\n#EndIf\nEndFunction')

    def test_strings_comments_and_regions_do_not_introduce_extra_declarations(self):
        source = '''Message("ordinary\n|&AtClientAtServerNoContext\n|Function Fake() EndFunction");
// &AtClientAtServerNoContext
&AtClientAtServerNoContext
Function F()
#Region Local
 Return 42;
#EndRegion
EndFunction'''
        self.assertEqual([node.name for node in self.routines(source)], ['F', 'F'])

    def test_ordinary_no_context_and_async_selection_remains_independent(self):
        nodes = parse('''Function Plain() Return 1; EndFunction
&AtClient
Async Function C() Return Await 2; EndFunction
&AtServer
Function S()
#If AtServer Then
 Return 3;
#Else
 Return 0;
#EndIf
EndFunction
&AtServerNoContext
Function N()
#If Not AtClient And Not AtServer And Server Then
 Return 4;
#Else
 Return 0;
#EndIf
EndFunction
&AtClientAtServerNoContext
Function D() Return 5; EndFunction''')
        self.assertEqual([(node.name, node.execution_context, node.module_context, node.is_async, node.is_dual)
                          for node in nodes],
                         [('Plain', 'client', True, False, False), ('C', 'client', True, True, False),
                          ('S', 'server', True, False, False), ('N', 'server', False, False, False),
                          ('D', 'client', False, False, True), ('D', 'server', False, False, True)])
        self.assertEqual(nodes[2].body[0].value.value, 3)
        self.assertEqual(nodes[3].body[0].value.value, 4)


if __name__ == '__main__':
    unittest.main()
