# Direct selected source forms

> Historical measurements below that name `compiled-strict` describe a retired
> backend. Current builds use only the direct BSL-to-Python generator.

Selected memory-only source forms now use the existing FormSession,
PreparedHandlers, FormBoundary model protocol and replication/InvocationPort
lifecycle with an exact source-form boundary. This is not a browser/native parity
claim and does not admit arbitrary interpreter subclasses.

The source specialization retains the actual application, family, scheduler,
form/session, logical side and compilation profile. It rejects database authority,
pending asynchronous work, replaced registries and changed declaration signatures.
Used native constructor bindings are revalidated; source declaration constructors
are also checked after argument evaluation. Returned property references expire
with their event boundary. Form procedures remain procedures when used as values.

System form names, attributes, tables and parameters retain precedence over
source exports. Common-module calls and read-only metadata use the existing
source boundary with the actual caller. Existing form attributes/items/commands,
client/server event exchange and byref event output slots remain on their canonical
protocols. Bare form attributes passed by reference retain the existing explicit
limitation; ordinary handler parameters and owned member slots are unaffected.

Every generated same-module routine receives its own safe-mode frame, not merely
an event-level frame. Invocation scopes preserve source transaction/safe-mode
context, module context, transaction-activation denial and the existing form step
budget. Source startup still must finish before form creation, and source forms
still require a memory-only application.

Definition validation uses the same exact source interpreter factory, rather than
silently validating source declarations through a generic form runtime. Temporary
validation children are released even when preparation fails. NoContext bindings
are explicitly rejected before validation session creation: the old NoContext
server contains a VM dispatch path and is not enabled by this slice. Existing
non-source form validation and boundaries keep their original default route.

## Verification and limits

The same 1,228 source tests now report 227 errors and 46 failures, versus 278 errors
and 47 failures before this slice: 52 fewer failing outcomes. The suite remains
red. No test assertion or CI gate was removed. Source NoContext, handler-bearing
objects, general source Execute and unsupported constructors such as TextDocument
remain separate gaps.

Dedicated poisoned-VM tests cover real server creation and client/server command
roundtrips, metadata/common modules, nested routine safe-mode isolation, blocked
filesystem effects, early NoContext denial, closed owners, failed validation
cleanup, stale references, registry/signature changes, foreign form/database
rejection and argument-time constructor rebinding.

Final integration on string parent `f15bf258`: 263 focused tests pass in normal
Python 3.12 and the same 263 pass in Python 3.10 `-O`. An additional explicit
`compiled-strict` NoContext control passes in both modes, confirming that the new
direct-only refusal leaves the legacy route available. Generic direct-form,
source lifecycle/security, Execute/Eval, signature and string regressions are
included in the focused set.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_forms test_python_direct_source_forms_security
```
