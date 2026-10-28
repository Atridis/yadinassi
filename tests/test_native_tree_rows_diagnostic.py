"""Temporary fail-only Rows observables; no native identity/LoadColumn claim."""
from pathlib import Path
import itertools
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRowCollection
from yadinassi import runtime

ROOT = Path(__file__).resolve().parents[1]
START = '// Begin isolated Rows view diagnostic (fail-only; no LoadColumn calls).\n'
END = '// End isolated Rows view diagnostic.\n\n'


def source():
    return (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')


def helpers():
    return START + source().split(START, 1)[1].split(END, 1)[0] + END


def calls():
    text = source(); start = '// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\n'
    end = '// End bounded ValueTree LoadColumn observations.\n'
    return start + text.split(start, 1)[1].split(end, 1)[0] + end


class RowsDiagnosticTests(unittest.TestCase):
    def vm(self, helper=None):
        output = []; vm = Interpreter(output.append)
        vm.execute('Procedure Показать(Label, Value) Message(Label + ": [" + Value + "]"); EndProcedure;'
                   + (helpers() if helper is None else helper))
        return vm, output

    def test_actual_host_observables_and_no_loadcolumn_dispatch(self):
        vm, output = self.vm(); original = BSLValueTreeRowCollection.get_method
        def checked(receiver, name):
            self.assertNotIn(name.casefold(), ('loadcolumn', 'загрузитьколонку'))
            return original(receiver, name)
        with mock.patch.object(BSLValueTreeRowCollection, 'get_method', checked):
            self.assertEqual(vm.execute('TreeRowsDiagnosticExperiment()'), 'FFTT')
            vm.execute(calls())
        self.assertEqual(len(output), 45)
        self.assertEqual(sum(len(line.encode('utf-16-le'))//2 for line in output), 3285)
        self.assertTrue(all('1?D0FFTT!' in line for line in output))
        # The ordinary action helper need not even exist in this interpreter.
        self.assertNotIn('treeloadprobe', vm.variables)

    def test_four_independent_fixtures_preserve_unrelated_tree(self):
        vm, _ = self.vm()
        vm.execute('Existing = New ValueTree; Existing.Columns.Add("Marker"); Existing.Rows.Add().Marker = 91;')
        existing = vm.variables['existing']; created = []; original = BSLValueTree.__init__
        def initialize(tree):
            original(tree); created.append(tree)
        with mock.patch.object(BSLValueTree, '__init__', initialize):
            self.assertEqual(vm.execute('TreeRowsDiagnosticExperiment()'), 'FFTT')
        self.assertEqual(len(created), 6)
        self.assertEqual(len({id(tree) for tree in created}), 6)
        self.assertEqual([int(tree.rows.count()) for tree in created], [2,0,2,0,1,1])
        self.assertEqual(int(existing.rows.count()), 1)
        self.assertEqual(int(existing.rows.items[0].get_member('Marker')), 91)

    def test_comparison_false_true_and_exception_are_distinct(self):
        real = runtime.equal
        for value, expected in ((False, 'T'), (True, 'F'), (None, 'E')):
            def equality(a, b):
                if isinstance(a, BSLValueTreeRowCollection) and isinstance(b, BSLValueTreeRowCollection):
                    if value is None: raise ValueError('synthetic comparison error')
                    return value
                return real(a, b)
            vm, _ = self.vm()
            with mock.patch.object(runtime, 'equal', equality):
                self.assertEqual(vm.execute('TreeRowsDiagnosticPart(1)'), expected)
                self.assertEqual(vm.execute('TreeRowsDiagnosticPart(2)'), expected)

    def test_fresh_wrappers_and_copied_containers_are_not_conflated(self):
        original = BSLValueTree.get_member
        for shared, expected in ((True, 'TFTT'), (False, 'TFFF')):
            def getter(tree, name):
                if name.casefold() in ('rows', 'строки'):
                    view = BSLValueTreeRowCollection(tree)
                    view.items = tree.rows.items if shared else list(tree.rows.items)
                    return view
                return original(tree, name)
            vm, _ = self.vm()
            with mock.patch.object(BSLValueTree, 'get_member', getter):
                self.assertEqual(vm.execute('TreeRowsDiagnosticExperiment()'), expected)

    def test_mutation_errors_are_e_and_setup_errors_hard_fail(self):
        vm, _ = self.vm()
        with mock.patch.object(BSLValueTreeRowCollection, 'add', side_effect=ValueError('synthetic add error')):
            self.assertEqual(vm.execute('TreeRowsDiagnosticPart(3)'), 'E')
            self.assertEqual(vm.execute('TreeRowsDiagnosticPart(4)'), 'E')
            self.assertEqual(vm.execute('TreeRowsDiagnosticPart(1)'), '?')
            self.assertEqual(vm.execute('TreeRowsDiagnosticExperiment()'), '?')
        with mock.patch.object(BSLValueTree, '__init__', side_effect=ValueError('synthetic setup error')):
            self.assertEqual(vm.execute('TreeRowsDiagnosticExperiment()'), '?')
        for value in ('"?"', '""', 'Undefined', '17', '"tFTT"', '"TFTTX"'):
            self.assertEqual(vm.execute(f'TreeRowsDiagnosticProbe(1, {value})'), '1?O0--!' + '.'*58)

    def test_all_81_vectors_fixed_packet_and_single_four_part_experiment(self):
        text = helpers(); begin = text.index('Функция TreeRowsDiagnosticPart(')
        end = text.index('КонецФункции', begin) + len('КонецФункции')
        vm, output = self.vm(text[:begin] + text[end:])
        observed = []
        def part(number):
            observed.append(int(number)); return vector[int(number)-1]
        vm.register_function('TreeRowsDiagnosticPart', part)
        for parts in itertools.product('TFE', repeat=4):
            vector = ''.join(parts); output.clear(); observed.clear()
            vm.execute(calls())
            self.assertEqual(observed, [1,2,3,4])
            self.assertEqual(len(output), 45)
            for i,line in enumerate(output,1):
                self.assertEqual(line, f'TL{i:02d}: [1?D0{vector}!' + '.'*56 + ']')
            self.assertEqual(sum(len(line) for line in output),3285)


if __name__ == '__main__': unittest.main()
