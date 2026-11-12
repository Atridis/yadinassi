# Typed input and ValueList choice

This planned application-host block adds a practical way for configuration BSL to
ask for a calculation parameter, date, quantity, reason or one value from a bounded
local list. It does not add a new database profile or automatic persistence.

## Closed scope

- Nonblocking scalar input: one String, Number, Date or Boolean type, with existing
  form qualifiers and scalar encoding. No mixed type chooser, references, arbitrary
  objects, implicit conversion, rounding or truncation.
- Single choice from a bounded ValueList containing scalar values and plain text
  presentations. No pictures, multiple selection or database lookup.
- Same live owner, callback, Scheduler and terminal receipt contract as the owned
  question/warning block. One pending interaction per owner, no reentrant dispatch,
  automatic callback replay or added root transaction authority.
- Separate negotiated typed interaction capability. Existing question/warning and
  legacy client envelopes are not silently widened.
- Retained raw drafts, validation before confirmation, terminal reservation before
  callback, copy-only recovery after an unknown response. No restart recovery claim.

## Boundaries being implemented

ScalarInputSpec holds a detached, bounded editor description and exact initial
value; accepted wire data must retain its admitted type and qualifiers. A list
selection holds an immutable snapshot and opaque tokens bound to original item
identities. ValueList revision alone is insufficient: field changes do not bump it.
Before selection, validate object membership/order and the scalar value,
presentation and check fields. A stale list refuses terminally rather than
retargeting a row index or returning changed data. No item handle crosses the wire.

The host owns enrollment, family generation and callback authority. The primitive
does not introduce another evaluator or callback dispatcher. It releases retained
list/item references after completion or cancellation.

## API and native evidence

Documented APIs are ShowInputValue / ПоказатьВводЗначения with callback, initial
value, prompt and optional Type or TypeDescription; and ValueList.ShowChooseItem /
ПоказатьВыборЭлемента with callback, title and optional initial item. Their completion
descriptions use two arguments. Documentation describes Undefined on cancellation
and a ValueListItem, not just its value, after list choice.

These are documentation inputs, not measured native parity. Before public binding,
measure real input, confirmation and cancellation in the isolated native client,
including callback arity/order, scalar type and exact returned list-item identity.
Never call the completion directly to manufacture native evidence. If a bounded
keyboard driver is used, it may interact only with a verified window of the owned
native process on its isolated display; inability to identify that window is a
closed acquisition failure, not permission to send keys blindly.

Designer acceptance is sufficient for XML layout loading. Authored source,
executable BSL and EPF integrity remain mandatory; a reserialized XML byte or
structural match is not an added gate. Native keyboard/pixel parity, automatic
coercions and list mutation behavior are not promised without observations.

## Verification plan

First test pure primitive contracts and stale/identity boundaries. Then integrate
the existing source-granted host and renderer, add one authored application and
cover repeated confirmation, cancellation, retained sibling drafts and lost replies
in Chromium. Announce exact local/native/browser counts before executing them.
Keep this branch separate from PRs on heavy CI and prepare one complete functional
PR after its prerequisites, rather than one PR per adapter.
