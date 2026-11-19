"""Positional omissions in persisted generated BSL routines."""
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


class DirectPersistedRoutineHoleTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.addCleanup(self.vm.close)
        self.vm.execute("""
            Procedure Add(X, Val Amount=2, Val Tail=7)
                X=X+?(Amount=Undefined,0,Amount)+Tail;
            EndProcedure
            Function Encode(Val First, Val Second)
                Return ?(First=Undefined,0,First)*10+?(Second=Undefined,0,Second);
            EndFunction
            Function LocalDefault(X=7, Val Tail=2)
                X=X+Tail;
                Return X;
            EndFunction
        """)

    def test_persisted_byref_and_defaults_in_source_ast_prepared_and_fragment(self):
        from yadinassi.syntax.parser import parse

        script='X=1; Add(X,,3);'
        for route in (self.vm.execute, lambda text: self.vm.execute_program(parse(text)),
                      lambda text: self.vm.execute_prepared(self.vm.prepare(text))):
            route(script)
            self.assertEqual(self.vm.variables['x'], 6)
        self.vm.execute('Execute "Add(X, Undefined, 3);";')
        self.assertEqual(self.vm.variables['x'], 9)
        self.assertEqual(self.vm.execute('Encode(,)'), 0)
        self.assertEqual(self.vm.execute('LocalDefault(,3)'), 10)

    def test_arity_checked_before_actual_effects(self):
        self.vm.execute('X=0; Function Tick() Raise "unexpected argument effect"; Return 1; EndFunction')
        for script in ('Encode(Tick(),,);', 'Execute "Encode(Tick(),,);";'):
            with self.subTest(script=script), self.assertRaisesRegex(BSLRuntimeError,'получено 3'):
                self.vm.execute(script)
            self.assertEqual(self.vm.variables['x'], 0)

    def test_same_side_server_calls_apply_holes_and_keep_references_live(self):
        self.vm.execute("""
            &AtServer
            Procedure AddServer(X, Val Amount=2, Val Tail=7) X=X+Amount+Tail; EndProcedure
        """)
        self.vm.execute("""
            &AtServer
            Procedure RunServer(X) AddServer(X,,3); EndProcedure
            X=1; RunServer(X);
        """)
        self.assertEqual(self.vm.variables['x'], 6)

    def test_client_server_hole_contract_unchanged(self):
        self.vm.execute('&AtServer\nProcedure AddServer(X, Val Amount=2) X=X+Amount; EndProcedure')
        with self.assertRaisesRegex(BSLRuntimeError,'Пропуск аргументов'):
            self.vm.execute('X=1; AddServer(X,);')
        self.assertEqual(self.vm.variables['x'], 1)
