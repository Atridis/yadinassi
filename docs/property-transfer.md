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

`Ref`, `Posted`, `LineNumber` and tree `Parent` cannot be changed on their
readonly owning endpoints. They can occur in Exclude when present on both
endpoints, and Include rejects a readonly target property. Reading these scalar
or reference values from a source into an ordinary writable Structure property
or row column is supported, both by default and with Include. Tree `Rows` and
whole tabular sections remain excluded in both directions; Include rejects these
aggregate properties. User properties with these spellings are ordinary
properties when neither endpoint exposes the corresponding built-in standard
property.

An explicit Include list controls assignment order and must name properties
present in **both** endpoints. Repeated valid names cause repeated assignments.
When Include is supplied, Exclude is ignored completely, without parsing or
validating it. Without Include, every Exclude name must also be present in both
endpoints. Unknown names are errors, not silently ignored.

The new profile admits comma-separated identifiers with surrounding ASCII
spaces. Empty strings/tokens, leading/trailing or repeated commas, quoted names,
tabs, newlines and Unicode whitespace trimming are not supported. Optional
omitted arguments and `Undefined` both mean the corresponding list is absent.

Schema validation, alias ambiguity, list syntax, presence and readonly checks
finish before assignments begin. **Setter failures are non-atomic:** an error
from a later typed setter leaves prior successful assignments intact. Values are
read and assigned one at a time; there is no separate deep copy or rollback.

These traversal, preflight, readonly and failure rules are an explicit bounded
**local host policy**, not an assertion of native 1C equivalence. Existing
member setters retain their current type adjustment, errors, index maintenance
and tabular-buffer dirty/size bookkeeping.

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

The local implementation does not infer unmeasured parser corners or native
failure order from those examples. Focused host tests are in
`tests/test_property_transfer.py`; existing structure checkpoint fixtures are
kept unchanged.
