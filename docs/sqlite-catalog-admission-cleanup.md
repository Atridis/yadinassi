# SQLite view admission cleanup

Before opening a read or write view, the backend reserves one close-only owner.
That owner retains the connection while connection PRAGMAs, BEGIN, schema checks
and view construction run. Successful admission transfers ownership to the view.
Failure attempts rollback and physical close, without returning a usable view.

A failed physical close does not prove that SQLite released its locks. The
backend therefore remains busy and retains the connection, even if rollback
succeeded or the close may already have taken effect. Backend close retries
cleanup. Ownership is released only after a close call returns successfully.
Failure before a connection was returned clears the empty reservation.

Ordinary cleanup errors do not replace the primary admission error. The first
interruption, including MemoryError, is preserved if cleanup also interrupts.
A new cleanup interruption is not hidden by an ordinary admission error. Existing
public error categories are unchanged: connection-admission SQLite errors remain
storage_error, and OperationalError during BEGIN/view admission remains busy.

This is a narrow extension of the existing admitted-view cleanup contract.
It covers begin_read/begin_write and their connection admission. It does not
change database creation, initial backend construction, export/receipt standalone
connections, filesystem durability, or record/receipt encoding. It is not a
thread-safety guarantee or protection against a second interruption during the
cleanup handler itself. A SQLite connection factory that opens a resource and
raises before returning its handle remains responsible for that resource.

Reopening a backend does not release a live connection owned by the earlier
backend. If rollback and physical close both fail, its lock may remain until
cleanup succeeds or the owning process exits. Never discard the handle, delete
SQLite journals or assume that a fresh backend makes that lock disappear.

Fault-injection coverage is in test_sqlite_catalog_admission_cleanup.py. It uses
real disposable SQLite files with proxy failures before/after BEGIN, during
connection PRAGMAs, schema/view admission, transaction probing and physical close.
Run it together with test_catalog_commit_cleanup_recovery.py and the existing
SQLite/catalog regression suites before accepting the change. Adding these tests
does not by itself establish that they have run or passed.
