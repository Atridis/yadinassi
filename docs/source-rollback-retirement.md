# Fail-closed source transaction rollback

A SQLite error while rolling back now retires the source store handle and clears
its explicit transaction state. It cannot be reused as if cleanup had succeeded.
The controlled error is `source transaction rollback failed; store closed`.

Explicit rollback, begin/commit failure cleanup and catalog/document/section
record abort paths share the helper. Successful rollback keeps the handle usable;
normal write/read ownership and lifecycle guards are unchanged. Closed-handle
cleanup is idempotent and no longer masks section-read closed-store errors.

Fault-injection tests cover failed rollback, combined commit/rollback failure,
post-BEGIN validation failure, record abort and driver close failure. If the
driver itself cannot close, the Python handle is still permanently retired; this
is not a guarantee that an operating-system lock vanished. The operation is not
reported successful and no automatic write retry is performed. No native 1C
compatibility claim is made.
