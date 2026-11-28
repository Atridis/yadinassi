# Direct source nonposting documents and sections

The direct source storage bridge now admits exact owned document managers,
objects, selections, references, sections and rows. It uses the existing
SourceDocumentCall and SourceDocumentSectionCall protocols with the actual
caller. No AST dispatch or interpreter construction is used for this slice.

Supported operations include explicit document creation, field assignment,
Read/Write, GetObject, selection, section Add/Get/Count/Delete/Clear, indexed
rows, iteration, saved methods and by-reference row fields. Whole document and
section bundles still use the canonical transaction writer and its revision,
mandatory-field, aggregate-size and lifecycle checks. Caller-owned transactions
remain caller-owned; failed bundle writes retain the original rollback behavior.

Documents remain nonposting. Write modes and posting are not enabled. Object
modules are rejected before creating the legacy specialized interpreter. A
legacy-attached object is also rejected when encountered through a saved object,
section, row or callable, before writing. Existing legacy backends are unchanged.

The adapter validates canonical source reference type, metadata snapshot and
absence of callbacks even for neutral reference members. Sections and rows are
revalidated on each access and invocation; Read/Clear/Delete invalidate old
buffers using the existing lifecycle. Captured call markers cannot be retargeted
between admission and invocation.

Dedicated poisoned-VM tests cover roundtrip persistence, selection and references,
byref rows, shared catalog/document rollback, failed aggregate writes, stale
methods/buffers, mutation during iteration, early posting-mode rejection and
legacy-attached/foreign capability denial. No real 1C run is claimed.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_documents \
  test_python_direct_source_document_guards \
  test_python_direct_source_document_security
```

## Verification

On SearchDirection parent `d747262b`, 365 focused tests pass under Python 3.12
and the same 365 pass under Python 3.10 `-O`. This includes direct startup,
Query/storage, document/section, security and the current string regressions.

The unchanged 1,228-test source discovery remains red: 332 errors and 49 failures,
compared with 423 errors and 49 failures before this slice (91 fewer errors).
An initial 133-test document-focused run had 132 passes; its remaining case
requires a catalog handler module, explicitly excluded from the direct backend.
Remaining source families include specialized forms, manager-module routing and
handler-bearing source objects. No assertion or CI gate was removed.
