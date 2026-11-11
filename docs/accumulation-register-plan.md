# Fresh accumulation register contract

The explicit `accumulation-balance-scalar-v1` profile is fresh-only format 14.
It admits authored canonical 2.20 metadata and source-bound synchronous document
handlers, Balance-kind scalar accumulation registers, and recorder-owned
movements. Existing format 13 recorder information registers are unchanged.
Their global dimension uniqueness is not reused: repeated dimensions and periods
are separate recorder/line occurrences, including across documents.

## Posting and authority

`SQLiteDBContext.create_accumulation` and `Interpreter(database_context=...)`
activate the profile. Documents expose bounded `RegisterRecords` collections with
Add/Clear/Count/Get, Write selection and explicit Write(). Rows have scalar fields,
Period, Active, and exact bilingual AccumulationRecordType. RecordType is never a
numeric flag or string. Type/TypeOf identity works; enum presentation and
TypeDescription admission remain deferred. Detached Add defaults are Active=true,
Receipt, the minimum Date, and LineNumber=0. Detached LineNumber after a write is
explicitly deferred; raw query rows use persisted occurrence ordinals.

Document values, Posted state and movement replacements share the existing root
journal and operation savepoint. Explicit handler writes are visible to queries
inside that transaction. Cancellation, exceptions and outer rollback restore
persistent state. Historical immutable outcomes remain recoverable after later
replacements. No new commit authority, automatic migration or second connection
is added. A read lease prevents simultaneous writes, validates the shared owner,
and pins the SQLite snapshot; it is not a cross-transaction optimistic query token.

Only Active=true movements are admitted by this activated profile. The measured
mixed-active write failed; all-inactive behavior is unmeasured. This host boundary
does not assert a universal native prohibition on inactive rows. The low-level
generic movement port remains a separately bounded occurrence storage primitive.
Ordinary document editors still refuse format14 rather than bypass posting.

## Typed query sources

Raw `AccumulationRegister.Name` exposes Period, Active, Recorder, LineNumber,
dimensions, resources and attributes. Recorder projection requires exactly one
declared document type. RecordType projection and enum query parameters are
explicitly deferred, not coerced into a different type.

`Balance(&At)` and `Turnovers(&Start,&End)` take exact second-resolution Date
parameters. Balance selects Period < At. Turnovers includes both endpoints,
including an equal-endpoint interval. Reversed intervals and other argument forms
are deferred. Virtual tables expose dimensions and resource suffixes Balance or
Turnover/Receipt/Expense, including Russian equivalents.

Receipt contributes positively and Expense negatively to net totals. Signed
resources are preserved in Receipt/Expense subtotals, not converted to absolute
values. Exact scaled-integer accumulation avoids the caller's Decimal precision.
Output qualifiers are independently derived: Number(38, resource scale, Any).
An exact value outside that output envelope fails rather than truncating or
rounding. All stored source fields and rows are validated and charged against
the existing query budgets before period filtering or projection.

Balance suppresses a group only when all resource balances are zero. Turnovers
retains zero-net groups with nonzero Receipt/Expense subtotals. An all-zero
Turnovers group, including cancellation within each direction, is explicitly
outside the first measured profile. An empty source is valid and remains empty.

Virtual grouping reuses the pinned caseless UCA contract and its string bounds;
it does not invent Unicode casefold identity. Stored dimension spelling remains
exact. Ordinary relational WHERE, ORDER BY and GROUP BY retain the existing
separate host casefold policy. This is not a claim of unified native collation
for every query operation. Joins, temporary tables, UNION and derived sources
reuse the bounded typed query pipeline and one owning read view.

## Evidence and deferred surface

Native run [42981217995](https://github.com/Atridis/yadinassi/actions/runs/42981217995)
completed and accepted all 16 observations against source tree
`15bb86ab74d5287b5927c9a870a4d2f42956712a`. The unchanged observer and handler
are replayed by the runtime test against a separate authored canonical fixture.
See `tests/fixtures/accumulation_register/README.md` for immutable provenance and
the distinction between Designer-acquired 2.4 and runtime-admitted 2.20 input.
The historical report still says runtime parity=false; no evidence is rewritten.

Turnover-kind registers, BalanceAndTurnovers, source filters and periodicity,
Boundary/PointInTime, standalone register manager APIs, persisted totals caches,
profile migrations, general native-dump admission and polymorphic Recorder
projection remain deferred. The native acquisition route and strict gates remain
unchanged; publication on its configured PR branch still triggers a fresh native
measurement and must be announced before execution.
