# Application-family identity and cancellation

The local interpreter host owns a family: root, imported files, common modules,
form interpreters and local activation interpreters share one schema/type scope.
Within a family, interpreters using the same exact database context share a
scope. Independently owned contexts (such as isolated form database connections)
retain separate scopes and lifetime; they may join the scheduler family but do
not gain cross-context reference compatibility. Independent roots remain
separate even when they use the same database context. Native targets must match.

The scope is a shared lazy `BSLMetadata` graph. Catalog/document/register managers
remain interpreter-local, so module bindings and document execution ownership
are not transferred with type identity. References, bound TypeDescription,
metadata lookup, Query parameters and temporary tables consequently agree within
the family without converting references to UUIDs. Transport/serialization
permissions are unchanged. A new schema generation is never silently admitted
into the old graph; existing backend generation checks remain authoritative.

`Interpreter.cancel_pending()` is root-only and cancels suspended cooperative
work without retiring the family. Interactive REPL interruption uses this path,
so already imported modules and subsequent imports remain usable. It does not
undo synchronous side effects or transactions and is not a hard preemption API.
`close()` remains the terminal family boundary: it fences existing children.
A standalone root can still execute again for embedding compatibility, but its
next execution gets a fresh schema scope. Old references cannot be assigned or
used as Query parameters in the reopened family. ConfigurationApplication's own
terminal lifecycle is not reopened by this embedding behavior.

## Failed promises at the Python host boundary

A terminal `failed` promise stores a traceback-free description, not a Python
exception instance. Every read of its host `result` and every later Await gets
an independent exception. The first escaping host call still raises the original
exception. Exception object identity is **not** a promise result contract.

Type, primitive argument values, notes and a bounded cause/context chain are
retained; mutable/custom argument objects become type-labelled diagnostic text.
Custom exception attributes, arbitrary payload graphs and traceback frames are
not retained. Delivery bypasses custom initialization/copy/reduce hooks;
specialized builtin exceptions use their builtin allocator. Unsupported custom
allocators or specialized builtin payloads that cannot be safely reconstructed
fall back to a RuntimeError carrying the original type name/arguments.
This is a Python embedding diagnostic contract, not new native 1C behavior.

Host faults are still distinct from catchable BSL rejections. Repeated Await must
not become successful Undefined, leak host-failure state into later calls, retain
caller's objects, or grow an accumulating traceback. Cancellation releases pending
tasks; already terminal promise values remain available without owning prior
host frames.
