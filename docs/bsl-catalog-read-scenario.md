# Read-only catalog scenario — measured native semantics

This block extends the Metadata API with named `Справочники` / `Catalogs`
managers, immutable references, dynamic reference/manager/selection type identity,
read-only fields, a selection cursor, and exact lookup. It is one feature block,
not separate releases for each method.

```bsl
Manager = Catalogs.Products;
Selection = Manager.Select();
While Selection.Next() Do
    Message(Selection.Code);
    Message(Selection.Description);
    Message(Selection.Ref = Manager.FindByCode(Selection.Code));
EndDo;
```

The name `Products` is illustrative, not an admitted fixture name. Named access
and string indexing resolve CONFIG identities from the same lazy snapshot as
`Metadata.Catalogs`. No database is opened by parsing an untaken branch or by
static `Type("String")`. Actual catalog operations require `FileDBContext` and a
caller-owned consistent offline copy. There is no authentication, live session,
transaction, write API, or query execution.

## Implementation

- Managers: named/index access, `EmptyRef`, `GetRef(UUID)` and fresh `GetRef()` / `GetRef(Undefined)`,
  zero-argument `Select`, `FindByCode`, and explicitly exact
  `FindByDescription(text, True)`.
- References: immutable catalog identity + record UUID; `UUID` /
  `УникальныйИдентификатор`, `IsEmpty` / `Пустая`, `Metadata`, `Ref`, and
  read-only field dereference; absent references return scalar defaults.
- Logical fields: `Code`, `Description`, `Ref`, `DeletionMark`, and the existing
  string/numeric attributes under their CONFIG names. Missing physical Code or
  Description in the admitted zero-length profiles maps to an empty string.
- Dynamic types are snapshot scoped and include the catalog metadata UUID and
  object category. Record UUID is not a metadata UUID or a native type GUID.
  Identical record UUIDs in different catalogs do not create equal references.
  `TypeOf(TypeOf(reference)) = Type("Type")`; codec/TypeDescription and dynamic
  constructor consumers explicitly refuse unsupported catalog types.
- Cursor has explicit `Next` / `Следующий`. Before the first record, fields are
  Undefined; exhaustion returns False while retaining the last record fields.
  The next call restarts the selection. `Reset` / `Сбросить` is unavailable, as
  is `Metadata()` on a manager (use a reference). These are native observations,
  not assumptions derived from Python iteration.

## Native evidence and admission boundary

Native run `41214218572`, source `dd2e8e00c1d24a4bc88e1999592db0e8d8c3d5c4`,
recorded two identity sets × five states × client/server: 20 captures and 3600
scalar observations. The source report SHA256 is
`923a8c3f6e5cb529a4d7ffb864e87398ad831dff3150a95f7f0f81a6468cd7b3`.
Tests retain source-bound native outputs and raw physical slots separately.
Local replay feeds captured slots through production parsing in synthetic
transport; this is explicitly not a retained full-image replay. Final native
runtime parity and the complete source-composition gates remain separate.

The production reader now admits bounded multiple active rows (4096 slot/row
ceiling) with zero or **one** physically free slot. Reserved bytes1:5 name the
free slot; its own bytes1:5 must be zero. Every marker is validated before any
active record is decoded. Unlinked free markers, active heads, out-of-range
heads, cycles and multiple-node free chains fail closed. No arbitrary-chain
allocator claim is made. Logical `DeletionMark=True` remains an active record.

Default multirow selection uses the measured ascending fixed-width digit String
Code profile. Equal codes, arbitrary string collation and zero-code multirow
ordering remain explicit unsupported cases, rather than physical-order guesses.
The cursor is an explicit state machine, not a Python list iterator.

Fresh UUID raw strings remain retained; replay compares relational properties,
never byte equality across independent executions. Setup writes/query witnesses
belong only to owned disposable native fixtures, not this public runtime.

## Deliberately bounded/deferred

The existing physical compiler admits flat catalogs with exactly its supported
string and numeric attribute shapes; this is not arbitrary-schema support.
Hierarchy, owner/parent filtering, custom ordering, partial description lookup,
collation/padding and duplicate-match ordering,
and advanced error/presentation semantics remain explicitly restricted. Relevant
code uses `!todo` markers for the final compatibility pass. Unsupported writes,
query runtime and transactions are outside this block, not hidden fallbacks.
