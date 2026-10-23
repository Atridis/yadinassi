"""Parser-only integration of async client routines and server module setup."""
import unittest

from yadinassi import ast
from yadinassi.errors import BSLError
from yadinassi.parser import parse, validate_async, validate_labels


class AsyncModuleSyntaxTests(unittest.TestCase):
    def test_side_local_vars_async_routines_and_initializer_coexist(self):
        nodes = parse('''
&AtClient
Var C;
&AtServer
Var S;
&AtClient
Async Function F() Return Await C; EndFunction
&AtServer
Function G() Return S; EndFunction
#If AtServer Then
S = 42;
#EndIf
''')
        variables = [n for n in nodes if isinstance(n, ast.Var)]
        self.assertEqual([(n.names, n.execution_context) for n in variables],
                         [(['C'], 'client'), (['S'], 'server')])
        routines = [n for n in nodes if isinstance(n, ast.Routine)]
        self.assertEqual([(n.name, n.is_async, n.execution_context) for n in routines],
                         [('F', True, 'client'), ('G', False, 'server')])
        initializer, = [n for n in nodes if isinstance(n, ast.ServerInitializer)]
        self.assertEqual(initializer.body[0].target.name, 'S')

    def test_server_guard_does_not_promote_unannotated_async_to_initializer(self):
        for declaration in ('Async Function Invisible()', 'Асинх Функция Invisible()',
                            'AsYnC\n// comment\nFunction Invisible()'):
            ending = 'КонецФункции' if 'Функция' in declaration else 'EndFunction'
            for before in ('', 'S = 1;\n'):
                source = ('#If AtServer Then\n' + before + declaration + '\nReturn Await 1;\n'
                          + ending + '\nS = 2;\n#EndIf')
                with self.subTest(declaration=declaration, before=before):
                    nodes = parse(source)
                    self.assertTrue(nodes)
                    self.assertTrue(all(isinstance(n, ast.ServerInitializer) for n in nodes))
                    body = [item for n in nodes for item in n.body]
                    self.assertEqual(len(body), 2 if before else 1)
                    self.assertTrue(all(isinstance(n, ast.Assign) for n in body))

    def test_explicit_excluded_client_async_and_var_preserve_server_root(self):
        nodes = parse('''#If AtServer Then
&AtClient
Var Hidden;
&AtClient
Async Function HiddenF() Return Await 1; EndFunction
S = 3;
#EndIf''')
        initializer, = nodes
        self.assertIsInstance(initializer, ast.ServerInitializer)
        self.assertEqual(initializer.body[0].value.value, 3)

    def test_module_await_and_server_async_still_rejected(self):
        for source in ('#If AtServer Then\nS = Await F();\n#EndIf',
                       '&AtServer\nAsync Function F() Return 1; EndFunction',
                       '&AtClient\nAsync Var X;'):
            with self.subTest(source=source), self.assertRaises(BSLError):
                parse(source)

    def test_direct_ast_initializer_is_top_level_synchronous_only(self):
        routine, = parse('Async Function F() Return Await 1; EndFunction')
        awaited = routine.body[0].value
        initializer = ast.ServerInitializer(routine.token, [ast.ExpressionStatement(routine.token, awaited)])
        with self.assertRaisesRegex(BSLError, 'Ждать допустимо'):
            validate_async([initializer])
        routine.body = [initializer]
        with self.assertRaisesRegex(BSLError, 'инициализатор.*уровне модуля'):
            validate_async([routine])
        initializer.body = []
        with self.assertRaisesRegex(BSLError, 'инициализатор.*уровне модуля'):
            validate_async([routine])
        validate_async([initializer])
        initializer.body = [routine]
        with self.assertRaisesRegex(BSLError, 'уровне модуля'):
            validate_async([initializer])

    def test_initializer_label_scope_is_isolated_from_client_routine(self):
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            parse('Async Procedure P() ~Client: Await 1; EndProcedure\n'
                  '#If AtServer Then\nGoto ~Client;\n#EndIf')
        nodes = parse('Async Procedure P() ~Same: Await 1; EndProcedure\n'
                      '#If AtServer Then\n~Same: S=1; Goto ~Same;\n#EndIf')
        validate_labels(nodes)


if __name__ == '__main__':
    unittest.main()
