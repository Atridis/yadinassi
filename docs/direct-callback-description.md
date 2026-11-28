# Passive direct CallbackDescription constructor

The public python-direct compiler accepts `New CallbackDescription` and
`New ОписаниеОповещения`. The immutable identity value stores handler name,
opaque target and additional data. Construction never resolves a handler,
reflects on the target, captures a module capability, schedules work or runs code.
Additional data retain identity. Bilingual readonly properties, String and
TypeOf are supported. Optional undefined slots are accepted; nonempty error
handler options remain explicitly unsupported.

This slice intentionally does **not** implement RunCallback. Existing legacy
callback dispatch uses interpreter call_routine/yield, module export resolution
and form enrollment. There is not yet a narrow canonical direct callback target
entry to reuse without introducing new authority. This patch does not connect
that old dispatcher, add async work or authorize arbitrary host targets. A stored
target is data, not permission to invoke it. Legacy callback classes are unchanged.

The old bilingual constructor test still fails on standalone `ThisObject`
lookup before construction, a separate unavailable module-context contract.
It is not declared fixed. New focused tests use explicit Undefined or an already
supplied opaque target, verify no handler runs, preserve extra identity, check
readonly/private access, and verify RunCallback remains denied.
