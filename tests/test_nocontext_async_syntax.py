"""Compiler-only composition of NoContext and client-only Async/Await."""
from dataclasses import fields
import unittest

from yadinassi.syntax import ast
from yadinassi.errors import BSLError
from yadinassi.syntax.parser import parse, validate_async


class NoContextAsyncSyntaxTests(unittest.TestCase):
    def test_async_and_module_context_metadata_are_independent(self):
        nodes = parse('''&AtClient
Async Function Client() Return Await 1; EndFunction
&AtServer
Function Server() Return 2; EndFunction
&AtServerNoContext
Function Detached() Return 3; EndFunction''')
        self.assertEqual([(node.name, node.execution_context, node.is_async, node.module_context)
                          for node in nodes],
                         [('Client', 'client', True, True), ('Server', 'server', False, True),
                          ('Detached', 'server', False, False)])
        self.assertEqual([field.name for field in fields(ast.Routine)][-3:],
                         ['is_async', 'module_context', 'is_dual'])
        legacy = ast.Routine(nodes[0].token, 'Legacy', [], True, False, [], 'client', True)
        self.assertTrue(legacy.is_async)
        self.assertTrue(legacy.module_context)
        self.assertFalse(legacy.is_dual)

    def test_async_no_context_is_rejected_in_its_own_compilation(self):
        for directive, declaration in (
                ('&AtServerNoContext', 'Async Function F() Return 1; EndFunction'),
                ('&НаСервереБезКонтекста', 'Асинх Функция F() Возврат 1; КонецФункции')):
            for guard in ('', '#If Server Then\n', '#If Not AtClient And Not AtServer Then\n'):
                with self.subTest(directive=directive, guard=guard), self.assertRaisesRegex(
                        BSLError, 'только на клиенте'):
                    parse('Message("must not execute");\n' + guard + directive + '\n' + declaration
                          + ('\n#EndIf' if guard else ''))

    def test_await_is_rejected_in_no_context_including_unreachable_code(self):
        for statement in ('Return Await 1;', 'Возврат Ждать 1;',
                          'If False Then Return Await 1; EndIf; Return 2;'):
            with self.subTest(statement=statement), self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
                parse('Message("must not execute");\n&AtServerNoContext\nFunction F()\n'
                      + statement + '\nEndFunction')

    def test_await_is_rejected_in_server_initializer_with_async_client_present(self):
        with self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
            parse('''Async Function Client() Return Await 1; EndFunction
&AtServerNoContext
Function Detached() Return 2; EndFunction
#If AtServer Then
If False Then Value = Await 1; EndIf;
#EndIf''')

    def test_no_context_body_preprocessing_does_not_inherit_async_permission(self):
        nodes = parse('''Async Function Client() Return Await 1; EndFunction
&AtServerNoContext
Function Detached()
#If AtClient Or AtServer Then
 Return Await 0;
#ElsIf Server And Not Client Then
 Return 42;
#Else
 Return Await 2;
#EndIf
EndFunction''')
        detached = next(node for node in nodes if node.name == 'Detached')
        self.assertFalse(detached.is_async)
        self.assertFalse(detached.module_context)
        self.assertEqual(detached.body[0].value.value, 42)

    def test_skipped_async_routines_do_not_promote_nested_no_context_declarations(self):
        for declaration in ('Async Procedure Hidden()', '&AtClient\nAsync Procedure Hidden()',
                            '&AtServer\nAsync Procedure Hidden()',
                            'ignored=1; Асинх Процедура Hidden()'):
            with self.subTest(declaration=declaration):
                nodes = parse('#If Not AtClient And Not AtServer Then\n' + declaration + '''
&AtServerNoContext
Function Promoted() Return 99; EndFunction
EndProcedure
#EndIf
&AtServerNoContext
Function Real() Return 42; EndFunction''')
                self.assertEqual([node.name for node in nodes], ['Real'])

    def test_excluded_async_keywords_do_not_break_no_context_body_boundaries(self):
        for guard in ('AtClient', 'AtServer', 'AtClient Or AtServer'):
            with self.subTest(guard=guard):
                nodes = parse(f'''&AtServerNoContext
Function Detached()
#If {guard} Then
 Async Function IncompleteAndExcluded()
 Await 0;
#EndIf
 Return 42;
EndFunction
Async Function Client() Return Await 1; EndFunction''')
                self.assertEqual({node.name for node in nodes}, {'Client', 'Detached'})
                detached = next(node for node in nodes if node.name == 'Detached')
                self.assertEqual(detached.body[0].value.value, 42)

    def test_direct_ast_cannot_grant_async_permission_to_no_context(self):
        routine, = parse('&AtServerNoContext\nFunction F() Return 1; EndFunction')
        routine.is_async = True
        for context in ('server', 'client'):
            routine.execution_context = context
            with self.subTest(context=context), self.assertRaisesRegex(BSLError, 'только на клиенте'):
                validate_async([routine])


if __name__ == '__main__':
    unittest.main()
