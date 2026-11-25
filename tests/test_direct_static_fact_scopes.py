"""Branch and loop semantics tested through the single BSL entry point."""
from contextlib import closing
import unittest

from yadinassi import Interpreter


class StaticFactScopeTests(unittest.TestCase):
    def test_nested_live_branches_publish_the_executed_assignments(self):
        common = """S=1;
If S>0 Then
    If S>1 Then Both=2; Else Both=3; EndIf;
    OnlyFirst=True;
Else
    Both=4;
EndIf;
"""
        with closing(Interpreter()) as vm:
            vm.execute(common)
            self.assertEqual(vm.variables['both'], 3)
            self.assertIs(vm.variables['onlyfirst'], True)

    def test_nested_loops_keep_existing_bindings_after_exit(self):
        loops = (
            ('For I=1 To 1 Do', ''),
            ('For Each I In A Do', 'A=New Array; A.Add(1); '),
            ('While S<1 Do', ''),
        )
        for loop, setup in loops:
            source = (setup + 'S=0; ' + loop + ' ' +
                      'If S=0 Then Inner=1; Else Inner=2; EndIf; '
                      'S=S+Inner; EndDo; S;')
            with self.subTest(loop=loop), closing(Interpreter()) as vm:
                self.assertEqual(vm.execute_prepared(vm.prepare(source)), 1)

    def test_unreached_string_assignment_does_not_change_the_value(self):
        with closing(Interpreter()) as vm:
            self.assertEqual(vm.execute('X=5; If False Then X="shadow"; Else X=6; EndIf; X;'), 6)
