"""Shared entry/exit accounting for the isolated direct-translator experiment.

One unit is a generated loop checkpoint, NOT a BSL AST node. This closes the
nested-entry reset hole; it does not supply VM scope, retained-unit authority,
source-admission caps, or a sandbox against trusted Python callbacks.
"""
from threading import Lock, get_ident
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation


class SharedBoundaryContext(BoundaryContext):
    """Overlapping executions share one budget until the last frame exits.

    The short lock serializes entry, checkpoint charging, revocation and exit.
    It is never held while running translated code, policies or host callbacks.
    A checkpoint does not roll back effects preceding concurrent revocation.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._frame_lock = Lock()
        self._frame_threads = {}
        self._active_frames = 0

    def enter(self):
        with self._frame_lock:
            if not self._active_frames:
                super().start()
            else:
                self._check()
            thread = get_ident()
            self._frame_threads[thread] = self._frame_threads.get(thread, 0) + 1
            self._active_frames += 1

    def leave(self):
        with self._frame_lock:
            thread = get_ident()
            depth = self._frame_threads.get(thread, 0)
            if not depth:
                raise BoundaryViolation('execution frame exited by non-owner')
            if depth == 1:
                del self._frame_threads[thread]
            else:
                self._frame_threads[thread] = depth - 1
            self._active_frames -= 1

    def start(self):
        # Legacy direct start must not reset an active execution's allowance.
        with self._frame_lock:
            if self._active_frames:
                self._check()
            else:
                super().start()

    def checkpoint(self):
        with self._frame_lock:
            super().checkpoint()

    def revoke(self):
        with self._frame_lock:
            super().revoke()


class SingleOwnerBoundaryContext(BoundaryContext):
    """Permanent constructing-thread ownership; foreign execution is unsupported.

    Same-owner nested entries share the outer budget. Sequential outer entries
    reset it. Unlike SharedBoundaryContext, another thread cannot execute on
    this context, even after the owner becomes idle. Thread-object identity
    avoids recycled thread-ident admission. Any thread may revoke permanently.

    Checkpoints never acquire a lock. Cancellation is observed at the next
    checkpoint/service boundary; it cannot roll back preceding effects or make
    an entire translated statement atomic with concurrent cancellation.

    By default unbudgeted checkpoints still increment loop_backedges. Setting
    count_unbudgeted=False explicitly disables that diagnostic counter ONLY
    without a budget; cancellation checks remain and budgeted counts stay exact.
    This is an opt-in host contract, not automatic single-thread detection.
    """

    def __init__(self, *, count_unbudgeted=True, **kwargs):
        from threading import current_thread, Event
        if type(count_unbudgeted) is not bool:
            raise TypeError('count_unbudgeted requires Boolean')
        super().__init__(**kwargs)
        self._owner_thread = current_thread()
        self._current_thread = current_thread
        self._cancelled = Event()
        self._depth = 0
        self._count_unbudgeted = count_unbudgeted

    def _require_owner(self):
        if self._current_thread() is not self._owner_thread:
            raise BoundaryViolation('single-owner execution belongs to another thread')

    def _check(self):
        # Inline the fixed owner contract rather than stacking guard adapters.
        if self._current_thread() is not self._owner_thread:
            raise BoundaryViolation('single-owner execution belongs to another thread')
        if self._admitted_epoch is None:
            raise BoundaryViolation('execution boundary not started')
        if self._cancelled.is_set() or self._revoked or self._epoch != self._admitted_epoch:
            raise BoundaryViolation('execution authority revoked')

    def enter(self):
        self._require_owner()
        if self._depth:
            self._check()
        else:
            super().start()
        self._depth += 1

    def leave(self):
        self._require_owner()
        if not self._depth:
            raise BoundaryViolation('execution frame exited without entry')
        self._depth -= 1

    def start(self):
        self._require_owner()
        if self._depth:
            self._check()
        else:
            super().start()

    def checkpoint(self):
        self._check()
        budget = self.loop_budget
        if budget is not None:
            if self.loop_backedges >= budget:
                raise BoundaryViolation('generated loop backedge budget exhausted')
            self.loop_backedges += 1
        elif self._count_unbudgeted:
            self.loop_backedges += 1

    def revoke(self):
        # Revocation is the only cross-thread mutation owned by this contract.
        # Event owns publication. Repeated revocation is monotonic/idempotent;
        # there is no recovery or exact revocation-count contract in this mode.
        self._cancelled.set()
        self._revoked = True
