# FillPropertyValues: built-in object and row transfer

`ЗаполнитьЗначенияСвойств / FillPropertyValues(Target, Source [, Include, Exclude])`
is a procedure. It shallowly assigns corresponding existing properties and does
not add properties or columns, clone values, replace owners, write a database,
or run object-module handlers.

## Supported endpoints

The extended profile accepts these exact built-in runtime classes:

| Endpoint | Source | Target |
| --- | --- | --- |
| Structure | Yes | Yes |
| FixedStructure | Yes | No, except the unchanged legacy structure-only path |
| ValueTableRow | Yes | Yes, unless it belongs to a read-only slice snapshot |
| ValueTreeRow | Yes | Yes |
| CatalogObject | Yes | Yes, as an editable detached buffer |
| DocumentObject | Yes | Yes, as an editable detached buffer |
| Catalog tabular-section row | Yes | Yes |
| Document tabular-section row | Yes | Yes |

Managers, references, selection cursors, section collections, entire tables or
trees, forms, registers, arbitrary host objects and subclasses are not endpoints.
A catalog reference can still be a *field value*: existing setters validate its
family and metadata scope. Untyped properties retain shallow value references,
including aliases and cycles, without traversing the value graph.

Both endpoints must have valid bounded schemas and live owner relationships.
Deleted/detached rows are refused in either role. Pending-write targets remain
locked, including their tabular rows. Reading a pending edit buffer does not
modify or resolve the pending write. A read-only table slice can be a source,
not a target.

## Matching and selection

By default the procedure copies common transferable properties in target schema
order: target structure insertion order; table/tree column order; standard object
properties followed by user metadata fields; tabular-row metadata field order.
Matching is case-insensitive, and target spelling/composition stays unchanged.

Built-in standard properties expose their usual Russian/English aliases:
`Code/Код`, `Description/Наименование`, `Number/Номер`, `Date/Дата`,
`DeletionMark/ПометкаУдаления`, `Ref/Ссылка`, `Posted/Проведен/Проведён`,
`LineNumber/НомерСтроки`, `Parent/Родитель` and `Rows/Строки`.
An alias group applies only when an endpoint actually exposes that standard
property. Two ordinary user columns named `Date` and `Дата` are not automatically
synonyms. Multiple source or target properties matching the same active alias
group are an error, even if their values happen to be equal. No spelling gets
implicit precedence.

`Ref`, `Posted`, `LineNumber` and tree `Parent`/`Rows` cannot be changed on
readonly owning endpoints. They can occur in Exclude when present on both
endpoints, and Include rejects a readonly target property. Reading readonly
scalar/reference properties into an ordinary writable Structure property or row
column is supported. Whole tabular sections are never transferred. User fields
with these spellings remain ordinary properties when neither endpoint exposes
the corresponding built-in standard property.

### Acquired Linux ordinary-row profile

With explicit `native_target="linux-8.3.27.1508"`, combinations of ordinary
ValueTableRow/ValueTreeRow and Structure/FixedStructure sources use the measured
Linux selection rules below. A FixedStructure target remains refused. The
48-input acquisition covers ordinary rows, not catalog/document objects or
metadata-backed tabular rows; see [the measurement record](property-transfer-measurement.md).

- Include traverses right to left, checking presence in both endpoints and target
  writability immediately before each assignment. Earlier successful writes are
  retained on error. For `"First,Missing,Last"`, `Last` is copied before the error;
  `First` is not. The same applies to a readonly tree `Parent` or `Rows` target.
- An exactly empty Include string is a successful no-op. It is not the same as an
  omitted/Undefined Include, which performs the default copy.
- Include overrides the *contents* of Exclude, but a supplied non-string Exclude
  is rejected before any assignment, even with empty Include.
- An exclusion absent from the source fails before assignment. The measured
  single mutable-Structure source-only exclusion is checked at its position in
  source schema order: preceding common nonexcluded fields are already copied
  when the missing target property causes an error. Admission is restricted to
  one source-only property and one occurrence of that missing exclusion. Other
  missing/mixed/fixed-source forms stay guarded before writes pending evidence.
- A tree source's `Parent` **and `Rows`** may fill writable Structure properties,
  by default or explicitly. Both remain shallow references to the original
  parent and child collection; no ancestry, owner, children or collection is
  cloned or replaced. Readonly tree targets still cannot be assigned.

These changes retain existing typed setters, index updates and owner checks.
They do not imply Windows parity or native equivalence for metadata-backed
objects. No native result is inferred from a successful host test; the unchanged
native source and separate capture/replay retain the evidence boundary.

