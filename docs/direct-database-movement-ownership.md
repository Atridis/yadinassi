# Direct database movement ownership

Direct execution admits native recorder and accumulation collection, set and row
receivers only while they belong to the current interpreter's live database host.
This is a live capability, not a detached-value whitelist.

Constructor-issued weak provenance is checked alongside the current document,
manager, metadata, schema, context, database identity and configuration generation.
Every register set and row must remain in its original owner's current inventory.
Coherent mutable backlink rewrites do not transfer authority. Clearing a set
revokes old rows; replacing a collection revokes retained handles. A second
interpreter cannot borrow these receivers even when it shares the database context.

Saved native methods are revalidated before invocation, including after argument
evaluation. Public protocol hooks and receiver state are checked before native
callbacks. Native row budgets, mutation rules, uncertain-commit restrictions and
posting transaction requirements remain in force. In particular, selecting a
set with its `Write` property does not authorize calling `Write()` outside a
posting transaction. There is no legacy VM fallback.

The capability covers exact native recorder/accumulation families and the
canonical accumulation record-type namespace in an accumulation posting profile.
It does not grant generic database receiver access or foreign host callbacks.

Generated posting handlers now use writer-owned loop-header checkpoints. The
counter is shared across handler events in the same activation; exceeding
`MAX_STEPS` raises the native uncatchable `PostingLimitError` and the existing
writer rolls the operation back. This is a generated-loop budget, not exact
legacy AST-step counting or full recursion-depth parity. It does not grant
transaction-control services to ordinary direct execution.
