from yadinassi.types.errors import BSLRuntimeError
import os
import threading
import unittest
from unittest.mock import patch
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from tests.direct_boundary_compile import compile_boundary
from yadinassi.execution.codegen.experimental_naked_control import SingleOwnerBoundaryContext

class SingleOwnerTests(unittest.TestCase):

    def program(self, source):
        return compile_boundary(source)

    def foreign(self, operation):
        outcomes = []

        def run():
            try:
                operation()
            except BaseException as error:
                outcomes.append(error)
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        return outcomes

    def test_new_thread_after_entry_cannot_execute_before_effects(self):
        effects = []
        ctx = SingleOwnerBoundaryContext(services={'Effect': lambda: effects.append(1)})
        program = self.program('Effect();')
        ctx.enter()
        try:
            errors = self.foreign(lambda: program.run({}, context=ctx))
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], BoundaryViolation)
            self.assertEqual(effects, [])
            self.assertEqual(ctx._depth, 1)
        finally:
            ctx.leave()

    def test_foreign_sequential_owner_is_also_rejected(self):
        ctx = SingleOwnerBoundaryContext()
        ctx.enter()
        ctx.leave()
        self.assertIsInstance(self.foreign(ctx.enter)[0], BoundaryViolation)
        self.assertEqual(ctx._depth, 0)

    def test_nested_budget_is_shared_and_sequential_resets(self):
        nested = self.program('x=1;')
        ctx = SingleOwnerBoundaryContext(loop_budget=2)
        ctx._services['Nested'] = lambda: nested.run({}, context=ctx)
        ctx._services['nested'] = ctx._services.pop('Nested')
        outer = self.program('r=0;For i=1 To 5 Do Nested();r=r+1;EndDo;')
        for unused in range(2):
            with self.assertRaises(BoundaryViolation):
                outer.run({}, context=ctx)
            self.assertEqual(outer.last_state['r'], 2)
            self.assertEqual(ctx.loop_backedges, 2)
            self.assertEqual(ctx._depth, 0)

    def test_start_does_not_reset_active_budget(self):
        ctx = SingleOwnerBoundaryContext(loop_budget=1)
        ctx.enter()
        try:
            ctx.checkpoint()
            ctx.start()
            with self.assertRaises(BoundaryViolation):
                ctx.checkpoint()
        finally:
            ctx.leave()

    def test_foreign_revoke_observed_before_further_body_effect(self):
        effects = []
        ctx = SingleOwnerBoundaryContext()

        def revoke():
            self.assertEqual(self.foreign(ctx.revoke), [])
        ctx._services.update(revoke=revoke, effect=lambda: effects.append(1))
        with self.assertRaises(BoundaryViolation):
            self.program('Revoke();Effect();').run({}, context=ctx)
        self.assertEqual(effects, [])
        self.assertEqual(ctx._depth, 0)
        with self.assertRaises(BoundaryViolation):
            ctx.enter()

    def test_foreign_checkpoint_service_and_leave_denied(self):
        effects = []
        ctx = SingleOwnerBoundaryContext(services={'effect': lambda: effects.append(1)})
        ctx.enter()
        try:
            for op in (ctx.checkpoint, ctx.leave, ctx.start, lambda: ctx.invoke('effect')):
                self.assertIsInstance(self.foreign(op)[0], BoundaryViolation)
            self.assertEqual(effects, [])
            self.assertEqual(ctx.loop_backedges, 0)
        finally:
            ctx.leave()

    def test_diagnostics_counter_opt_out_only_without_budget(self):
        for count in (False, True):
            ctx = SingleOwnerBoundaryContext(count_unbudgeted=count)
            ctx.enter()
            for unused in range(3):
                ctx.checkpoint()
            ctx.leave()
            self.assertEqual(ctx.loop_backedges, 3 if count else 0)
            ctx = SingleOwnerBoundaryContext(count_unbudgeted=count, loop_budget=2)
            ctx.enter()
            ctx.checkpoint()
            ctx.checkpoint()
            with self.assertRaises(BoundaryViolation):
                ctx.checkpoint()
            ctx.leave()
            self.assertEqual(ctx.loop_backedges, 2)

    def test_unwind_nested_failure(self):
        ctx = SingleOwnerBoundaryContext()
        nested = self.program('x=1/0;')
        ctx._services['nested'] = lambda: nested.run({}, context=ctx)
        with self.assertRaisesRegex(BSLRuntimeError, "Деление на ноль"):
            self.program('Nested();').run({}, context=ctx)
        self.assertEqual(ctx._depth, 0)

    def test_zero_budget_no_body_effect(self):
        ctx = SingleOwnerBoundaryContext(loop_budget=0)
        program = self.program('r=0;While True Do r=r+1;EndDo;')
        with self.assertRaises(BoundaryViolation):
            program.run({}, context=ctx)
        self.assertEqual(program.last_state['r'], 0)

    def test_owner_is_retained_thread_object_not_numeric_ident(self):
        ctx = SingleOwnerBoundaryContext()
        self.assertIs(ctx._owner_thread, threading.current_thread())

    def test_no_checkpoint_lock(self):

        class BadLock:

            def __enter__(self):
                raise AssertionError('hot checkpoint acquired lock')
        ctx = SingleOwnerBoundaryContext()
        ctx.enter()
        ctx._frame_lock = BadLock()
        ctx.checkpoint()
        ctx.leave()

    def test_context_backed_reference_cannot_be_used_by_foreign_thread(self):
        from types import SimpleNamespace
        from yadinassi.execution.codegen.experimental_naked_boundaries import HostMembers
        obj = SimpleNamespace(value=1)
        ctx = SingleOwnerBoundaryContext(members=(HostMembers(obj, readable=('value',), writable=('value',)),))
        ctx.enter()
        try:
            reference = ctx.reference_member(obj, 'value')
            for operation in (reference.get, lambda: reference.set(2)):
                errors = self.foreign(operation)
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], BoundaryViolation)
            self.assertEqual(obj.value, 1)
        finally:
            ctx.leave()

    def test_concurrent_revoke_is_monotonic_and_idempotent(self):
        ctx = SingleOwnerBoundaryContext()
        ctx.enter()
        threads = [threading.Thread(target=ctx.revoke) for unused in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        with self.assertRaises(BoundaryViolation):
            ctx.checkpoint()
        ctx.leave()
        with self.assertRaises(BoundaryViolation):
            ctx.enter()

    def test_direct_start_requires_owner_and_supports_legacy_checkpoint(self):
        ctx = SingleOwnerBoundaryContext(loop_budget=1)
        ctx.start()
        ctx.checkpoint()
        with self.assertRaises(BoundaryViolation):
            ctx.checkpoint()
        self.assertIsInstance(self.foreign(ctx.start)[0], BoundaryViolation)
