# SQLite creation failure boundary

Creating a database reserves a new destination exclusively. Validation failures
that occur before the destination is reserved do not create it. Once reserved,
any later failure leaves the destination in place: another process might already
have opened or changed the same file, even if its inode has not changed. Creation
never deletes an existing destination or automatically removes the reserved file
after failure.

An ordinary error once SQL COMMIT has been attempted is reported as
`uncertain_commit`, including an error closing the connection or reopening the
created backend. The destination may be complete or incomplete. A caller must
not assume failure means the file is empty, delete it automatically, or blindly
retry creation. Inspect the destination and its ownership with an appropriate
operational procedure before deciding what to do; this change does not add a
creation-recovery API or certify a concurrently modified file.

Before COMMIT the original ordinary error remains the error; a failed attempt can
still leave a destination requiring inspection. Interruptions and MemoryError
reaching the creation boundary remain visible, while cleanup is attempted. The
existing standalone backend constructor and connection setup can still mask an
interruption during their own cleanup. If SQLite cannot close a connection,
this function does not expose a recovery handle, and external locks may persist.
This bounded data-preservation rule does not claim that all creation failures can
be automatically resolved or that other SQLite connection lifetimes are fixed.
