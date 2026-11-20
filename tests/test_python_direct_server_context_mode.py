"""Standalone server/dual calls audit only the boundaries they actually cross."""
from cProfile import Profile
from pathlib import Path
from pstats import Stats
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_server import ServerBoundary


class DirectServerContextModeTests(unittest.TestCase):
    def run_profile(self, role, body, *, allow_extensions=False):
        vm = Interpreter(allow_extensions=allow_extensions)
        self.addCleanup(vm.close)
        vm.execute(f'&{role}\nFunction F(Val X) {body} EndFunction')
        plan = vm.prepare('R=F(1);')
        profile = Profile()
        profile.runcall(vm.execute_prepared, plan)
        counts = {Path(path).name: result[0] for (path, _, name), result in Stats(profile).stats.items()
                  if name == '_check' and Path(path).name in ('python_direct.py', 'python_direct_server.py')}
        self.assertEqual(vm.execution_context, 'client')
        self.assertTrue(vm._has_module_context)
        return vm.variables['r'], counts

    def test_dual_client_runs_same_side_without_full_audit(self):
        result, counts = self.run_profile('AtClientAtServerNoContext',
            'For I=1 To 128 Do X=X+StrLen("abc");EndDo;Return X;')
        self.assertEqual(result, 385)
        self.assertEqual(counts, {})

    def test_server_loop_does_not_add_audits_to_real_crossing(self):
        _, crossing = self.run_profile('AtServer', 'Return X;')
        result, counts = self.run_profile('AtServer', 'For I=1 To 128 Do X=X+StrLen("abc");EndDo;Return X;')
        self.assertEqual(result, 385)
        self.assertEqual(counts, crossing)
        self.assertGreater(crossing['python_direct.py'], 0)
        self.assertGreater(crossing['python_direct_server.py'], 0)

    def test_dynamic_and_explicit_extensions_stay_strict(self):
        baseline = self.run_profile('AtServer', 'Return X;')[1]['python_direct_server.py']
        result, dynamic = self.run_profile('AtServer', 'Return Eval("1+2");')
        self.assertEqual(result, 3)
        self.assertGreater(dynamic['python_direct_server.py'], baseline)
        result, strict = self.run_profile('AtServer', 'Return StrLen("abc");', allow_extensions=True)
        self.assertEqual(result, 3)
        self.assertGreater(strict['python_direct_server.py'], baseline)

    def test_dual_stops_after_actual_file_io_closes_owner(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('&AtClientAtServerNoContext\nFunction F()\nA=New BinaryData("file");Return 17;EndFunction')
        def close_owner(_path):
            vm.close()
            return b'data'
        with patch('yadinassi.streams.file_io._read_bytes', side_effect=close_owner):
            with self.assertRaises(BoundaryViolation):
                vm.execute('R=F();')
        self.assertNotIn('r', vm.variables)
        self.assertEqual(vm._module_context_stack, [True])

    def test_lean_server_checkpoint_still_meters(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        vm = Interpreter()
        self.addCleanup(vm.close)
        parent = make_boundary(vm)
        boundary = ServerBoundary(parent, side='client')
        boundary.loop_budget = 1
        boundary.enter()
        with patch.object(boundary, '_check', side_effect=AssertionError('full audit')):
            boundary.checkpoint()
            with self.assertRaisesRegex(BoundaryViolation, 'backedge budget exhausted'):
                boundary.checkpoint()
        self.assertEqual(boundary.loop_backedges, 1)
