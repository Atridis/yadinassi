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

    def profile(self, owner, text, method=SourceBoundary._check):
        count = 0
        full = method.__code__

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

    def test_root_plain_loop_emits_no_checkpoints_without_extensions(self):
        text = 'Total=0;For I=1 To 128 Do Total=Total+I;EndDo;'
        for enabled in (False, True):
            with self.subTest(extensions=enabled):
                owner = self.owner(extensions=enabled)
                self.assertEqual(self.profile(owner, text), 131 if enabled else 0)
                self.assertEqual(self.profile(owner, text, SourceBoundary.checkpoint), 129 if enabled else 0)
                self.assertEqual(owner.variables['total'], 8256)

    def test_native_array_reads_and_append_do_not_use_host_audits(self):
        owner = self.owner()
        self.assertEqual(self.profile(owner, 'A=New Array; Total=0; '
            'For I=1 To 16 Do A.Add(I); Total=Total+A[I-1]+A.Get(I-1); EndDo; '
            'N=A.Count(); Last=A.UBound();'), 0)
        self.assertEqual(owner.variables['total'], 272)
        self.assertEqual(owner.variables['n'], 16)
        self.assertEqual(owner.variables['last'], 15)

    def test_warm_local_and_qualified_calls_do_not_repeat_full_audits(self):
        from test_python_direct_source import common_module

        config = source(b'', common_module(b'Function Inc(Val X) Export Return X+1; EndFunction'))
        app = SourceApplication(config)
        self.addCleanup(app.close)
        app.start()
        owner = app.interpreter
        owner.execute('Function Local(Val X) Return Helpers.Inc(X); EndFunction;')
        owner.execute('R=Local(0);')
        self.assertEqual(self.profile(owner, 'R=0;For I=1 To 128 Do R=Local(R); EndDo;'), 0)
        self.assertEqual(owner.variables['r'], 128)

    def test_server_chain_only_audits_the_real_crossing(self):
        from test_source_server_call import configuration, module
        from yadinassi.configuration.configuration_source import import_source

        config = configuration('', 'Function Answer(Val N) Export '
            'R=0;For I=1 To N Do R=Local(R);EndDo;Return R;EndFunction '
            'Function Local(Val X) Return Middle.Inc(X); EndFunction')
        files = {f.path: f.content for f in config.files}
        for number, name, body in (
                (3, 'Middle', 'Function Inc(Val X) Export Return Last.Inc(X); EndFunction'),
                (4, 'Last', 'Function Inc(Val X) Export Return X+1; EndFunction')):
            extra = module(name, body, server_call=False)
            path = 'CommonModules/' + name + '.xml'
            extra[path] = extra[path].replace(b'<CommonModule>',
                f'<CommonModule uuid="00000000-0000-0000-0000-{number:012}">'.encode())
            files.update(extra)
        app = SourceApplication(import_source(files))
        self.addCleanup(app.close)
        app.start()
        owner = app.interpreter
        owner.execute('R=ServerAPI.Answer(1);')
        crossing = self.profile(owner, 'R=ServerAPI.Answer(1);')
        self.assertGreater(crossing, 0)
        self.assertEqual(self.profile(owner, 'R=ServerAPI.Answer(128);'), crossing)
        self.assertEqual(self.profile(owner, 'R=ServerAPI.Answer(128);', SourceBoundary.checkpoint), 0)
        self.assertEqual(owner.variables['r'], 128)

    def test_host_output_in_nested_module_revalidates_suspended_caller(self):
        from test_python_direct_source import common_module

        def output(_):
            # Temporarily replace the caller's namespace as a host integration
            # would when rebuilding it; the suspended frame owns the old one.
            owner.types = dict(owner.types)

        config = source(b'', common_module(
            b'Function Notify() Export Message("event"); Return 1; EndFunction'))
        app = SourceApplication(config, output=output)
        self.addCleanup(app.close)
        app.start()
        owner = app.interpreter
        with self.assertRaises(BoundaryViolation):
            owner.execute('R=Helpers.Notify(); Finished=True;')
        self.assertNotIn('finished', owner.variables)

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
                owner = self.owner(extensions=True)
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
