"""Pure BSL operations stay native before a later host boundary."""
import ast
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext


def source(iterations, steps):
    arithmetic = ''.join(f'X=X*3+I-{k};' for k in range(steps))
    return (f'R=0;For I=1 To {iterations} Do X=I;{arithmetic}'
            'If I%2=0 Then R=R+X*2;Else R=R-X*3;EndIf;EndDo;')


def reference(iterations, steps):
    result = Decimal(0)
    for index in range(1, iterations + 1):
        i = Decimal(index)
        x = i
        for k in range(steps):
            x = x * 3 + i - k
        if i % 2 == 0:
            result += x * 2
        else:
            result -= x * 3
    return result


class DirectScalarPrefixTests(TestCase):
    def vm(self, *, allow_extensions=False):
        vm = Interpreter(allow_extensions=allow_extensions)
        self.addCleanup(vm.close)
        return vm

    def test_literal_sum_in_all_three_source_shapes(self):
        expected = '_constants[0] + _constants[1] + _constants[2] + _constants[3]'
        for text in ('1+2+3+5', 'R=1+2+3+5;', 'R=1+2+3+5;Host();'):
            with self.subTest(text=text):
                vm = self.vm(allow_extensions=True)
                observed = []
                vm.register_function('Host', lambda: observed.append(vm.variables['r']))
                prepared = vm.prepare(text)
                code = prepared._plan.generated_source
                self.assertIn(expected, code)
                self.assertNotIn('_native_add', code)
                self.assertNotIn('_concatenate', code)
                result = vm.execute_prepared(prepared)
                self.assertEqual(result if text[0] == '1' else vm.variables['r'], Decimal(11))
                if 'Host' in text:
                    self.assertEqual(observed, [Decimal(11)])

    def test_trailing_host_does_not_put_checks_or_truth_wrappers_in_loop(self):
        for steps in (2, 6, 12):
            for host_call in ('', 'Host();'):
                with self.subTest(steps=steps, host=bool(host_call)):
                    vm = self.vm(allow_extensions=True)
                    published = []
                    vm.register_function('Host', lambda: published.append(vm.variables['r']))
                    prepared = vm.prepare(source(50, steps) + host_call)
                    tree = ast.parse(prepared._plan.generated_source)
                    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
                    self.assertEqual(len(loops), 1)
                    loop = ast.unparse(loops[0])
                    for unexpected in ('_context.', '_truth(', '_equal(', '_native_add('):
                        self.assertNotIn(unexpected, loop)
                    vm.execute_prepared(prepared)
                    expected = reference(50, steps)
                    self.assertEqual(vm.variables['r'], expected)
                    self.assertEqual(published, [expected] if host_call else [])

    def test_check_count_with_host_does_not_grow_with_work(self):
        calls = []
        check = BoundaryContext._check

        def counted(owner):
            check(owner)
            calls.append(None)

        counts = []
        for iterations, steps in ((4, 2), (40, 12)):
            vm = self.vm(allow_extensions=True)
            vm.register_function('Host', lambda: None)
            prepared = vm.prepare(source(iterations, steps) + 'Host();')
            before = len(calls)
            with patch.object(BoundaryContext, '_check', counted):
                vm.execute_prepared(prepared)
            counts.append(len(calls) - before)
        self.assertEqual(*counts)

    def test_types_after_host_are_not_inferred_from_prefix(self):
        vm = self.vm(allow_extensions=True)
        vm.register_function('Host', lambda: vm.variables.update(r='host'))
        vm.execute('R=1+2+3+5;Host();T=R+"!";')
        self.assertEqual(vm.variables['t'], 'host!')

    def test_unproven_suffix_preserves_dynamic_comparison(self):
        vm = self.vm(allow_extensions=True)
        vm.register_function('Host', lambda: vm.variables.update(r=True, v=1))
        vm.execute('R=1+2+3+5;Host();T=(R=V);')
        self.assertIs(vm.variables['t'], False)
