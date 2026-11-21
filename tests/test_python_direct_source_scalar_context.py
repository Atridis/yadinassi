"""Pure SourceApplication work does not multiply full context validation."""
from collections import Counter
from pathlib import Path
import sys
import unittest

from test_configuration_source_runtime import source
from test_python_direct_source import common_module
from test_source_server_call import configuration
import test_source_server_call as server_fixture
from yadinassi.configuration.configuration_source_runtime import SourceApplication


class SourceScalarContextTests(unittest.TestCase):
    def make(self, config, *, allow_extensions=False):
        app = SourceApplication(config, output=lambda _: None, allow_extensions=allow_extensions)
        self.addCleanup(app.close)
        app.start()
        return app.interpreter

    def count(self, vm, text):
        # Compare execution, not first-use module creation.
        vm.execute(text)
        counts = Counter()
        def trace(frame, event, _arg):
            if event == 'call' and Path(frame.f_code.co_filename).name == 'python_direct_source.py':
                name = frame.f_code.co_name
                if name in ('_check', '_check_loop'):
                    counts[(name, frame.f_locals['self'].side)] += 1
        previous = sys.getprofile()
        sys.setprofile(trace)
        try:
            vm.execute(text)
        finally:
            sys.setprofile(previous)
        return (counts[('_check', 'client')], counts[('_check', 'server')]), counts

    def test_real_server_crossing_constant_for_arithmetic_and_pure_builtin_loops(self):
        for body in ('Result=3;', 'Result=StrLen("a😀");'):
            with self.subTest(body=body):
                vm = self.make(configuration('', 'Function Measure(Val N) Export '
                    f'For I=1 To N Do {body} EndDo; Return Result; EndFunction'))
                first, small = self.count(vm, 'R=ServerAPI.Measure(1);')
                self.assertEqual(vm.variables['r'], 3)
                many, large = self.count(vm, 'R=ServerAPI.Measure(128);')
                self.assertEqual(vm.variables['r'], 3)
                self.assertTrue(all(x > 0 for x in first), first)
                self.assertEqual(first, many)
                self.assertEqual(large[('_check_loop', 'server')], small[('_check_loop', 'server')])

    def test_same_side_server_common_uses_own_crossing_context(self):
        conf = server_fixture.SourceServerCallTests().with_extra(configuration('',
            'Function Measure(Val N) Export Return Internal.Measure(N); EndFunction'),
            'Internal', 'Function Measure(Val N) Export '
            'For I=1 To N Do Result=СтрДлина("abc"); EndDo;'
            'Return Result; EndFunction', server_call=False)
        vm = self.make(conf)
        small, _ = self.count(vm, 'R=ServerAPI.Measure(1);')
        large, _ = self.count(vm, 'R=ServerAPI.Measure(128);')
        self.assertEqual(vm.variables['r'], 3)
        self.assertEqual(small, large)

    def test_client_text_aliases_and_coercion_preserve_result(self):
        conf = source(b'', common_module(b'Function Measure(Val N) Export '
            b'For I=1 To N Do Result=StrLen(Upper(TrimAll(" abc "))); EndDo;'
            b'Return Result; EndFunction'))
        vm = self.make(conf)
        self.assertEqual(self.count(vm, 'R=Helpers.Measure(1);')[0],
                         self.count(vm, 'R=Helpers.Measure(128);')[0])
        self.assertEqual(vm.variables['r'], 3)
        vm.execute('R=StrLen(123);')
        self.assertEqual(vm.variables['r'], 3)

    def test_opted_in_client_builtin_override_stays_strict(self):
        vm = self.make(source(b''), allow_extensions=True)
        vm.register_function('StrLen', lambda value: 9)
        full, _ = self.count(vm, 'R=StrLen("abc");')
        self.assertEqual(vm.variables['r'], 9)
        self.assertGreater(full[0], 0)

    def test_argument_evaluation_can_still_install_a_denying_policy(self):
        from unittest.mock import patch
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        from yadinassi.execution.direct.python_direct_source import SourceBoundary
        app = SourceApplication(source(b''))
        self.addCleanup(app.close)
        app.start()
        boundary = []
        calls = []
        def policy(operation, name):
            calls.append((operation, name))
            return False
        def install(_message):
            boundary[0].policy = policy
        app.interpreter.output = install
        app.interpreter.execute('Function Argument() Message("bind already happened");Return "abc";EndFunction')
        resolve = SourceBoundary.resolve_service
        def capture(context, name, *args, **kwargs):
            bound = resolve(context, name, *args, **kwargs)
            if name.casefold() == 'strlen': boundary.append(context)
            return bound
        with patch.object(SourceBoundary, 'resolve_service', capture):
            with self.assertRaisesRegex(BoundaryViolation, 'service policy denied: strlen'):
                app.interpreter.execute('R=StrLen(Argument());')
        self.assertEqual(calls, [('call', 'strlen')])
        self.assertNotIn('r', app.interpreter.variables)
