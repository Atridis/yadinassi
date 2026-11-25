"""Direct immutable namespaces, without legacy name or routine dispatch."""
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.direct.python_direct_names import NAMES
from yadinassi.collections.search_directions import BSLSearchDirections, SEARCH_DIRECTIONS


class DirectSystemNamesTests(unittest.TestCase):
    def test_all_aliases_preserve_canonical_identity(self):
        vm = Interpreter()
        for alias, value in NAMES.items():
            with self.subTest(alias=alias):
                self.assertIs(vm.execute(alias.swapcase()), value)

    def test_routines_and_prepared_execution_without_legacy_dispatch(self):
        vm = Interpreter()
        plan = vm.prepare('Function Read() Return Chars.LF; EndFunction R=Read(); S=StrFind("aba", "a", SearchDirection.FromEnd); N=Round(1.5,0,RoundMode.Round15as10);')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], '\n')
        self.assertEqual(vm.variables['s'], 3)
        self.assertEqual(vm.variables['n'], 1)

    def test_known_iterators_and_public_index(self):
        vm = Interpreter()
        vm.execute('N=0; For Each V In SearchDirection Do N=N+1; EndDo; T=Chars["Таб"];')
        self.assertEqual(vm.variables['n'], 2)
        self.assertEqual(vm.variables['t'], '\t')

    def test_readonly_and_no_reflection(self):
        for source in ('Chars.LF="bad";', 'Chars["LF"]="bad";', 'Chars.__class__', 'SearchDirection.Get()', 'For Each V In Chars Do EndDo;'):
            with self.subTest(source=source), self.assertRaises((BSLRuntimeError, BoundaryViolation)):
                Interpreter().execute(source)
        self.assertEqual(Interpreter().execute('Chars.LF'), '\n')

    def test_namespace_rebinding_is_explicitly_unsupported(self):
        for source in ('Chars=1;', 'Var Chars; Chars=1;',
                       'Function Read() Chars=1; Return Chars; EndFunction R=Read();',
                       'Function Chars() Return 1; EndFunction R=Chars();'):
            with self.subTest(source=source), self.assertRaises((BSLRuntimeError, PythonDirectUnsupported)):
                Interpreter().execute(source)

    def test_parameter_can_shadow_namespace(self):
        vm = Interpreter()
        vm.execute('Function Read(Val Chars) Return Chars; EndFunction R=Read("local");')
        self.assertEqual(vm.variables['r'], 'local')
        other = Interpreter()
        other.execute('Function Read() Var Chars; Chars=2; Return Chars; EndFunction R=Read();')
        self.assertEqual(other.variables['r'], 2)

    def test_namespace_lookalike_is_not_admitted(self):
        vm = Interpreter()
        vm.variables['candidate'] = BSLSearchDirections()
        with self.assertRaises(BoundaryViolation):
            vm.execute('candidate.FromBegin')
        vm.variables['candidate'] = SEARCH_DIRECTIONS
        self.assertIs(vm.execute('candidate.FromBegin'), SEARCH_DIRECTIONS.get_member('FromBegin'))

    def test_unchanged_regex_replay_completes_all_forty_cases(self):
        output = []
        vm = Interpreter(output.append)
        source = Path('integrational_tests/measurements/regex_family.bsl').read_text(encoding='utf-8')
        vm.execute(source)
        self.assertEqual(len(output), 42)  # Two controls, then RF-01..RF-40.
        for index,record in enumerate(output[2:],1):
            self.assertTrue(record.startswith(f'RF-{index:02}: [ok|'),record)
