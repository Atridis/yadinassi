# Direct main-demo process: first full cancellation flow

The original test
`test_main_demo_application_process.ConfigurationApplicationExampleTests.test_example_start_commonmodule_openform_servercall_and_exit`
now passes against the actual owned child process with direct default:

* Create/reopen the real 47-file main-demo SQLite configuration.
* Client/server startup, expected common-module messages and server call.
* Open DemoWelcome, invoke ShowDetails and open OperationDraft.
* EditDraft opens DraftDetails with a detached scalar parameter snapshot.
* Cancel the child, deliver the owned callback, retain the owner, close forms
  and the application. Database bytes are unchanged.

An additional real-process regression also covers AcceptDraft → ConfirmDraft →
Yes: AppliedCount becomes 1, repeating the same Yes response is rejected without
applying twice, and database bytes remain unchanged. This does not establish
posting, arbitrary callbacks, every button or document editing.
The original main-demo runtime suite now has 12 passes, including source-bound
Receipt posting and a query of the resulting accumulation movements. Arbitrary
document modules and every transaction scenario are not thereby certified.

## Mechanisms

CallbackDescription constructs only an enrolled client self-form capability via
the existing capture/target validation. Completion uses generated source handlers
rather than scheduler/dispatch_callback. Revision, one-shot, parent/child and
family lifetime checks stay with the existing host protocol. A stale function
closure is never stored in the callback.

The replicated client's field schema arrives after declaration preparation.
Only a changed set of validated static/table names triggers re-preparation of an
owned declaration snapshot. No renderer-provided source is accepted and ordinary
value changes never trigger compilation.

Native Structure crosses only scalar parameter/result boundaries. Parameters
remain a detached readonly FixedStructure; callback output for a direct owner is
a fresh native Structure. There is no general graph converter or alias scanner.
Legacy decoding and execution remain explicitly selectable.

Registered Query construction and public Execute/Select/Next/field reads also
work directly. Existing query execution and backend integrity checks are reused,
not interpreted by a VM. Source-bound document posting is covered by the subsequent posting slice;
arbitrary register and query Unload ValueTable protocols remain unsupported.
