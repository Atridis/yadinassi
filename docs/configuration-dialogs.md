# Negotiated nonblocking form dialogs

This bounded application-host slice lets checked configuration forms ask a user a
question or display a dismissible warning, then continue through the existing BSL
callback dispatcher and Scheduler. It is not a second evaluator, synchronous browser
`confirm`, native window emulation, or a root transaction capability.

The documented English names are **ShowQueryBox** and **ShowMessageBox**, with
Russian aliases **ПоказатьВопрос** and **ПоказатьПредупреждение**. The invented
ShowQuestion/ShowWarning global aliases are not installed. The example's local
`ShowWarning` procedure is just its declared button handler, not a global service.
Native acquisition is separate. Documented signatures are not themselves evidence
of native GUI timing, timeout/default handling, Escape, Enter or window-close parity.

## Closed source API

```bsl
Completion = New CallbackDescription("Answered", ThisObject, Extra);
ShowQueryBox(Completion, "Continue?", QuestionDialogMode.YesNoCancel);
// Optional title uses only these explicit positions:
ShowQueryBox(Completion, "Continue?", QuestionDialogMode.YesNoCancel,
 Undefined, Undefined, "Confirm");

&AtClient
Procedure Answered(Result, AdditionalParameters) Export
 If Result = DialogReturnCode.Yes Then
  // An explicit source action, not implicit saving by the dialog host.
 EndIf;
EndProcedure
```

Supported QuestionDialogMode members: OK, OKCancel, YesNo, YesNoCancel. Results are
exact immutable DialogReturnCode members OK, Cancel, Yes, No, not strings/numbers.
Russian namespaces/member aliases are available. Type/TypeOf recognize both value
types. Internal serialization, generic scalar wire transport, enum numeric values,
iteration and presentations are not inferred or enabled by this block.

Warnings have a **one-argument** callback:

```bsl
Completion = New CallbackDescription("Dismissed", ThisObject, Extra);
ShowMessageBox(Completion, "Review this notice");
ShowMessageBox(Completion, "Review this notice", Undefined, "Notice");

&AtClient
Procedure Dismissed(AdditionalParameters) Export
 // There is no result parameter for a warning.
EndProcedure
```

This first host contract requires a callback even for warnings. Both callbacks must
be exported synchronous client Procedures targeting the exact enrolled ThisObject.
AdditionalParameters preserves ordinary in-process identity; it never crosses the
wire. Public RunCallback and owned-form Close completion retain their existing
two-argument contracts. Only the trusted warning path selects one argument.

Only the shown arities are admitted. Explicit non-Undefined timeout/default-button
values, omitted argument holes, extra timeout-result/options and other modes are
rejected, not ignored. Text is plain Unicode, up to 4,096 characters; title up to
256. Invalid surrogates and control characters except newline/CR/tab are rejected.
No HTML, executable source, secret data or external resource is loaded by a dialog.

## Lifecycle

- The call requires an ordinary active client event of a live enrolled form and a
  renderer that negotiated this capability. Application startup, idle/server calls,
  opening/closing lifecycle events and non-enrolled posting/standalone hosts cannot
  create dialogs. A client CommonModule may delegate the call from the current form
  with that form's valid sealed callback. It gains no independent form authority.
- The source call returns immediately. Its dialog is published only after the
  initiating event succeeds. A following error or second request drops unpublished
  work. There is one dialog per owner, at most eight simultaneous family dialogs and
  256 issued tickets for a host lifetime.
- The requesting owner's business actions, reference selection and Close are paused.
  Snapshot reads remain available. A live owned child and a pending dialog cannot
  both occupy that owner. Other owners are not granted or denied authority by this
  lock. A renderer may choose a single app-level prompt/focus trap as UI policy.
- A response must match the exact opaque ticket, owner, enrollment, family generation
  and admitted choice. Invalid choices/foreign tickets do not consume it. A terminal
  ticket never dispatches again, including a different late answer.
- Delivery reuses the existing trusted completion event gate, execution budgets,
  revision handling and before/after replica synchronization. There is no implicit
  Write or rollback. Explicit callback writes and partial mutations remain real even
  if a later statement fails. The final owner snapshot/list is authoritative.
- OpenForm, Close and another ShowQueryBox/ShowMessageBox during completion are
  explicitly rejected in this first slice. There is no implicit native callback
  chaining. Known terminal receipts release callback/AdditionalParameters references.
- Unknown transport/sync or interruption locks the family and retains the in-process
  envelope. No automatic retry, repeat callback or restart recovery is offered.

## Wire opt-in

First hello may add exactly:

```text
{protocol:"yadinassi-configuration-app/3", dialogCapability:"yadinassi-owned-dialog/1"}
```

Negotiation is immutable. Forms-only/posting renderers may negotiate and receive an
empty dialog list, without gaining application-family source authority or changing
their legacy session/updates shapes. Without negotiation, response shapes are unchanged and
source dialog calls fail before enqueue, so a legacy client cannot leave an unseen
prompt. Opted-in responses always include these **top-level result** fields:

```text
dialogCapability: "yadinassi-owned-dialog/1"
dialogs: [{ticket, owner, kind, title, text, choices}]
```

The ticket is unpredictable 32-character lowercase hex, host-lifetime only. `kind`
is question or warning. Choices are closed wire strings `ok/cancel/yes/no`, or just
`dismiss` for a warning. Session `blocked` then means an owned child **or** a pending
dialog; legacy session shapes and the existing owned-form `updates` remain intact.

The response command is `application.answerDialog` with exactly
`{session, ticket, answer}`. The browser supplies no revision, handler, callback,
receiver, AdditionalParameters, source or durable database identity. The final owner
snapshot is `result.session/result.form`, not a duplicate owner entry in updates.

Finite errors: `dialog_pending`, `dialog_refused`, `dialog_retired`,
`retired_session`, `completion_failed`, `outcome_unknown`, plus existing application
errors. Known partial callback failure has nested `event_failed`; unknown state has
`outcome_unknown`. Snapshot and late response handling never replay source work.

## Authored example

```sh
python -m yadinassi.ui.configuration_app examples/configuration-dialogs --application-host --browser-session
```

The example opens **Confirmation workflow** with **Owner draft**, **Ask confirmation**,
**Show warning**, **Last answer**, **Total completions**, and the retained
**Open chooser** owned-form flow. Yes applies `Approved value`; No/Cancel and warning
dismissal preserve the owner draft. Completion messages demonstrate the same
AdditionalParameters object and one callback per ticket. Renderer draft conflict
recovery remains the existing explicit policy, not a promise of native modal parity.
