# Direct live metadata capability

The direct interpreter exposes the current SQLite-backed metadata graph as a
read-only capability. This is separate from detached source metadata even where
native collection classes are shared. Routing requires constructor/publication
provenance, not merely a matching class or the absence of a detached-source seal.

Admitted families are catalog, document and information-register collections and
objects, declared attributes and tabular sections, and the separate standard
attribute-description collection. Native ordering, bounds, name lookup, method
availability and read-only rules remain in force. Standard descriptions do not
acquire `MetadataObjectCollection` methods such as `Find` or `Get`.

Every access validates the current interpreter root, database context and
snapshot generation, original receiver links, reciprocal membership and public
protocol hooks. Foreign receivers from another interpreter cannot be borrowed,
even when both interpreters share a database context. Closed contexts, replaced
children, forged lazy caches and noncanonical callback substitutions are denied.
Lazy publications refresh only their expected fields. Iterators, saved methods
and reference slots revalidate ownership when used, including after argument or
loop-body effects. Ordinary read-only assignment errors retain RHS evaluation.

There is no generic database receiver grant, transport/serialization grant,
write capability or legacy VM fallback. Existing detached source metadata remains
an independent capability. No-database namespace fallback and imported/server
activation support are not expanded by this slice; in particular, the native
ability to shadow the `Metadata` name must not be lost through unconditional
external-name registration.
