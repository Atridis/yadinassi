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
