"""Plain client frames use local liveness without relaxing host effect guards."""
from collections import Counter
import sys
import unittest

from test_configuration_source_runtime import source
from test_python_direct_source import common_module
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_source import SourceBoundary


class SourceClientRoutineScopeTests(unittest.TestCase):
    def make(self, *, allow_extensions=False, output=print):
        extra = common_module(b"""
Function Increment(Val X) Return X+1; EndFunction
Function Work(Val N) Export
    X=0; For I=1 To N Do X=Increment(X); EndDo; Return X;
EndFunction
Procedure Say() Export Message("body"); Message("unreachable"); EndProcedure
""")
        app = SourceApplication(source(extra=extra), allow_extensions=allow_extensions, output=output)
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        return app

    def count_frame_checks(self, vm, n):
        code = f'R=Helpers.Work({n});'
        vm.execute(code)
        counts = Counter()
        filename = SourceBoundary._check.__code__.co_filename
        def trace(frame, event, _arg):
            if (event == 'call' and frame.f_code.co_filename == filename
                    and frame.f_code.co_name in ('_check', '_check_local_lifetime')):
                caller = frame.f_back
                if caller.f_code.co_name == '_check_loop':
                    caller = caller.f_back
                if caller.f_code.co_name == 'routine_scope':
                    counts[frame.f_code.co_name] += 1
        original = sys.getprofile()
        sys.setprofile(trace)
        try:
            vm.execute(code)
        finally:
            sys.setprofile(original)
        self.assertEqual(vm.variables['r'], n)
        return counts

    def test_nested_client_common_uses_local_liveness_at_routine_frames(self):
        vm = self.make().interpreter
        self.assertEqual(self.count_frame_checks(vm, 1), {'_check_local_lifetime': 4})
        self.assertEqual(self.count_frame_checks(vm, 32), {'_check_local_lifetime': 66})

    def test_explicit_extension_frames_still_use_full_checks(self):
        vm = self.make(allow_extensions=True).interpreter
        self.assertEqual(self.count_frame_checks(vm, 1), {'_check': 4})

    def test_output_callback_cannot_leave_live_code_under_stale_scope(self):
        out = []
        def output(value):
            out.append(value)
            if value == 'body':
                app.interpreter._family_generation += 1
        app = self.make(output=output)
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('Helpers.Say(); Message("later");')
        self.assertEqual(out, ['body'])
