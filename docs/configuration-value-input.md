# Owned typed input and list choice

A checked configuration form can ask for one scalar parameter or one item from a
local ValueList, then continue through its existing callback and application
Scheduler. This is a bounded nonblocking host service, not native window emulation
or a new database/storage profile.

```bsl
Extra = New Structure("Calls", 0);
Completion = New CallbackDescription("Completed", ThisObject, Extra);
ShowInputValue(Completion, 12.5, "Quantity");

&AtClient
Procedure Completed(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 If Result <> Undefined Then Message(String(Result)); EndIf;
EndProcedure
```

`ShowInputValue` / `ПоказатьВводЗначения` accepts the callback, initial value,
optional prompt and optional Type or TypeDescription. With no descriptor the
initial value must be an exact String, Number, Date or Boolean. Undefined requires
an explicit single scalar descriptor and uses its bounded form default. No union
type picker, reference, arbitrary object, rounding, truncation or type coercion is
performed. Fixed-length String space padding follows the existing form contract.
String uses a multiline editor. Confirming unchanged text preserves the original
line endings; browser-edited text uses LF. Enter inserts a line break and Ctrl+Enter
confirms. Cancel returns Undefined, which is distinct from an accepted empty String/Date,
zero Number or False Boolean.

```bsl
Options = New ValueList;
Options.Add("normal", "Normal processing");
Preferred = Options.Add("urgent", "Urgent processing");
Options.ShowChooseItem(Completion, "Priority", Preferred);
```

`ValueList.ShowChooseItem` / `ПоказатьВыборЭлемента` returns the **original
ValueListItem**, not its Value or a row number. Read `Result.Value` in the callback.
The list is limited to 128 exact scalar items and 32 KiB of public choices. Tokens
are opaque and host-lifetime only. Before accepting, the host rechecks item
identity, membership, order, scalar bytes, presentation and Check. Source drift
retires the prompt without calling its completion. A list mutation subsequently
undone is not promised as a history-tracking feature.

## Owner and transport boundaries

Both completions receive `(Result, AdditionalParameters)` through the existing
trusted callback evaluator. The callback must belong to the current enrolled form.
The synchronous call chain may delegate through source CommonModules, but an
independent child, server activation, async task, retired or foreign family cannot
borrow that form's authority. No form state is copied into common modules and no
root transaction controls are granted.

One owner may have one pending child form, question/warning, or typed input, never
two at once. Callback reentrancy cannot enqueue another interaction. Admission and
terminal reservation happen before delivery; the host never retries a callback.
The separate `yadinassi-owned-input/1` capability carries only exact scalar/editor
packets or opaque choice rows, not callbacks, list objects or runtime references.

The renderer validates locally, preserves unsubmitted drafts, fences repeated and
retired controls, and treats Escape as explicit cancellation. If a confirmed
answer's response is lost, the application locks; retained raw input is copy-only.
There is no automatic retry, implicit save, session transfer, or recovery of these
pending callbacks after host restart. A browser reload restores authoritative
pending descriptors, not unsent raw DOM text.

## Example and evidence

`examples/configuration-value-input` asks for quantity, date, reason and priority
while retaining the existing owned-details workflow. Use the application-host CLI
as for `examples/configuration-dialogs`, with the new example as the source.

Native acquisition is separate: eight real input/list actions are prepared with
an isolated, owned-window controller. Until their observations are collected and
reviewed, documentation and local tests do not establish native button, keyboard,
focus, cancellation or callback-timing parity. Unsupported native coercion and
window options remain outside this host subset.
