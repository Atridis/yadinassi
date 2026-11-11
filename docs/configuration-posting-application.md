# Explicit posting application host extension

`document-recorder-forms-v1` is a separate opt-in grant for scalar documents,
typed headers/sections and nonperiodic recorder-owned information registers.
It retains every original source byte, including forms, handlers and the host
manifest. Canonical reimport checks the complete grant before storage access.
Physical format 13 keeps the same DDL and immutable receipt encoding, with a
separate exact marker. Old posting and non-posting source grants are unchanged.
There is no migration, catalog-reference support, CommonModule authority or
application-module activation in this profile.

## Authored host commands, not native standard commands

`PostingApplication.xml` is an explicit **Yadinassi host extension**, not native
Designer `StandardCommand`, `FormWrite` or synchronous posting inside form BSL.
Its closed namespace is `urn:yadinassi:posting-application:1`, version `1`.
Every declared document form appears once by its exact public name. Each names
three declared custom commands by their exact name and integer XML ID, with
modes `Write`, `Post` and `UndoPosting`. Unknown fields, duplicates, undeclared
forms/commands and nonempty, async or non-client handlers are refused.

The source-granted command's empty client handler completes first. The existing
replication protocol then synchronizes its typed image through a reserved empty
server barrier. Only after server dispatch has returned does the trusted host
perform the root operation. A failed or cancelled dispatch has no posting
side effect. `WriteObject()` in a form cannot enter this root path. Child/form/
server Begin/Commit/Rollback and escaped transaction callables remain denied.

The host constructs a fresh document per operation. `AdditionalProperties` and
movement buffers start empty; arbitrary form-owned supplemental handler inputs
are not passed. The existing bounded source VM executes document lifecycle
handlers. Write, Posted state and recorder movements commit in one unit of work.
The fourteen retained native observations support only their measured scalar
recorder semantics, not these authored form command extensions.

## Retained buffers and recovery

The host binds a stable UUID to the immutable full draft, expected revision,
mode, source/profile and database identity. The browser never receives UUIDs,
expected revisions, SQL requests, source code or handler names. It receives
existing opaque record/form capabilities and a random, form-local receipt token.
A duplicate stale click cannot become a second root operation.

`Object.Posted` is an authoritative label-only field. A successful write
refreshes the whole saved image and the bounded record list, without replacing
a sibling draft. A dirty form refuses Close until it is saved. Unknown outcomes
lock editing and ordinary Write/Post/Undo commands. **Resolve saved operation**
uses the retained exact expanded requests and outcome; it never reruns handlers.
A committed write whose display refresh failed is shown separately and retries
only authoritative refresh. Receipt capability checks prevent recovery from
being attached to another form after navigation or a late response.

Recovery is **host-lifetime only**. The current database journal does not store
the complete request envelope needed to reconstruct this adapter after process
loss. Restart recovery is unavailable; no blind replay is offered. Closing the
last browser tab is not discard, rollback or successful recovery. Keep the
owned application alive while a receipt is unresolved. A broken transport
locks the application rather than guessing whether the request ran.

## Run the authored example

Create a new database explicitly from `examples/configuration-posting-application`:

```python
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_posting_application import import_posting_application, PROFILE
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
source = read_configuration_directory('examples/configuration-posting-application')
configuration = import_posting_application(source, posting_runtime=PROFILE)
SQLiteCatalogBackend.create_posting('posting.sqlite', configuration).close()
```

Then launch:

```sh
python -m yadinassi.ui.configuration_app examples/configuration-posting-application --posting-application --f posting.sqlite --open-browser
```

The example has typed line quantities, an editable exact DateTime, an
authoritative Posted label and explicit Write/Post/Undo commands. Posting writes
one recorder row for each document line. The explicit numeric Movement key
header must differ between documents with posted lines; it is independent of
automatic document numbering and defaults to 1 for a new document. `Note = "cancel"` deliberately cancels
BeforeWrite for an inspectable atomic-refusal scenario. It is an authored local
example, not a claim that arbitrary exported 1C configurations run unchanged.

The existing UI caps and opaque navigation protocol remain in effect: at most
eight open forms, bounded typed table cells and 256 visible records. A response
that exceeds the full projection envelope is refused, never truncated.
