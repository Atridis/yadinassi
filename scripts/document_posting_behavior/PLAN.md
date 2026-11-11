# Isolated document-posting observations

Status: acquisition plan, not recorded observations or parity evidence. No
production database or existing native fixture is modified. A new source-bound
host/stage route must use the existing Docker lifecycle, fresh NativeSmoke
infobase, official XML import followed by redump/signature verification, fixed
nonce, bounded output and verified cleanup. Do not alias the catalog case.

Exactly 12 sequential cases, each on a fresh owned document unless explicitly
reusing the prior recorder:

1. Ordinary Write on a new document: handler trace, persisted Posted and rows.
2. Posting a new document without marking the movement set for writing.
3. Posting with movement set marked for writing and two rows.
4. Reposting that recorder with one different row: replacement versus append.
5. Reposting with an empty marked movement set.
6. UndoPosting: handler trace, persisted Posted and remaining rows.
7. Ordinary Write on an already posted document, without altering movements.
8. Explicit movement-set Write inside posting without the automatic-write flag.
9. Two explicit writes for the same recorder inside one posting handler.
10. Cancellation in BeforeWrite and Posting, recording separately which phase ran.
11. Exception after explicit movement write: check whole operation rollback.
12. Post then rollback an outer transaction: inspect document and recorder rows
    from a new transaction after rollback.

Capture trace events for BeforeWrite, Posting, UndoPosting and OnWrite with the
visible write mode/Posted at each boundary. Output canonical typed scalar fields
only, numbered records, entered/completed witnesses and source/configuration
hashes. Never turn unexpected observations into expected results automatically.

Metadata prerequisite: canonical platform-accepted Document with Posting enabled,
its ObjectModule, and a nonperiodical recorder-subordinate InformationRegister
with the explicit document recorder declaration. Obtain/review the actual XML
and handler signatures before enabling dispatch; existing independent-register
XML is not evidence for this profile. Rights are confined to these owned objects.

Execution route: a new branch-limited pull_request workflow invokes
native_1c_document_posting_profile.py and its separate posting probe/stage. It
uses the existing pinned image/lifecycle with no network, nonroot, read-only
root filesystem and a fresh tmpfs infobase. The XML is an authored candidate,
not claimed as a known-good platform export; Designer import and exact redump
must succeed before any behavior is accepted. No existing workflow is changed.

Metadata syntax was inspected read-only in public XML at
https://github.com/vanessa-opensource/add/tree/2deeed6636dfbb84f42ae625fd40c8ab662bb64e/lib/CF/83xdd
(specifically Document RegisterRecords and RecorderSubordinate properties).
Fixture identities, modules and scalar observation data are newly authored.

## Acquisition extension: collision/control

Cases 1–12 use disjoint case-scoped dimensions so setup does not assume that
recorder ownership implies global dimension-key independence. Case 13 then
intentionally writes dimension 303 already owned by case 3, while case 14 uses
an otherwise equivalent marked movement with the unique dimension 1403. Both
outcomes are recorded, not asserted in the measurement route. A failed write
with successful readback is an observation, not a fabricated successful write.
Missing documents are observed through a bounded Posted-by-Ref query, not by
assuming GetObject returns Undefined or treating arbitrary read errors as absent.

Roundtrip validation is a material semantic projection, not byte XML parity.
