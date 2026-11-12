# Owned form results: bounded application-host contract

This is an opt-in, host-lifetime interaction for checked configuration application
families. It uses the existing form interpreter, callback dispatcher and Scheduler.
It does **not** claim native modal/window/uniqueness behavior, arbitrary OpenForm
options, or exact native callback timing. The native acquisition route is separate;
a locally authored source or a browser test is not native evidence.

Run the small authored application:

```sh
python -m yadinassi.ui.configuration_app examples/configuration-form-results --application-host --browser-session
```

The example has an editable **Owner value**, **Open chooser**, an editable **Result text**,
**Use value**, and **Keep chooser open**. The checkbox refuses the ordinary close
lifecycle without delivering a result. Completion reports its in-process count.

The source inventory includes the application module and both declared CommonForms.
The same bounded interaction works with a catalog or non-posting document owner in
`--business-application`, and with the existing reference application family. No
source importer, storage marker, transaction authority, or database format changes.
The dedicated posting application is **not enrolled**. Its retained receipts and
uncertain-outcome guards are unchanged. Standalone/form-only launchers are not
implicitly upgraded.

## Source-level calls

A live client form event may open one owned, declared CommonForm:

```bsl
Extra = New Structure("Calls", 0);
Completion = New CallbackDescription("Completed", ThisObject, Extra);
OpenForm("CommonForm.Details", New Structure("Message", "Choose"), ThisObject,
 Undefined, Undefined, Undefined, Completion);

&AtClient
Procedure Completed(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 // Apply a bounded result to this owner. Explicit existing server calls may Write.
EndProcedure
```

The complete call has exactly seven arguments. The three intermediate options must
be explicit `Undefined`. Non-Undefined uniqueness/window/navigation, omitted holes,
an eighth argument, a missing owner/completion, undeclared targets and business
object forms as owned targets are rejected, not ignored. The original unowned
`OpenForm(name[, parameters])` remains available. Parameters use its existing
bounded scalar Structure copy, not a new wire format.

`CallbackDescription` (`ОписаниеОповещения`) retains the exact public `Module =
ThisObject` identity. An internal sealed target binds that receiver to its live
form enrollment, application family and generation. This does not accept arbitrary
BSLObject receivers or expose a generic Module in place of the form. The completion
must be an exported synchronous client Procedure with exactly two parameters.
Functions, non-exported/server/NoContext/dual/async routines are outside this slice.
AdditionalParameters retains ordinary in-process object identity. It is not a
form attribute, serialized payload or cross-process value.

Inside the owned CommonForm, a successful ordinary client event can request:

```bsl
Close(New Structure("Text", MessageText));
// ThisObject.Close(result) uses the same host path.
```

`Close()` / `Close(Undefined)` and the normal renderer Close deliver Undefined when
accepted. Results are Undefined, Null, Boolean, Number, String, Date or a flat Structure/
FixedStructure of those scalar values, up to 32 identifier fields and 65,536 encoded
bytes, also subject to the existing scalar codec limits. The host detaches the
result at the Close call. Later changes to the original Structure do not alter it.
Nested collections, references, callbacks and form/object capabilities are refused.
A received FixedStructure is normalized to a detached Structure.

Close is queued, not a synchronous destroy primitive. A following handler failure
or a second Close request discards that event's close intent. Programmatic Close in
opening/closing lifecycle handlers is explicitly unsupported. OpenForm and Close
from a completion are explicitly rejected, including indirect calls; no recursive
completion chain is silently scheduled. An owned child may open its own single
child during an ordinary client command. The existing form/session budgets bound
the forest.

## Lifecycle and ownership

1. The initiating owner event finishes successfully before the host creates the
   child. Opening failure/cancellation retires known allocations without completion.
2. A live child locks its owner's business events, reference selection and Close.
   Snapshot/hello remain readable. There is no cascade discard or modal-window claim.
3. Accepted Close runs the existing BeforeClose and OnClose lifecycle. BeforeClose
   refusal leaves the child and owner lock intact and drops the proposed result.
   A later plain Close therefore does not reuse a refused result.
4. The server's ordinary close and retirement acknowledgements precede delivery.
   Missing/malformed/unknown acknowledgements lock the family and never replay.
5. A retained owner gets one trusted completion event through the existing
   `call_routine`/Scheduler path, with ordinary event revisions and execution budgets.
   Host-only replica synchronization admits pending owner state before completion
   and partial/result state afterward. It invokes no handler and performs no
   implicit Write. The existing source/object guards still run on the server.
6. A known callback failure is terminal even after partial mutation or explicit
   Write. The owner snapshot reflects actual retained state; visible business lists
   refresh authoritatively. There is no rollback promise. Refresh/snapshot never
   reruns completion. Unknown sync or interruption locks the family, without retry.

Terminal delivery/opening-failure records release callback/VM/enrollment/result
references and retain a bounded identity/state tombstone. Uncertain or not-yet-
delivered records keep the necessary envelope. Retired owners and changed generation/
enrollment cannot receive the callback. All state is host-lifetime only; restarting
the host does not restore a durable callback envelope or authorize replay.

## Renderer contract

The existing `yadinassi-configuration-app/3` envelope is retained. Every response
from an enrolled family has `updates`, including `[]` on empty hello/snapshot.
Legacy launchers omit it. Family session descriptors have exactly:

```text
{id, entry, title, owner: null | opaque_session_id, blocked: Boolean}
```

`updates` contains only final authoritative snapshots for retained live owners:

```text
[{session: opaque_session_id, form: existing_form_jsonrpc_response_with_id_1}]
```

No callback, AdditionalParameters, result packet, handler name, source or persistent
record/database identity is exposed. The browser cannot select an owner or callback.
Only existing opaque form/session capabilities are used. Each owner appears once;
if it is the request's own `result.session`, its final `result.form` replaces the
older response instead of also appearing in updates. Newly opened forms obtain
current snapshots through normal hello mounting, not unsolicited stale updates.

The frontend applies owner updates before unlock/repaint, without a new RPC. Raw
uncommitted drafts whose authoritative value is unchanged remain in their inputs.
Conflicting raw drafts remain copyable in the existing recovery view, with business
actions locked until explicit authoritative refresh. It does not silently replace
or discard those drafts. A known partial callback failure is `completion_failed`
with an `event_failed` owner snapshot; unknown outcomes remain `outcome_unknown`.
