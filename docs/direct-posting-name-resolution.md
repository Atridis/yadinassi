# Generated posting name resolution

Posting modules have two distinct bindings for built-in names that also name
document properties. Reading `Number` or `Date` reads the document property;
calling `Number(...)` or `Date(...)` uses the posting interpreter's built-in
service, as in the native posting adapter. Parent interpreter host-function
registrations are not inherited.

The generated compiler's posting-only trusted binding profile initializes
lexical slots needed by dynamic qualified-call arguments. Missing values use
the existing language missing-name error instead of leaking a Python
`NameError`. This does not expose database namespaces, transaction functions as
values, or arbitrary host objects. Existing source and standalone compiler
profiles retain their previous contracts.

The prepared posting cache key includes its binding profile and callable
external-name allowlist. Ownership, transaction admission, rollback and posting
loop checkpoints are unchanged.

A module routine whose own name collides with an external document property is
still rejected during compilation. This slice does not change that admission
rule; ordinary helper routines and local/parameter shadowing remain supported.
