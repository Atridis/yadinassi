# One document tabular-section read block

Local schema-backed preparation, no native apply/dispatch/publication.
Baseline commit: 9be9d601e4598de21c87098161928e827341973c (PR174).
The existing document_read_packet and linked_card_packet snapshots are unchanged;
integration should import existing packages, not duplicate them.

## Closed fixture
Two independent saved metadata/type/record identity sets; reversed column order
in repeat2. Each retains the measured document's complete header defaults/five
attributes and the supported target catalog XML unchanged (two owned target rows). Add ONLY Items:
Product single fixed CatalogRef, Quantity/Price/Amount Number9.2, Note String32.
Section/column metadata UUIDs, generated section/row TypeId/ValueId, owner record
UUID and Product record UUID remain distinct.

Three documents in each snapshot: Number30 posted with0lines; Number10 unposted
with1line; Number20 unposted with3lines. Both nonempty owners have LineNumber1.
Initial20 has first/second/first Product with repeated first Product, values6.50/2/-1.25.
Owner10 uses second Product; target descriptions Category/Second are distinct.
A separate never-used lookup_absent UUID measures Find returning Undefined.
Rewrite20 is a separately captured transition: last row first, middle replaced
with absent Product/Amount8/Note replacement, original first row last.
No physical deletion/reuse semantics inferred from Clear+Add or row replacement.

Existing owned fixture writes and initial one Regular-posted document are retained.
Rewrite uses only saved Number20/GetObject, unposted/count3/exact owner UUID guard,
Clear/Add then ordinary Write. Host must require initial setup AND initial Query
witness success before enabling this transition. Never apply it to a user DB.
Permissions remain the previously approved generated Document
Read/Insert/Update/Posting only, target catalog existing CRUD, and unchanged
Configuration ThickClient/MainWindowModeNormal. No new role/right/credential,
no registers, sequence membership, handler/module or external call.

## Batched observations
4 blocks ×24 fixed strict-scalar rows, each with document/catalog controls:
identity/count/dynamic types; three complete rows; Find/IndexOf/Total/ForEach;
DocumentSelection.Items alongside reference access.
Zero/one/three counts, zero-based Get/index, per-owner LineNumber, typed Product
traversal, foreign-row IndexOf, matching/missing Find and repeated Product are
raw observations. ForEach retains count, sum and ordered LineNumber string.
Negative/fractional Number and Total/IndexOf use XMLString; raw scalar results are
retained. Guarded acquisition prevents unsupported availability aborting a block.

Each state also has a separate24-row native Query witness, ordered by owner Number
then LineNumber. It verifies all4 rows' owner/line/Amount/Product, exhaustion and
zero-line owner. Decimal witness validation compares bounded decimal values while
preserving original lexical observations. Existing24-header setup witnesses remain
in initial setup, with target catalog count now2; require_initial_setup validates
that exact extended expectation without normalizing raw observations. Rewritten setup emits its own identity/count/type controls.

## Primary facts
Pinned official EDT platform8.3.27 plugin SHA256
4af9e1355b14b2836df4e89ae5d6c6e834d308e4233a490c12232e7dede67e4e,
backend.xdto SHA256
8569cd5d718b4009e09c2fa43a21e0bac6811d78018da0e8ec234b2a38101827.
Official documentation archive SHA256
a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642.
URLs and extracted member hashes in research/source-receipt.json.

backend TabularSection2896 derives MDObjectBase; Properties/ChildObjects;
Attribute children0..many. TabularSectionProperties2903 includes optional Name,
Synonym, Comment, ToolTip, FillChecking, StandardAttributes, LineNumberLength.
TypeCategories392 includes TabularSection and TabularSectionRow. GeneratedType529
declares separate TypeId/ValueId. This supports prepared XML syntax, NOT actual
Designer defaults/complete generated identity inventory.

Official generic API docs:
catalog125/catalog177/catalog270/Tabular_section.html: ForEach, zero-based index.
methods/Count756.html, Get1376.html, Find842.html, IndexOf840.html, Total841.html.
Line_of_a_tabular_section.html and properties/LineNumber3005.html.
Document ref/selection properties prop1257/prop1729 explicitly expose sections;
availability server/thick/external (not thin/web).
Find returns matching row or Undefined, but DOES NOT promise which duplicate;
the first-match relation is measured rather than assumed.
IndexOf absent row returns -1. Total accepts column name/index; this scope Amount.
Row and section dynamic type naming is documented generically by application prefix.

Full proprietary archives/schemas/docs stay in local research only. They are not
publication payload and not needed by the generator or future host runtime.
scripts/schema_facts.json contains only bounded interface facts/provenance.

## Next native evidence
1. Owned apply/redump: confirm tabular StandardAttributes/LineNumber defaults,
   generated section+row type inventory, exact saved names/UUIDs/QNames.
2. Same-postimage complete CONFIG root/document/section/column descriptors plus
   DBNames and raw physical table declarations/row bytes. Prove owner key and
   line numbering/order, type identities, liveness and rewrite effects. Do not
   reuse catalog or document header descriptor positions by analogy.
3. Capture both states, both identities, both execution contexts. Initial and
   rewritten remain distinct, with provenance and raw pre/post witnesses.
4. Admit only measured bounded physical profile; then actual frozen .1CD parity.

# !todo Composite types, arbitrary free chains, public mutation, Unload, sorting,
# optional omission of Note, zero-column sections and rare errors are deferred.

Empty/missing document reference section Count and repeated section/row equality
are raw observations only, not pre-decided native outcomes.

## Closed local host integration

`document-lines-v1` is a selected-only specialization of the existing reviewed
file-DB job, with unchanged owner/ref/registry/token/container and cleanup gates.
Twelve bounded sessions run both setup+witness outputs together, then four
readonly blocks per client/server context. The rewritten state must clone the
retained initial frozen image only after its authenticated setup and independent
Query witness pass. Each state records its setup-origin digest: applied baseline
for initial, initial frozen origin for rewritten. This is not a free-slot claim.

Exact used-QName XML equality and section/row generated type identities are checked
after apply/redump; unknown defaults are not stripped. On install failure only the
two UUID+Name+kind-verified generated XML files may be projected, under 64 KiB each.

Raw capture retains all five baseline/root/owned CONFIG payloads, selected
Document/Catalog/section/column DBNames entries and three bounded table candidates.
`_Document<id>_VT<section-id>` is an explicit naming hypothesis, never a production
binding. Missing table or unknown kind remains a finite unresolved result; no
owner join, row order, physical stride or rewrite liveness is inferred. All table
ownership mappings precede any target payload read, with one shared read budget.

The first native apply/redump measured an exact LineNumber standard subtree and
section-column default omissions; generated inputs now match that owned redump
without validator exceptions. Corrected run 41261954939 installed successfully
but failed in offline observation before retaining a complete capture. Its cause
remains unlocalized; no public Items admission or runtime parity is established.

Known offline failures now retain authenticated native outputs and the frozen
postimage digest only after the final same-descriptor integrity/quiescence checks
pass. The report remains failed, contains no parity assessment for that capture,
and exports only fixed stage/category/code and bounded source location—not raw
exception text. Source-change/I/O/regular-file and snapshot/protocol failures
still propagate and cannot bless a partial capture. Layout, bounded-resource and
sharing refusals remain failed measurements, never accepted physical results. Future public replay fixtures must contain only needed owned CONFIG, rows,
programs and observations: never installations, helpers, audit/session/token
metadata. Complete authenticated reports remain private evidence.
