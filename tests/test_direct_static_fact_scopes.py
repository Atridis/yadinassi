"""Static fact propagation must preserve branch intersections and loop scope."""

from contextlib import closing
import unittest

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_static_module import analyze
from yadinassi.syntax.parser import parse


class StaticFactScopeTests(unittest.TestCase):
    def test_nested_live_branches_merge_only_the_common_kind(self):
        common = """S=1;
If S>0 Then
    If S>1 Then Both=2; Else Both=3; EndIf;
    OnlyFirst=True;
Else
    Both=4;
EndIf;
"""
        for final, expected in (('Both;', True), ('OnlyFirst;', False)):
            with self.subTest(final=final):
                self.assertEqual(analyze(parse(common + final)) is not None, expected)
        mixed = 'S=1; If S>0 Then X=2; Else X="text"; EndIf; X;'
        implicit_else = 'S=1; If S>0 Then X=2; EndIf; X;'
        for source in (mixed, implicit_else):
            self.assertIsNone(analyze(parse(source)))

    def test_nested_loops_discard_new_facts_but_keep_existing_bindings(self):
        loops = (
            ('For I=1 To 1 Do', ''),
            ('For Each I In A Do', 'A=New Array; A.Add(1); '),
            ('While S<1 Do', ''),
        )
        for loop, setup in loops:
            source = (setup + 'S=0; ' + loop + ' ' +
                      'If S=0 Then Inner=1; Else Inner=2; EndIf; '
                      'S=S+Inner; EndDo; ')
            with self.subTest(loop=loop):
                self.assertIsNotNone(analyze(parse(source + 'S;')))
                self.assertIsNone(analyze(parse(source + 'Inner;')))
                with closing(Interpreter()) as vm:
                    self.assertEqual(vm.execute_prepared(vm.prepare(source + 'S;')), 1)

    def test_for_and_foreach_counter_fact_visibility_are_distinct(self):
        for_control = 'For I=1 To 1 Do EndDo; I;'
        foreach_control = 'A=New Array; A.Add(1); For Each I In A Do EndDo; I;'
        self.assertIsNotNone(analyze(parse(for_control)))
        self.assertIsNone(analyze(parse(foreach_control)))
        conflicting = (
            'I="shadow"; For I=1 To 1 Do EndDo; I;',
            'I="shadow"; A=New Array; A.Add(1); For Each I In A Do EndDo; I;',
        )
        for source in conflicting:
            with self.subTest(source=source):
                self.assertIsNone(analyze(parse(source)))

    def test_reachability_and_prefix_deopt_do_not_export_a_kind_conflict(self):
        source = 'X=5; If False Then x="shadow"; Else X=6; EndIf; X;'
        program = parse(source)
        self.assertIsNone(analyze(program, literal_reachability=False))
        self.assertIsNotNone(analyze(program, literal_reachability=True))
        conflicting = parse('X=5; While X>0 Do NewLocal=1; x="shadow"; EndDo; X;')
        self.assertIsNone(analyze(conflicting))
        prefix = analyze(conflicting, scalar_prefix=True)
        self.assertEqual(prefix, {id(conflicting[0].value): 'number'})
        routine = parse('Function F(Val N) If N>0 Then Return 1; EndIf; Return 0; EndFunction F(1);')
        self.assertIsNone(analyze(routine, module_declarations=True))

    def test_existing_opaque_names_do_not_become_proven_from_nested_writes(self):
        source = 'S=1; If S>0 Then GlobalName=2; Else GlobalName=3; EndIf; GlobalName;'
        self.assertIsNotNone(analyze(parse(source)))
        self.assertIsNone(analyze(parse(source), opaque_names=('globalname',)))
