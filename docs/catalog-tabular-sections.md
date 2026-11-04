# Catalog tabular sections: bounded XML and BSL adapter

This is a working yadinassi profile, not a claim of native 1C parity. The official [applied-object description](https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Standards/Applied_objects/?language=en) describes catalog objects as owner fields plus their tabular-section rows. The official [catalog design tutorial](https://1c-dn.com/library/tutorials/practical_developer_guide_tabular_sections/) describes tabular sections with their own attributes. Those sources motivate the object model; they do not establish our index conversion, deleted-handle behavior, errors, generated type identities or XML export completeness. Those details still need source-reviewed native measurements. No native sessions were run for this increment.

## Admitted metadata

The existing XML importer accepts catalog `ChildObjects/TabularSection` with a nonzero UUID, `Properties` containing Name/Synonym/Comment, and its own `ChildObjects/Attribute` definitions. Attributes reuse the existing bounded String, Number, Boolean, whole-second DateTime and single CatalogRef types and qualifiers. Metadata UUIDs remain globally unique in an import. Owner attributes and section names share a case-insensitive namespace; section attributes have their own namespace. Reserved object members and LineNumber/НомерСтроки cannot be used as row field names.

Limits are 16 sections per catalog, 512 per import and 64 fields per section, together with the existing XML file/size/depth and type limits. Unknown child objects and embedded executable components refuse. Unknown behavioral properties remain explicit activation issues; nonempty modules still prevent activation. Original accepted XML/BSL source bytes are retained exactly. The PR201 exact official catalog profile remains unchanged. Adding a section to that native-shaped profile does not automatically widen its fingerprint or admit all standard Designer properties. General Designer-generated configurations with additional properties are not silently accepted. A ConfigDumpInfo file accompanying section-bearing schemas remains unsupported until a separately reviewed nested-inventory profile exists; an owner-only inventory cannot silently hide sections. No configuration-update/migration workflow is added.

The [closed module inventory](configuration-module-inventory.md) also applies to section-bearing catalogs. Empty canonical configuration/catalog modules retain their actual metadata owner and allow this bounded section adapter. Unknown paths, including invented section modules, never acquire an owner and block activation even when empty. Executable source remains independently blocked. Inactive archives retain both the section schemas and exact XML/BSL bytes on reopen; compact unknown-path diagnostics do not clear executable-code or metadata issues. This composition adds no module execution or native tabular-section parity claim.

A configuration may contain a bounded section-bearing catalog alongside a separate catalog admitted by the closed 0–64 scalar-attribute composition profile. Each catalog keeps its own admission rules and actual UUID module ownership. The rich scalar envelope does not admit appended sections, and rich scalar Attribute defaults do not automatically become valid section-row defaults. XML-whitespace and QName checks also apply to section attributes. The section-bearing configuration still cannot activate with ConfigDumpInfo, even when an owner-only inventory matches the scalar sibling. These combinations are covered by synthetic local tests, not new native observations.

## Detached object operations

`Catalogs.Products.CreateItem()` and `Ref.GetObject()` expose each section by its metadata name. A new object starts with empty sections. The supported methods are:

- `Add()` / `Добавить()`: append a row with typed default field values.
- `Count()` / `Количество()`: return the current row count.
- `Get(index)` / `Получить(index)`, or `[index]`: read a row by zero-based position.
- `Delete(rowOrIndex)` / `Удалить(rowOrIndex)`: remove an owned live row or indexed row.
- `Clear()` / `Очистить()`: clear that section only.

A row exposes declared fields by property name or string index. Whole-section assignment and indexed row replacement refuse. Indices must be finite, exact integer Numbers within bounds; implicit coercion/truncation is not inferred. Deleted/cleared row handles refuse subsequent reads and writes. Iteration permits field edits but fails closed if collection structure changes. These are explicit local rules pending native measurement, not approximations presented as measured behavior.

```bsl
O = Catalogs.Products.CreateItem();
O.Code = "10";
R = O.Lines.Add();
R.Text = "Example";
R.Amount = 12.50;
O.Write();
P = O.Ref.GetObject();
Message(P.Lines[0].Text);
P.Lines.Clear();
P.Write();
```

Use the actual names and admitted types in the loaded configuration. Row fields retain exact runtime scalar/reference types. The [qualifier assignment contract](catalog-qualifier-assignment.md) truncates String values and rounds/saturates Numbers before changing the detached row, using the same normalizer as owner attributes, Code and Description. Unrepresentable UTF-16 boundaries refuse atomically. Durable reference existence is still checked by the backend when writing. Runtime buffers retain at most 1,000 rows across an owner's sections and a conservative 4 MiB of field content plus row overhead; the stricter backend write budgets still apply.

## Write, conflict and recovery

Section edits remain in the detached CatalogObject until `Write()`. Owner fields and all changed section contents are submitted through the existing atomic backend transaction and optimistic owner revision. A section edit causes a full section snapshot to be submitted, including untouched sibling sections. Without section edits, the draft omits sections and existing data stays untouched. DeletionMark does not clear rows. Local row UUIDs survive edits and position changes but are never exposed as BSL references or native line numbers.

Validation errors, duplicate codes and stale revisions preserve the edit buffer and leave committed data unchanged. An uncertain write freezes the exact immutable submitted draft, including row values and order. All nested row/collection mutations refuse until another `Write()` resolves that receipt or safely retries an uncommitted intent. Resolution never blindly appends duplicate rows.

## Explicit boundaries

Interpreter activation opts into this bounded section adapter. Existing UI activation does not opt in and continues to refuse section-bearing databases; no UI editor or renderer code is changed. Direct `Ref.Section` and `Selection.Section` access remain unsupported: obtain the detached object with `GetObject()`.

Dynamic section/row TypeOf descriptors, presentation strings, external codecs/transport, LineNumber/НомерСтроки, row UUID APIs, nested metadata collections, Insert/Move/Sort/Find/Load/Unload/Copy and unlisted methods remain unsupported. Row identity and lifecycle are internal local choices until appropriate behavior evidence exists. References still obey the backend's create-time existence checks described in the [storage contract](sqlite-catalog-sections.md).

`!todo`: acquire a bounded native behavior packet for collection methods, index conversions, detached row handles, iteration changes, default values, generated types and error semantics before widening compatibility claims. Keep native observations unchanged; internal storage and project-owned fixtures are not fixed before a public yadinassi release.
