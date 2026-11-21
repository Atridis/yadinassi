import os
import threading
import unittest
from unittest.mock import patch
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from tests.direct_boundary_compile import compile_boundary
from yadinassi.execution.codegen.experimental_naked_control import SharedBoundaryContext

class SharedBoundaryTests(unittest.TestCase):

    def program(self, source):
        return compile_boundary(source)

    def test_nested_entry_cannot_reset_budget(self):
        nested = self.program('x=1;')
        ctx = SharedBoundaryContext(loop_budget=2)
        ctx._services['nested'] = lambda: nested.run({}, context=ctx)
        outer = self.program('r=0;For i=1 To 5 Do Nested();r=r+1;EndDo;')
        with self.assertRaises(BoundaryViolation):
            outer.run({}, context=ctx)
        self.assertEqual(outer.last_state['r'], 2)
        self.assertEqual(ctx.loop_backedges, 2)
        self.assertEqual(ctx._active_frames, 0)
        self.assertEqual(ctx._frame_threads, {})

    def test_sequential_top_level_entry_gets_new_budget(self):
        ctx = SharedBoundaryContext(loop_budget=3)
        program = self.program('r=0;For i=1 To 2 Do r=r+1;EndDo;')
        self.assertEqual(program.run({}, context=ctx)['r'], 2)
        self.assertEqual(program.run({}, context=ctx)['r'], 2)
        self.assertEqual(ctx._active_frames, 0)

    def test_exception_unwinds_all_frames(self):
        nested = self.program('r=1/0;')
        ctx = SharedBoundaryContext(services={'nested': lambda: nested.run({}, context=ctx)})
        with self.assertRaises(Exception):
            self.program('Nested();').run({}, context=ctx)
        self.assertEqual(ctx._active_frames, 0)
        self.assertEqual(ctx._frame_threads, {})

    def test_revocation_unwinds_without_restart(self):
        ctx = SharedBoundaryContext()
        ctx._services['revoke'] = ctx.revoke
        with self.assertRaises(BoundaryViolation):
            self.program('Revoke();').run({}, context=ctx)
        self.assertEqual(ctx._active_frames, 0)
        with self.assertRaises(BoundaryViolation):
            self.program('r=1;').run({}, context=ctx)
        self.assertEqual(ctx._active_frames, 0)

    def test_legacy_start_cannot_reset_active_budget(self):
        ctx = SharedBoundaryContext(loop_budget=1)
        ctx.enter()
        try:
            ctx.checkpoint()
            ctx.start()
            with self.assertRaises(BoundaryViolation):
                ctx.checkpoint()
        finally:
            ctx.leave()

    def test_concurrent_entry_shares_budget_and_charges_atomically(self):
        ctx = SharedBoundaryContext(loop_budget=50)
        entered = threading.Barrier(3)
        completed = threading.Barrier(3)
        counts = []
        errors = []

        def worker():
            try:
                ctx.enter()
                entered.wait(timeout=3)
                count = 0
                try:
                    while True:
                        ctx.checkpoint()
                        count += 1
                except BoundaryViolation:
                    counts.append(count)
                completed.wait(timeout=3)
            except BaseException as error:
                errors.append(error)
            finally:
                ctx.leave()
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        entered.wait(timeout=3)
        completed.wait(timeout=3)
        for thread in threads:
            thread.join(timeout=3)
        self.assertEqual(errors, [])
        self.assertFalse(any((thread.is_alive() for thread in threads)))
        self.assertEqual(sum(counts), 50)
        self.assertEqual(ctx.loop_backedges, 50)
        self.assertEqual(ctx._active_frames, 0)

    def test_wrong_thread_cannot_exit_active_frame(self):
        ctx = SharedBoundaryContext()
        ctx.enter()
        errors = []

        def worker():
            try:
                ctx.leave()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=3)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], BoundaryViolation)
        self.assertEqual(ctx._active_frames, 1)
        ctx.leave()
