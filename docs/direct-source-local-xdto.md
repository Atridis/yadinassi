# Source-created empty XDTO factories

This bounded ordinary-source slice adds zero-argument `New XDTOFactory` /
`Новый ФабрикаXDTO`. Each factory starts with its own primitive descriptors and
has no source-package loader. An unknown source namespace returns Undefined.
Creating one does not replace or copy the application's global source factory.

The existing scalar Type/Create/Value slice applies: string, boolean, decimal,
integer, int and long. Descriptors and produced scalar values retain their
factory identity. Foreign applications, other factories in the same application,
and host-created factories do not gain admission. Packages, schemas, object
properties, XML/JSON IO, date and binary creation remain outside this capability.

Factory lifetime is bounded by its source application. Calls revalidate the
current ordinary source boundary, canonical hooks, registration, descriptor
identity and allocation accounting before invocation. Activation-bound closures
cannot be used after their boundary ends. Private application-owned canonical records pin factory and descriptor identity.
The public-facing marker is not the authority for owner, graph or accounting.
At most 32 factories are intentionally retained until application close; closing
releases those records. Scalar values are not retained by this factory registry.

At most 32 local factories may be created cumulatively per application; dropping
or collecting a factory does not refund this quota. Scalar node/unit allocations
are also cumulative across all local factories of that application, bounded by
the tightest existing scalar allocation aliases. Failed conversion must not spend
allocation budget. The global source factory retains its existing separate
allocation budget; this slice does not alter its package-loading contract.

Implicit routine-local assignment may shadow precisely the two factory namespace
aliases, using the existing source shadow rules. Before assignment the global
namespace remains readable. Explicit Var/parameters/module/exported slots retain
their existing meaning. Late export conflicts and Execute/Eval combined with
implicit shadowing remain rejected rather than weakening lexical guarantees.

No generic receiver grant, database/file/network capability or VM fallback is
introduced. These checks are not a sandbox against arbitrary replacement of the
entire trusted Python environment.
