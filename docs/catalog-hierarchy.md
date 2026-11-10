# Hierarchical catalogs

The explicit `groups_v1` catalog profile supports persisted folders and items.
It is an authored bounded contract, not a claim of native-platform parity.
XML admission requires `Hierarchical=true` and
`HierarchyType=HierarchyFoldersAndItems`; flat catalogs retain their existing
schema encoding and APIs. Creating a database containing this profile selects
SQLite v10. Existing databases are not migrated implicitly.

## Objects and persistence

`Catalogs.Products.CreateFolder()` creates a detached folder;
`CreateItem()` creates an item. `IsFolder` is read-only and immutable.
`Parent` is a typed reference to the same catalog. An empty reference denotes
the root. A nonempty parent must identify an existing folder. Assignments are
local until `Write()`. Folders can move with their descendants, but cycles,
foreign references, missing parents, item parents and depth beyond 32 levels
(root objects count as level 1) are rejected atomically. The existing revision,
numbering, transaction and retained-receipt contracts remain in force.
Deletion marks do not cascade or restructure the tree.

References, detached objects and selections expose `Parent` and `IsFolder`.
Russian aliases include `СоздатьГруппу`, `Родитель`, `ЭтоГруппа` and
`Иерархический` on catalog metadata. Flat catalogs do not acquire hierarchy
system fields; previously valid custom fields retain their meaning.

## Queries

`Parent` and `IsFolder` can be projected, filtered and ordered using the usual
query facilities. `Ref IN HIERARCHY (&Root)` includes the root itself and its
persisted descendants. An empty root selects all persisted references; an item
root selects that item. `NOT IN HIERARCHY` and `В ИЕРАРХИИ` are supported.
Operands must be references with the same catalog identity. `Null` follows
three-valued predicate logic. The graph is loaded in the pinned query view and
charged against existing row/cell/byte budgets, including queries through
joins and derived tables. Corrupt or unbounded graphs fail closed.

See [the BSL example](../examples/catalog-hierarchy-report.bsl), intended for
an admitted hierarchical `Products` catalog. Owners, item-only hierarchy,
cascade deletion, arbitrary object events and automatic schema migrations are
outside this profile. SQLite v10 also retains the supported document and
information-register ports.
