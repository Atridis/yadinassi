"""Temporary fail-only Rows observables; no native identity/LoadColumn claim."""
from pathlib import Path
import itertools
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.collections.value_trees import BSLValueTree, BSLValueTreeRowCollection
from direct_equality_fixture import direct_equality
from scripts import native_historical_replay as replay

ROOT = Path(__file__).resolve().parents[1]
START = '// Begin isolated Rows view diagnostic (fail-only; no LoadColumn calls).\n'
END = '// End isolated Rows view diagnostic.\n\n'

def source():
    text = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
    # These are exact historical Rows experiment tests, not current Columns measurements.
    return replay.without_tree_columns_diagnostic(text)

def helpers():
    return START + source().split(START, 1)[1].split(END, 1)[0] + END

def calls():
    text = source(); start = '// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\n'
    end = '// End bounded ValueTree LoadColumn observations.\n'
    return start + text.split(start, 1)[1].split(end, 1)[0] + end

class RowsDiagnosticTests(unittest.TestCase):
    def vm(self, helper=None, *, backend=None, allow_extensions=False):
        output = []; vm = Interpreter(output.append, allow_extensions=allow_extensions, execution_backend=backend)
        vm.execute('Procedure Показать(Label, Value) Message(Label + ": [" + Value + "]"); EndProcedure;'
                   + (helpers() if helper is None else helper))
        return vm, output

    def test_comparison_false_true_and_exception_are_distinct(self):
        # Instrument the actual direct compiler binding, not retired visitors.
        with direct_equality() as service:
            backend = 'python-direct'
            real = service.equal
            for value, expected in ((False, 'T'), (True, 'F'), (None, 'E')):
                comparisons = []
                def equality(a, b):
                    if isinstance(a, BSLValueTreeRowCollection) and isinstance(b, BSLValueTreeRowCollection):
                        comparisons.append((a, b))
                        if value is None: raise ValueError('synthetic comparison error')
                        return value
                    return real(a, b)
                with self.subTest(backend=backend, value=value):
                    vm, _ = self.vm(backend=backend)
                    with mock.patch.object(service, 'equal', equality):
                        self.assertEqual(vm.execute('TreeRowsDiagnosticPart(1)'), expected)
                        self.assertEqual(vm.execute('TreeRowsDiagnosticPart(2)'), expected)
                    self.assertEqual(len(comparisons), 2)

    def test_all_81_vectors_fixed_packet_and_single_four_part_experiment(self):
        text = helpers(); begin = text.index('Функция TreeRowsDiagnosticPart(')
        end = text.index('КонецФункции', begin) + len('КонецФункции')
        vm, output = self.vm(text[:begin] + text[end:], allow_extensions=True)
        observed = []
        def part(number):
            observed.append(int(number)); return vector[int(number)-1]
        vm.register_function('TreeRowsDiagnosticPart', part)
        self.addCleanup(vm.close)
        # The packet body is unchanged; only the four injected observations vary.
        plan = vm.prepare(calls())
        for parts in itertools.product('TFE', repeat=4):
            vector = ''.join(parts); output.clear(); observed.clear()
            vm.execute_prepared(plan)
            self.assertEqual(observed, [1,2,3,4])
            self.assertEqual(len(output), 45)
            for i,line in enumerate(output,1):
                self.assertEqual(line, f'TL{i:02d}: [1?D0{vector}!' + '.'*56 + ']')
            self.assertEqual(sum(len(line) for line in output),3285)

    def test_direct_actual_observation(self):
        vm, output = self.vm()
        self.addCleanup(vm.close)
        self.assertEqual(vm.execute('TreeRowsDiagnosticExperiment()'), 'FFTT')
        vm.execute(calls())
        self.assertEqual(len(output),45)
        self.assertTrue(all('1?D0FFTT!' in line for line in output))

    def test_class_hook_changes_fail_closed_not_synthetic_observations(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        vm, _ = self.vm()
        self.addCleanup(vm.close)
        with mock.patch.object(BSLValueTree, '__init__', side_effect=AssertionError('must not run')) as hook:
            with self.assertRaisesRegex(BoundaryViolation,'ValueTree class hooks changed'):
                vm.execute('TreeRowsDiagnosticExperiment()')
            hook.assert_not_called()

if __name__ == '__main__': unittest.main()
