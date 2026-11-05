# Static form-module name-validation profile v1

`yadinassi.form_module_analysis.analyze_form_module` describes a **complete,
non-executable** catalog form module in the deliberately narrow
`catalog-form-name-validation-static-v1` profile. `native_parity = False`.
This is infrastructure for the user's two-handler name-validation example, not
support for arbitrary imported forms, source activation, FormData, or a GUI.

## Binding and inputs

The host supplies exact bytes for catalog metadata, form metadata, form definition,
and original BSL source. `FormModuleBinding` commits to all four SHA-256 hashes,
database/configuration UUIDs and configuration generation, catalog/form UUIDs and
names. These are **caller-supplied identity commitments, not authentication or
proof of trusted provenance**. The caller must obtain bytes and identity from its
trusted storage boundary. All four paths must be exact canonical catalog/form
paths (no absolute paths, aliases, traversal, or cross-owner paths).

Metadata checks tie the catalog's default object form and declared child form to
the form UUID/name, main `cfg:CatalogObject.<catalog>` attribute, and two scalar
fields. The standard Catalog Code/Description metadata maps to the source paths
`Объект.Код` / `Объект.Наименование`; Code is read-only. String lengths derive from
the catalog metadata. Unknown XML elements, attributes, duplicate settings,
extra fields/events, DTDs, entities and unsupported owner types are rejected.
Recognized unrelated catalog settings are retained in the committed XML hash but
**not interpreted or accepted as configuration semantics**. This projection does
not relax the separate configuration importer's schema or activation blockers.

## Complete closed source profile

The input is bounded to 16 KiB of UTF-8 source (optional BOM), 512 tokens,
256 AST nodes and depth 24; each XML input is at most 32 KiB and 256 elements.
Message strings are at most 1024 characters. The source is never rewritten.
There are exactly two procedures, in client then server order, and exactly two
annotations, `&НаКлиенте`/`&AtClient` and `&НаСервере`/`&AtServer`.
Both bodies are parsed and checked together with no client/server omission pass.
Preprocessor/import directives and all other annotations are rejected, including
hidden no-context bodies. The initial profile intentionally rejects even `#` in
comments or strings and `&` except in those two annotation lines.

Handler names derive from the form's OnChange and BeforeWriteAtServer events.
Parameters are exactly `(Элемент)` and
`(Отказ, ТекущийОбъект, ПараметрыЗаписи)`, without defaults, exports or by-value
modifiers. The initial profile requires the illustrated Russian identifier
spellings and exact statement structure, rather than normalizing general BSL:

- Client: trim `Объект.Наименование` with `СокрЛП`; if `СтрДлина(...) < 3`, create
  zero-argument `Новый СообщениеПользователю`, set literal `Текст`, set literal
  `Поле = "Объект.Наименование"`, call `Сообщить()`.
- Server: return immediately for `ТекущийОбъект.ПометкаУдаления`; trim its
  `Наименование`; perform the same short-name check, setting `Отказ = Истина`
  before constructing the field message.

Message text can vary; every statement, call, member, constructor, branch and
literal type is checked. Extra routines, initialization, loops, helpers, dynamic
calls, references, file/network/SQL access and unrecognized statements are closed
errors. This is narrower than the general BSL grammar by design.

## Result and boundaries

The frozen result contains original source bytes, binding, paths, scalar field
and event descriptions, message text/field and AST count. No mutable AST,
executor, catalog reference, runtime object, host closure or activation grant is
returned. Do not execute this source or trust a fabricated description as a
capability. No runtime or importer consumes this description yet.

The language track owns UserMessage construction, properties and collection.
This profile describes only Text/Field/Message usage and carries no runtime
`data_key`, message transport, focus/navigation, native deferred queue, or
FormRuntime capability. Existing fail-closed configuration import/activation is
unchanged. No BSL execution, real 1C manual run, native parity or source-backed UI
is claimed by this increment. Tests provide synthetic static admission/rejection
evidence only.
