# Bounded source XDTO scalars

The ordinary exact source boundary exposes its current application's
`XDTOFactory` / `ФабрикаXDTO` for `Type(uri, name)` and `Create(type, value)`.
The supported returned type is a primitive or direct package alias of string,
boolean, decimal, integer, int or long. A created scalar DataValue exposes only
readonly `Value` / `Значение`. Existing scalar conversion/resource limits apply.

This is not generic object dispatch. Object creation/properties, Packages,
XML/JSON methods, date/binary scalar creation and standalone `New XDTOFactory`
are not admitted. Forms/object-handler/NoContext subclasses do not gain this
source capability. A foreign factory, descriptor or value is not reusable in a
second application. Saved method calls revalidate ownership before argument
execution and again at invocation.

The first BSL access requires the initial primitive factory. A factory whose
package inventory or packages were already loaded directly by host Python before first BSL access is
explicitly unsupported in this slice. Once admitted, canonical lazy package
loading preserves existing descriptor identities. The existing closed import
closure, resource budgets and atomic candidate publication remain in use; no
network/schema resolver is introduced. Public XML APIs remain unavailable even
though the package loader internally uses its canonical bounded XML reader.

Definition-time guards cover the relevant loader, descriptor and reader class
and helper bindings before callbacks. Private seals track the current registry
roots, descriptor graph, source inventory and allocation accounting. New scalar
values retain their own field identity. Mutation/replacement, stale or closed
ownership fails closed rather than accepting an apparently similar descriptor.

Lowered allocation aliases are checked against the tightest effective cap before
reservation. Inconsistent lowered descriptor/package-count aliases are rejected
before loading, so a post-check cannot discover the tighter cap only after an
atomic loader publication. Existing per-resource, per-batch and cumulative byte
limits retain their respective roles.
