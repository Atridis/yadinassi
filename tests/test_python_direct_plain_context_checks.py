"""Count actual context gates, including gates hidden behind direct dispatch."""
import cProfile
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import make_boundary


def checks(profile):
    return sum(entry.callcount for entry in profile.getstats()
               if not isinstance(entry.code, str)
               and entry.code.co_name == '_check'
               and entry.code.co_filename == make_boundary.__code__.co_filename)


class PlainContextChecksTests(unittest.TestCase):
    def interpreter(self, **kwargs):
        vm = Interpreter(**kwargs)
        self.addCleanup(vm.close)
        return vm

    def test_context_checks_are_absent_in_plain_source_and_prepared_runs(self):
        cases = (
            ('R=0; For I=1 To 8 Do R=R+I; EndDo;', Decimal(36)),
            ('A=New Array; A.Add(StrLen("abc")); R=A[0];', Decimal(3)),
            ('R=Year(Date("20261231"));', Decimal(2026)),
            ('A=New("Array"); R=A.Count();', Decimal(0)),
            ('R=0; Execute("R=3;"); R=R+Eval("1");', Decimal(4)),
            ('A=New Array; P=New FixedArray(A); R=P.Count();', Decimal(0)),
            ('A=New Map; P=New FixedMap(A); R=P.Count();', Decimal(0)),
            ('A=New Array; A.Add(1); P=New FixedArray(A); R=P.Find(1);', Decimal(0)),
            ('A=New NumberQualifiers(4,2); R=A.Digits;', Decimal(4)),
            ('A=New TextDocument; A.SetText("x"); R=A.GetText();', 'x'),
            ('J=New JSONWriter; J.SetString(); WriteJSON(J,7); R=J.Close();', '7'),
            ('J=New JSONReader; J.SetString("7"); R=ReadJSON(J); J.Close();', Decimal(7)),
            ('Procedure Inc(X) X=X+1; EndProcedure '
             'A=New Array; A.Add(0); A[0]=4; Inc(A[0]); R=A[0];', Decimal(5)),
            ('Procedure Inc(X) X=X+1; EndProcedure '
             'T=New ValueTable; T.Columns.Add("N"); Row=T.Add(); Row.N=4; '
             'Inc(Row.N); R=Row.N;', Decimal(5)),
        )
        for source, expected in cases:
            for prepared in (False, True):
                with self.subTest(source=source, prepared=prepared):
                    vm = self.interpreter()
                    p = cProfile.Profile()
                    if prepared:
                        plan = vm.prepare(source)
                        self.assertNotIn('._check(', plan._plan.generated_source)
                        p.runcall(vm.execute_prepared, plan)
                    else:
                        p.runcall(vm.execute, source)
                    self.assertEqual(vm.variables['r'], expected)
                    self.assertEqual(checks(p), 0)

    def test_persisted_bsl_function_keeps_the_light_context(self):
        vm = self.interpreter()
        vm.execute('Function Inc(Val X) Return X+1; EndFunction')
        p = cProfile.Profile()
        p.runcall(vm.execute, 'R=Inc(1);')
        self.assertEqual(vm.variables['r'], Decimal(2))
        self.assertEqual(checks(p), 0)

    def test_explicit_extensions_retain_context_checks(self):
        vm = self.interpreter(allow_extensions=True)
        vm.register_function('Increment', lambda value: value + 1)
        p = cProfile.Profile()
        p.runcall(vm.execute, 'R=Increment(1);')
        self.assertEqual(vm.variables['r'], Decimal(2))
        self.assertGreater(checks(p), 0)

    def test_plain_mode_still_stops_when_actual_file_io_closes_embedding(self):
        for prepared in (False, True):
            vm = self.interpreter()
            source = 'A=New BinaryData("file"); R=17;'
            def read_file(_path):
                vm.close()
                return b"file"
            with patch('yadinassi.streams.file_io._read_bytes', side_effect=read_file):
                with self.assertRaises(BoundaryViolation):
                    if prepared:
                        vm.execute_prepared(vm.prepare(source))
                    else:
                        vm.execute(source)
            self.assertNotIn('r', vm.variables)
