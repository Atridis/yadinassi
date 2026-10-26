"""Async grammar tests, not native execution or scheduling evidence.

Await's unary precedence is a bounded implementation choice. Compound operands
can be grouped explicitly; native ungrouped precedence has not been measured.
"""
import unittest

from yadinassi.syntax import ast
from yadinassi.errors import BSLError
from yadinassi.syntax.lexer import Lexer
from yadinassi.syntax.parser import parse, parse_expression, parse_fragment, validate_async


class AsyncParserTests(unittest.TestCase):
    def expression(self, expression):
        routine, = parse(f'Async Function F() Return {expression}; EndFunction')
        return routine.body[0].value

    def test_keywords_are_bilingual_and_case_insensitive(self):
        self.assertEqual([t.kind for t in Lexer('АсИнХ AsYnC ЖдАтЬ aWaIt').tokens()],
                         ['ASYNC', 'ASYNC', 'AWAIT', 'AWAIT', 'EOF'])

    def test_bilingual_routines_export_and_parameters(self):
        for source in (
            'Асинх Функция Ф(Знач А = 1) Экспорт Возврат Ждать А; КонецФункции',
            'aSyNc FuNcTiOn F(Val A = 1) Export Return aWaIt A; EndFunction',
        ):
            with self.subTest(source=source):
                routine, = parse(source)
                self.assertTrue(routine.is_async)
                self.assertTrue(routine.is_function)
                self.assertTrue(routine.exported)
                self.assertEqual(routine.execution_context, 'client')
                self.assertTrue(routine.parameters[0].by_value)
                self.assertIsInstance(routine.body[0].value, ast.Await)

    def test_async_procedure_and_sync_default(self):
        async_proc, sync_func = parse('Async Procedure P() Await 1; Return; EndProcedure '
                                     'Function F() Return 1; EndFunction')
        self.assertTrue(async_proc.is_async)
        self.assertFalse(async_proc.is_function)
        self.assertFalse(sync_func.is_async)
        self.assertIsInstance(async_proc.body[0].expression, ast.Await)

    def test_explicit_client_and_server_skip(self):
        client, server = parse('&AtClient\nAsync Function F() Return Await 1; EndFunction\n'
                               '&AtServer\nFunction S() Return 2; EndFunction')
        self.assertTrue(client.is_async)
        self.assertEqual(server.execution_context, 'server')
        self.assertFalse(server.is_async)

    def test_client_body_not_selected_by_server_preprocessor(self):
        client, server = parse('''
&AtClient
Async Function F()
#If Client Then
 Return Await 1;
#Else
 not valid @ client body;
#EndIf
EndFunction
&AtServer
Function S()
#If Server Then
 Return 2;
#Else
 Return Await 3;
#EndIf
EndFunction
''')
        self.assertTrue(client.is_async)
        self.assertEqual(server.body[0].value.value, 2)

    def test_await_nested_group_argument_and_return(self):
        call = self.expression('AddOne((Await Leaf()))')
        self.assertIsInstance(call, ast.Call)
        self.assertIsInstance(call.arguments[0], ast.Group)
        self.assertIsInstance(call.arguments[0].expression, ast.Await)
        self.assertIsInstance(call.arguments[0].expression.operand, ast.Call)
        nested = self.expression('Await (Await P)')
        self.assertIsInstance(nested.operand.expression, ast.Await)

    def test_scalar_await_is_valid_syntax(self):
        for operand in ('1', '"text"', 'True', 'Undefined', 'Null', '-1'):
            with self.subTest(operand=operand):
                self.assertIsInstance(self.expression('Await ' + operand), ast.Await)

    def test_bounded_unary_precedence_and_grouped_compound(self):
        node = self.expression('Await F().Value[0] + 2')
        self.assertIsInstance(node, ast.Binary)
        self.assertIsInstance(node.left, ast.Await)
        self.assertIsInstance(node.left.operand, ast.Index)
        node = self.expression('Await (1 + 2)')
        self.assertIsInstance(node.operand.expression, ast.Binary)
        node = self.expression('(Await F()).Value')
        self.assertIsInstance(node, ast.Attribute)
        self.assertIsInstance(node.object.expression, ast.Await)

    def test_await_invalid_contexts_rejected_before_returning_ast(self):
        for source in (
            'Message("before"); Await F();',
            'Message("before"); If False Then Await F(); EndIf;',
            'Procedure P() Await F(); EndProcedure',
            'Function F() Return Await 1; EndFunction',
            'Async Procedure P() EndProcedure Procedure Q() Await 1; EndProcedure',
            '&AtServer\nFunction F() Return Await 1; EndFunction',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
                parse(source)

    def test_server_async_rejected_in_server_compilation(self):
        for prefix in ('', '#If Server Then\n'):
            source = prefix + '&AtServer\nAsync Function F() Return 1; EndFunction\n'
            if prefix:
                source += '#EndIf\n'
            with self.subTest(prefix=prefix), self.assertRaisesRegex(BSLError, 'только на клиенте'):
                parse(source)

    def test_invalid_async_modifier_positions(self):
        for source in ('Async X = 1;', 'Async Async Function F() EndFunction',
                       'Procedure P() Async Procedure Q() EndProcedure EndProcedure',
                       'Function Async F() EndFunction'):
            with self.subTest(source=source), self.assertRaises(BSLError):
                parse(source)

    def test_async_procedure_still_cannot_return_value(self):
        with self.assertRaisesRegex(BSLError, 'не может возвращать значение'):
            parse('Async Procedure P() Return Await 1; EndProcedure')

    def test_dynamic_await_and_declarations_remain_unsupported(self):
        for parse_dynamic, source in ((parse_expression, 'Await F()'),
                                      (parse_fragment, 'Await F();'),
                                      (parse_fragment, 'Async Function F() EndFunction')):
            with self.subTest(source=source), self.assertRaises(BSLError):
                parse_dynamic(source)
        self.assertIsInstance(parse_expression('F()'), ast.Call)

    def test_direct_ast_rejects_await_outside_async_scope(self):
        awaited = self.expression('Await 1')
        token = awaited.token
        for program in (
            [ast.ExpressionStatement(token, awaited)],
            [ast.If(token, [(ast.Literal(token, False),
                            [ast.ExpressionStatement(token, awaited)])], [])],
            [ast.Routine(token, 'F', [], True, False, [ast.Return(token, awaited)])],
        ):
            with self.subTest(program=program), self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
                validate_async(program)

    def test_direct_ast_validates_async_routine_flags_and_scope(self):
        routine, = parse('Async Function F() Return Await 1; EndFunction')
        validate_async([routine])
        for context in ('server', 'other', None):
            routine.execution_context = context
            with self.subTest(context=context), self.assertRaisesRegex(BSLError, 'только на клиенте'):
                validate_async([routine])
        routine.execution_context = 'client'
        for flag in (1, 'true', None):
            routine.is_async = flag
            with self.subTest(flag=flag), self.assertRaisesRegex(BSLError, 'булевым'):
                validate_async([routine])

    def test_direct_ast_rejects_nested_routines_and_await_defaults(self):
        outer, inner = parse('Async Procedure P() EndProcedure '
                             'Async Function F() Return Await 1; EndFunction')
        outer.body = [ast.If(outer.token, [(ast.Literal(outer.token, False), [inner])], [])]
        with self.assertRaisesRegex(BSLError, 'уровне модуля'):
            validate_async([outer])
        with self.assertRaisesRegex(BSLError, 'уровне модуля'):
            validate_async(outer.body)
        inner.parameters = [ast.Parameter(inner.token, 'P', True, self.expression('Await 1'))]
        with self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
            validate_async([inner])

    def test_error_keeps_source_location(self):
        with self.assertRaises(BSLError) as caught:
            parse('\nAwait 1;', 'async-invalid.bsl')
        self.assertEqual(caught.exception.source, 'async-invalid.bsl')
        self.assertEqual(caught.exception.line, 2)


if __name__ == '__main__':
    unittest.main()
