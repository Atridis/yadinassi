# Admission-epoch fault-injection regressions

The b0038ba2 Linux light failures were reproduced independently. They concern
three assertions in two pre-epoch-cache tests, not three independent storage
cleanup failures.

`test_live_initializer_and_require_failures_cleanup_and_repair` clears the
PreparedSource importer cache, but its successful recovery read also publishes a
readonly admission epoch. A later `validate_replacement` mock is consequently
not reached by a warm read. The failed assertRaises leaves that unexpectedly
successful view open; the next writer observes busy and the earlier active view.
That second failure is a consequence of the first test's missing close.

The revised injection test explicitly retires the idle read handle, requires the
injected function to be called once, and closes a view even if failure injection
unexpectedly succeeds. BackendError, empty active ownership and cleared importer
state are still required. A separate test proves warm reuse skips the initializer
but a following writer invalidates the proof, reaches that same injected fault,
cleans ownership and allows a repaired subsequent read.

The layout test now distinguishes cold read, warm read, writer and read after the
writer. Source/map load counts are respectively 1/0/1/1. Warm tracing is attached
to the retained connection before begin, rather than only inside read_source;
it still requires BEGIN, data_version sampling and ROLLBACK. Existing corrupt
registry/source, changed-epoch and rollback-failure tests remain unchanged.

No runtime cache, admission, write, ownership or cleanup code is changed.
