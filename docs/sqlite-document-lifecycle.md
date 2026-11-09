# SQLite document lifecycle v7

This is yadinassi's **local, non-posting document contract**, not evidence of
native 1C document-method parity. It does not read native database files. The
profile accepts an authored, bounded XML-shaped configuration; arbitrary full
Designer exports, generated type GUIDs and application modules are not admitted.

## Create and reopen explicitly

`--create-db application.sqlite --import-xml ./configuration` explicitly creates
an owned file. `--f application.sqlite` opens an existing file and never creates
or upgrades one. New configurations containing admitted documents use format 7.
Catalog-only configurations keep their existing format choice (2/3/4, or the
separate 5/6 source profiles). Existing v1–v6 files retain their layouts and
catalog receipt representations; there is no v1–v6-to-v7 migration in this block.
Documents are unavailable in those older profiles.

A configuration may contain documents without catalogs. Document and catalog
names occupy separate namespaces; all admitted metadata UUIDs are distinct.
`Metadata.Documents` supports Count, Find, named access and the existing bounded
numeric access convention. A document's metadata has Name and FullName.

## Admitted metadata

Declare `<Document>Orders</Document>` in Configuration.xml and provide
Documents/Orders.xml. Its Properties must explicitly declare:

```xml
<Name>Orders</Name>
<NumberType>String</NumberType>
<NumberLength>9</NumberLength>
<NumberPeriodicity>Nonperiodical</NumberPeriodicity>
<CheckUnique>true</CheckUnique>
<Autonumbering>true</Autonumbering>
<Posting>Deny</Posting>
```

The version 2.20 MDClasses envelope, field type namespaces and qualifiers follow
the bounded catalog XML profile. NumberLength is 1–9. Autonumbering may be false
for explicit nonempty numbers. true selects local `decimal_v1` numbering,
independent of the catalog importer numbering option. Numbers are globally
unique within one document kind, not partitioned by year/date. Auto numbers are
zero-padded positive decimal strings; explicit occupied numbers are skipped.
Allocation and owner write commit together. Rollback does not consume a number.
A full range fails with `number_exhausted`; duplicates fail `duplicate_number`.
This policy is not a claim about native numbering algorithms.

Custom attributes and tabular-section fields support bounded String, Number,
Boolean, whole-second DateTime and a fixed catalog reference target. String and
Decimal assignment reuse catalog qualifiers. Nonempty referenced catalog items
must exist in the same database; reference assignment requires the same runtime
metadata snapshot. Document references as custom field types, composite types,
Undefined/Null field values and dynamic transfer codecs remain unsupported.

Unknown properties, generated-type declarations, forms and unsupported module
paths block activation. ObjectModule and ManagerModule files are retained
byte-for-byte; only empty/comment-only supported modules are inert. Posting,
register movements and event execution are not silently skipped.

## End-to-end BSL example

With a catalog Categories and document Orders whose custom fields are Text,
Amount, Active, Stamp, Category and whose section Lines has Boolean Flag:

```bsl
Customer = Catalogs.Categories.CreateItem();
Customer.Code = "C1";
Customer.Description = "Customer";
Customer.Write();

Order = Documents.Orders.CreateDocument();
Order.Date = Date(2026, 11, 9, 12, 30, 5);
Order.Text = "First order";
Order.Amount = 12.50;
Order.Active = True;
Order.Stamp = Date(2026, 11, 9);
Order.Category = Customer.Ref;
Line = Order.Lines.Add();
Line.Flag = True;
Order.Write();

Number = Order.Number;
Reference = Documents.Orders.FindByNumber(Number);
Saved = Reference.GetObject();
Message(Saved.Category.Description);
Message(Saved.Lines.Get(0).Flag);
Saved.Text = "Updated";
Saved.DeletionMark = True;
Saved.Write();

Selection = Documents.Orders.Select(Date(2026, 11, 9), Date(2026, 11, 10));
While Selection.Next() Do
    Message(Selection.Number);
    Message(Selection.DeletionMark);
EndDo;
```

