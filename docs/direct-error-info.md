# Direct ErrorInfo snapshots

The direct handler kept its own activation-local error stack, but ErrorInfo still
read the unused VM stack and returned an empty snapshot. The canonical service now
observes the same lazy direct error record as ErrorDescription. This does not run
a VM handler or change transaction admission.

Exact BSLErrorInfo scalar fields are read-only in direct BSL: Description, Code,
AdditionalInformation, Cause, ModuleName, LineNumber and InitialString (Russian
aliases too). Reads inspect raw canonical data with exact field type validation;
subclasses and malformed fields do not gain host attribute callbacks. Category
methods and extended Raise forms are not certified by this slice. Saved snapshots
remain values after the handler ends; no exception traceback is added to them.

Same-side helpers inherit diagnostics, a logical server call starts fresh, and
Eval does not see the caller's ErrorInfo. Nested handlers clear stale outer state,
rethrow retains the original snapshot, silent handlers do not format errors, and
custom host service replacements retain their own behavior.

The inventory-period replay still refuses BeginTransaction in cases13/14; it now
reports the actual reason instead of an empty description. On the earlier head,
that replay stopped at a missing ValueTable.Columns iterator before reaching those
cases. This is not a new numeric regression or a license to relax transaction
security.

Safe direct transaction support needs a separate owned execution-token lifecycle:
root admission, per-boundary token/backend identity, unwind on BaseException,
unclosed transaction rollback, uncertain-commit resolution, and consistent import,
source-handler and server-crossing denial. The current direct blanket guard is
not removed here. Async/pending tasks and existing caller admission stay unchanged.

Definition-time class, raw storage and default-category identities are captured
before host integrations can rebind public aliases. Direct snapshot construction
uses that raw storage, not a late public constructor or empty-info factory.
A fresh-process regression verifies that public alias/factory rebinding calls no
foreign constructor. Independent review repeated the diagnostic cohort; all new
checks passed, with only the separately reproduced baseline array diagnostic-text
mismatch in the broader experimental tests.
