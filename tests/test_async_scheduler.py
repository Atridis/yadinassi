"""Host-independent contracts for the cooperative BSL scheduler."""
import gc
from decimal import getcontext, localcontext
import unittest
import weakref

from yadinassi.async_runtime import AwaitRequest, Scheduler, SchedulerLimitError
from yadinassi.errors import BSLRuntimeError
from yadinassi.native_targets import (
    LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, current_native_target, target_context,
)


def failure(message='failure'):
    return BSLRuntimeError(message, 'test.bsl', 2, 3)


def returning(value):
    if False:
        yield
    return value


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = Scheduler(LINUX_8_3_27_1508)

    def test_eager_prefix_then_fifo_scalar_await(self):
        seen = []
        def task(label):
            seen.append((label, 'before'))
            result = yield AwaitRequest(31)
            seen.append((label, 'after', result))
            return result
        first = self.scheduler.start(task('a'))
        second = self.scheduler.start(task('b'))
        self.assertEqual(seen, [('a', 'before'), ('b', 'before')])
        self.assertEqual(first.state, 'pending')
        self.scheduler.run_until_idle()
        self.assertEqual(seen[2:], [('a', 'after', 31), ('b', 'after', 31)])
        self.assertEqual((first.result, second.result), (31, 31))
        self.assertFalse(self.scheduler.pending)

    def test_settled_promise_still_suspends(self):
        terminal = self.scheduler.start(returning(31))
        def task():
            return (yield AwaitRequest(terminal))
        waiting = self.scheduler.start(task())
        self.assertEqual(waiting.state, 'pending')
        self.scheduler.run_until_idle()
        self.assertEqual(waiting.result, 31)

    def test_idle_does_not_mean_completed(self):
        signal = self.scheduler.new_pending()
        def task():
            return (yield AwaitRequest(signal))
        promise = self.scheduler.start(task())
        self.scheduler.run_until_idle()
        self.assertEqual(promise.state, 'pending')
        self.assertEqual(set(self.scheduler.pending), {signal, promise})
        self.scheduler.resolve(signal, 17)
        self.assertEqual(promise.state, 'pending')
        self.scheduler.run_until_idle()
        self.assertEqual(promise.result, 17)

    def test_rejection_is_thrown_at_await_with_identity(self):
        signal = self.scheduler.new_pending()
        error = failure()
        caught = []
        def task():
            try:
                yield AwaitRequest(signal)
            except BSLRuntimeError as exc:
                caught.append(exc)
                return 42
        promise = self.scheduler.start(task())
        self.scheduler.reject(signal, error)
        self.assertFalse(caught)
        self.scheduler.run_until_idle()
        self.assertEqual(caught, [error])
        self.assertEqual(promise.result, 42)

    def test_returned_promises_are_adopted_pending_and_terminal(self):
        signal = self.scheduler.new_pending()
        outer = self.scheduler.start(returning(signal))
        self.scheduler.resolve(outer, 99)  # Adoption already claimed settlement.
        self.scheduler.reject(outer, failure())
        self.assertEqual(outer.state, 'pending')
        self.scheduler.resolve(signal, 31)
        self.assertEqual((outer.state, outer.result), ('fulfilled', 31))
        terminal_outer = self.scheduler.start(returning(signal))
        self.assertEqual(terminal_outer.result, 31)

    def test_adopted_rejection_preserves_error(self):
        signal = self.scheduler.new_pending()
        outer = self.scheduler.start(returning(signal))
        error = failure()
        self.scheduler.reject(signal, error)
        self.assertEqual(outer.state, 'rejected')
        self.assertIs(outer.result, error)

    def test_deep_adoption_does_not_use_python_recursion(self):
        promises = [self.scheduler.new_pending() for _ in range(2000)]
        for previous, following in zip(promises, promises[1:]):
            self.scheduler.resolve(previous, following)
        self.scheduler.resolve(promises[-1], 31)
        self.assertTrue(all(p.result == 31 for p in promises))
        self.assertFalse(self.scheduler.pending)

    def test_reset_closes_all_tasks_even_when_one_finalizer_fails(self):
        seen = []
        def task(label):
            try:
                yield AwaitRequest(self.scheduler.new_pending())
            finally:
                seen.append(label)
                if label == 'bad':
                    raise ValueError('finalizer failed')
        self.scheduler.start(task('bad'))
        self.scheduler.start(task('good'))
        with self.assertRaisesRegex(ValueError, 'finalizer failed'):
            self.scheduler.reset()
        self.assertCountEqual(seen, ['bad', 'good'])
        self.assertFalse(self.scheduler.pending)
        self.assertFalse(self.scheduler.is_active)

    def test_pump_budget_retains_pending_and_ready_tasks(self):
        seen = []
        def task():
            while True:
                seen.append(len(seen))
                yield AwaitRequest(1)
        promise = self.scheduler.start(task())
        with self.assertRaisesRegex(SchedulerLimitError, 'step budget exhausted'):
            self.scheduler.run_until_idle(max_steps=3)
        self.assertEqual(len(seen), 4)
        self.assertEqual(promise.state, 'pending')
        self.assertIn(promise, self.scheduler.pending)
        self.assertFalse(self.scheduler.is_active)
        with self.assertRaisesRegex(SchedulerLimitError, 'step budget exhausted'):
            self.scheduler.run_until_idle(max_steps=2)
        self.assertEqual(len(seen), 6)
        self.scheduler.reset()
        self.assertFalse(self.scheduler.pending)

    def test_pump_completing_exact_budget_succeeds(self):
        def task():
            yield AwaitRequest(1)
            return 2
        promise = self.scheduler.start(task())
        self.scheduler.run_until_idle(max_steps=1)
        self.assertEqual(promise.result, 2)

    def test_pump_rejects_invalid_budgets(self):
        for budget in (0, -1, True, None, 1.5):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                self.scheduler.run_until_idle(max_steps=budget)

    def test_promise_presentation_is_explicitly_unsupported(self):
        with self.assertRaisesRegex(TypeError, 'presentation'):
            str(self.scheduler.new_pending())

    def test_repeated_rejection_delivery_has_bounded_host_traceback(self):
        signal = self.scheduler.new_pending()
        info = object()
        error = BSLRuntimeError('retained', 'source.bsl', 7, 9,
                                info=info, source_line='Raise "retained";')
        try:
            raise error
        except BSLRuntimeError:
            self.scheduler.reject(signal, error)
        self.assertIsNone(error.__traceback__)
        lengths = []
        def task():
            for _ in range(1000):
                try:
                    yield AwaitRequest(signal)
                except BSLRuntimeError as caught:
                    self.assertIs(caught, error)
                    self.assertIs(caught.info, info)
                    self.assertEqual((caught.source, caught.line, caught.column),
                                     ('source.bsl', 7, 9))
                    self.assertEqual(caught.source_line, 'Raise "retained";')
                    count, traceback = 0, caught.__traceback__
                    while traceback is not None:
                        count += 1
                        traceback = traceback.tb_next
                    lengths.append(count)
            # An uncaught final delivery must shed its host frames at settlement.
            yield AwaitRequest(signal)
        result = self.scheduler.start(task())
        self.scheduler.run_until_idle()
        self.assertEqual(len(lengths), 1000)
        self.assertEqual(min(lengths), max(lengths))
        self.assertLessEqual(max(lengths), 2)
        self.assertEqual(result.state, 'rejected')
        self.assertIs(result.result, error)
        self.assertIsNone(error.__traceback__)

    def test_rejection_does_not_retain_host_exception_chain_or_task_payload(self):
        class Payload:
            pass
        references = []
        info = object()
        def task():
            payload = Payload()
            references.append(weakref.ref(payload))
            try:
                raise ValueError('host failure')
            except ValueError as host:
                raise BSLRuntimeError('BSL failure', 'source.bsl', 5, 6,
                                      info=info, source_line='x = 1 / 0;') from host
            yield
        promise = self.scheduler.start(task())
        self.assertEqual(promise.state, 'rejected')
        error = promise.result
        self.assertIs(error.info, info)
        self.assertEqual((error.message, error.source, error.line, error.column,
                          error.source_line),
                         ('BSL failure', 'source.bsl', 5, 6, 'x = 1 / 0;'))
        self.assertIsNone(error.__traceback__)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        gc.collect()
        self.assertIsNone(references[0]())

    def test_delivery_clears_host_chains_added_after_settlement(self):
        signal = self.scheduler.new_pending()
        error = failure()
        self.scheduler.reject(signal, error)
        error.__context__ = ValueError('later host context')
        error.__cause__ = ValueError('later host cause')
        def task():
            try:
                yield AwaitRequest(signal)
            except BSLRuntimeError as caught:
                self.assertIs(caught, error)
                self.assertIsNone(caught.__context__)
                self.assertIsNone(caught.__cause__)
                return 7
        result = self.scheduler.start(task())
        self.scheduler.run_until_idle()
        self.assertEqual(result.result, 7)

    def test_caught_rejection_releases_fulfilled_consumer_payload(self):
        class Payload:
            pass
        references = []
        signal = self.scheduler.new_pending()
        info = object()
        error = BSLRuntimeError('failure', 'source.bsl', 2, 3, info=info)
        self.scheduler.reject(signal, error)
        def task():
            payload = Payload()
            references.append(weakref.ref(payload))
            try:
                yield AwaitRequest(signal)
            except BSLRuntimeError as caught:
                self.assertIs(caught, error)
                self.assertIs(caught.info, info)
            return 1
        result = self.scheduler.start(task())
        self.scheduler.run_until_idle()
        self.assertEqual((result.state, result.result), ('fulfilled', 1))
        self.assertIs(signal.result, error)
        self.assertIsNone(error.__traceback__)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        gc.collect()
        self.assertIsNone(references[0]())

    def test_yield_inside_rejection_handler_clears_delivery_frames(self):
        signal = self.scheduler.new_pending()
        gate = self.scheduler.new_pending()
        error = failure()
        self.scheduler.reject(signal, error)
        def task():
            try:
                yield AwaitRequest(signal)
            except BSLRuntimeError as caught:
                self.assertIs(caught, error)
                yield AwaitRequest(gate)
                self.assertIs(caught, error)
            return 1
        result = self.scheduler.start(task())
        self.scheduler.run_until_idle()
        self.assertEqual(result.state, 'pending')
        self.assertIsNone(error.__traceback__)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__cause__)
        self.scheduler.resolve(gate, 7)
        self.scheduler.run_until_idle()
        self.assertEqual((result.state, result.result), ('fulfilled', 1))
        self.assertIsNone(error.__traceback__)

    def test_one_shot_resolution(self):
        signal = self.scheduler.new_pending()
        self.scheduler.resolve(signal, 1)
        self.scheduler.resolve(signal, 2)
        self.scheduler.reject(signal, failure())
        self.assertEqual((signal.state, signal.result), ('fulfilled', 1))

    def test_cycles_reject_without_hanging(self):
        direct = self.scheduler.new_pending()
        self.scheduler.resolve(direct, direct)
        self.assertEqual(direct.state, 'rejected')
        a, b = self.scheduler.new_pending(), self.scheduler.new_pending()
        self.scheduler.resolve(a, b)
        self.scheduler.resolve(b, a)
        self.assertEqual((a.state, b.state), ('rejected', 'rejected'))
        self.assertFalse(self.scheduler.pending)

    def test_foreign_promises_are_never_adopted_or_awaited(self):
        other = Scheduler(WINDOWS_8_3_27_2342)
        foreign = other.new_pending()
        outer = self.scheduler.start(returning(foreign))
        self.assertEqual(outer.state, 'rejected')
        def task():
            yield AwaitRequest(foreign)
        awaiting = self.scheduler.start(task())
        self.assertEqual(awaiting.state, 'pending')
        self.scheduler.run_until_idle()
        self.assertEqual(awaiting.state, 'rejected')
        with self.assertRaises(BSLRuntimeError):
            self.scheduler.resolve(foreign, 1)
        self.assertEqual(foreign.state, 'pending')

    def test_procedure_errors_have_separate_sink(self):
        error = failure()
        def task():
            yield AwaitRequest(None)
            raise error
        promise = self.scheduler.start(task(), procedure=True)
        self.assertEqual(self.scheduler.procedure_errors, [])
        self.scheduler.run_until_idle()
        self.assertEqual(promise.state, 'rejected')
        self.assertEqual(self.scheduler.procedure_errors, [error])

    def test_eager_bsl_failure_rejects_without_sync_throw(self):
        error = failure()
        def task():
            raise error
            yield
        promise = self.scheduler.start(task())
        self.assertIs(promise.result, error)
        self.assertEqual(promise.state, 'rejected')
        self.assertFalse(self.scheduler.procedure_errors)

    def test_host_exceptions_are_not_bsl_rejections(self):
        def task():
            yield AwaitRequest(None)
            raise ValueError('host bug')
        promise = self.scheduler.start(task())
        with self.assertRaisesRegex(ValueError, 'host bug'):
            self.scheduler.run_until_idle()
        self.assertEqual(promise.state, 'pending')
        self.assertFalse(self.scheduler.is_active)
        self.scheduler.reset()

    def test_context_isolated_and_nested_start_restores_parent(self):
        root = self.scheduler.active_context
        root.context_stack.append('server')
        contexts = []
        owner = object()
        def child():
            context = self.scheduler.active_context
            contexts.append(context)
            self.assertEqual(context.context_stack, ['client', 'server'])
            self.assertNotIn(owner, context.locals)
            yield AwaitRequest(None)
            self.assertIs(self.scheduler.active_context, context)
        def parent():
            context = self.scheduler.active_context
            contexts.append(context)
            context.locals[owner] = {'x': 1}
            self.scheduler.start(child())
            self.assertIs(self.scheduler.active_context, context)
            yield AwaitRequest(None)
            self.assertEqual(context.locals[owner], {'x': 1})
        self.scheduler.start(parent())
        self.assertIs(self.scheduler.active_context, root)
        self.assertIsNot(contexts[0], contexts[1])
        self.assertIsNot(contexts[0].context_stack, contexts[1].context_stack)
        self.scheduler.run_until_idle()
        self.assertIs(self.scheduler.active_context, root)

    def test_native_target_and_decimal_precision_each_resume(self):
        observed = []
        def task():
            observed.append((current_native_target(), getcontext().prec))
            yield AwaitRequest(None)
            observed.append((current_native_target(), getcontext().prec))
        with target_context(WINDOWS_8_3_27_2342), localcontext() as context:
            context.prec = 12
            self.scheduler.start(task())
            self.assertEqual(getcontext().prec, 12)
            self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
            self.scheduler.run_until_idle()
            self.assertEqual(getcontext().prec, 12)
            self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
        self.assertEqual(observed, [(LINUX_8_3_27_1508, 38)] * 2)

    def test_run_inline_does_not_drain_and_keeps_context(self):
        seen = []
        root = self.scheduler.active_context
        def task():
            yield AwaitRequest(None)
            seen.append('async')
        self.scheduler.start(task())
        def inline():
            self.assertTrue(self.scheduler.is_active)
            self.assertIs(self.scheduler.active_context, root)
            self.assertEqual(getcontext().prec, 38)
            return 3
            yield
        self.assertEqual(self.scheduler.run_inline(inline()), 3)
        self.assertEqual(seen, [])
        self.assertFalse(self.scheduler.is_active)
        self.scheduler.run_until_idle()
        self.assertEqual(seen, ['async'])

    def test_inline_suspension_is_rejected_and_closed(self):
        closed = []
        def inline():
            try:
                yield AwaitRequest(None)
            finally:
                closed.append(True)
        with self.assertRaisesRegex(RuntimeError, 'cannot suspend'):
            self.scheduler.run_inline(inline())
        self.assertEqual(closed, [True])
        self.assertFalse(self.scheduler.is_active)

    def test_nested_pump_is_rejected(self):
        def task():
            with self.assertRaisesRegex(RuntimeError, 'Nested'):
                self.scheduler.run_until_idle()
            yield AwaitRequest(None)
        self.scheduler.start(task())
        self.scheduler.run_until_idle()

    def test_scheduler_owns_pending_task_without_host_reference(self):
        signal = self.scheduler.new_pending()
        seen = []
        def task():
            yield AwaitRequest(signal)
            seen.append(1)
        generator = task()
        reference = weakref.ref(generator)
        self.scheduler.start(generator)
        del generator
        gc.collect()
        self.assertIsNotNone(reference())
        self.scheduler.resolve(signal)
        self.scheduler.run_until_idle()
        gc.collect()
        self.assertEqual(seen, [1])
        self.assertIsNone(reference())

    def test_reset_closes_under_task_context_and_clears_waiters(self):
        signal = self.scheduler.new_pending()
        seen = []
        def task():
            context = self.scheduler.active_context
            try:
                yield AwaitRequest(signal)
            finally:
                seen.append(self.scheduler.active_context is context)
                seen.append(current_native_target())
        promise = self.scheduler.start(task(), procedure=True)
        self.scheduler.reset()
        self.assertEqual(seen, [True, LINUX_8_3_27_1508])
        self.assertFalse(self.scheduler.pending)
        self.assertEqual(promise.state, 'rejected')
        self.assertFalse(self.scheduler.procedure_errors)
        self.scheduler.resolve(signal, 1)
        self.scheduler.run_until_idle()
        self.assertEqual(len(seen), 2)


if __name__ == '__main__':
    unittest.main()