After closing and reopening the same file, FindByNumber and GetObject return the
same persisted fields and ordered lines. A detached edit changes no data until
Write. New objects have an empty public Ref until successful persistence;
SetNewObjectRef accepts a nonempty reference of the same document type/snapshot.
GetRef accepts UUID, and EmptyRef/IsEmpty/UUID remain available. Missing lookup
returns a typed empty reference; missing GetObject returns Undefined.

Standard fields are Number, Date, DeletionMark, Ref and Posted. Number, Date and
DeletionMark are writable in a detached object; Ref is read-only. Posted is
always false and read-only because this profile cannot post documents. Write
accepts no posting-mode argument. SetDeletionMark, posting/unposting, Delete,
Copy, Fill, movements and configurable validation/events are unsupported.

Selection is a detached snapshot ordered by date, number (codepoint), then
record UUID text; bounds are inclusive whole-second dates. It contains at most
1,000 matching documents; overflow fails rather than truncating. GetObject on a
selection returns the selected snapshot, so a later conflicting write refuses.
Next remains false after exhaustion. These are local deterministic contracts,
not inferred native collation or cursor semantics.

Sections support Add, Get/index, Count, Clear, Delete(row/index), iteration,
field access and read-only one-based LineNumber. Removed rows are detached;
structural mutation invalidates an active iterator. Only owner Write persists
sections. Independent row writes/replacement are unsupported.

`Type("DocumentRef.Orders")`, DocumentObject/Manager/Selection and
`DocumentTabularSection.Orders.Lines` / DocumentTabularSectionRow identities are
scoped to one metadata snapshot, with Russian aliases. Section identity is
explicitly local and has no fabricated native generated GUID. Document
presentation and internal/XML codecs remain unsupported (empty reference
presentation alone is empty text).

## Storage, transactions and integrity

Format 7 adds only the distinct `document_schema`, `document_record`,
`document_sequence` and `document_commit_receipt` tables. Catalog schemas never
contain shadow documents. Catalogs, catalog queries, catalog keys, catalog
scans and catalog references cannot address document records. Document Query
support is not part of this block.

Document Number, Date, DeletionMark and revision are dedicated columns. Custom
fields and ordered sections use bounded tagged JSON in the document row. This
is the same strict scalar codec as catalog persistence, not a native serialized
value format. A whole document plus all sections is committed atomically; row
UUIDs are internal identities, never BSL references. The logical port carries
DocumentSchema, DocumentKey, DocumentCard, DocumentDraft and DocumentRevision,
not SQL, connections or catalog identities.

A document transaction permits one successful owner write. It shares the
application's pinned SQLite transaction, owned connection cleanup and savepoint
rollback machinery. Mixed catalog/document batches are not exposed. Revisions
are optimistic tokens, not native DataVersion. A stale detached update fails.
Read-only openings reject document transaction creation and object mutation
writes; reads remain available.

After an uncertain commit response, the object freezes its exact write intent,
including sections and requested numbering. Calling Write again resolves its
persisted receipt before any replay. A matching committed receipt restores the
original revision and generated number. Proved absence permits the same frozen
intent to retry; mismatch refuses. Catalog and document operation IDs cannot
collide across receipt tables. An unconfirmed response never clears IsNew.

Admission retains the existing private-directory, regular-file, symlink,
owner/link-count and SQLite marker/DDL checks. Format 7 additionally validates
all document schemas, catalog-reference targets and sequence inventory. Each
transaction rechecks the admitted schema rows and physical schema version;
metadata table edits cannot bypass admission by leaving schema_version unchanged.
No destructive upgrade, arbitrary SQL, module execution or implicit creation
is added.

Bounds: 512 combined catalog/document schemas, 64 fields per owner/section,
16 sections per document, 512 combined sections, 1,000 lines per owner,
1 MiB canonical document write payload, 10,000 documents per kind and 16 MiB
aggregate document read payload per kind. Existing configuration/file/database
ceilings still apply. Corrupt stored values are rejected, never normalized on
read. Owned SQLite tests establish these contracts; no native 1C run is claimed.