### Remaining bounded host policy

Default execution and `windows-8.3.27.2342`, plus any combination involving a
catalog/document object or its tabular row even under Linux, keep the original
explicit local policy: Include follows list order and preflights all selected
properties; Exclude is ignored completely when Include is supplied. Missing
exclusions fail before writes. Tree `Rows` remains closed for these combinations.
This is not a measured Windows or object-transfer behavior claim.

For all new combinations, default traversal uses target schema order as described
above, except the bounded Linux source-only exclusion error path. Repeated valid
Include names cause repeated assignments in the selected traversal order.
Comma-separated identifiers may have surrounding ASCII spaces. Apart from the
exactly empty Linux Include, empty strings/tokens, leading/trailing or repeated
commas, quoted names, tabs, newlines and Unicode whitespace trimming remain
unsupported. Optional omitted arguments and `Undefined` mean the list is absent.

Schema validation, alias ambiguity, resource bounds and admitted list syntax
are checked before assignments begin. **Setter failures are non-atomic:** a
later setter failure leaves earlier writes intact. Values are read and assigned
one at a time through existing member setters, with their current type adjustment,
errors, index maintenance and tabular-buffer dirty/size bookkeeping. There is no
deep copy or rollback. Ordering outside the acquired rows and further parser or
mixed-exclusion corners remain explicitly deferred, not guessed from the capture.

## Examples

```bsl
Table = New ValueTable;
Table.Columns.Add("Text");
Table.Columns.Add("Amount", New TypeDescription("Number"));
Row = Table.Add();
FillPropertyValues(Row, New Structure("Text,Amount", "draft", 12.5));

Card = Documents.Orders.CreateDocument();
FillPropertyValues(Card, SourceCard, , "Дата,Проведен,ПометкаУдаления");
// Tabular sections are not copied by the preceding call.
For Each SourceRow In SourceCard.Lines Do
    TargetRow = Card.Lines.Add();
    FillPropertyValues(TargetRow, SourceRow);
EndDo;
// No Write() is performed by FillPropertyValues.
```

The document example requires an admitted document configuration and its existing
backend capabilities; it does not enable an unavailable document/schema surface.

## Local limits and existing compatibility

Local admission bounds are 4,096 entries per property/schema collection, 256
UTF-16 units per property name, 1,000,000 shared UTF-16 name units across endpoint
schema checks and selection lists, 65,536 UTF-16 units and 4,096 tokens per list.
Owner-row membership checks are bounded at 100,000 entries; target table indexes
are bounded at 256 definitions and 4,096 total column positions. Existing typed
setters and owners retain their own limits. Values are not stringified or
recursively inspected merely to perform a shallow transfer.

The original Structure-to-Structure path is unchanged. Its platform-specific
INCLUDE/EXCLUDE ordering, historical partial-failure cases, fixed-target no-op,
and restrictions on simultaneous lists remain separate. This extension does
not normalize or replace those measured behaviors. Runtime procedure identity,
argument evaluation and omission dispatch also remain unchanged.

The official Syntax Assistant description specifies include precedence and
presence requirements. Its contradictory parameter-table sentence is not used
to reverse that precedence. Official development examples show document-to-
document copying without whole tabular sections and explicit loops over rows:

- [Development example: filling object properties](https://its.1c.ru/db/content/metod8dev/src/developers/platform/metod/other/i8102322.htm)
- [Standard: copying properties between rows and objects](https://its.1c.ru/db/content/v8std/src/400/300/i8100448.htm)

The local implementation does not infer unmeasured parser corners, object or
Windows failure order from those examples. Focused host tests are in
`tests/test_property_transfer.py`; existing structure checkpoint fixtures are
kept unchanged.

## Context-owned helpers and asynchronous host failures

Imported helpers, common modules and logical server activations construct `Type`,
`Query` and `TempTablesManager` against their own metadata/catalog snapshot.
Inherited RU/EN aliases are rebound by exact core implementation identity; explicit
host overrides and their parameter contract are preserved. `FillPropertyValues`
continues to use ordinary setters. A reference from another snapshot is still
rejected, including another interpreter connected to the same SQLite database.
No cross-database reference conversion or implicit persistence is introduced.

A raw host exception after `Await` terminates that task instead of leaving a
closed generator registered as pending. Its promise records an internal `failed`
outcome and awaiting/adopting it cannot silently succeed with `Undefined`.
The original exception escapes to the host, not the BSL procedure-error channel;
unrelated ready/pending work remains available to a later pump. This is an
embedding correctness guarantee, not a new claim of native platform behavior.
