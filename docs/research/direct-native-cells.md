# Standalone routine native cells (experimental lightweight baseline)

The direct AST compiler boxes only address-taken locals/parameters into private
one-element Python lists. Ordinary locals remain Python locals. Known internal
calls forward the same cell, including two aliases of the same variable and
recursive calls. ByVal locals get independent storage when subsequently passed
by reference. No per-read property getter, `_as_ref`, or dictionary lookup is
needed for these internal cells.

Persistent/exported entry and complex array/property addresses still adapt the
existing reference protocol at the boundary. Declared module globals retain
live dictionary storage. Imports, source-owned/configuration/database profiles
are deliberately excluded from this change. Host references receive activation
and context checks; they cannot outlive the routine that exposed them. Pure
internal routines do not allocate activation guards.

This is not a complete compatibility claim. Module locals publish/reload at
explicit dynamic edges and final publication rather than every assignment;
callback/finalizer visibility can differ. Literal integral loop induction may
use Python integers internally before normalizing the public counter at exit.
Routine addition with a Decimal literal uses direct Python addition; historical
implicit string concatenation in this case is not retained. Complex references
are not promised the native-cell performance.

## Measurement scope

External artifact `native-cells-ab-20261118` measures exact 14406828 versus
86089153, three fresh-process AB/BA/AB pairs, n=512 and 4096, five rotated rounds,
20/5 invocations per sample. Output Decimal(n) is validated for each lane;
profiling is separate. This is prepared execution only, not default/compilation.
Raw Python also calls an increment function once per iteration using a list cell.
Shared dictionary-ID and list-ID variants are separate Python representation
experiments, not alternative compiled implementations. All operate on identical
Decimal increments. No production bypass or disabled owner checks is measured.
