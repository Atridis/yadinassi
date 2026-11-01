# Bounded ordinary regular-expression workflows

Local implementation checkpoint: **native 8.3.27 calibration is pending**. The
current local outputs are observations, not native goldens or a PCRE compatibility
claim. Official EDT pages document these APIs since 8.3.23 (selected descriptions
updated in 8.3.24); the measured target remains 8.3.27.1508.

## Workflow

- `StrLikeByRegularExpression / СтрПодобнаПоРегулярномуВыражению` checks a pattern.
- `StrFindByRegularExpression / СтрНайтиПоРегулярномуВыражению` supports the existing
  `SearchDirection`, optional start/occurrence, IgnoreCase and MultilineSearch.
- `StrFindAllByRegularExpression / СтрНайтиВсеПоРегулярномуВыражению` returns an Array.
- `StrReplaceByRegularExpression / СтрЗаменитьПоРегулярномуВыражению` replaces matches
  using literal text and numbered `$0`/`$n` references.
- Readonly `ResultOfSearchByRegularExpression` and
  `ResultOfSearchByRegularExpressionGroup` expose `Value`, `Length`, `StartIndex`.
  `GetGroups()` returns an independent Array of readonly group values. These
  result types are returned by APIs, not public constructors. Internal codec
  serialization is explicitly refused, rather than fabricating XML/XDTO support.

The grammar accepts literals, escaped punctuation, ordinary character classes and
ranges/negation, common `\d/\s/\w` categories and complements, dot, anchors and word
boundaries, alternation, numbered/noncapturing groups, and greedy/lazy
`? * + {m} {m,n} {m,}` repeats. Parser and VM are pure Python; there is **no stdlib
`re` execution**, compiled regex dependency, subprocess, filesystem or network
capability in this family.

## Bounds and implementation

Ordered explicit-stack backtracking preserves branch priority. It is **not a
linear-time algorithm**. The protection is a deterministic whole-operation work
budget, not a wall-clock timeout or a claim that short inputs prevent exponential
backtracking. The same counter covers parsing, compilation, VM transitions,
character-class checks, capture copies, search candidate starts, all matches and
replacement/result materialization. No budget reset occurs per match. Nullable
repetitions have an explicit progress guard and cannot spin at the same position.
A limit error is catchable in BSL; no partial Array/replacement escapes a failed
call and no unbounded fallback is attempted.

| Resource | Limit |
|---|---:|
| Pattern UTF-16 units | 4096 |
| Input/replacement UTF-16 units | 65536 |
| Nested groups | 32 |
| Capturing groups | 32 |
| Numeric argument coefficient digits | 128 (1024-byte Decimal precheck) |
| Compiled instructions | 2048 |
| Counted-repeat bound | 1024 |
| Distinct unbounded-repeat guards | 128 |
| Pending branch states | 4096 |
| Whole-call primitive work units | 2,000,000 |
| Matches | 4096 |
| Aggregate result/group objects, or replacement pieces | 8192 |
| Aggregate copied result/capture/replacement UTF-16 units | 1,048,576 |

Optional positions/occurrences require numeric values, not implicit numeric-string coercion; flags require Boolean. The numeric admission guard is explicitly CPython/C-Decimal-specific (other implementations fail closed), not a portable semantic size claim. CPython Decimal coefficient storage is bounded before digit-tuple conversion, and range is checked before integral conversion.

Limits are checked before corresponding growth. This is a bounded ordinary
subset, not an implementation of every native regex extension. Python 3.10
syntax is supported; current local execution used Python 3.12. Actual 3.10
execution still needs verification in the existing native-image path.

## Explicit limits and calibration gates

`!todo`: pattern backreferences, lookaround, named groups, inline flags, Unicode
property escapes, atomic/possessive/conditional/recursive extensions and XDTO/XML
serialization are unsupported and rejected, never silently reinterpreted.

Public offsets are currently UTF-16 based while matching consumes Unicode scalar
characters. Starts inside a surrogate pair are explicitly rejected. Native40
must settle matching units, IgnoreCase/category Unicode behavior, multiline
newlines, backward search bounds, empty/zero-width progress, group inclusion and
optional-group positions, `$` escaping and missing replacement groups. These
provisional local choices are not yet asserted as native parity. Unicode behavior
outside measured cases is not claimed identical across Python Unicode versions.

See [the single closed native profile](regex-family-native-profile.md). It uses
short fixed strings only; no stress-pattern execution or file fixtures.

The normal build workflow now defines a separate read-only Ubuntu compatibility
job using the repository's existing checkout/setup-python action references and
Python `3.10`. It verifies the running CPython version, then executes the three
focused regex/runtime/profile modules normally and with `-O`, under a ten-minute
job limit. Release additionally depends on this job. **Defining the job is not
proof it has run**: exact-head 3.10 execution remains pending until CI succeeds.
No native1C credentials, artifact uploads, extra triggers or permissions are added.
