"""Retired visitor entrypoints cannot revive evaluation or bypass direct admission."""
from contextlib import closing
import unittest
from yadinassi import Interpreter
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse


class ReferenceVisitBoundaryTests(unittest.TestCase):
    def test_retired_visitors_reject_before_effects(self):
        with closing(Interpreter()) as vm:
            node=parse('R=1;')[0]
            for invoke in (lambda:vm.visit(node),lambda:vm._visit(node),lambda:vm.block([node])):
                with self.assertRaises(PythonDirectUnsupported):invoke()
            self.assertNotIn('r',vm.variables)

    def test_custom_visitor_does_not_replace_direct_execution(self):
        with closing(Interpreter()) as vm:
            seen=[]
            vm._visit=lambda node:seen.append(node)
            with self.assertRaises(PythonDirectUnsupported):vm.execute('R=1;')
            self.assertEqual(seen,[])
            self.assertNotIn('r',vm.variables)

    def test_direct_execute_and_prepared_remain_public_boundaries(self):
        for prepared in (False,True):
            with closing(Interpreter()) as vm:
                source='Function F(Val X) Return X+1;EndFunction;R=F(41);'
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual(vm.variables['r'],42)
