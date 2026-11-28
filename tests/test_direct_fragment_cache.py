"""Bounded fragment reuse preserves exact source and execution ownership."""
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_fragment_cache import FragmentUnitCache
from yadinassi.syntax import parser


class FragmentUnitAdmissionTests(unittest.TestCase):
    def test_fingerprint_collision_only_impacts_admission(self):
        class CollisionText(str):
            def __hash__(self):
                return 1

        cache = FragmentUnitCache()
        for i in range(16):
            cache.remember((str(i), 'test profile'), i, 65536)
        a = (CollisionText('A'), 'test profile')
        b = (CollisionText('B'), 'test profile')
        self.assertEqual(hash(a), hash(b))
        cache.remember(a, 'unit A', 65536)
        self.assertNotIn(a, cache.units)
        cache.remember(b, 'unit B', 65536)
        self.assertNotIn(a, cache.units)
        self.assertEqual(cache.units[b], 'unit B')
        self.assertNotIn((b[0], 'another profile'), cache.units)
        self.assertEqual(len(cache.units), 16)

    def test_one_off_history_is_bounded_and_keeps_no_text(self):
        cache = FragmentUnitCache()
        resident = tuple((str(i), 'test profile') for i in range(16))
        for key in resident:
            cache.remember(key, object(), 65536)
        for i in range(100):
            cache.remember(('transient ' + str(i), 'test profile'), object(), 65536)
        self.assertEqual(tuple(cache.units), resident)
        self.assertLessEqual(len(cache._misses), 16)
        self.assertTrue(all(type(fingerprint) is int for fingerprint in cache._misses))

    def test_repeated_working_set_adapts_without_exceeding_caps(self):
        cache = FragmentUnitCache()
        for i in range(16):
            cache.remember((f'A{i:02}',), i, 48)
        next_set = tuple((f'B{i:02}',) for i in range(16))
        for _ in range(2):
            for key in next_set:
                cache.remember(key, object(), 48)
                self.assertLessEqual(len(cache.units), 16)
                self.assertLessEqual(sum(len(k[0]) for k in cache.units), 48)
        self.assertEqual(tuple(cache.units), next_set)
        original = cache.units[next_set[-1]]
        cache.remember(next_set[-1], object(), 48)
        self.assertIs(cache.units[next_set[-1]], original)
        self.assertEqual(cache._source_chars, 48)


class FragmentAdmissionBehaviorTests(unittest.TestCase):
    def test_cyclic_fragments_keep_live_slots_without_thrashing(self):
        for operation, payload, name in (
                ('R=R+Eval(T[I%17]);', 'A+B', 'parse_expression'),
                ('Execute(T[I%17]);', 'R=R+A+B;', 'parse_fragment')):
            with self.subTest(operation=operation):
                vm = Interpreter()
                self.addCleanup(vm.close)
                vm.variables['t'] = [payload + ' ' * i for i in range(17)]
                plan = vm.prepare('A=1;B=2;R=0;For I=0 To 999 Do ' + operation + 'EndDo;R;')
                with patch.object(parser, name, wraps=getattr(parser, name)) as parse:
                    self.assertEqual(vm.execute_prepared(plan), 3000)
                self.assertLess(parse.call_count, 200)

    def test_owned_source_uses_bounded_separate_eval_and_execute_caches(self):
        from test_configuration_source_runtime import source
        from yadinassi.configuration.configuration_source_runtime import SourceApplication

        output = []
        app = SourceApplication(source(b'''Procedure OnStart()
A=1;B=2;T=New Array;U=New Array;P="";
For J=1 To 17 Do P=P+" ";T.Add("A+B"+P);U.Add("R=R+A+B;"+P);EndDo;
R=0;
For I=0 To 199 Do R=R+Eval(T[I%17]);Execute(U[I%17]);EndDo;
If R=1200 Then Message("correct");EndIf;
EndProcedure'''), output=output.append)
        self.addCleanup(app.close)
        with patch.object(parser, 'parse_expression', wraps=parser.parse_expression) as evaluate, \
                patch.object(parser, 'parse_fragment', wraps=parser.parse_fragment) as execute:
            app.start()
        self.assertEqual(output, ['correct'])
        self.assertLess(evaluate.call_count, 64)
        self.assertLess(execute.call_count, 64)

    def test_equivalent_expressions_keep_distinct_diagnostics_on_hit(self):
        output = []
        vm = Interpreter(output=output.append)
        self.addCleanup(vm.close)
        vm.variables['expressions'] = ['1/0', '\n1/0', '    1/0', '1/0', '\n1/0']
        vm.execute('For Each X In Expressions Do '
                   'Try Eval(X);Except Message(ErrorDescription());EndTry;EndDo;')
        self.assertEqual([part.split(':')[:3] for part in output], [
            ['<Вычислить>', str(line), str(column)]
            for line, column in ((1, 2), (2, 2), (1, 6), (1, 2), (2, 2))
        ])
