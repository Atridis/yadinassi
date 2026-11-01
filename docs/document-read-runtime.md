# Bounded read-only Documents

The Documents block reads a caller-owned consistent offline `.1CD` copy. It does
not open a native session or implement writing, posting, unposting, queries or
transactions. Existing Catalog APIs remain unchanged.

The measured profile supports `Documents`/`Документы`, named/indexed managers,
`EmptyRef`, `GetRef`, immutable references with `UUID`/`IsEmpty`/`Metadata`,
`FindByNumber`, and `Select(start, end)`/`Next`. Header/card fields are Number,
Date, Posted, DeletionMark and Ref, plus five fixed attributes: String32,
Number9.2, Boolean, DateTime and a single typed Catalog reference. The latter can
be traversed to the target Catalog card. Metadata.Documents shares the same
validated CONFIG identity snapshot with the target Catalog namespace.

Only String8 nonperiodical numbering and the two measured five-attribute orders
are admitted. Number lookup is exact for ASCII digit stored numbers (up to eight characters);
unmeasured case/padding/Unicode forms and duplicate matches fail closed. Selection
is chronological and date boundaries are inclusive. Unlike Catalog selection,
Document exhaustion remains terminal and retains the last row. Before positioning,
fields are Undefined. Missing/empty reference cards have typed scalar defaults.
Dynamic reference/manager/selection types compose with Type/TypeOf and equality;
references compose with ValueIsFilled. Unsupported serialization, TypeDescription
consumers and dynamic construction fail rather than exposing Python objects.

## Evidence and remaining gates

Native run `41256261065`, source
`d5a6284b6542f306002cf9cb7f86221d057b55b0`, report SHA256
`a879485a6ae04dccc62e59faf84c41704a71a1c890578a1b48246769ed6331e0`
accepted both generated identity sets and observed 32 blocks over eight captures.
The actual 155-byte Document layout, generated type-to-metadata mapping, regular
Posted=True row and chronological behavior are captured. Its runtime lacked
Documents, so this measurement itself was **not runtime parity**.

Focused replay retains those original programs and native owned CONFIG/data bytes
in synthetic page placement. The raw root declares the baseline NativeOracleItems
catalog, whose descriptor was not captured. An explicitly synthetic auxiliary
baseline descriptor is added only by the transport test, never labeled native.
32 historical blocks match through FileDBContext; fresh UUIDs are compared by
relations, not byte equality. Actual frozen native `.1CD` parity and final platform
checks remain separate gates. Two final header probes clarify empty-string number
lookup without replacing the old captured programs or their golden observations.

## Closed boundaries

Document storage admits zero rows or a reserved zero-free-head plus active rows;
it does not inherit the Catalog deleted-slot chain profile. Exact declaration,
owner graph, UUID binding, file-size and cumulative resource guards remain in force.
`!todo` Physical free/deleted chains and logical DeletionMark=True require Document
witnesses. Equal-date ordering, other numbering/header profiles, composite or
Document-target fields, hierarchy, tabular parts and document presentation remain
unsupported pending their own evidence. GetRef-generated UUID versions are not
claimed to match native UUID version bits.

## Public fixture minimization

The replay fixtures contain only generated disposable-IB object identities,
public platform CONFIG defaults, generated setup values, selected raw rows and
read-only observation programs/results. They are not user database extracts.
Unused installation/helper/admin-audit metadata is excluded from the public
fixture, including audit correlation tokens. The complete original report stays
separate; its digest still binds the measurement provenance. A recursive regression
rejects authentication/session/audit fields in both public fixtures. Removing that
unused metadata leaves every retained CONFIG byte, record byte, program and
observation unchanged and does not change runtime or native measurement sources.
