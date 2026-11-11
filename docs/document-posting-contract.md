# Recorder posting: bounded measured contract

Measurement: GitHub run 42948065433 attempt 1, 1C 8.3.27.1508,
source tree 2b5584da27a9b5b4e35206956e437fec9e137777. Fourteen observations
are preserved under `tests/fixtures/document_posting`. This is acquisition,
not a claim that the runtime already matches the platform.

For the owned nonperiodic scalar recorder register and document fixture:

- Ordinary first Write calls BeforeWrite then OnWrite, both seeing Posted=False.
- Posting calls BeforeWrite, OnWrite, Posting. OnWrite and Posting see Posted=True.
- Unposting calls BeforeWrite, UndoPosting, OnWrite. UndoPosting still sees
  Posted=True; OnWrite sees False. Persisted movements are removed.
- Unmarked, unexplicitly-written movement sets are not persisted by posting.
- A marked set is written automatically; explicit set Write also persists it.
- The same document object's in-memory movement set survives its next Write.
  Reposting after adding a row retains the previous rows; doing no Add is not
  Clear. These observations do not establish loading behavior for a new object.
- Two explicit set writes replace the owned recorder partition, not append it.
- Ordinary Write of an already posted document retains Posted and movements.
- Cancellation, an exception after explicit movement Write, and outer rollback
  leave no persisted new document or movements in the measured cases.
- Equal dimension keys in two recorder partitions conflict (case 13); the paired
  unique-key control succeeds (case 14). Recorder ownership does not imply
  independent dimension uniqueness. Resources do not form the dimension key.

Fresh-only runtime activation is separate from existing v11/v12 profiles. No
implicit migrations or additive updates are allowed until historical recorder
receipts are explicitly supported. Privileged/real-time posting, periodic and
accumulation registers, and unmeasured handler families remain outside scope.
Unknown or failed setup/readback/query cases are not accepted as successful
measurements. Cosmetic Designer XML defaults are not byte-parity requirements.


## Implemented runtime boundary

The explicit source grant is `document-recorder-scalar-v1`. The host creates a
new physical format 13 database with the existing format 7 document layout and
dedicated posting-state, recorder-partition and immutable receipt tables.
`SQLiteCatalogBackend.create_posting` and `SQLiteDBContext.create_posting`
require a canonically reimported `PostingConfiguration`. Opening an older file
does not grant posting. There is no conversion of an existing database.

This profile contains scalar documents and nonperiodic recorder-owned
information registers. The document source module is retained byte-for-byte,
bound by its hash, and compiled as a bounded synchronous server handler.
BeforeWrite, OnWrite, Posting and UndoPosting are the supported lifecycle
handlers. Privileged execution, real-time posting, additional handler families,
object-module initialization and document writes nested inside handlers are
refused. A handler cannot acquire or terminate the caller's transaction.

A document write, its Posted state and all recorder replacements share one
journal and one operation savepoint. Cancel, exceptions and resource-limit
failures roll back the whole document operation while preserving earlier
operations in an explicit outer transaction. Explicit movement writes are
immediately visible to Query in that same snapshot. Root receipts bind distinct
deterministic child receipts, including multiple replacements of one partition.
A Posted state change requires a document create/update revision staged in that
same root operation.

The movement buffer is retained for the same object across successful writes.
A newly loaded object starts with an empty buffer; implicit loading of persisted
movement rows is not claimed. Writes replace one recorder partition, while
dimension uniqueness is enforced across all recorders of a register. Unposting
removes the document's persisted movements.

Query supports the document Posted field and recorder register scalar fields,
Active, LineNumber and Recorder. Sources share the existing typed relational,
derived-table and package query pipeline and its resource bounds. Recorder
reference projection requires one declared document type; registers with
multiple document types still permit scalar-source queries. Unsupported virtual
period tables and polymorphic recorder-reference projection are refused.

Fresh source admission checks the exact executable and recorder grants and
scalar types. Measured passive GeneratedType metadata and the documented
default property values are validated without requiring cosmetic XML byte
roundtrips. Original source bytes are still preserved and hashed.

## Verification scope

The fourteen retained platform observations are immutable acquisition evidence.
The runtime suite executes the unchanged observer through public BSL Query and
compares all fourteen values with that evidence. Its final combined result is
pending at this checkpoint; no successful runtime parity result is claimed here.
The existing acquisition workflow remains a separate source-bound isolated
platform measurement, not a replacement for runtime comparison or general
regression tests.

Configuration changes, migration and historical cross-generation recorder
receipt recovery are intentionally refused for this fresh-only profile.
