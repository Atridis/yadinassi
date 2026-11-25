"""Mutable Array observations from Linux 1C 8.3.27.1508, run 45423566791."""

import ast
from contextlib import closing
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


# Expected positions, not Python conversion rules. See native artifact
# 14934532505, 04_array_indices.bsl (raw SHA256 7233e5f1...).
CASES = (
    ('0', 0, 0), ('1', 1, 1), ('2', None, None), ('-1', None, None),
    ('-0.5', None, 0), ('0.5', 0, 0), ('1.9', 1, 1), ('True', None, 1),
)


def run(vm, source, prepared):
    return vm.execute_prepared(vm.prepare(source)) if prepared else vm.execute(source)


class MutableArrayIndexTests(unittest.TestCase):
    def test_measured_mutable_indices_across_public_representations(self):
        constructors = (
            'A=New Array;A.Add(7);A.Add(9);',
            'A=New Array(2);A.Set(0,7);A.Set(1,9);',
            'A=StrSplit("first,second",",");A.Set(0,7);A.Set(1,9);',
        )
        for prepared in (False, True):
            for setup in constructors:
                for expression, bracket, method in CASES:
                    with self.subTest(prepared=prepared, setup=setup, index=expression):
                        with closing(Interpreter()) as vm:
                            vm.execute(setup)
                            for read, write, position in (
                                (f'A[{expression}]', f'A[{expression}]=99;', bracket),
                                (f'A.Get({expression})', f'A.Set({expression},99);', method),
                                (f'A.Получить({expression})', f'A.Установить({expression},99);', method),
                            ):
                                if position is None:
                                    with self.assertRaises(BSLRuntimeError):
                                        run(vm, read, prepared)
                                    with self.assertRaises(BSLRuntimeError):
                                        run(vm, write, prepared)
                                    expected = (7, 9)
                                else:
                                    self.assertEqual(run(vm, read, prepared), (7, 9)[position])
                                    run(vm, write, prepared)
                                    expected = (99, 9) if position == 0 else (7, 99)
                                self.assertEqual(vm.execute('A.Count()'), 2)
                                self.assertEqual((vm.execute('A[0]'), vm.execute('A[1]')), expected)
                                vm.execute('A[0]=7;A[1]=9;')

    def test_bracket_and_method_evaluate_receiver_index_and_rhs_once(self):
        source = '''
            Function Receiver(Val A) Message("receiver"); Return A; EndFunction
            Function Key(Val N) Message("index"); Return N; EndFunction
            Function RHS() Message("rhs"); Return 99; EndFunction
            A=New Array(0); A.Add(7); A.Add(9);
        '''
        for prepared in (False, True):
            output = []
            with closing(Interpreter(output.append)) as vm:
                vm.execute(source)
                for expression, expected in (
                    ('Message(Receiver(A)[Key(0.5)]);', ['receiver', 'index', '7']),
                    ('Message(Receiver(A).Get(Key(True)));', ['receiver', 'index', '9']),
                    ('Receiver(A)[Key(-1)]=RHS();', ['receiver', 'index', 'rhs']),
                    ('Receiver(A).Set(Key(-1),RHS());', ['receiver', 'index', 'rhs']),
                ):
                    with self.subTest(prepared=prepared, expression=expression):
                        output.clear()
                        if expression.startswith('Message'):
                            run(vm, expression, prepared)
                        else:
                            with self.assertRaises(BSLRuntimeError):
                                run(vm, expression, prepared)
                        self.assertEqual(output, expected)
                        self.assertEqual((vm.execute('A[0]'), vm.execute('A[1]')), (7, 9))
                run(vm, 'Read=A.Get; Write=A.Set; Previous=A; A=New Array(0); '
                        'Write(True,42); R=Read(-0.5);', prepared)
                self.assertEqual(vm.execute('R'), 7)
                self.assertEqual(vm.execute('Previous[1]'), 42)
                self.assertEqual(vm.execute('A.Count()'), 0)

    def test_native_subscript_syntax_and_checked_live_indices(self):
        with closing(Interpreter()) as vm:
            plan = vm.prepare('A=New Array;A.Add(7);A.Add(9); S=0; '
                              'For I=0 To 1 Do A[I]=A.Get(I); S=S+A[I];EndDo; S;')
            tree = ast.parse(plan._plan.generated_source)
            loop = next(n for n in ast.walk(tree) if type(n) in (ast.For, ast.While))
            self.assertTrue(any(type(n) is ast.Subscript for n in ast.walk(loop)))
            hot = ast.unparse(loop)
            self.assertNotIn('._check(', hot)
            self.assertNotIn('.checkpoint(', hot)
            self.assertEqual(vm.execute_prepared(plan), 16)
            with self.assertRaises(BSLRuntimeError):
                vm.execute('A=New Array;A.Add(7); For I=-1 To -1 Do A[I]; EndDo;')
            with self.assertRaises(BSLRuntimeError):
                vm.execute('F=New FixedArray(New Array(2)); F[0.5];')
