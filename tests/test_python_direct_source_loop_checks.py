"""Local source checks do not remove authority boundaries or loop metering."""
import sys
import unittest
from unittest.mock import patch

from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_source import SourceBoundary
from tests.test_configuration_source_runtime import source


class SourceLoopChecksTests(unittest.TestCase):
    def owner(self, *, extensions=False):
        app = SourceApplication(source(), allow_extensions=extensions)
        self.addCleanup(app.close)
        app.start()
        return app.interpreter

    def profile(self, owner, text):
        count = 0
        full = SourceBoundary._check.__code__

        def profile(frame, event, arg):
            nonlocal count
            if event == 'call' and frame.f_code is full:
                count += 1

        original = sys.getprofile()
        try:
            sys.setprofile(profile)
            owner.execute(text)
        finally:
            sys.setprofile(original)
        return count

    def test_root_plain_loop_uses_lease_checkpoints_only(self):
        text = 'Total=0;For I=1 To 128 Do Total=Total+I;EndDo;'
        for enabled in (False, True):
            with self.subTest(extensions=enabled):
                owner = self.owner(extensions=enabled)
                self.assertEqual(self.profile(owner, text), 131 if enabled else 2)
                self.assertEqual(owner.variables['total'], 8256)

    def test_dynamic_unit_keeps_full_loop_checkpoints(self):
        owner = self.owner()
        text = 'X=0;Execute "For I=1 To 8 Do X=X+I; EndDo;";'
        count = self.profile(owner, text)
        self.assertGreaterEqual(count, 11)
        self.assertEqual(owner.variables['x'], 36)

    def test_revocation_close_and_metering_stop_before_next_body(self):
        original = SourceBoundary.checkpoint

        for mode in ('revoke', 'close', 'budget'):
            with self.subTest(mode=mode):
                owner = self.owner()
                seen = []

                def checkpoint(context):
                    seen.append(context.loop_backedges)
                    if mode == 'budget':
                        context.loop_budget = 2
                    elif len(seen) == 3:
                        if mode == 'revoke':
                            context.revoke()
                        else:
                            owner.close()
                    return original(context)

                with patch.object(SourceBoundary, 'checkpoint', checkpoint):
                    with self.assertRaises(BoundaryViolation):
                        owner.execute('Total=0;For I=1 To 128 Do Total=Total+I;EndDo;')
                self.assertEqual(seen, [0, 1, 2])
                if mode != 'close':
                    self.assertEqual(owner.variables['total'], 3)

    def test_builtin_host_effect_still_checks_lifetime_on_return(self):
        seen = []
        def output(text):
            seen.append(text)
            app.interpreter.close()
        app = SourceApplication(source(), output=output)
        self.addCleanup(app.close)
        app.start()
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('For I=1 To 2 Do Message("effect"); EndDo;')
        self.assertEqual(seen, ['effect'])
