# Bounded direct form-handler simulation

`simulate_form_event` is an explicit local-only host API. It freshly validates
exact original source and all three metadata byte inputs against the caller's
identity binding on every call. Canonical paths are derived, not read. The caller
must authenticate storage; hashes and UUIDs alone are not authentication.
No public analysis/AST, external sink, receiver, backend, path or runtime object
is accepted. Only Code/Description strings, DeletionMark/Cancel booleans and one
of OnChange/BeforeWriteAtServer are accepted. Exact scalar checks and existing
catalog qualifiers reconstruct a fresh private receiver before execution.

The complete #221 source profile is mandatory, plus distinct handler names that
do not collide with its receiver, parameter, message and builtin symbols. Both
original bodies are validated; the selected original procedure is invoked on
its own logical side through the existing interpreter, without rewriting BSL,
executing module initialization, or crossing client/server marshalling. No
routine names are registered. There is no managed-form event dispatch.

Each call owns a fresh interpreter, private scalar receiver, 256-node execution
budget and a one-record message sink. Reachable functions are only СокрЛП and
СтрДлина; the only constructor is СообщениеПользователю. Builtin namespace fallback
is blocked. The closed source cannot reach DataKey, SetData, dynamic calls, SQL,
files, network or persistence. No constructor or bind_data behavior is expanded.
The exact #217 UserMessageRecord must contain only bounded Text/Field, with empty
DataPath and absent DataKey/TargetID. Messages become frozen scalar DTOs.

The result contains an immutable candidate snapshot, cancellation flag and tuple
of messages. Server cancellation does not adopt or roll back the candidate;
callers may discard it. Deletion-mark early return preserves the input candidate
and cancellation. A failure raises and returns no partial result or messages;
there are no callbacks to retry. Input scalars and any prior result are unchanged.
No DB Write, baseline adoption, transaction, real 1C run, native parity, importer
activation, FormSession integration or GUI navigation is provided or claimed.

The exact source inventory is 125: base 121, three dependency runtime modules,
and this one runner. Eighteen local test methods cover original-body behavior,
closed admission/capabilities, isolation, bounds and failures. Synthetic fixtures
are separate from the original demo smoke; original demo bytes stay unchanged.
