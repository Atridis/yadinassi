"""NoContext loops meter live execution without rechecking transport inventories."""
import sys
import unittest
from unittest.mock import patch

from tests import test_source_forms as forms
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.source import python_direct_source_nocontext as nocontext
from yadinassi.forms.form_runtime import FormLimitError


class SourceNoContextLoopTests(unittest.TestCase):
    app = forms.SourceNoContextTests.app
    controller = forms.SourceNoContextTests.controller
    run_command = forms.SourceNoContextTests.run_command

    def test_pure_loop_does_not_add_full_checks(self):
        full_codes = {nocontext._check.__code__, nocontext.NoContextBoundary._check.__code__}
        for same_server in (False, True):
            counts = []
            for count in (0, 128):
                with self.subTest(same_server=same_server, count=count):
                    controller = self.controller(
                        f'R=0;For I=1 To {count} Do R=R+I;EndDo;Return R;',
                        server_call=same_server)
                    calls = 0

                    def profile(frame, event, arg):
                        nonlocal calls
                        if event == 'call' and frame.f_code in full_codes:
                            calls += 1

                    original = sys.getprofile()
                    try:
                        sys.setprofile(profile)
                        result = self.run_command(controller)
                    finally:
                        sys.setprofile(original)
                    self.assertIsNone(result['error'])
                    # Remote form transport presents a scalar in the form
                    # attribute; same-server delivery may keep the number.
                    greeting = dict(controller.client.session.snapshot().attributes)['Greeting']
                    self.assertEqual(int(str(greeting).replace('\u00a0', '')), count*(count+1)//2)
                    counts.append(calls)
            self.assertEqual(len(counts), 2)
            self.assertGreater(counts[0], 0)
            self.assertEqual(counts[0], counts[1])

    def test_shared_meter_counts_routine_entry_and_terminal_probe(self):
        for count in (99998, 99999):
            with self.subTest(count=count):
                controller = self.controller(f'For I=1 To {count} Do EndDo;Return 7;')
                server = controller.nocontext
                routine = server.prototype.server_routines['calculate']
                if count == 99998:
                    self.assertEqual(nocontext.invoke(server, routine, ['x']), 7)
                else:
                    with self.assertRaisesRegex(FormLimitError, 'Source NoContext execution limit'):
                        nocontext.invoke(server, routine, ['x'])

    def test_revoke_or_replace_budget_stops_before_loop_body(self):
        original = nocontext.NoContextBoundary.checkpoint
        for changed in ('revoke', 'budget'):
            with self.subTest(changed=changed):
                controller = self.controller('For I=1 To 2 Do Message("effect");EndDo;')
                server = controller.nocontext
                routine = server.prototype.server_routines['calculate']
                effects = []

                def checkpoint(context):
                    if changed == 'revoke':
                        context.revoke()
                    else:
                        context.vm._source_call_budget = [0]
                    return original(context)

                with patch.object(nocontext.NoContextBoundary, 'checkpoint', checkpoint):
                    with self.assertRaises(BoundaryViolation):
                        nocontext.invoke(server, routine, ['x'], output=effects.append)
                self.assertEqual(effects, [])
