# Bounded source XDTO object trees and lists

The subsequent [string-only XML capability](direct-source-xdto-xml-strings.md)
adds staged IO for these graphs. The IO exclusions below describe this original
object-tree slice, not a grant for general XML or JSON operations.

This extends the global source factory's flat-object capability, not the local
empty-factory capability. Current package object types may contain nested object
properties and bounded lists of the previously admitted scalar types or object
types. The whole reachable descriptor graph is admitted, with no inheritance,
new scalar families, generic receiver access, or XML/JSON IO.

Direct named properties retain exact spelling. Nested values must be objects
created through this application's guarded global factory and match the declared
type. Canonical native attach/detach semantics prohibit shared ownership and
cycles; assigning the same object to its existing slot remains a no-op. Variable
aliases to attached children remain valid. Unset detaches children for later
reattachment. Object descriptor introspection remains unavailable.

Lists support Count, Get, GetXDTO, Add, Insert, Set, Delete and Clear, with native
numeric indexing and bounded iteration. Scalar reads yield native values while
native XDTO-valued mutation results retain scalar provenance. A list property is
created lazily and charged once. After Unset removes its property, a retained old
list handle remains readable and empty but cannot mutate or attach children. A
new read of the property creates a separate current list.

Private application-owned object/list records retain identities, containers,
entries, scalar fields and reciprocal ownership. They are checked before native
traversal and before/after argument evaluation. Only the known successful mutation
footprint is resealed; unrelated host mutation cannot acquire provenance.
Records are released on application close and bounded by cumulative allocation.

Node and unit budgets use the tighter active native aliases. Object creation and
lazy lists cost one node; primitive list insertion costs both a scalar node and
an entry node; object insertion costs an entry node. Replacement does not allocate
an entry; deletion, Clear and Unset do not refund previous allocations. Failed
conversion, ownership, capacity or quota checks preserve state and accounting.

XML/JSON readers, writers and serializers are not included. This is a source
boundary capability, not a sandbox against replacing trusted Python internals.
No VM fallback or new real-1C parity claim is introduced.

Iteration uses the native entry snapshot. An iterator acquired before Clear or
Unset may still yield those now-detached children; a newly acquired iterator of
the orphan list is empty. Every yield still revalidates the application and
private inventory. Creation also verifies the current inventory before spending
allocation quota. Public scalar wrappers reject malformed field maps before any
attribute lookup.
