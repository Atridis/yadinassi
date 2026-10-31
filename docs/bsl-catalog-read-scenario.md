# Read-only catalog scenario — local implementation, native acceptance pending

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

## Current local implementation

- Managers: named/index access, `EmptyRef`, `GetRef(UUID)` and fresh `GetRef()`,
  `Metadata`, zero-argument `Select`, `FindByCode`, and explicitly exact
  `FindByDescription(text, True)`.
- References: immutable catalog identity + record UUID; `UUID` /
  `УникальныйИдентификатор`, `IsEmpty` / `Пустая`, `Metadata`, `Ref`, and
  read-only field dereference for present records.
- Logical fields: `Code`, `Description`, `Ref`, `DeletionMark`, and the existing
  string/numeric attributes under their CONFIG names. Missing physical Code or
  Description in the admitted zero-length profiles maps to an empty string.
- Dynamic types are snapshot scoped and include the catalog metadata UUID and
  object category. Record UUID is not a metadata UUID or a native type GUID.
  Identical record UUIDs in different catalogs do not create equal references.
  `TypeOf(TypeOf(reference)) = Type("Type")`; codec/TypeDescription and dynamic
  constructor consumers explicitly refuse unsupported catalog types.
- Cursor has explicit `Next` / `Следующий` and `Reset` / `Сбросить`; it is not a
  Python iterable masquerading as a native cursor. Synthetic tests establish
  implementation behavior, not native order or boundary semantics.

## Critical remaining native gates

**The production storage reader still admits at most one active record and
rejects nonreserved free/deleted physical slots.** Those guards must remain until
the batched native fixture establishes liveness, empty/deleted-slot encoding and
selection ordering. A logical deletion mark is not physical deletion: marked
records remain active and visible to the reader.

The prepared native batch uses two independent catalog/record identity sets,
empty/one/several rows, deleted-middle and reused-slot states, client/server
contexts, cursor transitions, fields, lookup and type observations. Fresh UUIDs
must remain raw in evidence and be compared by relational properties, never
normalized to fixed UUID literals. Setup writes/query witnesses belong only to
owned disposable native fixtures, not this public runtime.

Still pending: reviewed host/lifecycle integration, saved applied configuration
and redump, independent setup witnesses, immutable image clones, real captures,
physical analysis, runtime replay, and final supported-context decisions. No
native acceptance or multirow completeness is claimed by this document.

## Deliberately bounded/deferred

The existing physical compiler admits flat catalogs with exactly its supported
string and numeric attribute shapes; this is not arbitrary-schema support.
Hierarchy, owner/parent filtering, custom ordering, partial description lookup,
collation/padding and duplicate-match ordering, absent-reference field defaults,
and advanced error/presentation semantics remain explicitly restricted. Relevant
code uses `!todo` markers for the final compatibility pass. Unsupported writes,
query runtime and transactions are outside this block, not hidden fallbacks.
