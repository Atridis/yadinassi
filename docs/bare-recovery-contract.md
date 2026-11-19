# Reconstructed bare compiler: isolated recovery candidate

This is new reconstruction over published PR337 sources, **not** the lost
8666/26d/c29 tree. Historical test counts and timings are not evidence for it.
The reconstructed compiler is called explicitly through `native_bare_compiler`.
**The public default backend is not switched by this package.** Its integration
tests use a test-only caller; no production fallback or alternate dispatch is
added. Explicit interpreter and compiled-strict backends are unchanged.

## Implemented small contract

- Integral literals/counters/indices use Python int; fractional literals use
  Decimal. Arithmetic, comparisons and truthiness are native Python operations.
- BareArray is one slotted wrapper and one list, with thin basic method proxies.
- Map/Structure store raw values in one dict; structure names are canonicalized.
- ValueList uses four-field records. UnloadValues creates one result list and a
  BareArray wrapper, not an extra copy or old adapter.
- Table uses positional list rows with owner and one shared name→index schema.
  Columns are transient references, not eagerly duplicated metadata. Discarded
  Columns.Add results lower directly to add_column. Find remains linear.
- Native len, str.upper/lower/strip are supported without coercion/adapters.
- Same-module source routines compile to ordinary Python functions. Value
  parameters use locals; reference variables share a single-element list, with
  direct cell indexing and no per-call adapter. Aliasing/forwarding/recursion
  have focused tests.

## Map iteration and compiler size

Known Maps compile to dict.items and Key/Value tuple projections. Known other
native collections use their ordinary iterator. Unknown receiver types bind an
iterator once and conditionally project fields only at unknown uses. There is
one loop body, not duplicated trees; nested-depth 2/4/8/16 tests check linear
source growth. Conditions and loop-carried writes invalidate type facts.

Only an actually executed whole-element assignment constructs BareMapEntry;
false conditional assignments create none. Last-element assignment after a loop
also materializes on demand. Python-level Map iteration still exposes entries,
so class-only and compiled projection allocation counts intentionally differ.
No legacy resolver or interpreter retry exists in this compiler.

## Explicit gaps and semantic differences

No imports, host free functions, dynamic execution, SQL/form integration,
async/server routines, routine defaults/omissions, cross-execution routine
registry, routine free module variables, indexed/member by-reference arguments,
table indexes or full column metadata.
Whole unmaterialized map-entry argument/byref escapes, iterator reassignment and
branch-dependent iterator representation are unsupported; assign an entry to an
alias first. Other unlisted syntax/functions/methods fail explicitly.

Native negative indexing, missing-find ValueError, equality, sorting, Unicode
and error behavior are intentional differences, not parity bugs. Precise BSL
source error positions and undefined-name diagnostics remain incomplete. Table
sort is currently a single-column native operation, not the complete 1C sort
language. Stale reference semantics are not reproduced.

Trusted code/data only, **not a sandbox**: no input graph admission or environment
walk. Lifecycle closure is checked once at execution entry. Supplied objects can
execute their native Python methods; this backend is not authorization isolation.
There is no broad-suite-green claim. Before a default switch the missing APIs,
CI scenarios and explicit security/host contract must be reviewed individually.

## Independent multidimensional arrays and direct strings

Array dimensions create independent BareArray children only when dimensions are
provided. Dimension expressions evaluate once, left to right. Empty construction
retains its direct single-list branch; native size errors/negative-size behavior
are not adapted to old contracts.

Mid uses native slicing with a one-based start (nonpositive starts clamp to zero;
negative counts produce empty strings). Integer literal bounds fold at compile
time; other arguments evaluate once. StrReplace uses str.replace directly.
Unicode indexes count Python code points, not UTF-16 units. No implicit string or
index conversions are performed.

## Basic FillPropertyValues

Only BareStructure→BareStructure is supported. Existing destination/source keys
are copied; missing keys are skipped, None is copied, payloads are shared, and no
new destination keys are added. Two arguments allocate no filter sets and split
no names. Optional include/exclude strings are normalized once per call;
exclusion wins, unknown names are skipped, empty include copies nothing, and
None means no filter. Host objects, old/fixed structures and legacy partial-write
error-order semantics are not adapted.
