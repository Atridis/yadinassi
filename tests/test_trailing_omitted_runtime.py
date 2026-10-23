"""Bounded trailing-position regressions, with local async/host composition checks.

The native nine-case witness grounds the same-side routine results and arity
guards. The AST, bilingual and async checks do not claim separate native probes.
"""

from decimal import Decimal
import unittest

from yadinassi import Interpreter, ast
from yadinassi.async_runtime import Promise
from yadinassi.errors import BSLRuntimeError
from yadinassi.parser import parse


ROUTINES = '''
    Var argumentsCalled, bodiesCalled;
    argumentsCalled = 0; bodiesCalled = 0;
    Function Encode(Val first, Val second)
        Return ?(first = Undefined, 0, first) * 10
            + ?(second = Undefined, 0, second);
    EndFunction
    Function Defaults(first = 1, second = 2)
        bodiesCalled = bodiesCalled + 1; Return Encode(first, second);
    EndFunction
    Function Required(first, second)
        bodiesCalled = bodiesCalled + 1; Return Encode(first, second);
    EndFunction
    Function One(value)
        bodiesCalled = bodiesCalled + 1; Return value;
    EndFunction
    Function Tick()
        argumentsCalled = argumentsCalled + 1; Return argumentsCalled;
    EndFunction
'''


class TrailingOmittedArgumentTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_empty_call_and_terminal_holes_have_distinct_ast_positions(self):
        cases = (('P()', ()), ('P(,)', (True, True)),
                 ('P(,,)', (True, True, True)), ('P(1,)', (False, True)),
                 ('P(1,,)', (False, True, True)),
                 ('P(,1,)', (True, False, True)))
        for source, omissions in cases:
            with self.subTest(source=source):
                call = parse(source)[0].expression
                self.assertIsInstance(call, ast.Call)
                self.assertEqual(len(call.arguments), len(omissions))
                self.assertEqual(tuple(isinstance(value, ast.OmittedArgument)
                                       for value in call.arguments), omissions)

    def test_direct_calls_keep_defaults_distinct_from_explicit_undefined(self):
        self.vm.execute(ROUTINES + '''
            Message(Defaults()); Message(Required(,));
            Message(Defaults(5,)); Message(Defaults(5, Undefined));
        ''')
        self.assertEqual(self.output, ['12', '0', '52', '50'])
        self.assertEqual(self.vm.execute('bodiesCalled'), Decimal(4))
        self.assertEqual(self.vm.execute('argumentsCalled'), Decimal(0))

    def test_russian_function_and_procedure_accept_terminal_holes(self):
        self.vm.execute('''
            Функция Значения(Знач первый = 1, Знач второй = 2)
                Возврат первый * 10 + ?(второй = Неопределено, 0, второй);
            КонецФункции
            Процедура Пропуски(первый, второй)
                Сообщить(первый = Неопределено);
                Сообщить(второй = Неопределено);
            КонецПроцедуры
            Сообщить(Значения(5,)); Сообщить(Значения(5, Неопределено));
            Пропуски(,);
        ''')
        self.assertEqual(self.output, ['52', '50', 'Да', 'Да'])

    def test_execute_preserves_terminal_defaults_and_explicit_required_holes(self):
        self.vm.execute(ROUTINES + '''
            result = 99;
            Execute("result = Defaults(5,);"); Message(result);
            Выполнить("result = Required(,);"); Сообщить(result);
            Execute("result = Defaults(5, Undefined);"); Message(result);
        ''')
        self.assertEqual(self.output, ['52', '0', '50'])
        self.assertEqual(self.vm.execute('bodiesCalled'), Decimal(3))
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm._execute_depth[0], 0)

    def test_arity_rejection_precedes_argument_and_body_effects(self):
        self.vm.execute(ROUTINES)
        for expression, count in (('Required()', 0), ('Required(,,)', 3),
                                  ('One(Tick(),)', 2), ('One(Tick(), 2,)', 3),
                                  ('Required(Tick(),,)', 3)):
            for dynamic in (False, True):
                statement = (f'Execute("result = {expression};")'
                             if dynamic else f'result = {expression}')
                with self.subTest(expression=expression, dynamic=dynamic):
                    with self.assertRaisesRegex(BSLRuntimeError, f'получено {count}'):
                        self.vm.execute(statement, 'trailing-arity.bsl')
                    self.assertEqual(self.vm.execute('argumentsCalled'), Decimal(0))
                    self.assertEqual(self.vm.execute('bodiesCalled'), Decimal(0))
                    self.assertIsNone(self.vm.locals)
                    self.assertEqual(self.vm._execute_depth[0], 0)
        self.assertEqual(self.output, [])

    def test_awaited_arguments_and_async_defaults_compose_without_runtime_changes(self):
        self.vm.execute('''
            Async Function Pair(Val first = 1, Val second = 2)
                Return Await (first * 10 + second);
            EndFunction
            Async Function Compose()
                first = Await Pair(Await 5,);
                second = Await Pair(,);
                Return first + second;
            EndFunction
            Async Procedure Show(first = 1, second = 2)
                Message(Await Pair(first,));
            EndProcedure
            result = Compose(); Show(,);
        ''')
        promise = self.vm.variables['result']
        self.assertIsInstance(promise, Promise)
        self.assertEqual(promise.result, Decimal(64))
        self.assertEqual(self.output, ['12'])
        self.assertEqual(self.vm.pending_promises, ())
        self.assertIsNone(self.vm.locals)

    def test_unsupported_host_and_constructor_holes_precede_all_effects(self):
        self.vm.execute(ROUTINES + '''
            items = New Array;
            Function Receiver()
                argumentsCalled = argumentsCalled + 10; Return items;
            EndFunction
        ''')
        host_calls = []
        self.vm.register_function('Host', lambda *values: host_calls.append(values))
        self.vm.register_type('HostType', lambda *values: host_calls.append(values))
        for expression in ('Message(Tick(),)', 'Host(Tick(),)',
                           'items.Add(Tick(),)', 'Receiver().Add(Tick(),)',
                           'New Array(Tick(),)', 'New HostType(Tick(),)'):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(BSLRuntimeError, 'Пропуск аргументов'):
                    self.vm.execute(expression)
                self.assertEqual(self.vm.execute('argumentsCalled'), Decimal(0))
                self.assertEqual(self.vm.execute('items.Count()'), Decimal(0))
                self.assertEqual(host_calls, [])
                self.assertEqual(self.output, [])


if __name__ == '__main__':
    unittest.main()
