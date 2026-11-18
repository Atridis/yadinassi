# Known nonconstructible table children

ValueTableRow, ValueTableColumn and ValueTableColumnCollection (and their Russian
aliases) have public runtime types but no public constructors. Previously these
names were absent from the direct finite constructor registry, so even a
`Try New ValueTableRow; Except ... EndTry` failed whole-program preflight.

The registry now marks the six names with the same denied-factory sentinel
already used for ValueListItem and collection indexes. This provides a catchable
BSL error at the reached call site; it does not construct anything, register a
factory, admit subclasses or delegate to the VM. Static argument expressions do
not run before rejection. Dynamic New retains its separate target/parameter
evaluation order. A custom registered factory for one of these denied names is
not invoked; wholly unknown constructors remain preflight-unsupported.

The unchanged original `table.ctor-row`, `table.ctor-column` and
`table.ctor-columns` native observations all require `[error]`. Tests replay
those three records together with the existing eight table checkpoint controls,
using the original helpers and source lines, and compare exact frozen output.
Additional regressions cover source/AST/prepared/Eval/Execute, catch/recovery,
no argument effects, no VM dispatch, denied custom registration and canonical
runtime dynamic-New order. The entire eight-test table runtime module passes
on this tree (including the separately reviewed reference/omission repairs).
No full native-suite parity is claimed.
