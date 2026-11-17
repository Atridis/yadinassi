# Direct source temporary-storage accounting

Source temporary storage accepts the direct compiler's exact list and Structure
representations through a private capture opt-in. The ordinary ValueStorage
capture contract is unchanged. Existing node, depth, text, Decimal and retained
storage quotas still apply. Subclasses, malformed structure fields and cycles fail
closed. Shared children are charged per occurrence.

Snapshots validate and account for retained values; they do not replace them.
Same-server Put/Get retains the original collection identity, including later
mutations. Get and replacement remeasure all relevant retained values before
publishing updated accounting. Failed capture or quota checks do not partially
replace entries or accounting. ServerCall continues to copy its input/output
packets independently, so client arrays do not alias retained server arrays.

Exact SourceTemporaryCall markers are validated against the current application's
exact store, operation, wrapper and canonical hooks before argument effects and
again at invocation. A marker installed into a standalone interpreter is rejected
before argument evaluation, including a captured HostFunction value. This does
not grant source capabilities to a standalone interpreter. Ownership, closed
application checks, actual server context and transaction boundaries are unchanged.

The no-VM suite replays the existing source-storage tests and native evidence with
legacy dispatch poisoned. Native fixture case 14 (Map) remains explicitly outside
this list/Structure slice; its original source-wide test is not altered. Other
unsupported snapshot types retain their existing failures.
