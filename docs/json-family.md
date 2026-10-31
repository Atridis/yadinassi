# JSON family: implementation scope and native acceptance

This feature is one end-to-end JSON block, not a general claim of platform parity.

## Public surface

- `ЧтениеJSON / JSONReader`: `SetString`, `OpenFile`, `Read`, `Skip`, `Close`,
  `CurrentValueType`, `CurrentValue` and their official Russian aliases.
- `ЗаписьJSON / JSONWriter`: string/file setup, object/array start/end,
  property names, scalar values, and `Close`.
- `ПрочитатьJSON / ReadJSON`: primitive values and nested Array/Structure,
  or Map when the second argument is true.
- `ЗаписатьJSON / WriteJSON`: primitives and nested mutable/fixed Array,
  Structure and Map; map keys must be strings. JSON null maps to Undefined,
  not the distinct BSL Null value.
- `ТипЗначенияJSON / JSONValueType`, `ПереносСтрокJSON / JSONLineBreak`, and
  basic `ПараметрыЗаписиJSON / JSONWriterSettings` newline/indent settings.
- Type/TypeOf identities are explicit. Internal serialization and
  cross-context transport of these new objects are not invented.

Normal local files support UTF-8, optional UTF-8 BOM, UTF-16 and Windows-1251.
The implementation buffers a bounded document rather than claiming an
unbounded streaming implementation. Local budgets are 1,000,000 characters,
100,000 tokens, nesting depth 128 and 4,096 decimal digits/exponent magnitude,
not inferred native limits.

## Primary API source

Official 1C EDT SyntaxHelper documentation:

`https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`

SHA-256: `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Read as a ZIP archive, not executed. Relevant members under `nl/en/html/` and
`nl/ru/html/SyntaxHelperContext/`:

- `objects/catalog63/catalog2298/JSONReader/`
- `objects/catalog63/catalog2298/JSONWriter/`
- `objects/catalog63/catalog2298/JSONWriterSettings/`
- `objects/catalog2/catalog2300/JSONValueType/`
- `objects/catalog2/catalog2300/JSONLineBreak/`
- `objects/Global_context/methods/catalog4870/ReadJSON4872.html`
- `objects/Global_context/methods/catalog4870/WriteJSON4871.html`

## Verification status

Focused local workflow tests are in `tests/test_json_processing.py`.
Native acceptance is pending; source documentation is not native evidence.
Default formatting and reader cursor transitions must be checked in the same
whole-family native batch as the ordinary workflows, before claiming parity.

## Deliberate remaining scope

Search `# !todo` in `yadinassi/json_processing.py` for deferred work:
advanced escaping/quote modes, date restoration and serialization options,
conversion/revival callbacks, non-standard comments, reader CurrentLine/CurrentPosition, and exact malformed-input
error diagnostics. XDTO serialization, external Stream objects and
arbitrary application types are not included. No silent stringification of
unsupported types or non-string map keys is permitted.
